"""Three-field annular solver translated from the pinned upstream implementation."""
from copy import deepcopy
import time
import warnings
import numpy as np
from scipy.interpolate import interp1d
from .annular import Film, Drop, blend
from .solver import MixtureSolver, SolverState


class ThreeFieldSolver:
    """Liquid film and entrained drops with pressure/vapor from MixtureSolver."""
    framework = "ThreeField"

    def __init__(self, input_set, mix_solver=None):
        self.inputSet = input_set.for_solver(self.framework)
        self.mixSolver = mix_solver or MixtureSolver(input_set)
        if self.mixSolver.STATE == SolverState.UNSOLVED: self.mixSolver.solve()
        if not self.mixSolver.converged:
            raise RuntimeError("Annular framework requires a converged precursor mixture solution")
        if self.inputSet.geometry.to_dict() != self.mixSolver.inputSet.geometry.to_dict():
            raise ValueError("Mixture precursor geometry differs from annular input")
        if [b.to_dict() for b in self.inputSet.bc] != [b.to_dict() for b in self.mixSolver.inputSet.bc]:
            raise ValueError("Mixture precursor boundary conditions differ from annular input")
        self.initialize_solver()

    def initialize_solver(self):
        m = self.inputSet.model
        if m.DROPDRAG == "DISTORDED":
            raise NotImplementedError("Upstream DROPDRAG=DISTORDED references undefined liquid/vapor variables")
        for key in ("NZ", "NTIME", "TIME", "DT", "Z", "DZ", "fluid", "boundaryConditions"):
            setattr(self, key, getattr(self.mixSolver, key))
        if not np.array_equal(self.Z, np.linspace(0, self.inputSet.geometry.LENGTH, int(m.NNODES)+1)):
            raise ValueError("Mixture precursor grid does not match annular input")
        self.onset_diagnostics = []
        self.film, self.drop = [], []
        for mix in self.mixSolver.mixture:
            film, drop = self._initialize_fields(mix)
            self.film.append(film)
            self.drop.append(drop)
        self.filmInit, self.dropInit = [], []
        for k in range(int(self.inputSet.options.SSMAXITER)):
            film, drop = deepcopy(self.film[0]), deepcopy(self.drop[0])
            mix = deepcopy(self.mixSolver.mixtureInit[-1])
            film.TIME = drop.TIME = mix.TIME = k*self.inputSet.options.SSTSTEP
            film.DT = drop.DT = mix.DT = self.inputSet.options.SSTSTEP
            film.mix = drop.mix = mix
            self.filmInit.append(film)
            self.dropInit.append(drop)
        self.STATE = SolverState.UNSOLVED
        self.history, self.elapsed_seconds = [], 0.0
        self.point_converged = self.transient_converged = False

    def _initialize_fields(self, mix):
        g, m, f = self.inputSet.geometry, self.inputSet.model, mix.fluid
        film, drop = Film(self.inputSet, mix), Drop(self.inputSet, mix)
        avg = np.sum(mix.HFLUX*g.PERIM, axis=1)/np.sum(g.PERIM)
        with np.errstate(divide="ignore", invalid="ignore"):
            evap = np.r_[0, np.fmax(0, np.diff(mix.X())/np.diff(mix.XEQ()))]
        evap[~np.isfinite(evap)] = 1
        film.HFLUX = blend(mix, np.broadcast_to((evap*avg)[:, None], mix.HFLUX.shape), mix.HFLUX)
        film.mevap = -film.HFLUX/f.HFG
        e0 = m.OAFDROPRATIO if m.OAFENTRAINED == "RATIO" else self.EQUIL(film, drop, mix, mix.OAFIDX())
        drop.W[:] = e0*mix.OAFWL()+mix.W-mix.W[mix.OAFIDX()]
        inlet = (mix.liquid.W(0)-drop.W[0])*g.PERIM/np.sum(g.PERIM)
        film.W = np.fmax(0, inlet+np.cumsum(film.mevap, axis=0)*g.PERIM*self.DZ)
        drop.W = mix.liquid.W()-film.W.sum(axis=1)
        drop.U = drop.USLIP()
        film.U = film.UALGEBR()
        film.H = np.full((self.NZ, 1), f.HF)
        drop.H[:] = f.HF
        return film, drop

    def EQUIL(self, film, drop, mix, j):
        """Exact upstream onset iteration, including its documented tolerance fallback."""
        o, g = self.inputSet.options, self.inputSet.geometry
        w = float(mix.liquid.W(j))
        if w <= 0: raise ValueError("Annular onset requires positive liquid flow")
        tol0, tol = o.OAFEQUILTOL, o.OAFEQUILTOL
        wd, delta = [], []
        for k in range(int(o.OAFEQUILMAXITER)):
            if k == 0: guess = .5*w
            elif k == 1: guess = (.7-float(delta[-1] > 0)*.4)*w
            elif np.all(np.diff(delta)/np.diff(wd) > 0):
                try:
                    finite = np.isfinite(delta)
                    x, y = np.asarray(delta)[finite], np.asarray(wd)[finite]
                    if len(np.unique(x)) != len(x): raise ValueError("Duplicate residuals")
                    guess = float(np.fmax(np.fmin(interp1d(x, y, fill_value="extrapolate")(0), w), 0))
                except ValueError:
                    guess = float(np.fmax(np.fmin(wd[-1]*(1-20*delta[-1]), w), 0))
                    wd[-1] = delta[-1] = np.nan
                    tol = tol0*10
            else:
                guess = float(np.fmax(np.fmin(wd[-1]*(1-20*delta[-1]), w), 0))
                tol = tol0*10
            wd.append(guess)
            drop.W[j] = guess
            film.W[j] = (w-guess)*g.PERIM/np.sum(g.PERIM)
            residual = float(drop.MDEP(j, False)*np.sum(g.PERIM)+np.sum(film.MENT(j)*g.PERIM))
            delta.append(residual)
            if abs(residual) < tol: break
        self.onset_diagnostics.append({"node": int(j), "iterations": k+1, "residual_kg_s_m": residual,
                                       "original_tolerance_kg_s_m": tol0, "effective_tolerance_kg_s_m": tol,
                                       "converged": abs(residual) < tol})
        if abs(residual) >= tol:
            warnings.warn("Annular onset equilibrium did not converge", RuntimeWarning)
        return drop.W[j]/w

    @property
    def converged(self):
        fields = self.film+self.drop+[self.filmInit[-1], self.dropInit[-1]]
        nested_ok = all(d["converged"] for d in self.onset_diagnostics) and not any(f.inner_failures for f in fields)
        return self.STATE in (SolverState.INITIALSTEPCONVERGED, SolverState.SOLVEDCONVERGED) and self.point_converged and self.transient_converged and nested_ok

    def solve(self, progress=None):
        if self.STATE != SolverState.UNSOLVED: raise RuntimeError("Reinitialize this solver before solving again")
        started, o = time.perf_counter(), self.inputSet.options
        try:
            self.STATE = SolverState.SOLVEDCONVERGED
            for k in range(1, len(self.filmInit)):
                ok, change = self._advance(self.filmInit[k-1], self.dropInit[k-1], self.filmInit[k], self.dropInit[k])
                self._record("initialization", self.filmInit[k], self.dropInit[k], ok, change, progress)
                if np.all(change < [o.SSCONVWF, o.SSCONVUF, o.SSCONVUD]):
                    if not ok: warnings.warn("Temporal convergence reached without point convergence", RuntimeWarning)
                    self.STATE, self.point_converged = SolverState.INITIALSTEPCONVERGED, ok
                    self.filmInit, self.dropInit = self.filmInit[:k+1], self.dropInit[:k+1]
                    break
                if k+1 < len(self.filmInit):
                    self.filmInit[k].copy_flow_properties(self.filmInit[k+1])
                    self.dropInit[k].copy_flow_properties(self.dropInit[k+1])
            else:
                self.STATE = SolverState.INITIALSTEPNOTCONVERGED
            self.filmInit[-1].copy_flow_properties(self.film[0])
            self.dropInit[-1].copy_flow_properties(self.drop[0])
            self.transient_converged = self.NTIME == 1
            if self.STATE == SolverState.INITIALSTEPCONVERGED and self.NTIME > 1:
                self.STATE, self.transient_converged = SolverState.SOLVEDCONVERGED, True
                for k in range(1, self.NTIME):
                    ok, change = self._advance(self.film[k-1], self.drop[k-1], self.film[k], self.drop[k])
                    self._record("transient", self.film[k], self.drop[k], ok, change, progress)
                    self.transient_converged &= ok
                    if not ok: self.STATE = SolverState.SOLVEDNOTCONVERGED
            return self
        finally:
            self.elapsed_seconds = time.perf_counter()-started

    def _advance(self, fold, dold, film, drop):
        m, o, g = self.inputSet.model, self.inputSet.options, self.inputSet.geometry
        fold.copy_flow_properties(film)
        dold.copy_flow_properties(drop)
        dz, dt, rho, mix = self.DZ, film.DT, film.fluid.RHOF, film.mix
        point_ok = True
        for j in range(1, self.NZ):
            wf_old, uf_old, wf_up, uf_up = fold.W[j], fold.U[j], film.W[j-1], film.U[j-1]
            ud_old, ud_up = dold.U[j], drop.U[j-1]
            for itr in range(1, int(o.MAXITER)+1):
                wf, wl, uf, ud = film.W[j].copy(), film.WL(j).copy(), film.U[j].copy(), drop.U[j]
                total = film.MTOT(drop, j)
                wfnew = uf*(wf_up+wf_old/uf_old*dz/dt+g.PERIM*total*dz)/(uf+dz/dt)
                film.W[j] = (1-o.RELAXWF)*wf+o.RELAXWF*wfnew
                if m.POSFILM: film.W[j] = np.fmax(film.W[j], 0)
                if m.MOMENTFILM == "ALGEBRAIC": film.U[j] = film.UALGEBR(j)
                elif m.MOMENTFILM == "EQUILIBRIUMS": film.U[j] = film.UEQUILS(j)
                elif m.MOMENTFILM == "EQUILIBRIUM": film.U[j] = film.UEQUIL(drop, j)
                elif m.MOMENTFILM == "FULL":
                    thick = np.fmax(abs(film.THICK(j)), m.THINFILMTHICK)
                    if np.all(thick > m.THINFILMTHICK):
                        new = (uf_up*uf+uf_old*dz/dt+film.FTOT(drop, j)*dz/(rho*thick))/(uf+dz/dt)
                        new = np.fmin(np.fmax(new, 0), mix.liquid.U(j))
                        film.U[j] = blend(mix, mix.liquid.U(j), (1-o.RELAXUF)*uf+o.RELAXUF*new, j)
                    else: film.U[j] = film.UEQUIL(drop, j)
                else: raise NotImplementedError(f"MOMENTFILM={m.MOMENTFILM}")
                drop.W[j] = mix.liquid.W(j)-np.sum(film.W[j])
                if m.MOMENTDROP == "SLIP": drop.U[j] = drop.USLIP(j)
                elif m.MOMENTDROP == "ALGEBRAIC": drop.U[j] = drop.UALGEBR(film, j)
                elif m.MOMENTDROP in ("EQUILIBRIUMS", "EQUILIBRIUM"):
                    drop.U[j] = drop.UEQUIL(film, j, int(m.MOMENTDROP == "EQUILIBRIUMS"))
                elif m.MOMENTDROP == "FULL":
                    new = (ud_up*ud+ud_old*dz/dt+drop.FTOT(film, j)*dz/rho)/(ud+dz/dt)
                    drop.U[j] = blend(mix, mix.liquid.U(j), (1-o.RELAXUD)*ud+o.RELAXUD*new, j)
                else: raise NotImplementedError(f"MOMENTDROP={m.MOMENTDROP}")
                dwl, duf, dud = abs(film.WL(j)-wl), abs(film.U[j]-uf), abs(drop.U[j]-ud)
                if not np.all(np.isfinite(np.r_[film.W[j], film.U[j], drop.W[j], drop.U[j]])):
                    raise FloatingPointError(f"Nonfinite three-field state at t={film.TIME:g} s node {j}")
                if np.all(dwl < o.ERRORWF) and np.all(duf < o.ERRORUF) and dud < o.ERRORUD: break
            else: point_ok = False
            film.ITR["N"][j] = drop.ITR["N"][j] = itr
            film.ITR["DWL"][j], film.ITR["DU"][j], drop.ITR["DU"][j] = dwl, duf, dud
        return point_ok, np.array([np.max(abs(film.WL()-fold.WL())), np.max(abs(film.U-fold.U)), np.max(abs(drop.U-dold.U))])

    def _record(self, phase, film, drop, ok, changes, progress):
        r = {"phase": phase, "time_s": film.TIME, "point_converged": bool(ok), "max_iterations": int(max(film.ITR["N"])),
             "time_dWL_kg_s_m": float(changes[0]), "time_dUF_m_s": float(changes[1]), "time_dUD_m_s": float(changes[2])}
        self.history.append(r)
        if progress: progress(r)

    def save(self, directory):
        from .multifield_output import save_multifield
        return save_multifield(self, directory)

    def _physical_inventory_diagnostics(self):
        """Independent field inventory/area closure, also used by FourField.

        Film/drop enthalpies are prescribed saturated liquid in the annular
        source. Actual W/U inventories are reported with precursor vapor;
        upstream Three/FourField does not impose phase-volume closure as a
        convergence or acceptance gate. No normalized volume fraction is used.
        Zero flow with zero velocity is indeterminate, not silently zeroed.
        The all-node result includes the blended pre-annular region; a separate
        mask AFFNC >= 1-1e-12 identifies the numerically unblended annular region.
        """
        geometry, records, previous_inventory = self.inputSet.geometry, [], None
        common = np.all(np.stack([mix.AFFNC() >= 1-1e-12 for mix in self.mixSolver.mixture]), axis=0)
        # Use a fixed downstream control volume, with its upstream face also
        # annular at every stored time. A moving onset boundary is not used.
        outside = np.flatnonzero(~common)
        first = int(outside[-1]+1) if outside.size else 0
        common_cells = self.NZ-1-first if first < self.NZ-1 else 0
        for k, (film, drop, mix) in enumerate(zip(self.film, self.drop, self.mixSolver.mixture)):
            with np.errstate(divide="ignore", invalid="ignore"):
                film_inventory = np.sum(film.W/film.U, axis=1)
                drop_inventory = drop.W/drop.U
                vapor_inventory = mix.vapor.W()/mix.vapor.U()
                inventory = film_inventory+drop_inventory+vapor_inventory
                occupied = (film_inventory+drop_inventory)/film.fluid.RHOF+vapor_inventory/film.fluid.RHOV(mix.vapor.H())
                relative = occupied/geometry.AREA-1
            finite = np.isfinite(relative) & np.isfinite(inventory)
            annular = mix.AFFNC() >= 1-1e-12
            mass_flux = np.sum(film.W, axis=1)+drop.W+mix.vapor.W()
            mass = np.diff(mass_flux)
            if k: mass += self.DZ/film.DT*(inventory[1:]-previous_inventory[1:])
            records.append({"time_s": float(self.TIME[k]),
                "max_area_closure_relative": float(np.max(abs(relative))) if np.all(finite) else float("inf"),
                "outlet_area_closure_relative": float(relative[-1]),
                "max_unblended_annular_area_closure_relative": (float(np.max(abs(relative[annular]))) if np.all(finite[annular]) else float("inf")) if np.any(annular) else None,
                "unblended_annular_node_count": int(np.count_nonzero(annular)),
                "nonfinite_inventory_or_area_node_count": int(np.count_nonzero(~finite)),
                "nonfinite_unblended_annular_node_count": int(np.count_nonzero(annular & ~finite)),
                "max_all_phase_cell_mass_residual_kg_s": float(np.max(abs(mass))),
                "global_all_phase_mass_residual_kg_s": float(np.sum(mass)),
                "max_common_annular_cell_mass_residual_kg_s": float(np.max(abs(mass[first:]))) if common_cells else None,
                "common_annular_mass_residual_kg_s": float(np.sum(mass[first:])) if common_cells else None,
                "common_annular_mass_inventory_kg": float(np.sum(inventory[first+1:])*self.DZ) if common_cells else None,
                "integrated_phase_mass_inventory_kg": float(np.sum(inventory[1:])*self.DZ)})
            previous_inventory = inventory
        maximum = max(x["max_area_closure_relative"] for x in records)
        annular_errors = [x["max_unblended_annular_area_closure_relative"] for x in records
                          if x["max_unblended_annular_area_closure_relative"] is not None]
        indeterminate = any(x["nonfinite_unblended_annular_node_count"] for x in records)
        return {"physical_consistency": None,
                "phase_volume_closure_role": "informational",
                "phase_volume_closure_status": "indeterminate" if indeterminate else "reported" if annular_errors else "no_applicable_region",
                "area_closure_relative_tolerance": None,
                "max_area_closure_relative": maximum,
                "max_unblended_annular_area_closure_relative": max(annular_errors) if annular_errors else None,
                "outlet_area_closure_relative": records[-1]["outlet_area_closure_relative"],
                "common_annular_upstream_face_z_m": float(self.Z[first]) if common_cells else None,
                "common_annular_downstream_face_z_m": float(self.Z[-1]) if common_cells else None,
                "common_annular_cell_count": common_cells,
                "max_common_annular_cell_mass_residual_kg_s": max(x["max_common_annular_cell_mass_residual_kg_s"] for x in records) if common_cells else None,
                "max_abs_common_annular_mass_residual_kg_s": max(abs(x["common_annular_mass_residual_kg_s"]) for x in records) if common_cells else None,
                "inventory_by_time": records,
                "inventory_interpretation": "W/U is kg/m; occupied area = sum(Wfilm/Ufilm)/rhoF + Wdrop/(Udrop*rhoF) + Wvapor/(Uvapor*rhoV). Phase-volume closure is informational for ThreeField/FourField: the original MATLAB frameworks do not impose this residual as a convergence or acceptance gate. No area-residual acceptance threshold is applied. Finite residuals and indeterminate NaN/Inf inventory or area values do not change solver acceptance; existing solver convergence and exceptions remain unchanged. AFFNC >= 1-1e-12 identifies the numerically unblended annular region for reporting, and absence of such nodes leaves that result unavailable. Common-annular mass diagnostics use a fixed downstream control volume whose upstream face and all cells satisfy this mask at every time; its residual is outflow minus inflow plus backward-Euler storage, with no storage for the initial steady state. Pre-annular values are source initialization quantities and all-region area/mass diagnostics there are descriptive. Zero/zero inventory is indeterminate and is not silently zeroed. Any four-field film-thickness caps do not independently enforce this inventory identity. Numerical convergence and algebraic flow partition do not establish mass-storage conservation or physical validation. Whether a discrepancy is shared with upstream is established by a separate reference comparison; see the baseline verification report."}

    def diagnostics(self):
        """Report raw balances and clipping; numerical convergence is separate."""
        cur, prev, drop = self.filmInit[-1], self.filmInit[-2], self.dropInit[-1]
        sources = np.stack([cur.MTOT(drop, j) for j in range(1, self.NZ)])
        residual = cur.W[1:]-cur.W[:-1]+self.DZ/cur.DT*(cur.W[1:]/cur.U[1:]-prev.W[1:]/prev.U[1:])-self.inputSet.geometry.PERIM*sources*self.DZ
        positive = cur.W[1:] > 0
        return {**self._physical_inventory_diagnostics(), "interpretation": "Checks below do not establish full physical validation; POSFILM changes the unconstrained mass equation at dryout",
                "max_liquid_partition_error_kg_s": float(max(np.max(abs(f.W.sum(axis=1)+d.W-f.mix.liquid.W())) for f, d in zip(self.film, self.drop))),
                "max_film_mass_residual_kg_s": float(np.max(abs(residual))),
                "max_positive_film_mass_residual_kg_s": float(np.max(abs(residual[positive]))) if np.any(positive) else 0.0,
                "clipped_node_wall_count": int(np.count_nonzero(~positive)),
                "min_film_flow_kg_s": float(min(np.min(f.W) for f in self.film)),
                "min_drop_flow_kg_s": float(min(np.min(d.W) for d in self.drop)),
                "max_onset_equilibrium_residual_kg_s_m": float(max((abs(x["residual_kg_s_m"]) for x in self.onset_diagnostics), default=0))}
