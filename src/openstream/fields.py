"""Native translation of OpenSTREAM's mixture and phase field equations.

Source: upstream/+Solvers/+Mixture/{Mixture,Liquid,Vapor}.m, a614c717.
SI units throughout. Axial indices are zero based; wall arrays have shape
``(NZ, NWALL)``. Call ``update(indices)`` after changing enthalpy to reproduce
the MATLAB enthalpy setter's cached-property cascade. No property is evaluated
at the solved axial pressure: upstream uses one system pressure per time step.

Copyright (c) 2024 OpenSTREAM contributors. MIT license; see LICENSE.
"""
from __future__ import annotations

from copy import deepcopy
import warnings
import numpy as np


def _col(a):
    return np.asarray(a)[..., None]


def _idx(i):
    return slice(None) if i is None else i


def _geom(geometry, name):
    value = getattr(geometry, name)
    return value() if callable(value) else value


class Mixture:
    """Mixture state with the upstream cached and derived field interface."""

    def __init__(self, input_set, fluid, z, time=0.0, dt=1.0):
        self.inputSet = input_set
        self.fluid = fluid
        self.Z = np.array(z, dtype=float, copy=True)
        self.NZ = len(self.Z)
        self.DZ = float(self.Z[1] - self.Z[0])
        self.TIME, self.DT = float(time), float(dt)
        self.NWALL = int(_geom(input_set.geometry, "NWALL"))
        self.W = np.ones(self.NZ)
        self.P = np.full(self.NZ, fluid.PRESSURE)
        self.H = np.full(self.NZ, fluid.HF)
        self.HFLUX = np.zeros((self.NZ, self.NWALL))
        self.xeq = np.zeros(self.NZ)
        self.x = np.zeros(self.NZ)
        self.vf = np.zeros(self.NZ)
        self.rho = np.full(self.NZ, fluid.RHOF)
        self.up = np.zeros(self.NZ)
        self.cbt = np.zeros((self.NZ, self.NWALL), dtype=bool)
        self.mfbt = np.zeros_like(self.cbt)
        self.chf = np.full_like(self.HFLUX, np.nan)
        self.relaxtcond = np.ones_like(self.HFLUX)
        self.relaxtevap = np.ones_like(self.HFLUX)
        self.nearwalltrelax = np.ones(self.NZ)
        self.MRM = {key: np.zeros_like(self.HFLUX) for key in
                    ("WV", "X", "HV", "TV", "TCOND", "TEVAP")}
        self.MRM["HV"][:] = fluid.HG
        self.NEARWALL = {key: np.zeros_like(self.HFLUX) for key in
                         ("H", "XEQ", "HBULK", "XBULK", "TRELAX")}
        self.NEARWALL["H"][:] = fluid.HF
        self.DP, self.DPSUM, self.MDER = {}, {}, {}
        self.ITR = np.zeros(self.NZ, dtype=int)
        self.oafidx_const = None
        self.sigm_const = None
        self._first_update = True
        self.liquid, self.vapor = Liquid(self), Vapor(self)
        self.validate_options()

    def validate_options(self):
        if self.inputSet.model.NEARWALLRATIO in (0,1):
            raise NotImplementedError("NEARWALLRATIO endpoints 0 and 1 make upstream near-wall diagnostics singular; require 0 < NEARWALLRATIO < 1")
        supported = {
            "THERMALNONEQ": {"EQUILIBRIUM", "SAHAZUBER", "EPRI", "MRM"},
            "VOID": {"HOMOGENEOUS", "SLIP", "BESTION", "EPRI"},
            "SPMTM": {"BLASIUS"},
            "TPFM": {"HOMOGENEOUS", "SLIP", "EPRI"},
            "TPKM": {"HOMOGENEOUS", "SLIP", "ROMIE"},
            "BTMTM": {"TPFM", "VAPOR"},
            "CBT": {"NONE", "ELEVATION", "BIASI", "BEZRUKOV"},
            "MFBT": {"NONE", "CONSTANT"},
            "SPHTM": {"DITTUSBOELTER", "GNIELINSKI", "SIEDERTATE"},
            "TPHTM": {"THOM"},
            "BTHTM": {"VAPOR", "DOUGALL", "BISHOP", "MOECK", "DELORME", "CONDIEIV"},
            "THERMALRELAX": {"TIMEX", "FOURIERX", "VOID", "HOMOGENEOUS", "FOURIER"},
            "NEARWALLH": {"RATIO", "FILM"},
            "NEARWALLRELAX": {"QUALITY", "VOID", "FILM"},
            "OAF": {"WALLIS", "WALLIS_SIMP", "LEVITAN"},
            "INTTRANSH": {"BULK", "SATURATED"},
        }
        for name, values in supported.items():
            value = getattr(self.inputSet.model, name)
            if value not in values:
                raise NotImplementedError(f"Mixture field option {name}={value!r} is not ported")
        if self.NWALL>1 and self.inputSet.model.BTHTM=="DELORME":
            raise NotImplementedError("BTHTM=DELORME with multiple walls requires review of upstream linear HFLUX indexing")

    def update(self, i=None):
        """Run the MATLAB H-setter cascade at the selected zero-based nodes."""
        j = np.arange(self.NZ) if i is None else np.atleast_1d(i)
        m, f, g = self.inputSet.model, self.fluid, self.inputSet.geometry
        self.xeq[j] = (self.H[j] - f.HF) / f.HFG
        first_update = self._first_update
        self._first_update = False
        if first_update:
            # Upstream X_CALC's first-call shortcut (old cache length <= 1).
            self.x[j] = np.fmax(self.xeq[j],0)
        elif m.THERMALNONEQ == "MRM":
            self.x[j] = self.MRM["WV"][j].sum(axis=-1) / self.W[j]
        elif m.THERMALNONEQ == "EPRI":
            self._quality_epri(j)
        else:
            self.x[j] = np.fmax(self.xeq[j], 0)
            if m.THERMALNONEQ == "SAHAZUBER":
                pe = self.MFLUX(j) * _geom(g, "HDIAM") * f.CPF / f.KF
                q = np.sum(np.asarray(g.PERIM) * self.HFLUX[j], axis=-1) / np.sum(g.PERIM)
                bo = q / self.MFLUX(j) / f.HFG
                xb = np.fmax(-0.0022 * np.fmin(7e4, pe) * bo, np.fmin(self.xeq[0], -1e-6))
                use = self.xeq[j] > xb
                # At zero heat flux upstream evaluates exp(+/-Inf) only at
                # selected nodes. Preserve the limiting saturated value.
                with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
                    c = xb[use] * np.exp(self.xeq[j[use]] / xb[use] - 1)
                c = np.where(xb[use] == 0, 0, c)
                self.x[j[use]] = (self.xeq[j[use]] - c) / (1 - c)
        if not first_update:
            self.x[j] = np.fmin(self.x[j], 1)
        rl, rv = f.RHOL(self.liquid.H(j)), f.RHOV(self.vapor.H(j))
        x = self.x[j]
        hom = x * rl / (x * rl + (1 - x) * rv)
        if m.VOID in ("HOMOGENEOUS", "SLIP"):
            slip = 1 if m.VOID == "HOMOGENEOUS" else m.SLIP
            self.vf[j] = x * rl / (x * rl + slip * (1 - x) * rv)
        elif m.VOID == "BESTION":
            drift = 0.188 * np.sqrt(m.G * _geom(g, "HDIAM") * (rl - rv) / rv)
            self.vf[j] = self.JG(j) / (self.JG(j) + self.JL(j) + drift)
        else:
            c1 = 4 / (f.PRESSURE / f.PCRIT - (f.PRESSURE / f.PCRIT) ** 2)
            k1 = np.fmin(0.8, 1 / (1 + np.exp(-self.liquid.RE(0) / 1e5)))
            r = (1 + 1.57 * rv / rl) / (1 - k1)
            k0 = k1 + (1 - k1) * (rv / rl) ** 0.25
            vf = hom
            for _ in range(100):
                ll = (1 - np.exp(-c1 * vf)) / (1 - np.exp(-c1))
                c0 = ll / (k0 + (1 - k0) * vf ** r)
                ugj = 1.41 * ((rl-rv) * f.SIGMA * m.G / rl**2)**0.25 * np.sqrt((1-vf)/(1+vf)) * np.cos(np.deg2rad(g.ANGLE))
                new = self.JG(j) / (c0 * (self.JG(j) + self.JL(j)) + ugj)
                err = np.nanmax(np.abs(new-vf))
                self.vf[j] = new
                if err < 0.001:
                    break
                vf = new
            if err > 0.001:
                warnings.warn(f"EPRI void model did not converge: error={err:g}", RuntimeWarning)
        self.rho[j] = self.vf[j] * rv + (1-self.vf[j]) * rl
        self.up[j] = self.x[j] * self.vapor.U(j) + (1-self.x[j]) * self.liquid.U(j)
        self._update_cbt(j)
        if m.MFBT == "CONSTANT":
            self.mfbt[j] = self.TWALL(j) > f.TSAT + m.DTMFB
        else:
            self.mfbt[j] = False
        self.relaxtcond[j] = self._relaxation(j, False)
        self.relaxtevap[j] = self._relaxation(j, True)
        self.nearwalltrelax[j] = self._nearwall_time(j)

    def _quality_epri(self,j):
        """X_CALC EPRI: retain old quality while constructing departure data."""
        f = self.fluid
        hliq = self.liquid.H()
        cpl,kl,pr = f.CPL(hliq),f.KL(hliq),f.PRANDTLL(hliq)
        rel = self.liquid.RE()
        qwd = self.HFLUX.copy()
        hdb = self.liquid.HWALL(self.TWALL())
        conversion = 0.29307107/0.3048**2/(5/9)
        hb = 193*np.exp(-self.P/4.344e6)*conversion
        hhn = 0.2*rel**0.662*pr*kl/_geom(self.inputSet.geometry,"HDIAM")
        qwd *= 3.41*0.3048**2
        hdb /= conversion
        hb, hhn = _col(hb/conversion), _col(hhn/conversion)
        aa = 4*hb*(hdb+hhn)**2
        bb = 2*hdb**2*(hhn+0.5*hdb)+8*qwd*hb*(hhn+hdb)
        cc = 4*hb*qwd**2+qwd*hdb**2
        z = (bb-np.sqrt(bb**2-4*aa*cc))/(2*aa)*(5/9)
        xd = -_col(cpl)*z/f.HFG
        # MATLAB find(...,1) uses column-major linear indexing.
        ids = np.flatnonzero(np.ravel(_col(self.XEQ())-xd,order="F")>0)
        if not len(ids):
            self.x[j] = np.fmax(self.xeq[j],0)
        else:
            departure = np.ravel(xd,order="F")[ids[0]]
            with np.errstate(divide="ignore",invalid="ignore"):
                xdmod = departure*(1-np.tanh(1-self.xeq[j]/departure))
            self.x[j] = np.fmax((self.xeq[j]-xdmod)/(1-xdmod),0)

    def copy_flow_properties(self, other, all=False):
        """Copy into ``other`` without aliasing; preserve its first axial node.

        MATLAB linear indexing preserves only element (1,1) of wall arrays;
        reproduce that column-major behavior, rather than preserving a row.
        """
        if not np.array_equal(self.Z, other.Z):
            raise ValueError("Source and target meshes differ")
        names = ("MRM", "W", "P", "H", "DP", "DPSUM", "MDER", "ITR", "NEARWALL", "cbt", "mfbt")
        for name in names:
            source, target = getattr(self, name), getattr(other, name)
            old_h = other.H.copy() if name == "H" else None
            if isinstance(source, dict):
                for key, value in source.items():
                    if key not in target or all:
                        target[key] = np.array(value, copy=True)
                    else:
                        a, b = np.ravel(value, order="F"), np.ravel(target[key], order="F").copy()
                        b[1:] = a[1:]
                        target[key] = b.reshape(np.shape(value), order="F")
            elif all:
                setattr(other, name, np.array(source, copy=True))
            else:
                a, b = np.ravel(source, order="F"), np.ravel(target, order="F").copy()
                b[1:] = a[1:]
                setattr(other, name, b.reshape(np.shape(source), order="F"))
            # MATLAB setter executes at this point in the copy order.
            if name == "H":
                changed = np.flatnonzero(old_h != other.H)
                other.update(changed if len(changed) else None)

    def MFLUX(self, i=None): return self.W[_idx(i)] / self.inputSet.geometry.AREA
    def XEQ(self, i=None): return self.xeq[_idx(i)]
    def X(self, i=None): return self.x[_idx(i)]
    def VF(self, i=None): return self.vf[_idx(i)]
    def RHO(self, i=None): return self.rho[_idx(i)]
    def UP(self, i=None): return self.up[_idx(i)]
    def U(self, i=None): return self.MFLUX(i) / self.RHO(i)
    def T(self, i=None): return self.fluid.T(self.H[_idx(i)])
    def LHGR(self, i=None): return self.HFLUX[_idx(i)] * np.asarray(self.inputSet.geometry.PERIM)
    def WWALL(self, i=None): return _col(self.W[_idx(i)]) * _geom(self.inputSet.geometry, "RWALL")
    def MCT(self, i=None): return (self.U(i)-self.UP(i)) * self.W[_idx(i)] / self.U(i)
    def HM(self, i=None): return self.vapor.C(i)*self.vapor.H(i) + (1-self.vapor.C(i))*self.liquid.H(i)
    def ECT(self, i=None): return (self.HM(i)-self.H[_idx(i)])*self.W[_idx(i)]/self.U(i)
    def JL(self, i=None): return (1-self.X(i))*self.MFLUX(i)/self.fluid.RHOL(self.liquid.H(i))
    def JG(self, i=None): return self.X(i)*self.MFLUX(i)/self.fluid.RHOV(self.vapor.H(i))
    def MU(self, i=None): return self.X(i)*self.fluid.MUV(self.vapor.H(i))+(1-self.X(i))*self.fluid.MUL(self.liquid.H(i))
    def RE(self, i=None): return 4*self.W[_idx(i)]/self.MU(i)/np.sum(self.inputSet.geometry.PERIM)
    def REL(self, i=None): return 4*self.W[_idx(i)]/self.fluid.MUL(self.liquid.H(i))/np.sum(self.inputSet.geometry.PERIM)
    def FW(self, i=None):
        c = self.inputSet.model.FRICTION
        return c[0]*self.RE(i)**c[1]+c[2]
    def FWL(self, i=None):
        c = self.inputSet.model.FRICTION
        return c[0]*self.REL(i)**c[1]+c[2]
    def PHI2F(self, i=None):
        m, f = self.inputSet.model, self.fluid
        rl, rv = f.RHOL(self.liquid.H(i)), f.RHOV(self.vapor.H(i))
        if m.TPFM == "HOMOGENEOUS": return (1+self.X(i)*(rl/rv-1))*self.FW(i)/self.FWL(i)
        if m.TPFM == "SLIP": return rl/self.RHO(i)*self.FW(i)/self.FWL(i)
        xcf = 1.02*self.X(i)**0.825*(self.MFLUX(i)*737.3381e-6)**-0.45
        if f.PRESSURE < 4.137e6: xcf = xcf/1.02*0.357*(1+10*f.PRESSURE/f.PCRIT)
        return 1+(rl/rv-1)*xcf
    def TAUW(self, i=None):
        tau = 0.5*(self.FWL(i)/4)/self.fluid.RHOL(self.liquid.H(i))*self.MFLUX(i)**2*self.PHI2F(i)
        tau = np.broadcast_to(_col(tau), np.shape(self.HFLUX[_idx(i)])).copy()
        if self.inputSet.model.BTMTM == "VAPOR":
            tau = np.where(self.CBT(i)|self.MFBT(i), self.vapor.TAUW(i), tau)
        return tau
    def KIDX(self, i=None):
        """Zero-based obstruction nodes, optionally filtered to selected nodes."""
        indices = np.argmin(abs(self.Z[:,None]-np.atleast_1d(self.inputSet.model.KLOC)), axis=0)
        selected = np.atleast_1d(np.arange(self.NZ)[_idx(i)])
        return indices[np.isin(indices, selected)]
    def KLOCZ(self, i=None):
        """Actual mesh locations [m] of the selected obstruction nodes."""
        return self.Z[self.KIDX(i)]
    def _local(self, name, default, i=None):
        out = np.full(self.NZ, default, dtype=float)
        values = np.broadcast_to(np.atleast_1d(getattr(self.inputSet.model, name)), self.KIDX().shape)
        # Duplicate indices use the last assignment, as in MATLAB.
        for j, value in zip(self.KIDX(), values): out[j] = value
        return out[_idx(i)]
    def KLOSS(self, i=None): return self._local("KLOSS", 0, i)
    def KTRELAX(self, i=None): return self._local("KTRELAX", np.nan, i)
    def KDIST(self, i=None):
        dz = self.Z[_idx(i)][...,None]-np.r_[0,np.atleast_1d(self.inputSet.model.KLOC)]
        return np.min(np.where(dz>=0, dz, np.inf), axis=-1)
    def PHI2K(self, i=None):
        f = self.fluid
        rl, rv = f.RHOL(self.liquid.H(i)), f.RHOV(self.vapor.H(i))
        kind = self.inputSet.model.TPKM
        if kind == "HOMOGENEOUS": return 1+self.X(i)*(rl/rv-1)
        if kind == "SLIP": return rl/self.RHO(i)
        return self.X(i)**2/np.fmax(1e-6,self.VF(i))*rl/rv+(1-self.X(i))**2/np.fmax(1e-6,1-self.VF(i))
    def DPGRAV(self, i=None):
        return -self.inputSet.model.G*np.cos(np.deg2rad(self.inputSet.geometry.ANGLE))*self.RHO(i)*self.DZ
    def DPWALL(self, i=None): return -np.sum(np.asarray(self.inputSet.geometry.PERIM)*self.TAUW(i), axis=-1)/self.inputSet.geometry.AREA*self.DZ
    def DPACCZ(self, i=None):
        j = np.arange(self.NZ) if i is None else np.asarray(i)
        return -self.MFLUX(i)*(self.UP(i)-self.UP(np.fmax(0,j-1)))
    def DPACCT(self, UPold, i=None): return -self.RHO(i)*(self.UP(i)-UPold)*self.DZ/self.DT
    def DPACCS(self, MCTold, i=None): return -(self.MCT(i)-MCTold)/self.inputSet.geometry.AREA*self.DZ/self.DT
    def DPK(self, i=None): return -0.5*self.KLOSS(i)/self.fluid.RHOL(self.liquid.H(i))*self.MFLUX(i)**2*self.PHI2K(i)
    def DPPARTS(self, UPold, MCTold, i=None):
        out = {"GRAV":self.DPGRAV(i),"WALL":self.DPWALL(i),"ACCZ":self.DPACCZ(i),"ACCT":self.DPACCT(UPold,i),"ACCS":self.DPACCS(MCTold,i),"K":self.DPK(i)}
        out["TOT"] = sum(out.values())
        return out
    def DPTOT(self, UPold, MCTold, i=None): return self.DPPARTS(UPold,MCTold,i)["TOT"]
    def CBT(self, i=None): return self.cbt[_idx(i)]
    def MFBT(self, i=None): return self.mfbt[_idx(i)]
    def CHF(self, i=None): return self.chf[_idx(i)]

    def _update_cbt(self, j):
        m, g = self.inputSet.model, self.inputSet.geometry
        p, massflux, x, d = self.P[-1], self.MFLUX(j), self.XEQ(j), _geom(g,"HDIAM")
        chf = np.full(len(j), np.nan)
        if m.CBT == "BIASI":
            p, massflux, d = p/1.01235e5, massflux/10, d*100
            n = 0.6-0.2*(d>=1)
            hp = -1.159+0.149*p*np.exp(-0.019*p)+8.99*p/(10+p*p)
            yp = 0.7249+0.099*p*np.exp(-0.032*p)
            chf = np.fmax(3.780e3/d**n/massflux**0.6*hp*(1-x),1.883e3/d**n/massflux**(1/6)*(yp/massflux**(1/6)-x))*1e4
        elif m.CBT == "BEZRUKOV":
            p /= 1e6
            chf = 0.795*(1-x)**(-0.5+0.105*p)*massflux**(-0.127+0.311*(1-x))*(1-0.0185*p)*1e6
        multiplier = m.CBTMULT(self.Z[j]) if callable(m.CBTMULT) else m.CBTMULT
        chf = chf*multiplier
        if np.max(m.KLOC)>0:
            z0 = np.where(self.Z[j]<np.atleast_1d(m.KLOC)[0],1e6,self.KDIST(j))
            c = np.broadcast_to(np.atleast_1d(m.CBTKEFFECT), (2,))
            chf *= 1+c[0]*np.exp(c[1]*z0/_geom(g,"HDIAM"))
        self.chf[j] = _col(chf)
        self.cbt[j] = _col(self.Z[j]>=m.CBTELEVATION) if m.CBT=="ELEVATION" else self.HFLUX[j]>self.chf[j]

    def HWALLBOIL(self, i=None):
        q = self.HFLUX[_idx(i)]+1e-6
        return np.fmax(0,q/(_col(self.fluid.TSAT-self.liquid.T(i))+22.5*(q/1e6)**0.5*np.exp(-_col(self.P[_idx(i)])/1e6/8.7)))

    def HWALLPOSTCBT(self, twall, i=None):
        f, m, g = self.fluid, self.inputSet.model, self.inputSet.geometry
        d = _geom(g,"HDIAM")
        xe = np.fmin(1,np.fmax(0,self.XEQ(i)))
        tbv = np.broadcast_to(_col(np.fmax(f.TSAT,self.T(i))),np.shape(twall))
        if m.BTHTM == "VAPOR":
            return self.vapor.HWALL(twall,i), np.broadcast_to(_col(self.vapor.T(i)),np.shape(twall))
        reg = self.MFLUX(i)*d/f.MUG
        if m.BTHTM == "DOUGALL":
            nu = 0.023*(reg*(xe+(1-xe)*f.RHOG/f.RHOF))**0.8*f.PRANDTLG**0.4
            hw = np.broadcast_to(_col(nu*f.KG/d),np.shape(twall))
        elif m.BTHTM == "BISHOP":
            hf = f.H(np.fmax(f.TSAT+10,(f.TSAT+twall)/2))
            nu = 0.0193*(_col(self.MFLUX(i))*d/f.MUV(hf))**0.8*f.PRANDTLV(hf)**1.23*_col(xe+(1-xe)*f.RHOG/f.RHOF)**0.68*(f.RHOG/f.RHOF)**0.068
            hw = nu*f.KV(hf)/d
        elif m.BTHTM == "DELORME":
            # Exact one-wall upstream correlation. Its source uses linear
            # HFLUX indexing, so multi-wall input is explicitly unavailable.
            vh = xe*f.RHOF/(xe*f.RHOF+(1-xe)*f.RHOG)
            with np.errstate(divide="ignore",invalid="ignore"):
                reh = reg*xe/vh
                xeq = np.fmax(0,self.XEQ(i))
                phi = 0.13864*f.PRANDTLG**0.2031*reh**0.20006*(self.HFLUX[_idx(i),0]*d*f.CPG/f.KG/f.HFG)**-0.09232*(1.3072-1.0833*xeq+0.8455*xeq**2)
                phi = np.fmin(np.pi/2,np.fmax(0,phi))
                hva = np.fmax(f.HG,self.H[_idx(i)])+f.HFG*np.exp(-np.tan(phi))*np.exp(-(3*vh)**-4)
            xa = f.HFG*xeq/(hva-f.HF)
            tva = f.T(hva)
            hf = f.H(np.fmax(f.TSAT+10,(_col(tva)+twall)/2))
            rv = f.RHOV(hva)
            rev = _col(self.MFLUX(i))*d/f.MUV(hf)*_col(xa+rv/f.RHOF*(1-xa))
            nu = 0.008348*rev**0.8774*f.PRANDTLV(hf)**0.6112
            hw = nu*f.KV(hf)/d
            tbv = _col(tva)
        else:
            prw = f.PRANDTLV(f.H(np.fmax(f.TSAT+10,twall)))
            if m.BTHTM == "MOECK":
                c = m.MOECKCOEF
                y = 1-0.1*(f.RHOF/f.RHOG-1)**0.4*(1-xe)**0.4
                nu = c[0]*_col(reg*(xe+(f.RHOG/f.RHOF)*(1-xe)))**c[1]*prw**c[2]*_col(y)**c[3]
                hw = nu*f.KG/d
            elif m.BTHTM == "CONDIEIV":
                hw = 0.00128*(f.KG/1e3)**0.4593*prw**2.2598/d**0.8095/(1+_col(xe))**2.0514*_col(reg)**(0.6249+0.2043*np.log(_col(xe)+1))*1e3
            else:
                raise NotImplementedError(m.BTHTM)
        return hw,tbv

    def HWALL(self, twall, i=None):
        hw = np.fmax(self.liquid.HWALL(twall,i),self.HWALLBOIL(i))
        tbv = np.full(np.shape(hw),self.fluid.TSAT)
        mask = self.CBT(i)|self.MFBT(i)
        if np.any(mask):
            post,tpost = self.HWALLPOSTCBT(twall,i)
            hw,tbv = np.where(mask,post,hw),np.where(mask,tpost,tbv)
        return hw,tbv

    def TWALL(self, i=None, return_bulk=False):
        tbl = np.broadcast_to(_col(self.liquid.T(i)),np.shape(self.HFLUX[_idx(i)]))
        tw = tbl.copy()
        mask = self.CBT(i)|self.MFBT(i)
        for _ in range(20):
            old = tw
            hw,tbv = self.HWALL(tw,i)
            tb = np.where(mask,tbv,tbl)
            tw = tb+self.HFLUX[_idx(i)]/hw
            err = np.nanmax(abs(tw-old))
            if err<0.1: break
        if err>0.1: warnings.warn(f"Wall temperature did not converge: error={err:g} K",RuntimeWarning)
        return (tw,tb) if return_bulk else tw

    def _fourier(self, i, evaporation):
        m,f,g = self.inputSet.model,self.fluid,self.inputSet.geometry
        d = _geom(g,"HDIAM")
        kind = "EVAP" if evaporation else "COND"
        d0,n,bias,b = getattr(m,"RELAX"+kind+"COEF")
        xeq = self.XEQ(i)
        if m.THERMALRELAX in ("FOURIERX","TIMEX"):
            values = np.asarray(getattr(m,"RELAX"+kind+("FO" if m.THERMALRELAX=="FOURIERX" else "T")))[:len(m.RELAXX)]
            fo = np.interp(xeq,m.RELAXX,values)
            if m.THERMALRELAX=="TIMEX":
                alpha = f.ALPHAV(self.vapor.H(i)) if evaporation else f.ALPHAL(self.liquid.H(i))
                fo = fo*alpha/d**2
            return np.broadcast_to(_col(fo),np.shape(self.HFLUX[_idx(i)]))
        vf = self.liquid.VF(i) if evaporation else self.vapor.VF(i)
        if m.THERMALRELAX=="VOID":
            delta = _col(xeq)-self.MRM["X"][_idx(i)]
            return 1/(_col(vf)+bias)**n/abs(delta)**b*(d0/d)**2
        if m.THERMALRELAX=="HOMOGENEOUS":
            if evaporation:
                where = np.flatnonzero(np.any(self.cbt,axis=-1))
                vf0 = self.liquid.VF(where[0]) if len(where) else vf
                dd = d0*(vf/vf0)**n
                fo = (1-vf)/(vf+bias)/12*(dd/d)**2
            else:
                x = self.liquid.X(i)
                fo = f.RHOV(self.vapor.H(i))/f.RHOL(self.liquid.H(i))*x/np.fmax(1-x,bias)/12*(d0/d)**2
        else:
            c = getattr(m,"RELAX"+kind+"FOCOEF")
            re = self.vapor.RE(i) if evaporation else self.liquid.RE(i)
            fo = c[0]*(c[1]/re)**c[2]*(f.QK/f.QKMAX)**c[3]
            if evaporation: fo *= max(d/c[4],(d/c[4])**c[5])
            fo = np.fmax(2e-6,fo)
        return np.broadcast_to(_col(fo),np.shape(self.HFLUX[_idx(i)]))

    def FOURIERCOND(self, i=None): return self._fourier(i,False)
    def FOURIEREVAP(self, i=None): return self._fourier(i,True)
    def _relaxation(self, i, evaporation):
        f = self.fluid
        alpha = f.ALPHAV(self.vapor.H(i)) if evaporation else f.ALPHAL(self.liquid.H(i))
        t = _geom(self.inputSet.geometry,"HDIAM")**2/_col(alpha)*self._fourier(i,evaporation)
        override = _col(self.KTRELAX(i))
        return np.fmax(1e-6,np.where(override>0,override,t))
    def RELAXTCOND(self, i=None): return self.relaxtcond[_idx(i)]
    def RELAXTEVAP(self, i=None): return self.relaxtevap[_idx(i)]
    def RELAXT(self, i=None):
        w = self.WWALL(i)*_col(self.XEQ(i))-self.MRM["WV"][_idx(i)]
        return np.where(w<0,self.RELAXTCOND(i),self.RELAXTEVAP(i))
    def MINT(self, i=None):
        w = self.WWALL(i)*_col(self.XEQ(i))-self.MRM["WV"][_idx(i)]
        return np.fmin(0,w/_col(self.vapor.U(i))/self.RELAXTCOND(i)),np.fmax(0,w/_col(self.vapor.U(i))/self.RELAXTEVAP(i))
    def MINTCOND(self, i=None): return self.MINT(i)[0]
    def MINTEVAP(self, i=None): return self.MINT(i)[1]
    def MTRANSV(self, i=None):
        """Unused upstream transverse vapor exchange diagnostic [kg/(s m)].

        The original fixed 0.01 s relaxation and phase velocity are preserved.
        This diagnostic is intentionally not added to MTOT or solver updates.
        """
        vapor_mass = self.MRM["WV"][_idx(i)]
        equilibrium = np.sum(vapor_mass, axis=-1, keepdims=True)*self.WWALL(i)/_col(self.W[_idx(i)])
        return (equilibrium-vapor_mass)/_col(self.vapor.U(i))/0.01
    def WALEVAPRATIO(self, i=None):
        m = self.inputSet.model
        r = ((np.fmin(m.WBOILINGXSAT,np.fmax(m.WBOILINGXSUB,self.XEQ(i)))-m.WBOILINGXSUB)/(m.WBOILINGXSAT-m.WBOILINGXSUB))**m.WBOILINGN
        return _col(r)*(~(self.CBT(i)|self.MFBT(i)))
    def MWALEVAP(self, i=None):
        hv = self.MRM["HV"][_idx(i)] if self.inputSet.model.INTTRANSH=="BULK" else self.fluid.HG
        return self.WALEVAPRATIO(i)*self.LHGR(i)/(hv-_col(self.liquid.H(i)))
    def MTOT(self, i=None): return self.MINTCOND(i)+self.MINTEVAP(i)+self.MWALEVAP(i)
    def HINT(self, i=None):
        cond,evap = self.MINT(i)
        hv = self.MRM["HV"][_idx(i)]
        if self.inputSet.model.INTTRANSH=="BULK": return np.zeros_like(cond),evap*(_col(self.liquid.H(i))-hv)
        return cond*(self.fluid.HG-hv),evap*(self.fluid.HF-hv)
    def HINTCOND(self, i=None): return self.HINT(i)[0]
    def HINTEVAP(self, i=None): return self.HINT(i)[1]
    def HWALEVAP(self, i=None):
        if self.inputSet.model.INTTRANSH=="BULK": return np.zeros_like(self.HFLUX[_idx(i)])
        return self.MWALEVAP(i)*(self.fluid.HG-self.MRM["HV"][_idx(i)])
    def HWALHEAT(self, i=None): return (self.CBT(i)|self.MFBT(i))*self.LHGR(i)
    def HTOT(self, i=None): return self.HINTCOND(i)+self.HINTEVAP(i)+self.HWALEVAP(i)+self.HWALHEAT(i)
    def HVTOT(self, i=None):
        w = self.MRM["WV"][_idx(i)].sum(axis=-1)
        with np.errstate(divide="ignore",invalid="ignore"):
            out = self.HTOT(i).sum(axis=-1)/w
        return np.where(w<=1e-8,0,out)

    def NEARWALLRATIO(self): return self.inputSet.model.NEARWALLRATIO
    def WNEARWALL(self, i=None): return self.WWALL(i)*self.NEARWALLRATIO()
    def ANEARWALL(self): return self.NEARWALLRATIO()*_geom(self.inputSet.geometry,"RWALL")*self.inputSet.geometry.AREA
    def _nearwall_time(self, i):
        m,f = self.inputSet.model,self.fluid
        if m.NEARWALLRELAX=="QUALITY":
            t = np.interp(self.XEQ(i),m.NEARWALLRELAXX,np.asarray(m.NEARWALLRELAXT)[:len(m.NEARWALLRELAXX)])
        elif m.NEARWALLRELAX=="VOID":
            d,n,bias = m.NEARWALLRELAXCOEF
            t = d*d/f.ALPHAL(self.liquid.H(i))/(self.vapor.VF(i)+bias)**n
        else:
            rv,rl = f.RHOV(self.vapor.H(i)),f.RHOL(self.liquid.H(i))
            t = 0.0541*(1-0.88*self.XEQ(i))*np.fmin(1,1+0.16*(1-self.MFLUX(i)/2000))*(1+386*(rv/rl)**2)
            t = np.where(self.XEQ(i)<=self.OAFX(i),0.13,t)
        return np.fmax(1e-6,np.where(self.KTRELAX(i)>0,self.KTRELAX(i),t))
    def NEARWALLTRELAX(self, i=None): return self.nearwalltrelax[_idx(i)]
    def HNEARWALLEQ(self, i=None, skipAdjustments=False):
        m = self.inputSet.model
        h = self.H[_idx(i)]
        ratio = m.NEARWALLHRATIO if m.NEARWALLH=="RATIO" else np.fmax(1,(self.MFLUX(i)/900)**0.35)
        out = ratio*h
        if not skipAdjustments:
            j = np.arange(self.NZ) if i is None else np.asarray(i)
            out = np.where(np.isin(j,self.KIDX()),h,out)
            out = self.AFDISTR(h,out,i)
        return out
    def OAFX(self, i=None):
        m,f,g = self.inputSet.model,self.fluid,self.inputSet.geometry
        d,gg = _geom(g,"HDIAM"),self.MFLUX(i)
        if m.OAF=="WALLIS": return (0.6+0.4*np.sqrt(m.G*d*(f.RHOF-f.RHOG)*f.RHOF)/gg)/(0.6+np.sqrt(f.RHOF/f.RHOG))
        if m.OAF=="WALLIS_SIMP": return np.sqrt(m.G*d*(f.RHOF-f.RHOG)*f.RHOG)/gg
        return 2.7*(f.RHOG*f.SIGMA/gg**2/d)**0.25*(f.RHOG/f.RHOF)**(1/3)
    def OAFIDX(self):
        if self.oafidx_const is None:
            ids = np.flatnonzero(self.XEQ()<=self.OAFX())
            self.oafidx_const = int(ids[-1]) if len(ids) else 0
        return self.oafidx_const
    def OAFZ(self): return self.Z[self.OAFIDX()]
    def OAFWL(self): return self.liquid.W(self.OAFIDX())
    def AFFNC(self, i=None):
        if self.sigm_const is None:
            m,g = self.inputSet.model,self.inputSet.geometry
            p = np.asarray(m.OAFTRANSITION)*(m.NNODES/g.LENGTH)
            # Upstream works in node indices (not metres); shifting both
            # node and centre from 1-based to 0-based preserves the argument.
            with np.errstate(over="ignore"):
                self.sigm_const = 1/(1+np.exp(-p[0]*(np.arange(self.NZ)-(self.OAFIDX()+p[1]))))
        return self.sigm_const[_idx(i)]
    def AFDISTR(self, param1, param2, i=None):
        a = self.AFFNC(i)
        if np.ndim(a)>0 and (np.ndim(param1)>1 or np.ndim(param2)>1):
            a = _col(a)
        return (1-a)*param1+a*param2


class Liquid:
    def __init__(self,mix): self.mix = mix
    def TIME(self): return self.mix.TIME
    def Z(self,i=None): return self.mix.Z[_idx(i)].copy()
    def X(self,i=None): return 1-self.mix.X(i)
    def VF(self,i=None): return 1-self.mix.VF(i)
    def H(self,i=None):
        mix = self.mix
        with np.errstate(divide="ignore",invalid="ignore"):
            h = (mix.H[_idx(i)]-mix.X(i)*mix.vapor.H(i))/(1-mix.X(i))
        h = np.fmin(h,mix.fluid.HF)
        return np.where(np.isnan(h)|(1-mix.X(i)<1e-2),mix.fluid.HF,h)
    def C(self,i=None): return self.VF(i)*self.mix.fluid.RHOL(self.H(i))/self.mix.RHO(i)
    def W(self,i=None): return self.X(i)*self.mix.W[_idx(i)]
    def Q(self,i=None): return self.W(i)/self.mix.fluid.RHOL(self.H(i))
    def MFLUX(self,i=None): return self.W(i)/self.mix.inputSet.geometry.AREA
    def U(self,i=None):
        with np.errstate(divide="ignore",invalid="ignore"):
            u = self.MFLUX(i)/self.VF(i)/self.mix.fluid.RHOL(self.H(i))
        return np.where(np.isnan(u)|(1-self.mix.X(i)<1e-2),self.mix.U(i),u)
    def T(self,i=None): return self.mix.fluid.T(self.H(i))
    def RE(self,i=None): return 4*self.W(i)/self.mix.fluid.MUL(self.H(i))/np.sum(self.mix.inputSet.geometry.PERIM)
    def NU(self,twall,i=None): return _nusselt(self,twall,i,False)
    def HWALL(self,twall,i=None): return self.NU(twall,i)*_col(self.mix.fluid.KL(self.H(i)))/_geom(self.mix.inputSet.geometry,"HDIAM")
    def HFLUX(self,i=None): return self.mix.HFLUX[_idx(i)]-self.mix.vapor.HFLUX(i)-self.mix.vapor.HFLUXWALEVAP(i)


class Vapor:
    def __init__(self,mix): self.mix = mix
    def TIME(self): return self.mix.TIME
    def Z(self,i=None): return self.mix.Z[_idx(i)].copy()
    def X(self,i=None): return self.mix.X(i)
    def VF(self,i=None): return self.mix.VF(i)
    def H(self,i=None):
        mix = self.mix
        with np.errstate(divide="ignore",invalid="ignore"):
            if mix.inputSet.model.THERMALNONEQ=="MRM":
                w = mix.MRM["WV"][_idx(i)]
                h = (mix.MRM["HV"][_idx(i)]*w).sum(axis=-1)/w.sum(axis=-1)
                # Source Vapor.H replaces only NaN in the MRM branch.
                # Preserve infinity as invalid state instead of hiding it as HG.
                invalid = np.isnan(h)
            else:
                x = np.fmin(mix.X(i),mix.XEQ(i))
                h = (mix.H[_idx(i)]-(1-x)*mix.fluid.HF)/x
                invalid = ~np.isfinite(h)
        return np.where(invalid,mix.fluid.HG,h)
    def C(self,i=None): return self.VF(i)*self.mix.fluid.RHOV(self.H(i))/self.mix.RHO(i)
    def W(self,i=None): return self.X(i)*self.mix.W[_idx(i)]
    def Q(self,i=None): return self.W(i)/self.mix.fluid.RHOV(self.H(i))
    def MFLUX(self,i=None): return self.W(i)/self.mix.inputSet.geometry.AREA
    def U(self,i=None):
        with np.errstate(divide="ignore",invalid="ignore"):
            u = self.MFLUX(i)/self.VF(i)/self.mix.fluid.RHOV(self.H(i))
        return np.where(np.isnan(u),self.mix.U(i),u)
    def T(self,i=None): return self.mix.fluid.T(self.H(i))
    def RE(self,i=None): return self.mix.fluid.RHOV(self.H(i))*self.U(i)*_geom(self.mix.inputSet.geometry,"HDIAM")/self.mix.fluid.MUV(self.H(i))
    def FW(self,i=None):
        c = self.mix.inputSet.model.FRICTION
        return c[0]*self.RE(i)**c[1]+c[2]
    def TAUW(self,i=None):
        tau = 0.5*self.FW(i)/4*self.mix.fluid.RHOV(self.H(i))*self.U(i)**2
        return np.broadcast_to(_col(tau),np.shape(self.mix.HFLUX[_idx(i)]))
    def NU(self,twall,i=None): return _nusselt(self,twall,i,True)
    def HWALL(self,twall,i=None): return self.NU(twall,i)*_col(self.mix.fluid.KV(self.H(i)))/_geom(self.mix.inputSet.geometry,"HDIAM")
    def HFLUXWALEVAP(self,i=None): return self.mix.WALEVAPRATIO(i)*self.mix.HFLUX[_idx(i)]
    def HFLUX(self,i=None): return self.mix.HWALHEAT(i)/np.asarray(self.mix.inputSet.geometry.PERIM)


def _nusselt(phase,twall,i,vapor):
    mix = phase.mix
    m,f = mix.inputSet.model,mix.fluid
    re = phase.RE(i)
    pr = f.PRANDTLV(phase.H(i)) if vapor else f.PRANDTLL(phase.H(i))
    if m.SPHTM=="DITTUSBOELTER": nu = 0.023*re**0.8*pr**0.4
    elif m.SPHTM=="GNIELINSKI":
        ff = phase.FW(i) if vapor else mix.FWL(i)
        nu = ff/8*(re-1000)*pr/(1+12.7*np.sqrt(ff/8)*(pr**(2/3)-1))
    elif m.SPHTM=="SIEDERTATE":
        nu = 0.027*re**0.8*pr**(1/3)
        tw = np.fmax(f.TSAT,twall)+1e-6 if vapor else np.fmin(f.TSAT,twall)-1e-6
        # FluidProperties.H uses the same native CoolProp P,T backend.
        hw = f.H(tw)
        mub = f.MUV(phase.H(i)) if vapor else f.MUL(phase.H(i))
        muw = f.MUV(hw) if vapor else f.MUL(hw)
        return _col(nu)*(_col(mub)/muw)**0.14
    else:
        raise NotImplementedError(f"SPHTM={m.SPHTM}")
    return np.broadcast_to(_col(nu),np.shape(mix.HFLUX[_idx(i)]))
