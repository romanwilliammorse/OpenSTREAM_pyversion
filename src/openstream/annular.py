"""Shared annular film/drop closures translated from AbstractFilm and ThreeField.

Film quantities have shape (node,wall), drop quantities (node,). SI units.
The source's signed mass fluxes, force definitions and fixed-point/secant
algorithms are retained, including their explicit convergence limitations.
"""
from __future__ import annotations
from copy import deepcopy
import warnings
import numpy as np
from .fields import _col, _idx


def blend(mix, a, b, i=None):
    r = mix.AFFNC(i)
    if np.ndim(a) > np.ndim(r) or np.ndim(b) > np.ndim(r):
        r = _col(r)
        if np.ndim(a) == np.ndim(r)-1: a = _col(a)
        if np.ndim(b) == np.ndim(r)-1: b = _col(b)
    return (1-r)*a+r*b


class AnnularField:
    def __init__(self, inputs, mix, wall=False):
        self.inputSet, self.mix, self.fluid = inputs, mix, mix.fluid
        self.NZ, self.DZ, self.Z = mix.NZ, mix.DZ, mix.Z.copy()
        self.TIME, self.DT = mix.TIME, mix.DT
        shape = (self.NZ, inputs.geometry.NWALL()) if wall else (self.NZ,)
        self.W, self.U, self.H = np.ones(shape), np.ones(shape), np.full(shape, self.fluid.HF)
        self.ITR = {"N": np.zeros(self.NZ), "DU": np.zeros(shape)}
        self.inner_failures = []

    def copy_flow_properties(self, target):
        if not np.array_equal(self.Z, target.Z): raise ValueError("Meshes differ")
        for key in ("W", "U", "H", "ITR"):
            src, dst = getattr(self, key), getattr(target, key)
            def partial(a, b):
                out = np.ravel(b, order="F").copy()
                out[1:] = np.ravel(a, order="F")[1:]
                return out.reshape(np.shape(b), order="F")
            if isinstance(src, dict):
                for k in src: dst[k] = partial(src[k], dst[k])
            else: setattr(target, key, partial(src, dst))

    def _secant(self, force, i, maxiter, tolerance, label):
        u0, f0 = self.U[_idx(i)].copy(), force()
        u1 = u0+.1
        self.U[_idx(i)] = u1
        f1 = force()
        error = np.inf
        for _ in range(2, int(maxiter)):
            with np.errstate(divide="ignore", invalid="ignore"):
                u2 = u0-f0*(u1-u0)/(f1-f0)
            self.U[_idx(i)] = u2
            f2 = force()
            error = float(np.fmax.reduce(np.ravel(abs(f2))))
            if error < tolerance: break
            u0, f0, u1, f1 = u1, f1, u2.copy(), f2
        if not np.isfinite(error) or error > tolerance or not np.all(np.isfinite(self.U[_idx(i)])):
            self.inner_failures.append({"model": label, "node": i, "residual": error})
            warnings.warn(f"{label} did not converge, residual {error:g}", RuntimeWarning)
        return blend(self.mix, self.mix.liquid.U(i), self.U[_idx(i)], i)


class Film(AnnularField):
    def __init__(self, inputs, mix):
        super().__init__(inputs, mix, wall=True)
        self.HFLUX = mix.HFLUX.copy()
        self.mevap = -self.HFLUX/self.fluid.HFG
        self.ITR["DWL"] = np.zeros_like(self.W)

    def WL(self, i=None): return self.W[_idx(i)]/self.inputSet.geometry.PERIM
    def THICK(self, i=None): return self.WL(i)/self.U[_idx(i)]/self.fluid.RHOF
    def RE(self, i=None): return abs(4*self.WL(i)/self.fluid.MUF)
    def MEVAP(self, i=None): return self.mevap[_idx(i)]
    def MTOT(self, drop, i=None): return self.MEVAP(i)+self.MENT(i)+_col(drop.MDEP(i))
    def _cw_lam(self, i=None): return np.fmax(16/np.fmax(self.RE(i), 1e-6), .005)
    def CW(self, i=None):
        value = self._cw_lam(i) if self.inputSet.model.THINFILMFRIC == "LAMINAR" else np.full_like(self.W[_idx(i)], .005)
        return blend(self.mix, .005, value, i)
    def _cv_thick(self, thick, c):
        return _col(c*(1+75/self.inputSet.geometry.AREA*np.sum(self.inputSet.geometry.PERIM*thick, axis=-1)))
    def CV(self, i=None):
        m = self.inputSet.model
        if m.VAPORFRIC == "CONSTANT": cv = np.full_like(self.W[_idx(i)], m.VAPORFRICCST)
        elif m.VAPORFRIC == "WALLIS": cv = np.broadcast_to(_col(m.VAPORFRICCST*(1+75*(1-self.mix.vapor.VF(i)))), self.W[_idx(i)].shape)
        elif m.VAPORFRIC == "WALLISTHICK": cv = self._cv_thick(abs(self.THICK(i)), m.VAPORFRICCST)
        else: raise NotImplementedError(f"VAPORFRIC={m.VAPORFRIC}")
        return blend(self.mix, 0, cv, i)
    def FWALL(self, i=None): return -.5*self.CW(i)*self.fluid.RHOF*self.U[_idx(i)]**2
    def UWALL(self, i=None): return np.sqrt(-self.FWALL(i)/self.fluid.RHOF)
    def YPLUS2THICK(self, yplus, i=None): return yplus/self.UWALL(i)*self.fluid.MUF/self.fluid.RHOF
    def FVAPOR(self, i=None): return .5*self.CV(i)*self.fluid.RHOG*(_col(self.mix.vapor.U(i))-self.U[_idx(i)])**2
    def FBUOY(self, i=None): return blend(self.mix, 0, abs(self.THICK(i))*_col(self.mix.DP["Tot"][_idx(i)])/self.DZ, i)
    def FGRAV(self, i=None):
        return blend(self.mix, 0, -abs(self.THICK(i))*self.inputSet.model.G*np.cos(np.deg2rad(self.inputSet.geometry.ANGLE))*self.fluid.RHOF, i)
    def FDEP(self, drop, i=None): return blend(self.mix, 0, (_col(drop.U[_idx(i)])-self.U[_idx(i)])*_col(drop.MDEP(i)), i)
    def FTOT(self, drop, i=None): return self.FWALL(i)+self.FVAPOR(i)+self.FBUOY(i)+self.FGRAV(i)+self.FDEP(drop, i)
    def UALGEBR(self, i=None): return blend(self.mix, self.mix.liquid.U(i), np.sqrt(2*self.mix.TAUW(i)/self.fluid.RHOF/self.CW(i)), i)
    def UEQUILS(self, i=None):
        o = self.inputSet.options
        return self._secant(lambda: self.FVAPOR(i)+self.FWALL(i), i, o.UFEQUILMAXITER, o.UFEQUILTOL, "Film.UEQUILS")
    def UEQUIL(self, drop, i=None):
        o = self.inputSet.options
        return self._secant(lambda: self.FTOT(drop, i), i, o.UFEQUILMAXITER, o.UFEQUILTOL, "Film.UEQUIL")
    def X(self, i=None): return 1-self.W[_idx(i)]/self.mix.NEARWALL["W"][_idx(i)]
    def ENTNUM(self, i=None):
        f, g, o = self.fluid, self.inputSet.geometry, self.inputSet.options
        wf = abs(self.W[_idx(i)])
        cw, slip = self._cw_lam(i), np.ones_like(wf)
        for _ in range(int(o.ENTNUMMAXITER)):
            delta = f.RHOG/f.RHOF*slip*wf/_col(np.fmax(1e-10, self.mix.vapor.W(i)))*g.AREA/g.PERIM
            cv = self._cv_thick(delta, .005)
            new = np.sqrt(cw/cv*f.RHOF/f.RHOG)
            error = float(np.fmax.reduce(np.ravel(abs(new/slip-1))))
            slip = new
            if error < o.ENTNUMTOL: break
        if not np.isfinite(error) or error > o.ENTNUMTOL or not np.all(np.isfinite(slip)):
            self.inner_failures.append({"model": "ENTNUM", "node": i, "residual": error})
            warnings.warn(f"Okawa entrainment number not converged: {error:g}", RuntimeWarning)
        return cv*f.RHOG*_col(self.mix.JG(i))**2*delta/f.SIGMA
    def OKAWAMENT(self, i, coefs):
        ent = self.ENTNUM(i)
        powers, breaks = np.asarray(coefs[3::2]), np.asarray(coefs[4::2])
        ke, exponent = np.full_like(ent, coefs[2]), np.full_like(ent, powers[0])
        prefactor = coefs[2]
        for k, threshold in enumerate(breaks):
            prefactor *= threshold**(powers[k]-powers[k+1])
            ke = np.where(ent >= threshold, prefactor, ke)
            exponent = np.where(ent >= threshold, powers[k+1], exponent)
        flux = ke*self.fluid.RHOF*ent**exponent*(self.fluid.RHOF/self.fluid.RHOG)**coefs[1]
        return np.fmin(1, np.fmax(0, (self.RE(i)-(coefs[0]-50))/100))*flux
    def MENT(self, i=None):
        m, f, g = self.inputSet.model, self.fluid, self.inputSet.geometry
        w = self.W[_idx(i)]
        if m.ENTRAINMENT == "NONE": flux = np.zeros_like(w)
        elif m.ENTRAINMENT == "GOVAN":
            critical = f.MUF*np.exp(5.8504+.4249*f.MUG/f.MUF*np.sqrt(f.RHOF/f.RHOG))*g.PERIM/4
            flux = 5.75e-5*((abs(w)/g.PERIM-critical/g.PERIM)**2*16/(f.RHOF*f.SIGMA*g.HDIAM()))**.316*(f.RHOF/f.RHOG)**.632*_col(self.mix.vapor.W(i))/g.AREA
            flux = np.where(abs(w) <= critical, 0, flux)
        else:
            c = {"OKAWA2003": [320, .111, 4.79e-4, 1],
                 "OKAWA2004": [320, 0, .0310, 2.3, .0675, 1.2, .2950, .5],
                 "OKAWA2004MOD": [320, 0, .0310, 2.3, .0675, 1.2],
                 "OKAWAGEN": m.OKAWACOEFS}
            if m.ENTRAINMENT not in c: raise NotImplementedError(f"ENTRAINMENT={m.ENTRAINMENT}")
            flux = self.OKAWAMENT(i, c[m.ENTRAINMENT])
        return -blend(self.mix, 0, np.where(w < 0, -flux, flux), i)


class Drop(AnnularField):
    def RE(self, i=None):
        raise NotImplementedError("Upstream Drop.RE calls undefined Drop.MU; REV is a different vapor-relative Reynolds number")
    def CONC(self, i=None):
        w = self.W[_idx(i)]
        return np.sign(w)*abs(w)/(abs(w)/self.fluid.RHOF+self.mix.vapor.W(i)/self.fluid.RHOG)
    def KENH(self, i=None):
        m = self.inputSet.model
        if m.DEPENHANCEMENT == "NONE": return np.ones_like(self.W[_idx(i)])
        if m.DEPENHANCEMENT != "WINDECKER": raise NotImplementedError(m.DEPENHANCEMENT)
        loc = np.atleast_1d(m.KLOC)
        if len(loc) == 0 or np.any(np.diff(loc) <= 0) or loc[0] <= 0 or loc[-1] >= self.Z[-1]:
            raise ValueError("WINDECKER requires strictly increasing interior KLOC")
        section = np.searchsorted(loc, self.Z[_idx(i)], side="right")
        blockage = np.r_[0, np.broadcast_to(m.KBLOCKRATIO, loc.shape)][section]
        tuning = np.r_[0, np.broadcast_to(m.KTUNING, loc.shape)][section]
        peak = .95*(4.791*blockage+1)*(7.898*blockage+1)
        z = self.mix.KDIST(i)
        enh = np.where(z <= .05, (peak-1)*z/.05+1,
                       np.where(z <= .15, peak, np.where(z <= .45, 1/((1-1/peak)*(z-.15)/.3+1/peak), 1)))
        return tuning*(enh-1)+1
    def MDEP(self, i=None, enhanced=True):
        f, g, m = self.fluid, self.inputSet.geometry, self.inputSet.model
        conc = abs(self.CONC(i))+1e-6
        if m.DEPOSITION == "NONE": flux = np.zeros_like(conc)
        elif m.DEPOSITION == "OKAWA": flux = .0632*(conc/f.RHOG)**-.5*np.sqrt(f.SIGMA/(f.RHOG*g.HDIAM()))*conc
        elif m.DEPOSITION == "GOVAN":
            # MATLAB if on a vector selects one branch for the entire call.
            flux = (.18*conc if np.all(conc/f.RHOG < .3) else .083*(conc/f.RHOG)**-.65*conc)/np.sqrt(f.RHOG*g.HDIAM()/f.SIGMA)
        else: raise NotImplementedError(m.DEPOSITION)
        flux = np.where(self.W[_idx(i)] < 0, -flux, flux)
        return blend(self.mix, 0, self.KENH(i)*flux if enhanced else flux, i)
    def VR(self, i=None): return self.mix.vapor.U(i)-self.U[_idx(i)]
    def DIAM(self, i=None): return np.full_like(self.W[_idx(i)], self.inputSet.model.DROPDIAM)
    def AREA(self, i=None): return np.pi*self.DIAM(i)**2
    def VOLUME(self, i=None): return np.pi/6*self.DIAM(i)**3
    def DENSITY(self, i=None): return self.W[_idx(i)]/self.U[_idx(i)]/self.VOLUME(i)/self.fluid.RHOF/self.inputSet.geometry.AREA
    def AI(self, i=None): return self.DENSITY(i)*self.AREA(i)
    def REV(self, i=None): return self.fluid.RHOV(self.H[_idx(i)])*abs(self.VR(i))*self.DIAM(i)/self.fluid.MUV(self.H[_idx(i)])
    def DRAG(self, i=None):
        m, re = self.inputSet.model, self.REV(i)
        re = np.where(re <= 1e-3, 1e-3, re)
        if m.DROPDRAG == "CONSTANT": cd = np.full_like(re, m.DROPDRAGCOEF)
        elif m.DROPDRAG == "STOKES": cd = 24/re
        elif m.DROPDRAG == "VISCOUS": cd = 24/re*(1+.15*re**.687)
        else: raise NotImplementedError("DROPDRAG=DISTORDED references undefined upstream liquid/vapor variables")
        return np.fmin(cd, 1)
    def FBUOY(self, i=None): return blend(self.mix, 0, self.mix.DP["Tot"][_idx(i)]/self.DZ, i)
    def FGRAV(self, i=None): return blend(self.mix, 0, -self.inputSet.model.G*np.cos(np.deg2rad(self.inputSet.geometry.ANGLE))*self.fluid.RHOF, i)
    def FDRAG(self, i=None): return blend(self.mix, 0, self.AREA(i)/self.VOLUME(i)*np.sign(self.VR(i))*.5*self.DRAG(i)*self.fluid.RHOG*abs(self.VR(i))**2, i)
    def FENT(self, film, i=None):
        force = np.sum(self.inputSet.geometry.PERIM*(film.U[_idx(i)]-_col(self.U[_idx(i)]))*(-film.MENT(i)), axis=-1)*self.fluid.RHOF*self.U[_idx(i)]/self.W[_idx(i)]
        return blend(self.mix, 0, force, i)
    def FTOT(self, film, i=None, opt=0):
        force = self.FDRAG(i)+self.FBUOY(i)+self.FGRAV(i)
        return force if opt == 1 else force+self.FENT(film, i)
    def USLIP(self, i=None): return blend(self.mix, self.mix.liquid.U(i), self.inputSet.model.DROPSLIP*self.mix.vapor.U(i), i)
    def UALGEBR(self, film, i=None):
        area = self.mix.liquid.VF(i)*self.inputSet.geometry.AREA-np.sum(self.inputSet.geometry.PERIM*film.THICK(i), axis=-1)
        return blend(self.mix, self.mix.liquid.U(i), self.W[_idx(i)]/self.fluid.RHOF/area, i)
    def UEQUIL(self, film, i=None, opt=0):
        o = self.inputSet.options
        return self._secant(lambda: self.FTOT(film, i, opt), i, o.UDEQUILMAXITER, o.UDEQUILTOL, "Drop.UEQUIL")
    def X(self, i=None): return 1-self.W[_idx(i)]/self.mix.NEARWALL["WBULK"][_idx(i)]
