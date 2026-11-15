"""Four-field film/base/wave closures translated from the pinned MATLAB source.

All quantities are SI. Arrays are (node,wall); initially the solver supports one
wall because several original multiwall formulas use ambiguous linear indices.
Copyright (c) 2024 OpenSTREAM contributors; MIT, see LICENSE.
"""
from __future__ import annotations

import numpy as np

from .annular import Film as AbstractFilm, Drop, blend
from .fields import _col, _idx


def _copy_arrays(source, target, names, all=False):
    if not np.array_equal(source.Z, target.Z):
        raise ValueError("Source and target meshes differ")
    for name in names:
        src, dst = getattr(source, name), getattr(target, name)
        if all:
            setattr(target, name, src.copy())
        else:
            values = np.ravel(dst, order="F").copy()
            values[1:] = np.ravel(src, order="F")[1:]
            setattr(target, name, values.reshape(dst.shape, order="F"))


class Base(AbstractFilm):
    def __init__(self, film):
        super().__init__(film.inputSet, film.mix)
        self.film = film
        self.H[:] = 1e6

    def EPSILON(self, i=None):
        with np.errstate(divide="ignore", invalid="ignore"):
            value = self.W[_idx(i)] / self.film.W[_idx(i)]
        return np.where(np.isnan(value), 1.0, value)
    def BETA(self, i=None): return 1-self.film.wave.BETA(i)
    def BETAP(self, i=None): return blend(self.mix, 0, self.BETA(i), i)
    def ETA(self, i=None): return self.EPSILON(i)*self.BETA(i)
    def MENT(self, i=None): return 0.0*self.film.MENT(i)
    def MEVAP(self, i=None): return self.BETAP(i)*self.film.MEVAP(i)
    def MDEP(self, drop, i=None): return self.ETA(i)*_col(drop.MDEP(i))
    def MTURB(self, i=None):
        wave = self.film.wave
        with np.errstate(divide="ignore", invalid="ignore"):
            value = np.fmin(abs(self.WL(i)), wave.WL(i))/self.inputSet.model.WAVEMIXCOEF/wave.WIDTH(i)
        return blend(self.mix, 0, np.fmin(value, 10), i)
    def MWAVE(self, drop, i=None, return_net=False):
        net = (-self.MEVAP(i)-self.MENT(i)-self.MDEP(drop, i)
               +self.fluid.RHOF*(self.EQTHICK(i)-self.THICK(i))/self.inputSet.model.RELAXTB)
        value = blend(self.mix, 0, np.fmax(net, 0)+self.MTURB(i), i)
        return (value, net) if return_net else value
    def MTOT(self, drop, i=None):
        return self.MEVAP(i)+self.MENT(i)+self.MDEP(drop,i)+self.MWAVE(drop,i)-self.film.wave.MBASE(drop,i)
    def FWAVE(self, drop, i=None):
        value = self.film.wave.BETA(i)*self.FVAPOR(i)
        if self.inputSet.model.WAVEBASEINT == "VAPORSHEARDROPMASS":
            value = value+self.film.wave.FDEP(drop,i)
        elif self.inputSet.model.WAVEBASEINT != "VAPORSHEAR":
            raise NotImplementedError(f"WAVEBASEINT={self.inputSet.model.WAVEBASEINT}")
        return value
    def FWAVEMASS(self, drop, i=None):
        return blend(self.mix,0,self.MWAVE(drop,i)*(self.film.wave.U[_idx(i)]-self.U[_idx(i)]),i)
    def FBASEVAPOR(self, i=None): return self.BETA(i)*self.FVAPOR(i)
    def FDEP(self, drop, i=None):
        return blend(self.mix,0,self.MDEP(drop,i)*(_col(drop.U[_idx(i)])-self.U[_idx(i)]),i)
    def FTOT(self, drop, i=None):
        value = self.FWALL(i)+self.FWAVE(drop,i)+self.FWAVEMASS(drop,i)+self.FBASEVAPOR(i)+self.FDEP(drop,i)
        if self.inputSet.model.MOMENTBASE != "FULLNOP":
            value = value+self.FBUOY(i)+self.FGRAV(i)
        return value
    def EQTHICK(self, i=None):
        m, diameter = self.inputSet.model, self.inputSet.geometry.HDIAM()
        if m.BASEEQTHICK == "YPLUS": value = self.YPLUS2THICK(m.BASEYPLUS,i)
        else:
            coefs = {"RISO": [5.37e-5,-.64,1.21], "MFVAL": [1.8e-5,-.5,1.5],
                     "COEFS": m.BASEEQTHICKCOEF}
            if m.BASEEQTHICK not in coefs: raise NotImplementedError(f"BASEEQTHICK={m.BASEEQTHICK}")
            c = coefs[m.BASEEQTHICK]
            value = diameter*c[0]*_col(self.film.mix.vapor.RE(i))**c[1]*self.film.RE(i)**c[2]
        return np.fmin(value,diameter/2)
    def TBASE(self, i=None):
        with np.errstate(divide="ignore",invalid="ignore"):
            value = self.BETA(i)*self.film.wave.SPACING(i)/(self.film.wave.U[_idx(i)]-self.U[_idx(i)])
        return blend(self.mix,0,np.where(np.isinf(value),0,value),i)
    def TDRY(self, drop, i=None):
        delta = -self.MEVAP(i)-self.MDEP(drop,i)
        with np.errstate(divide="ignore",invalid="ignore"):
            value = self.TBASE(i)-self.W[_idx(i)]*self.BETA(i)/self.inputSet.geometry.PERIM/self.U[_idx(i)]/delta
        return np.fmax(np.where(delta<=0,0,value),0)
    def FDRY(self, drop, i=None):
        base = self.TBASE(i)
        with np.errstate(divide="ignore",invalid="ignore"): value = self.TDRY(drop,i)/base
        return np.where(base==0,0,value)
    def WMIN(self, drop, i=None):
        beta, mass = self.BETA(i), self.W[_idx(i)]
        with np.errstate(divide="ignore",invalid="ignore"):
            value = mass-self.inputSet.geometry.PERIM*self.U[_idx(i)]*(-self.MEVAP(i)-self.MDEP(drop,i))/beta*self.TBASE(i)
        return np.fmax(np.where(beta==0,mass,value),0)
    def WMINL(self, drop, i=None): return self.WMIN(drop,i)/self.inputSet.geometry.PERIM
    def THICKMIN(self, drop, i=None): return self.WMIN(drop,i)/self.fluid.RHOF/self.U[_idx(i)]/self.inputSet.geometry.PERIM
    def copy_flow_properties(self,target,all=False): _copy_arrays(self,target,("W","U","H"),all)


class Wave(AbstractFilm):
    def __init__(self, film):
        super().__init__(film.inputSet,film.mix)
        self.film = film
        self.H[:] = 1e6
        self.FREQUENCY = np.ones_like(self.W)

    def THICK(self, i=None): return self.AMPLITUDE(i)*self.BETA(i)
    def EPSILON(self, i=None):
        with np.errstate(divide="ignore",invalid="ignore"):
            value = self.W[_idx(i)]/self.film.W[_idx(i)]
        return np.where(self.W[_idx(i)]<=0,0,value)
    def BETA(self, i=None):
        epsilon = self.EPSILON(i)
        with np.errstate(divide="ignore",invalid="ignore"): value = self.WIDTH(i)/self.SPACING(i)
        return blend(self.film.mix,epsilon,np.where(np.isnan(value),epsilon,value),i)
    def BETAP(self, i=None): return 1-self.film.base.BETAP(i)
    def ETA(self, i=None): return 1-self.film.base.ETA(i)
    def MENT(self, i=None): return self.film.MENT(i)-self.film.base.MENT(i)
    def MEVAP(self, i=None): return self.BETAP(i)*self.film.MEVAP(i)
    def MDEP(self, drop, i=None): return self.ETA(i)*_col(drop.MDEP(i))
    def MTURB(self, i=None): return self.film.base.MTURB(i)
    def MBASE(self, drop, i=None):
        _, net = self.film.base.MWAVE(drop,i,True)
        return blend(self.mix,0,np.fmax(-net,0)+self.MTURB(i),i)
    def MTOT(self, drop, i=None):
        return self.MEVAP(i)+self.MENT(i)+self.MDEP(drop,i)+self.MBASE(drop,i)-self.film.base.MWAVE(drop,i)
    def FWALL(self, i=None): raise NotImplementedError("Upstream wave field has no wall shear stress")
    def FBASE(self, drop, i=None): return -self.film.base.FWAVE(drop,i)
    def FBASEMASS(self, drop, i=None):
        return blend(self.mix,0,self.MBASE(drop,i)*(self.film.base.U[_idx(i)]-self.U[_idx(i)]),i)
    def FVAPOR(self, i=None): return self.FDRAG(i)+self.FSHEAR(i)
    def FDRAG(self, i=None):
        difference = _col(self.mix.vapor.U(i))-self.U[_idx(i)]
        force = .5*self.SHAPEFACTOR(i)*self.DRAGCOEF(i)*self.fluid.RHOG*difference**2
        return blend(self.mix,0,self.BETA(i)*force,i)
    def FSHEAR(self, i=None):
        return self.BETA(i)*.5*self.CV(i)*self.fluid.RHOG*(_col(self.mix.vapor.U(i))-self.U[_idx(i)])**2
    def FDEP(self, drop, i=None):
        return blend(self.mix,0,self.MDEP(drop,i)*(_col(drop.U[_idx(i)])-self.U[_idx(i)]),i)
    def FTOT(self, drop, i=None):
        return self.FVAPOR(i)+self.FBUOY(i)+self.FGRAV(i)+self.FDEP(drop,i)+self.FBASE(drop,i)+self.FBASEMASS(drop,i)
    def SHAPEFACTOR(self, i=None):
        c = self.inputSet.model.SHAPEFACTORCOEF
        return (self.RE(i)/c[0])**c[1]*c[2]*_col(self.film.mix.vapor.RE(i))**c[3]
    def EQSTROUHAL(self, i=None):
        m = self.inputSet.model
        if m.EQSTROUHAL == "CSTFREQ":
            return np.broadcast_to(_col(m.CSTWAVEFREQ*self.inputSet.geometry.HDIAM()/self.film.mix.vapor.U(i)),self.W[_idx(i)].shape)
        coefs = {"RISO":[1.1236e-4,.5,0],"SAWAI":[77.67,-1.3,.46],"MFVAL":[4.1e-8,.5,.5],"CUSTOM":m.EQSTROUHALCOEF}
        if m.EQSTROUHAL not in coefs: raise NotImplementedError(f"EQSTROUHAL={m.EQSTROUHAL}")
        c = coefs[m.EQSTROUHAL]
        return c[0]*_col(self.film.mix.vapor.RE(i))**c[1]*self.film.RE(i)**c[2]
    def EQFREQUENCY(self, i=None): return self.EQSTROUHAL(i)*_col(self.film.mix.vapor.U(i))/self.inputSet.geometry.HDIAM()
    def EQPERIOD(self, i=None): return 1/self.EQFREQUENCY(i)
    def SPACING(self, i=None): return self.U[_idx(i)]/self.FREQUENCY[_idx(i)]
    def PERIOD(self, i=None): return 1/self.FREQUENCY[_idx(i)]
    def N(self, i=None): return 1/self.SPACING(i)
    def WIDTH(self, i=None):
        spacing = self.SPACING(i)
        with np.errstate(divide="ignore",invalid="ignore"): value = self.AMPLITUDE(i)/self.SHAPEFACTOR(i)
        return np.fmin(np.where(np.isnan(value),spacing,value),spacing)
    def AMPLITUDE(self, i=None):
        value = np.sqrt(abs(self.WL(i)*self.SHAPEFACTOR(i)/(self.fluid.RHOF*self.FREQUENCY[_idx(i)])))
        return np.fmin(value,self.inputSet.geometry.HDIAM()/2-self.film.base.THICK(i))
    def DELTAFREQ(self, i=None):
        value = (self.EQFREQUENCY(i)-self.FREQUENCY[_idx(i)])/self.U[_idx(i)]/self.inputSet.model.RELAXTW
        return blend(self.mix,0,value,i)
    def REV(self, i=None):
        return self.fluid.RHOG*(_col(self.film.mix.vapor.U(i))-self.U[_idx(i)])*self.inputSet.model.WAVEDRAGCOEF[0]/self.fluid.MUG
    def DRAGCOEF(self, i=None):
        c = self.inputSet.model.WAVEDRAGCOEF
        return (c[1]/self.REV(i))**2+c[2]
    def copy_flow_properties(self,target,all=False): _copy_arrays(self,target,("W","U","H","FREQUENCY"),all)


class Film(AbstractFilm):
    """Dependent aggregate film; base and wave arrays are the primary state."""
    def __init__(self,inputs,mix):
        self.inputSet,self.mix,self.fluid = inputs,mix,mix.fluid
        self.NZ,self.DZ,self.Z = mix.NZ,mix.DZ,mix.Z.copy()
        self.TIME,self.DT = mix.TIME,mix.DT
        self.HFLUX = mix.HFLUX.copy()
        self.mevap = -self.HFLUX/self.fluid.HFG
        self.ITR = {}
        self.inner_failures = []
        self.base = Base(self)
        self.wave = Wave(self)

    @property
    def W(self): return self.base.W+self.wave.W
    @property
    def U(self):
        with np.errstate(divide="ignore",invalid="ignore"):
            value = self.W/(self.base.W/self.base.U+self.wave.W/self.wave.U)
        return np.where(self.W==0,self.base.U,value)
    @property
    def H(self): return self.base.H
    @property
    def basefilm(self):
        """Python alias for post-processing; upstream actual property is base."""
        return self.base
    def EQUIL(self,Wf,i=None):
        # One wall avoids upstream linear-index U(zIdx) ambiguity.
        mass = self.base.EQTHICK(i)*self.base.U[_idx(i)]*self.inputSet.geometry.PERIM*self.fluid.RHOF
        with np.errstate(divide="ignore",invalid="ignore"): return np.fmin(mass/Wf,1)
    def distributeOAFW(self,Wf,i=None):
        value = np.asarray(Wf)
        m = self.inputSet.model
        if m.OAFFILMSPLIT == "RATIO": fraction = m.OAFBASERATIO
        elif m.OAFFILMSPLIT == "EQUILIBRIUM": fraction = self.EQUIL(value,i)
        else: raise NotImplementedError(f"OAFFILMSPLIT={m.OAFFILMSPLIT}")
        self.wave.W[_idx(i)] = (1-fraction)*value
        self.base.W[_idx(i)] = fraction*value
        return fraction
    def initialize_base_wave(self,inlet_mass):
        g = self.inputSet.geometry
        inlet = inlet_mass*g.PERIM/np.sum(g.PERIM)
        self.base.W = np.fmax(0,inlet+np.cumsum(self.MEVAP(),axis=0)*g.PERIM*self.DZ)
        self.wave.W = np.zeros_like(self.base.W)
        self.base.U = self.UALGEBR()
        self.wave.U = self.base.U.copy()
        self.distributeOAFW(self.base.W.copy())
        self.wave.U = np.broadcast_to(_col(self.mix.vapor.U())*.5,self.base.U.shape).copy()
        self.base.H = np.full((self.NZ,1),self.fluid.HF)
        self.wave.H = self.base.H.copy()
        self.wave.FREQUENCY = self.wave.EQFREQUENCY()
        j = self.mix.OAFIDX()
        self.wave.FREQUENCY[:j+1] = self.wave.EQFREQUENCY(j)
        for field in (self.base,self.wave):
            field.ITR = {"N":np.zeros(self.NZ),**{key:np.zeros_like(field.W) for key in ("DWL","DU","DFW")}}
    def copy_flow_properties(self,target,all=False):
        self.base.copy_flow_properties(target.base)
        self.wave.copy_flow_properties(target.wave)
