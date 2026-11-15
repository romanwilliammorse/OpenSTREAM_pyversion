"""Two-fluid axial sweep and backward-Euler time integration.

Translation of upstream +Solvers/+TwoFluid/@TwoFluidSolver. The precursor
mixture supplies pressure gradient and several closure values, as upstream.
See docs/twofluid_notes.md for intentional preservation of handle semantics.
Copyright (c) 2024 OpenSTREAM contributors. MIT license.
"""
from __future__ import annotations

import time
import warnings
import numpy as np

from .solver import MixtureSolver,SolverState
from .tf_fields import Liquid,Vapor,TwoFluidMixture


class TwoFluidSolver:
    """Native two-fluid solver with optional solved mixture precursor.

    ``liquid`` and ``vapor`` hold physical-time phase states with independent
    ``W`` [kg/s], ``U`` [m/s], ``H`` [J/kg] arrays. ``mixture`` exposes combined
    diagnostics, with explicitly prescribed precursor closures. All indices
    are zero based. Call ``solve()`` then inspect convergence and balances.
    """
    framework = "TwoFluid"

    def __init__(self,input_set,mix_solver=None):
        self.inputSet = input_set.for_solver("TwoFluid")
        self._validate_options()
        self.mixSolver = MixtureSolver(self.inputSet) if mix_solver is None else mix_solver
        if self.mixSolver.STATE==SolverState.UNSOLVED: self.mixSolver.solve()
        if not self.mixSolver.converged:
            raise RuntimeError("Two-fluid initialization requires a converged mixture precursor")
        if self.mixSolver.inputSet.geometry.to_dict()!=self.inputSet.geometry.to_dict():
            raise ValueError("Two-fluid and precursor geometries differ")
        if [b.to_dict() for b in self.mixSolver.inputSet.bc]!=[b.to_dict() for b in self.inputSet.bc]:
            raise ValueError("Two-fluid and precursor boundary conditions differ")
        if self.mixSolver.NZ != int(self.inputSet.model.NNODES)+1:
            raise ValueError("Two-fluid and precursor meshes differ")
        self.initialize_solver()

    def _validate_options(self):
        supported = {
            "MOMENTLIQUID":{"MIXTURE","SLIP","FULL"},
            "MOMENTGAS":{"MIXTURE","SLIP","FULL"},
            "INTLENGTH":{"CONSTANT"},"INTAREA":{"DISPGAS2DISPLIQ"},
            "LOCRELVEL":{"AREAMEAN","SCALED","DRIFT"},
            "DROPDRAG":{"CONSTANT","STOKES","VISCOUS","DISTORDED"},
            "BUBBLEDRAG":{"CONSTANT","STOKES","VISCOUS","DISTORDED"},
            "INTNU":{"CONSTANT","RANZMARSHALL","RELAXATION"},
            "INTTRANSH":{"BULK","SATURATED"},
        }
        for name,values in supported.items():
            value = getattr(self.inputSet.model,name)
            if value not in values:
                raise NotImplementedError(f"Two-fluid {name}={value!r} is not supported; see twofluid_notes.md")
        if self.inputSet.geometry.NWALL()>1 and "FULL" in (self.inputSet.model.MOMENTLIQUID,self.inputSet.model.MOMENTGAS):
            raise NotImplementedError("Two-fluid FULL momentum with multiple walls: upstream wall force is vector-valued but U is scalar")

    def initialize_solver(self):
        for name in ("NZ","NTIME","TIME","DT","Z","DZ","fluid","boundaryConditions"):
            setattr(self,name,getattr(self.mixSolver,name))
        self.liquid,self.vapor,self.mixture = [],[],[]
        for k,precursor in enumerate(self.mixSolver.mixture):
            l = Liquid(self.inputSet,self.fluid[k],self.Z,self.TIME[k],self.DT)
            v = Vapor(self.inputSet,self.fluid[k],self.Z,self.TIME[k],self.DT)
            group = TwoFluidMixture(precursor,l,v)
            l.mix = v.mix = group
            l.W,v.W = precursor.liquid.W().copy(),precursor.vapor.W().copy()
            l.U,v.U = precursor.liquid.U().copy(),precursor.vapor.U().copy()
            l.H = np.fmin(precursor.H,self.fluid[k].HF)
            v.H = np.fmax(precursor.H,self.fluid[k].HG)
            self.liquid.append(l)
            self.vapor.append(v)
            self.mixture.append(group)
        dt = self.inputSet.options.SSTSTEP
        # MATLAB's default Copyable is shallow for nested .mix handles.
        # Array values remain independent; the linked physical phases do not
        # change until initialization is copied into the physical time zero.
        self.liquidInit = [self.liquid[0].clone(time=0,dt=dt)]
        self.vaporInit = [self.vapor[0].clone(time=0,dt=dt)]
        self.STATE = SolverState.UNSOLVED
        self.history = []
        self.elapsed_seconds = 0.0
        self.point_converged = False
        self.transient_converged = False
        self.physical_bounds = False
        self.balance_diagnostics = []

    @property
    def converged(self):
        return (self.STATE in (SolverState.INITIALSTEPCONVERGED,SolverState.SOLVEDCONVERGED)
                and self.point_converged and self.transient_converged and self.physical_bounds)

    def solve(self,progress=None):
        """Execute the upstream six phase equations in their original order."""
        if self.STATE!=SolverState.UNSOLVED:
            raise RuntimeError("Reinitialize the two-fluid solver before solving again")
        start = time.perf_counter()
        o = self.inputSet.options
        self.STATE = SolverState.SOLVEDCONVERGED
        try:
            for k in range(1,int(o.SSMAXITER)):
                l = self.liquid[0].clone(time=k*o.SSTSTEP,dt=o.SSTSTEP)
                v = self.vapor[0].clone(time=k*o.SSTSTEP,dt=o.SSTSTEP)
                oldl,oldv = self.liquidInit[-1],self.vaporInit[-1]
                self.liquidInit.append(l)
                self.vaporInit.append(v)
                okay,delta = self._advance(oldl,oldv,l,v,self.mixSolver.mixture[0])
                self._record("initialization",l,v,okay,delta,progress)
                if np.all(delta < [o.SSCONVW,o.SSCONVW,o.SSCONVU,o.SSCONVU,o.SSCONVH,o.SSCONVH]):
                    self.STATE = SolverState.INITIALSTEPCONVERGED
                    self.point_converged = okay
                    if not okay:
                        warnings.warn("Two-fluid temporal convergence without point convergence (upstream behavior)",RuntimeWarning)
                    break
            else:
                self.STATE = SolverState.INITIALSTEPNOTCONVERGED
            self.liquidInit[-1].copy_flow_properties(self.liquid[0])
            self.vaporInit[-1].copy_flow_properties(self.vapor[0])
            self.transient_converged = self.NTIME==1
            if self.STATE==SolverState.INITIALSTEPCONVERGED and self.NTIME>1:
                self.STATE = SolverState.SOLVEDCONVERGED
                self.transient_converged = True
                for k in range(1,self.NTIME):
                    okay,delta = self._advance(self.liquid[k-1],self.vapor[k-1],self.liquid[k],self.vapor[k],self.mixSolver.mixture[k])
                    self._record("transient",self.liquid[k],self.vapor[k],okay,delta,progress)
                    self.transient_converged &= okay
                    if not okay: self.STATE = SolverState.SOLVEDNOTCONVERGED
            self.physical_bounds = all(np.all(np.isfinite(p.W)) and np.all(p.W>=0) and np.all(np.isfinite(p.U)) and np.all(p.U>0)
                                       and np.all(np.isfinite(p.H)) for p in self.liquid+self.vapor)
            if not self.physical_bounds:
                warnings.warn("Two-fluid output violates positive-flow or finite-state bounds; result is not accepted as converged",RuntimeWarning)
            self.balance_diagnostics = self._balances()
            return self
        finally:
            self.elapsed_seconds = time.perf_counter()-start

    def _advance(self,oldl,oldv,l,v,precursor):
        oldl.copy_flow_properties(l)
        oldv.copy_flow_properties(v)
        o,m = self.inputSet.options,self.inputSet.model
        dz,dt = self.DZ,l.DT
        okay = True
        for j in range(1,self.NZ):
            wlold,ulold,hlold = oldl.W[j],oldl.U[j],oldl.H[j]
            wvold,uvold,hvold = oldv.W[j],oldv.U[j],oldv.H[j]
            wlup,ulup,hlup = l.W[j-1],l.U[j-1],l.H[j-1]
            wvup,uvup,hvup = v.W[j-1],v.U[j-1],v.H[j-1]
            for iteration in range(1,int(o.MAXITER)+1):
                wli,uli,hli = l.W[j],l.U[j],l.H[j]
                wvi,uvi,hvi = v.W[j],v.U[j],v.H[j]
                mtot = np.sum(l.MTOT(v,j))
                wlnew = uli*(wlup+wlold/ulold*dz/dt+mtot*dz)/(uli+dz/dt)
                l.W[j] = (1-o.RELAXWL)*wli+o.RELAXWL*wlnew
                mtot = np.sum(v.MTOT(l,j))
                wvnew = uvi*(wvup+wvold/uvold*dz/dt+mtot*dz)/(uvi+dz/dt)
                v.W[j] = (1-o.RELAXWV)*wvi+o.RELAXWV*wvnew
                if m.MOMENTLIQUID=="MIXTURE": ulnew = uli
                elif m.MOMENTLIQUID=="SLIP": ulnew = l.USLIP(v,j)
                else:
                    # Source uses old point-iteration inventory W/U and a
                    # 1e-3 kg/s threshold, retained without reinterpretation.
                    ftot = float(np.asarray(l.FTOT(v,j)).item())/(wli/uli) if wli>1e-3 else 0.0
                    ulnew = (uli*ulup+ulold*dz/dt+ftot*dz)/(uli+dz/dt)
                    ulnew = np.fmin(1.5*precursor.liquid.U(j),np.fmax(0,ulnew))
                    if wli<=1e-3: ulnew = uli
                l.U[j] = (1-o.RELAXUL)*uli+o.RELAXUL*ulnew
                if m.MOMENTGAS=="MIXTURE": uvnew = uvi
                elif m.MOMENTGAS=="SLIP": uvnew = v.USLIP(l,j)
                else:
                    ftot = float(np.asarray(v.FTOT(l,j)).item())/(wvi/uvi) if wvi>1e-3 else 0.0
                    uvnew = (uvi*uvup+uvold*dz/dt+ftot*dz)/(uvi+dz/dt)
                    uvnew = np.fmin(1.5*precursor.vapor.U(j),np.fmax(0,uvnew))
                    if wvi<=1e-3: uvnew = uvi
                v.U[j] = (1-o.RELAXUV)*uvi+o.RELAXUV*uvnew
                htot = np.sum(l.HTOT(v,j))/(wli/uli) if wli>1e-3 else 0.0
                hlnew = (hlup*uli+hlold*dz/dt+htot*dz)/(uli+dz/dt)
                l.H[j] = (1-o.RELAXHL)*hli+o.RELAXHL*hlnew
                htot = np.sum(v.HTOT(l,j))/(wvi/uvi) if wvi>1e-3 else 0.0
                hvnew = (hvup*uvi+hvold*dz/dt+htot*dz)/(uvi+dz/dt)
                v.H[j] = (1-o.RELAXHV)*hvi+o.RELAXHV*hvnew
                delta = np.abs(np.array([l.W[j]-wli,v.W[j]-wvi,l.U[j]-uli,v.U[j]-uvi,l.H[j]-hli,v.H[j]-hvi]))
                if not np.all(np.isfinite(delta)):
                    raise FloatingPointError(f"Nonfinite two-fluid iteration at t={l.TIME:g} s, z={l.Z[j]:g} m")
                if np.all(delta<[o.ERRORW,o.ERRORW,o.ERRORU,o.ERRORU,o.ERRORH,o.ERRORH]): break
            else:
                okay = False
                self.STATE = SolverState.SOLVEDNOTCONVERGED
            for phase,values in ((l,(delta[0],delta[2],delta[4])),(v,(delta[1],delta[3],delta[5]))):
                phase.ITR["N"][j] = iteration
                for key,value in zip(("DW","DU","DH"),values): phase.ITR[key][j] = value
        temporal = np.array([np.max(abs(l.W-oldl.W)),np.max(abs(v.W-oldv.W)),np.max(abs(l.U-oldl.U)),np.max(abs(v.U-oldv.U)),np.max(abs(l.H-oldl.H)),np.max(abs(v.H-oldv.H))])
        return okay,temporal

    def _record(self,phase,l,v,okay,delta,progress):
        record = dict(phase=phase,time_s=float(l.TIME),point_converged=bool(okay),max_iterations=int(np.max(l.ITR["N"])))
        for key,value in zip(("time_dWL_kg_s","time_dWV_kg_s","time_dUL_m_s","time_dUV_m_s","time_dHL_J_kg","time_dHV_J_kg"),delta): record[key]=float(value)
        for label,field in (("L",l),("V",v)):
            for key,units in (("DW","kg_s"),("DU","m_s"),("DH","J_kg")):
                record[f"point_{key}{label}_{units}"]=float(np.max(field.ITR[key]))
        self.history.append(record)
        if progress is not None: progress(record)

    def _balances(self):
        """Independent physical checks; convergence alone is not validation.

        The area check uses the actual solved W, U and phase densities, not
        the normalized VF closure that forces fractions to sum to one.
        """
        records=[]
        for k,(l,v) in enumerate(zip(self.liquid,self.vapor)):
            f=self.fluid[k]
            occupied=l.W/(f.RHOL(l.H)*l.U)+v.W/(f.RHOV(v.H)*v.U)
            relative=occupied/self.inputSet.geometry.AREA-1
            mass=(l.W[-1]+v.W[-1])-(l.W[0]+v.W[0])
            energy=l.W[-1]*l.H[-1]+v.W[-1]*v.H[-1]-l.W[0]*l.H[0]-v.W[0]*v.H[0]
            power=float(np.sum(self.mixture[k].LHGR()[1:])*self.DZ)
            if k:
                oldl,oldv=self.liquid[k-1],self.vapor[k-1]
                mass+=sum(np.sum((p.W[1:]/p.U[1:]-q.W[1:]/q.U[1:])*self.DZ/self.DT) for p,q in ((l,oldl),(v,oldv)))
                energy+=sum(np.sum((p.W[1:]/p.U[1:]*p.H[1:]-q.W[1:]/q.U[1:]*q.H[1:])*self.DZ/self.DT) for p,q in ((l,oldl),(v,oldv)))
            source=l.HTOT(v)+v.HTOT(l)+l.H[:,None]*l.MTOT(v)+v.H[:,None]*v.MTOT(l)-self.mixture[k].LHGR()
            records.append(dict(time_s=float(self.TIME[k]),mass_balance_residual_kg_s=float(mass),energy_balance_residual_W=float(energy-power),
                                max_area_closure_relative=float(np.max(abs(relative))),outlet_area_closure_relative=float(relative[-1]),
                                max_source_energy_identity_residual_W_m=float(np.max(abs(source))),
                                steady_discrete_product_term_W=float(-sum(np.sum(np.diff(p.W)*np.diff(p.H)) for p in (l,v)))))
        return records

    def diagnostics(self):
        """Return source balance evidence and explicit physical-consistency status.

        A relative area error above 1e-6 fails an algebraic closure check.
        Passing that check alone would still leave physical validation unknown.
        """
        records=self.balance_diagnostics or self._balances()
        max_area=max(r["max_area_closure_relative"] for r in records)
        return {"physical_consistency":False if max_area>1e-6 else None,
                "area_closure_relative_tolerance":1e-6,
                "max_area_closure_relative":max_area,
                "outlet_area_closure_relative":records[-1]["outlet_area_closure_relative"],
                "mass_balance_residual_kg_s":records[-1]["mass_balance_residual_kg_s"],
                "energy_balance_residual_W":records[-1]["energy_balance_residual_W"],
                "max_source_energy_identity_residual_W_m":max(r["max_source_energy_identity_residual_W_m"] for r in records),
                "by_time":records,
                "limitation":"Numerical convergence does not establish physical area closure. Agreement with an upstream reference is a separate case-specific check; see the baseline verification report."}

    def save(self,directory):
        from .multifield_output import save_multifield
        return save_multifield(self,directory)

    def plotz(self,filename=None,time_index=-1):
        import matplotlib.pyplot as plt
        fig,axes = plt.subplots(1,3,figsize=(13,4.5),layout="constrained")
        for ax,name,unit in zip(axes,("W","U","H"),("kg/s","m/s","J/kg")):
            for label,phase in (("Liquid",self.liquid[time_index]),("Vapor",self.vapor[time_index])):
                ax.plot(self.Z,getattr(phase,name),label=label)
            ax.set(xlabel="Axial position [m]",ylabel=f"{name} [{unit}]")
            ax.grid(alpha=.25)
            ax.legend()
        if filename is not None: fig.savefig(filename,dpi=170)
        return fig
