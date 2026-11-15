"""Mixture time integration translated from the pinned MATLAB implementation.

Upstream: +Solvers/+Mixture/@MixtureSolver/{MixtureSolver,solve}.m.
The axial sweep, point iteration, pseudo-time initialization, relaxation and
dimensional stopping tolerances retain their original order and equations.
"""
from __future__ import annotations

from enum import IntEnum
import time
import warnings
import numpy as np

from .fields import Mixture
from .properties import FluidProperties
from .numerics import colon, interpolate


class SolverState(IntEnum):
    UNSOLVED = 0
    SOLVEDCONVERGED = 1
    SOLVEDNOTCONVERGED = 2
    INITIALSTEPCONVERGED = 3
    INITIALSTEPNOTCONVERGED = 4


DP_KEYS = {"Grav": "GRAV", "Wall": "WALL", "Acc_z": "ACCZ",
           "Acc_t": "ACCT", "Acc_s": "ACCS", "K": "K", "Tot": "TOT"}


class MixtureSolver:
    """Native mixture solver; construct with :class:`InputSet`, then ``solve()``.

    ``mixture`` stores physical states, ``mixtureInit`` stores pseudo-time
    states. Arrays are node-major, with a second dimension for walls. Indices
    are zero based. The upstream STATE is retained; ``converged`` additionally
    requires point convergence and must be checked before using a result.
    """

    def __init__(self, input_set):
        self.inputSet = input_set.for_solver("Mixture")
        self.initialize_solver()

    def initialize_solver(self):
        s = self.inputSet
        if not s.bc:
            raise ValueError("At least one boundary-condition record is required")
        if any(x.MFLOW <= 0 for x in s.bc):
            raise ValueError("The upstream forward axial sweep requires positive inlet flow")
        self.DT = s.options.TSTEP
        self.TIME = colon(s.bc[0].TIME, self.DT, s.bc[-1].TIME)
        self.NTIME = len(self.TIME)
        self.Z = np.linspace(0, s.geometry.LENGTH, int(s.model.NNODES)+1)
        self.NZ, self.DZ = len(self.Z), s.geometry.LENGTH / s.model.NNODES
        self._interpolate_boundary_conditions()
        self.fluid = [FluidProperties(p, s.model) for p in self.boundaryConditions["PRESSURE"]]
        self.mixture = [self._new_field(i, t, self.DT) for i, t in enumerate(self.TIME)]
        self.mixtureInit = [self._new_field(0, 0, s.options.SSTSTEP)]
        self.STATE = SolverState.UNSOLVED
        self.history = []
        self.elapsed_seconds = 0.0
        self.point_converged = False
        self.transient_converged = False

    def _interpolate_boundary_conditions(self):
        s, z = self.inputSet, self.Z
        times = [b.TIME for b in s.bc]
        bc = {key: interpolate(times, [getattr(b, key) for b in s.bc], self.TIME,
                               s.options.TIMEINTERP) for key in
              ("TIME", "PRESSURE", "HIN", "MFLOW", "POWER")}
        # Explicit (time,node,wall) arrays replace MATLAB reshape/permute.
        axial = np.stack([interpolate(np.cumsum(b.WMESH), b.WPOWER, z,
                                      s.options.AXIALINTERP, True) for b in s.bc])
        power = interpolate(times, axial, self.TIME, s.options.TIMEINTERP)
        denominator = np.sum(power[:, 1:, :] * s.geometry.PERIM[None, None, :] * self.DZ, axis=(1, 2))
        if np.any(denominator <= 0):
            raise ValueError("Interpolated power distribution has nonpositive integral")
        bc["WPOWER"] = power
        bc["HFLUX"] = power * (bc["POWER"] / denominator)[:, None, None]
        if np.any(bc["HFLUX"] < 0):
            raise ValueError("Interpolation produced negative heat flux, outside upstream limits")
        self.boundaryConditions = bc

    def _new_field(self, i, t, dt):
        m = Mixture(self.inputSet, self.fluid[i], self.Z, t, dt)
        b, f, nw = self.boundaryConditions, self.fluid[i], self.inputSet.geometry.NWALL()
        m.W[:] = b["MFLOW"][i]
        m.P[:] = b["PRESSURE"][i]
        m.HFLUX[:] = b["HFLUX"][i]
        m.H[:] = b["HIN"][i]
        m.update()
        m.MRM["WV"] = np.fmax(0, m.XEQ())[:, None] * m.WWALL()
        m.MRM["X"] = np.broadcast_to(np.fmax(0, m.XEQ())[:, None], (self.NZ, nw)).copy()
        m.MRM["HV"][:] = f.HG
        m.MRM["TV"][:] = f.T(m.MRM["HV"])
        # Do not refresh derived properties here: the MATLAB MRM assignment
        # has no setter; its next refresh occurs on copying/setting H.
        m.NEARWALL = {
            "TRELAX": np.zeros((self.NZ, nw)), "W": m.WNEARWALL().copy(),
            "H": np.broadcast_to(m.H[:, None], (self.NZ, nw)).copy(),
            "HFLUX": np.zeros((self.NZ, nw)),
            "XEQ": np.broadcast_to(m.XEQ()[:, None], (self.NZ, nw)).copy(),
            "WBULK": m.W-m.WNEARWALL().sum(axis=1), "HBULK": m.H.copy(), "XBULK": m.XEQ().copy(),
        }
        m.DP = {k: np.zeros(self.NZ) for k in DP_KEYS}
        m.DPSUM = {k: np.zeros(self.NZ) for k in DP_KEYS}
        m.MDER = {k: np.zeros(self.NZ) for k in ("U_z", "U_t", "U", "H_z", "H_t", "H")}
        m.ITR = {k: np.zeros(self.NZ) for k in ("N", "DW", "DP", "DPSUM", "DH")}
        m.ITR.update({k: np.zeros((self.NZ, nw)) for k in ("DWV", "DHV")})
        return m

    @property
    def converged(self):
        return self.STATE == SolverState.INITIALSTEPCONVERGED and self.point_converged and self.transient_converged

    def solve(self, progress=None):
        """Solve in place and return self; ``progress`` receives step dictionaries.

        No MATLAB, MATLAB Engine or Octave is imported or invoked. A repeated
        solve requires ``initialize_solver()`` as in upstream.
        """
        if self.STATE != SolverState.UNSOLVED:
            raise RuntimeError("Reinitialize this solver before solving again")
        started = time.perf_counter()
        o = self.inputSet.options
        try:
            for k in range(1, int(o.SSMAXITER)):
                old = self.mixtureInit[-1]
                m = self._new_field(0, k*o.SSTSTEP, o.SSTSTEP)
                self.mixtureInit.append(m)
                if k > 1:
                    # Upstream copies at the end of the preceding iteration
                    # and again at the start of this one. Keep both setter
                    # cascades; EPRI and lagged MRM caches can observe them.
                    old.copy_flow_properties(m)
                point_ok, changes = self._advance(old, m)
                self._record("initialization", m, point_ok, changes, progress)
                if np.all(changes < [o.SSCONVW, o.SSCONVP, o.SSCONVH, o.SSCONVW, o.SSCONVH]):
                    if not point_ok:
                        warnings.warn("Temporal convergence reached but point convergence failed (upstream behavior)", RuntimeWarning)
                    self.STATE = SolverState.INITIALSTEPCONVERGED
                    self.point_converged = point_ok
                    break
            else:
                self.STATE = SolverState.INITIALSTEPNOTCONVERGED
            self.mixtureInit[-1].copy_flow_properties(self.mixture[0])
            self.transient_converged = self.NTIME == 1
            if self.STATE == SolverState.INITIALSTEPCONVERGED and self.NTIME > 1:
                self.transient_converged = True
                for k in range(1, self.NTIME):
                    point_ok, changes = self._advance(self.mixture[k-1], self.mixture[k])
                    self._record("transient", self.mixture[k], point_ok, changes, progress)
                    self.transient_converged &= point_ok
                    if not point_ok:
                        self.STATE = SolverState.SOLVEDNOTCONVERGED
            # Upstream retains INITIALSTEPCONVERGED after successful transients.
            return self
        finally:
            self.elapsed_seconds = time.perf_counter()-started

    def _advance(self, old, m):
        o, model, g, f = self.inputSet.options, self.inputSet.model, self.inputSet.geometry, m.fluid
        old.copy_flow_properties(m)
        dz, dt = self.DZ, m.DT
        point_ok = True
        for j in range(1, self.NZ):
            wold, uold, upold = old.W[j], old.U(j), old.UP(j)
            mctold, hold, ectold = old.MCT(j), old.H[j], old.ECT(j)
            uvold, wvold, hvold = old.vapor.U(j), old.MRM["WV"][j].copy(), old.MRM["HV"][j].copy()
            dwv = dhv = np.zeros(g.NWALL())
            for iteration in range(1, int(o.MAXITER)+1):
                wi, pi, hi = m.W[j], m.P[j], m.H[j]
                u = m.U(j)
                wnew = (m.W[j-1]+wold/uold*dz/dt)/(1+dz/u/dt)
                m.W[j] = (1-o.RELAXWM)*wi+o.RELAXWM*wnew
                pnew = m.P[j-1]+m.DPTOT(upold, mctold, j)
                m.P[j] = (1-o.RELAXPM)*pi+o.RELAXPM*pnew
                dect = -(m.ECT(j)-ectold)/dt
                hnew = (m.H[j-1]+dz/m.W[j]*(dect+np.sum(m.LHGR(j)))+hold/u*dz/dt)/(1+dz/u/dt)
                m.H[j] = (1-o.RELAXHM)*hi+o.RELAXHM*hnew
                m.update(j if m.H[j] != hi else None)
                if model.THERMALNONEQ == "MRM":
                    wvi, hvi = m.MRM["WV"][j].copy(), m.MRM["HV"][j].copy()
                    uv, wveq, tr = m.vapor.U(j), m.WWALL(j)*m.XEQ(j), m.RELAXT(j)
                    if o.MRMTIMEINT == "EULER":
                        wvnew = uv*(m.MRM["WV"][j-1]+(wvold/uvold/dt+m.MTOT(j))*dz)/(uv+dz/dt)
                        hvnew = (uv*m.MRM["HV"][j-1]+(hvold/dt+m.HVTOT(j)*uv)*dz)/(uv+dz/dt)
                    elif o.MRMTIMEINT == "EXPONENTIAL":
                        a = uv/dz+1/tr
                        b = m.MRM["WV"][j-1]/dz+m.MWALEVAP(j)+wveq/uv/tr
                        wvnew = uv*(wvold/uvold*np.exp(-a*dt)-b/a*np.expm1(-a*dt))
                        wv = m.MRM["WV"][j]
                        with np.errstate(divide="ignore", invalid="ignore"):
                            hvwall = (m.HWALEVAP(j)+m.HWALHEAT(j))/wv
                            d = np.fmax(0, wveq-wv)/wv
                        hvwall = np.where(wv <= 1e-8, 0, hvwall)
                        d = np.where(wv <= 1e-8, 0, d)
                        hl = m.liquid.H(j) if model.INTTRANSH == "BULK" else f.HF
                        a = uv/dz+d/tr
                        b = uv*m.MRM["HV"][j-1]/dz+d/tr*hl+uv*hvwall
                        hvnew = hvold*np.exp(-a*dt)-b/a*np.expm1(-a*dt)
                    else:
                        raise NotImplementedError(f"MRMTIMEINT={o.MRMTIMEINT}")
                    wvnew = np.fmin(m.WWALL(j), np.fmax(0, wvnew))
                    m.MRM["WV"][j] = (1-o.RELAXWV)*wvi+o.RELAXWV*wvnew
                    m.MRM["X"][j] = m.MRM["WV"][j]/m.WWALL(j)
                    hvnew = np.fmax(m.H[j], np.fmax(f.HG, hvnew))
                    m.MRM["HV"][j] = (1-o.RELAXHV)*hvi+o.RELAXHV*hvnew
                    dwv, dhv = abs(m.MRM["WV"][j]-wvi), abs(m.MRM["HV"][j]-hvi)
                dw, dp, dh = abs(m.W[j]-wi), abs(m.P[j]-pi), abs(m.H[j]-hi)
                if not np.all(np.isfinite([m.W[j], m.P[j], m.H[j], m.RHO(j)])) or m.W[j] <= 0 or m.P[j] <= 0:
                    raise FloatingPointError(f"Nonphysical/nonfinite state at t={m.TIME:g} s, z={m.Z[j]:g} m")
                if dw < o.ERRORW and dp < o.ERRORP and dh < o.ERRORH and np.all(dwv < o.ERRORW) and np.all(dhv < o.ERRORH):
                    break
            else:
                point_ok = False
            m.MRM["TCOND"][j] = m.RELAXTCOND(j)
            m.MRM["TEVAP"][j] = m.RELAXTEVAP(j)
            m.MRM["TV"][j] = f.T(m.MRM["HV"][j])
            tr, heq = m.NEARWALLTRELAX(j), m.HNEARWALLEQ(j)
            rate = m.LHGR(j)/(m.RHO(j)*m.ANEARWALL())
            m.NEARWALL["TRELAX"][j] = tr
            m.NEARWALL["W"][j] = m.WNEARWALL(j)
            m.NEARWALL["H"][j] = (m.NEARWALL["H"][j-1]*u+old.NEARWALL["H"][j]*dz/dt+rate*dz+heq*dz/tr)/(u+dz/dt+dz/tr)
            if model.NEARWALLEQOAF and j == m.OAFIDX():
                m.NEARWALL["H"][j] = m.HNEARWALLEQ(j, True)
            m.NEARWALL["HFLUX"][j] = -(heq-m.NEARWALL["H"][j])*m.WNEARWALL(j)/u/tr/g.PERIM
            m.NEARWALL["XEQ"][j] = (m.NEARWALL["H"][j]-f.HF)/f.HFG
            m.NEARWALL["WBULK"][j] = m.W[j]-np.sum(m.NEARWALL["W"][j])
            m.NEARWALL["HBULK"][j] = (m.W[j]*m.H[j]-np.sum(m.NEARWALL["W"][j]*m.NEARWALL["H"][j]))/m.NEARWALL["WBULK"][j]
            m.NEARWALL["XBULK"][j] = (m.NEARWALL["HBULK"][j]-f.HF)/f.HFG
            parts = m.DPPARTS(upold, mctold, j)
            for name, source in DP_KEYS.items():
                m.DP[name][j] = -parts[source]
            m.MDER["U_z"][j] = m.U(j)*(m.UP(j)-m.UP(j-1))/dz
            m.MDER["U_t"][j] = (m.UP(j)-upold)/dt
            m.MDER["U"][j] = m.MDER["U_z"][j]+m.MDER["U_t"][j]
            m.MDER["H_z"][j] = m.U(j)*(m.H[j]-m.H[j-1])/dz
            m.MDER["H_t"][j] = (m.H[j]-hold)/dt
            m.MDER["H"][j] = m.MDER["H_z"][j]+m.MDER["H_t"][j]
            for key, value in zip(("N", "DW", "DP", "DH", "DWV", "DHV"), (iteration, dw, dp, dh, dwv, dhv)):
                m.ITR[key][j] = value
        m.DPSUM = {k: np.cumsum(v) for k, v in m.DP.items()}
        changes = np.array([np.max(abs(m.W-old.W)), np.max(abs(m.P-old.P)), np.max(abs(m.H-old.H)),
                            np.max(abs(m.MRM["WV"]-old.MRM["WV"])), np.max(abs(m.MRM["HV"]-old.MRM["HV"]))])
        return point_ok, changes

    def _record(self, phase, m, point_ok, changes, progress):
        record = dict(phase=phase, time_s=m.TIME, point_converged=bool(point_ok),
                      max_iterations=int(np.max(m.ITR["N"])),
                      time_dW_kg_s=float(changes[0]), time_dP_Pa=float(changes[1]), time_dH_J_kg=float(changes[2]),
                      time_dWV_kg_s=float(changes[3]), time_dHV_J_kg=float(changes[4]),
                      point_dW_kg_s=float(np.max(m.ITR["DW"])), point_dP_Pa=float(np.max(m.ITR["DP"])),
                      point_dH_J_kg=float(np.max(m.ITR["DH"])))
        self.history.append(record)
        if progress is not None:
            progress(record)

    def save(self, directory):
        """Write portable NPZ/CSV/JSON, original inputs, and plots to a new directory."""
        from .output import save_result
        return save_result(self, directory)

    def plotz(self, filename=None, time_index=-1):
        """Create the representative upstream axial plots using Matplotlib."""
        from .output import plot_axial
        return plot_axial(self, filename, time_index)
