"""Native four-field annular solver, translated from the pinned MATLAB source.

Preserves base/wave mass transport, wave-number relaxation, field momentum,
initialization and upstream stopping criteria. No replacement mixture physics.
Copyright (c) 2024 OpenSTREAM contributors; MIT, see LICENSE.
"""
from __future__ import annotations

import time
import warnings

import numpy as np
from scipy.interpolate import interp1d

from .annular import Drop, blend
from .ff_fields import Film
from .solver import SolverState
from .threefield import ThreeFieldSolver


class FourFieldSolver(ThreeFieldSolver):
    """Separate base film, disturbance waves, droplets and precursor vapor.

    The aggregate film is available as ``film``; its independent fields are
    ``film[k].base`` and ``film[k].wave``. Only a single wall is supported while
    the original linear-index ambiguities for multiple walls remain unresolved.
    """
    framework = "FourField"

    def initialize_solver(self):
        m = self.inputSet.model
        if self.inputSet.geometry.NWALL() != 1:
            raise NotImplementedError("FourField multiple walls have unresolved upstream linear-index expressions")
        if m.RELAXTB <= 0 or m.RELAXTW <= 0 or np.any(np.asarray(m.WAVEMIXCOEF)<=0):
            raise ValueError("FourField requires positive RELAXTB, RELAXTW and WAVEMIXCOEF; source divides by them")
        super().initialize_solver()
        # MATLAB Film.copyElement copies base/wave, rebinds their .film only,
        # and leaves their .mix pointing to the physical precursor at t=0.
        # initializeBaseAndWave() with no arguments does not rebind .mix.
        for film in self.filmInit:
            film.base.mix = film.wave.mix = self.film[0].mix
        self.wave_frequency_converged = False

    def _initialize_fields(self,mix):
        g,m,f = self.inputSet.geometry,self.inputSet.model,mix.fluid
        film,drop = Film(self.inputSet,mix),Drop(self.inputSet,mix)
        average = np.sum(mix.HFLUX*g.PERIM,axis=1)/np.sum(g.PERIM)
        with np.errstate(divide="ignore",invalid="ignore"):
            evaporation = np.r_[0,np.fmax(0,np.diff(mix.X())/np.diff(mix.XEQ()))]
        evaporation[~np.isfinite(evaporation)] = 1
        film.HFLUX = blend(mix,(evaporation*average)[:,None],mix.HFLUX)
        film.mevap = -film.HFLUX/f.HFG
        fraction = m.OAFDROPRATIO if m.OAFENTRAINED=="RATIO" else self.EQUIL(film,drop,mix,mix.OAFIDX())
        drop.W = fraction*mix.OAFWL()+mix.W-mix.W[mix.OAFIDX()]
        film.initialize_base_wave(mix.liquid.W(0)-drop.W[0])
        onset = mix.OAFIDX()
        initial_total = film.W[:onset+1].copy()
        film.base.W[:onset+1] = film.base.W[onset]
        film.wave.W[:onset+1] = np.fmax(0,initial_total-film.base.W[:onset+1])
        drop.W = mix.liquid.W()-film.W.sum(axis=1)
        drop.U = drop.USLIP()
        drop.H[:] = f.HF
        return film,drop

    def EQUIL(self,film,drop,mix,j):
        """Four-field onset iteration; third iteration differs from ThreeField."""
        o,g = self.inputSet.options,self.inputSet.geometry
        total = float(mix.liquid.W(j))
        if total<=0: raise ValueError("Annular onset requires positive liquid flow")
        initial_tolerance,tolerance = o.OAFEQUILTOL,o.OAFEQUILTOL
        guesses,residuals = [],[]
        for k in range(int(o.OAFEQUILMAXITER)):
            if k==0: guess = .5*total
            elif k==1: guess = (.7-float(residuals[-1]>0)*.4)*total
            elif k==2:
                # Unlike ThreeField (where this branch is commented out),
                # FourField explicitly interpolates its third guess.
                guess = float(np.fmax(np.fmin(interp1d(residuals,guesses,fill_value="extrapolate")(0),total),0))
            elif np.all(np.diff(residuals)/np.diff(guesses)>0):
                try:
                    valid = ~np.isnan(residuals)
                    x,y = np.asarray(residuals)[valid],np.asarray(guesses)[valid]
                    if len(np.unique(x))!=len(x): raise ValueError("Duplicate onset residuals")
                    guess = float(np.fmax(np.fmin(interp1d(x,y,fill_value="extrapolate")(0),total),0))
                except ValueError:
                    guess = float(np.fmax(np.fmin(guesses[-1]*(1-20*residuals[-1]),total),0))
                    guesses[-1]=residuals[-1]=np.nan
                    tolerance = initial_tolerance*10
            else:
                guess = float(np.fmax(np.fmin(guesses[-1]*(1-20*residuals[-1]),total),0))
                tolerance = initial_tolerance*10
            guesses.append(guess)
            drop.W[j] = guess
            film.distributeOAFW((total-guess)*g.PERIM/np.sum(g.PERIM),j)
            residual = float(drop.MDEP(j)*np.sum(g.PERIM)+np.sum(film.MENT(j)*g.PERIM))
            residuals.append(residual)
            if abs(residual)<tolerance: break
        self.onset_diagnostics.append({"node":int(j),"iterations":k+1,"residual_kg_s_m":residual,
                                       "original_tolerance_kg_s_m":initial_tolerance,
                                       "effective_tolerance_kg_s_m":tolerance,"converged":abs(residual)<tolerance})
        if abs(residual)>=tolerance: warnings.warn("Four-field onset equilibrium did not converge",RuntimeWarning)
        return drop.W[j]/total

    @property
    def converged(self):
        # SSCONVFW is absent from the original steady-stop predicate. Preserve
        # STATE, but require the frequency evidence for a stronger native flag.
        nested = [field for film in self.film+[self.filmInit[-1]] for field in (film.base,film.wave)]
        return super().converged and self.wave_frequency_converged and not any(f.inner_failures for f in nested)

    def diagnostics(self):
        """Unmodified balance residuals; finite iteration/clamping errors remain visible.

        FourField uses a separate mixture precursor for pressure and energy.
        The film/base/wave/drop transport residuals below do not validate that
        precursor or establish experimental validity.
        """
        final, drop, mix = self.film[-1], self.drop[-1], self.mixSolver.mixture[-1]
        g = self.inputSet.geometry
        state = np.concatenate([np.ravel(getattr(field,key)) for field in
                                (final.base,final.wave,drop) for key in ("W","U","H")]
                               +[np.ravel(final.wave.FREQUENCY)])
        result = {**self._physical_inventory_diagnostics(),
            "nonfinite_state_count": int(np.sum(~np.isfinite(state))),
            "base_plus_wave_minus_film_max_kg_s": float(np.max(abs(final.base.W+final.wave.W-final.W))),
            "film_plus_drop_minus_liquid_max_kg_s": float(np.max(abs(final.W.sum(axis=1)+drop.W-mix.liquid.W()))),
            "all_fields_minus_mixture_max_kg_s": float(np.max(abs(final.W.sum(axis=1)+drop.W+mix.vapor.W()-mix.W))),
            "base_min_kg_s": float(np.min(final.base.W)), "wave_min_kg_s": float(np.min(final.wave.W)),
            "drop_min_kg_s": float(np.min(drop.W)), "base_min_m_s": float(np.min(final.base.U)),
            "wave_min_m_s": float(np.min(final.wave.U)), "drop_min_m_s": float(np.min(drop.U)),
            "frequency_min_Hz": float(np.min(final.wave.FREQUENCY)),
            "frequency_temporally_converged": self.wave_frequency_converged,
            "onset_equilibrium_converged": all(d["converged"] for d in self.onset_diagnostics),
            "nested_closure_failures": [failure for f in self.film+[self.filmInit[-1]]
                                        for phase in (f.base,f.wave) for failure in phase.inner_failures],
            "balance_note": "Raw final pseudo-time mass residuals; POSFILM clipping and sequential source updates are retained.",
        }
        if len(self.filmInit)>=2:
            cur,prev,dc = self.filmInit[-1],self.filmInit[-2],self.dropInit[-1]
            onset = cur.mix.OAFIDX()
            for label in ("base","wave"):
                phase,old = getattr(cur,label),getattr(prev,label)
                sources = np.stack([phase.MTOT(dc,j) for j in range(1,self.NZ)])
                residual = (phase.W[1:]-phase.W[:-1]+self.DZ/cur.DT*(phase.W[1:]/phase.U[1:]-old.W[1:]/old.U[1:])
                            -g.PERIM*sources*self.DZ)
                wet = (phase.W[1:]>0)&(np.arange(1,self.NZ)[:,None]>=onset)
                unclamped = wet&(cur.base.W[1:]>0)&(cur.wave.W[1:]>0)
                result[label+"_mass_residual_max_kg_s"] = float(np.max(abs(residual)))
                result[label+"_wet_annular_mass_residual_max_kg_s"] = float(np.max(abs(residual[wet]))) if np.any(wet) else None
                result[label+"_unclamped_annular_mass_residual_max_kg_s"] = float(np.max(abs(residual[unclamped]))) if np.any(unclamped) else None
                result[label+"_zero_mass_node_count"] = int(np.sum(phase.W==0))
        return result

    def solve(self,progress=None):
        if self.STATE!=SolverState.UNSOLVED: raise RuntimeError("Reinitialize this solver before solving again")
        started,o = time.perf_counter(),self.inputSet.options
        try:
            self.STATE = SolverState.SOLVEDCONVERGED
            for k in range(1,len(self.filmInit)):
                ok,change = self._advance(self.filmInit[k-1],self.dropInit[k-1],self.filmInit[k],self.dropInit[k],
                                         sweep_mix=self.mixSolver.mixture[0])
                self._record("initialization",self.filmInit[k],self.dropInit[k],ok,change,progress)
                # Exact upstream convergence predicate: timeDFw is logged,
                # but NOT included in this stop decision.
                if np.all(change[[0,1,2,3,5]] < [o.SSCONVWF,o.SSCONVUF,o.SSCONVWF,o.SSCONVUF,o.SSCONVUD]):
                    if not ok: warnings.warn("Temporal convergence reached without point convergence",RuntimeWarning)
                    self.STATE,self.point_converged = SolverState.INITIALSTEPCONVERGED,ok
                    self.wave_frequency_converged = bool(change[4]<o.SSCONVFW)
                    self.filmInit,self.dropInit = self.filmInit[:k+1],self.dropInit[:k+1]
                    break
                if k+1<len(self.filmInit):
                    self.filmInit[k].copy_flow_properties(self.filmInit[k+1])
                    self.dropInit[k].copy_flow_properties(self.dropInit[k+1])
            else:
                self.STATE = SolverState.INITIALSTEPNOTCONVERGED
            self.filmInit[-1].copy_flow_properties(self.film[0])
            self.dropInit[-1].copy_flow_properties(self.drop[0])
            self.transient_converged = self.NTIME==1
            if self.STATE==SolverState.INITIALSTEPCONVERGED and self.NTIME>1:
                self.STATE,self.transient_converged = SolverState.SOLVEDCONVERGED,True
                for k in range(1,self.NTIME):
                    ok,change = self._advance(self.film[k-1],self.drop[k-1],self.film[k],self.drop[k],
                                             sweep_mix=self.mixSolver.mixture[k])
                    self._record("transient",self.film[k],self.drop[k],ok,change,progress)
                    self.transient_converged &= ok
                    if not ok: self.STATE=SolverState.SOLVEDNOTCONVERGED
            return self
        finally:
            self.elapsed_seconds = time.perf_counter()-started

    def _advance(self,old_film,old_drop,film,drop,*,sweep_mix):
        m,o,g = self.inputSet.model,self.inputSet.options,self.inputSet.geometry
        base,wave = film.base,film.wave
        old_base,old_wave = old_film.base,old_film.wave
        old_base.copy_flow_properties(base); old_wave.copy_flow_properties(wave); old_drop.copy_flow_properties(drop)
        # MATLAB solve.m uses the physical precursor for this outer sweep;
        # aggregate film/drop and base/wave retain their own source handles.
        mix = sweep_mix
        dz,dt,rho = self.DZ,film.DT,film.fluid.RHOF
        onset = mix.OAFIDX()
        fraction = film.distributeOAFW(film.W[onset].copy(),onset)
        total = film.W[:onset+1].copy()
        base.W[:onset+1] = fraction*film.W[onset]
        wave.W[:onset+1] = np.fmax(0,total-base.W[:onset+1])
        point_ok = True
        for j in range(1,self.NZ):
            wb_old,ub_old = old_base.W[j].copy(),old_base.U[j].copy()
            ww_old,uw_old,fw_old = old_wave.W[j].copy(),old_wave.U[j].copy(),old_wave.FREQUENCY[j].copy()
            wb_up,ub_up,ww_up,uw_up,fw_up = base.W[j-1].copy(),base.U[j-1].copy(),wave.W[j-1].copy(),wave.U[j-1].copy(),wave.FREQUENCY[j-1].copy()
            ud_old,ud_up = old_drop.U[j],drop.U[j-1]
            for iteration in range(1,int(o.MAXITER)+1):
                wb,wlb,ub = base.W[j].copy(),base.WL(j).copy(),base.U[j].copy()
                ww,wlw,uw,fw = wave.W[j].copy(),wave.WL(j).copy(),wave.U[j].copy(),wave.FREQUENCY[j].copy()
                ud = drop.U[j]
                wb_new = ub*(wb_up+wb_old/ub_old*dz/dt+g.PERIM*base.MTOT(drop,j)*dz)/(ub+dz/dt)
                base.W[j] = (1-o.RELAXWB)*wb+o.RELAXWB*wb_new
                ww_new = uw*(ww_up+ww_old/uw_old*dz/dt+g.PERIM*wave.MTOT(drop,j)*dz)/(uw+dz/dt)
                wave.W[j] = (1-o.RELAXWW)*ww+o.RELAXWW*ww_new
                if m.POSFILM:
                    total = film.W[j].copy()
                    wave.W[j] = np.fmax(wave.W[j],0)
                    base.W[j] = np.fmax(total-wave.W[j],0)
                drop.W[j] = mix.liquid.W(j)-np.sum(film.W[j])
                if m.WAVEFREQUENCY=="EQUILIBRIUM": wave.FREQUENCY[j] = wave.EQFREQUENCY(j)
                elif m.WAVEFREQUENCY=="RELAXATION":
                    new = uw*(fw_up+fw_old/uw_old*dz/dt+wave.DELTAFREQ(j)*dz)/(uw+dz/dt)
                    wave.FREQUENCY[j] = (1-o.RELAXFW)*fw+o.RELAXFW*new
                else: raise NotImplementedError(f"WAVEFREQUENCY={m.WAVEFREQUENCY}")
                if m.MOMENTBASE=="ALGEBRAIC": base.U[j] = base.UALGEBR(j)
                elif m.MOMENTBASE=="EQUILIBRIUMS": base.U[j] = base.UEQUILS(j)
                elif m.MOMENTBASE=="EQUILIBRIUM": base.U[j] = base.UEQUIL(drop,j)
                elif m.MOMENTBASE in ("FULL","FULLNOP"):
                    thick = abs(base.THICK(j))
                    if np.all(thick>m.THINFILMTHICK):
                        new = (ub_up*ub+ub_old*dz/dt+base.FTOT(drop,j)*dz/(rho*thick))/(ub+dz/dt)
                        new = np.fmin(np.fmax(new,0),mix.liquid.U(j))
                        base.U[j] = blend(mix,mix.liquid.U(j),(1-o.RELAXUB)*ub+o.RELAXUB*new,j)
                    else: base.U[j] = base.UEQUIL(drop,j)
                else: raise NotImplementedError(f"MOMENTBASE={m.MOMENTBASE}")
                if m.MOMENTWAVE=="ALGEBRAIC": wave.U[j] = wave.UALGEBR(j)
                elif m.MOMENTWAVE=="EQUILIBRIUM": wave.U[j] = wave.UEQUIL(drop,j)
                elif m.MOMENTWAVE=="FULL":
                    thick = np.fmax(abs(wave.THICK(j)),m.THINWAVETHICK)
                    new = (uw_up*uw+uw_old*dz/dt+wave.FTOT(drop,j)*dz/(rho*thick))/(uw+dz/dt)
                    new = np.fmin(np.fmax(new,0),mix.vapor.U(j))
                    wave.U[j] = blend(mix,mix.liquid.U(j),(1-o.RELAXUW)*uw+o.RELAXUW*new,j)
                else: raise NotImplementedError(f"MOMENTWAVE={m.MOMENTWAVE}")
                if m.MOMENTDROP=="SLIP": drop.U[j]=drop.USLIP(j)
                elif m.MOMENTDROP=="ALGEBRAIC": drop.U[j]=drop.UALGEBR(film,j)
                elif m.MOMENTDROP in ("EQUILIBRIUM","EQUILIBRIUMS"):
                    drop.U[j]=drop.UEQUIL(film,j,int(m.MOMENTDROP=="EQUILIBRIUMS"))
                elif m.MOMENTDROP=="FULL":
                    new = (ud_up*ud+ud_old*dz/dt+drop.FTOT(film,j)*dz/rho)/(ud+dz/dt)
                    drop.U[j]=blend(mix,mix.liquid.U(j),(1-o.RELAXUD)*ud+o.RELAXUD*new,j)
                else: raise NotImplementedError(f"MOMENTDROP={m.MOMENTDROP}")
                errors = [abs(base.WL(j)-wlb),abs(base.U[j]-ub),abs(wave.WL(j)-wlw),abs(wave.U[j]-uw),abs(wave.FREQUENCY[j]-fw),abs(drop.U[j]-ud)]
                if not np.all(np.isfinite(np.r_[base.W[j],base.U[j],wave.W[j],wave.U[j],wave.FREQUENCY[j],drop.W[j],drop.U[j]])):
                    raise FloatingPointError(f"Nonfinite four-field state at t={film.TIME:g} s node {j}")
                thresholds = [o.ERRORWF,o.ERRORUF,o.ERRORWF,o.ERRORUF,o.ERRORFW,o.ERRORUD]
                if all(np.all(error<threshold) for error,threshold in zip(errors,thresholds)): break
            else: point_ok=False
            base.ITR["N"][j]=wave.ITR["N"][j]=drop.ITR["N"][j]=iteration
            base.ITR["DWL"][j],base.ITR["DU"][j] = errors[:2]
            wave.ITR["DWL"][j],wave.ITR["DU"][j] = errors[2:4]
            if "DF" not in wave.ITR: wave.ITR["DF"]=np.zeros_like(wave.W)
            wave.ITR["DF"][j],drop.ITR["DU"][j]=errors[4:]
        changes = np.array([np.max(abs(base.WL()-old_base.WL())),np.max(abs(base.U-old_base.U)),
                            np.max(abs(wave.WL()-old_wave.WL())),np.max(abs(wave.U-old_wave.U)),
                            np.max(abs(wave.FREQUENCY-old_wave.FREQUENCY)),np.max(abs(drop.U-old_drop.U))])
        return point_ok,changes

    def _record(self,phase,film,drop,ok,changes,progress):
        record = {"phase":phase,"time_s":film.TIME,"point_converged":bool(ok),
                  "max_iterations":int(max(np.max(film.base.ITR["N"]),np.max(film.wave.ITR["N"]),np.max(drop.ITR["N"])))}
        names = ("time_dWLb_kg_s_m","time_dUb_m_s","time_dWLw_kg_s_m","time_dUw_m_s","time_dFw_Hz","time_dUd_m_s")
        record.update({key:float(value) for key,value in zip(names,changes)})
        record["wave_frequency_temporally_converged"] = bool(changes[4]<self.inputSet.options.SSCONVFW)
        self.history.append(record)
        if progress: progress(record)
