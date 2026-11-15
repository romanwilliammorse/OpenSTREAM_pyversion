"""Native two-fluid fields translated from upstream +Solvers/+TwoFluid.

The prescribed precursor mixture and the upstream shallow phase-copy links
are intentional. See docs/twofluid_notes.md before interpreting conservation.
Copyright (c) 2024 OpenSTREAM contributors. MIT license.
"""
from __future__ import annotations

from enum import IntEnum
import numpy as np
from .fields import _col, _idx, _geom


class Regime(IntEnum):
    LIQUID=0
    BUBBLY_SUBCOOLED=1
    BUBBLY_SATURATED=2
    INTERMEDIATE=3
    ANNULAR=4
    DFFB=5


class TwoFluidMixture:
    """Two-fluid aggregation with prescribed precursor forcing/closures."""
    def __init__(self,mixture,liquid,vapor):
        self.mixture,self.liquid,self.vapor = mixture,liquid,vapor
        self.fluid,self.inputSet,self.NZ = liquid.fluid,liquid.inputSet,liquid.NZ
    def TIME(self): return self.mixture.TIME
    def Z(self,i=None): return self.mixture.Z[_idx(i)]
    def HFLUX(self,i=None): return self.mixture.HFLUX[_idx(i)]
    def LHGR(self,i=None): return self.HFLUX(i)*self.inputSet.geometry.PERIM
    def WALEVAPRATIO(self,i=None): return self.mixture.WALEVAPRATIO(i)
    def W(self,i=None): return self.liquid.W[_idx(i)]+self.vapor.W[_idx(i)]
    def MFLUX(self,i=None): return self.W(i)/self.inputSet.geometry.AREA
    def RHO(self,i=None):
        vf = self.vapor.VF(self.liquid,i)
        return (1-vf)*self.fluid.RHOL(self.liquid.H[_idx(i)])+vf*self.fluid.RHOV(self.vapor.H[_idx(i)])
    def U(self,i=None):
        vf = self.vapor.VF(self.liquid,i)
        rl,rv = self.fluid.RHOL(self.liquid.H[_idx(i)]),self.fluid.RHOV(self.vapor.H[_idx(i)])
        return ((1-vf)*rl*self.liquid.U[_idx(i)]+vf*rv*self.vapor.U[_idx(i)])/((1-vf)*rl+vf*rv)
    def TAUW(self,i=None): return self.mixture.TAUW(i)
    def DPDZ(self,i=None): return self.mixture.DP["Tot"][_idx(i)]/self.mixture.DZ
    def H(self,i=None): return (self.liquid.W[_idx(i)]*self.liquid.H[_idx(i)]+self.vapor.W[_idx(i)]*self.vapor.H[_idx(i)])/self.W(i)
    def XEQ(self,i=None): return self.mixture.XEQ(i)
    def VF(self,i=None): return self.vapor.VF(self.liquid,i)
    def OAFX(self,i=None): return self.mixture.OAFX(i)
    def AFDISTR(self,a,b,i=None): return self.mixture.AFDISTR(a,b,i)
    def CHF(self,i=None): return self.mixture.CHF(i)
    def CBT(self,i=None): return self.mixture.CBT(i)
    def RELAXTCOND(self,i=None): return self.mixture.RELAXTCOND(i)
    def RELAXTEVAP(self,i=None): return self.mixture.RELAXTEVAP(i)


class _Phase:
    def __init__(self,input_set,fluid,z,time=0,dt=1):
        self.inputSet,self.fluid = input_set,fluid
        self.Z = np.array(z,copy=True)
        self.NZ,self.DZ = len(z),float(z[1]-z[0])
        self.TIME,self.DT = time,dt
        self.W,self.U,self.H = np.ones(self.NZ),np.ones(self.NZ),np.ones(self.NZ)
        self.ITR = {key:np.zeros(self.NZ) for key in ("N","DW","DU","DH")}
        self.mix = None
    def copy_flow_properties(self,target,all=False):
        if not np.array_equal(self.Z,target.Z): raise ValueError("Two-fluid meshes differ")
        sl = slice(None) if all else slice(1,None)
        for name in ("W","U","H"):
            getattr(target,name)[sl] = getattr(self,name)[sl]
        for name,value in self.ITR.items(): target.ITR[name][sl] = value[sl]
    def clone(self,time=None,dt=None):
        """MATLAB Copyable default: independent arrays, shared .mix handle."""
        new = type(self)(self.inputSet,self.fluid,self.Z,self.TIME if time is None else time,self.DT if dt is None else dt)
        self.copy_flow_properties(new,all=True)
        new.mix = self.mix
        return new
    def X(self,i=None): return self.W[_idx(i)]/self.mix.W(i)
    def T(self,i=None): return self.fluid.T(self.H[_idx(i)])
    def TAUW(self,i=None): return self.mix.TAUW(i)
    def FBUOY(self,other,i=None): return self.inputSet.geometry.AREA*self.VF(other,i)*self.mix.DPDZ(i)
    def FWALL(self,other,i=None):
        # Wall dependence is retained; FULL momentum with multiple walls is
        # rejected by the solver because upstream assigns this to scalar U.
        return -_col(self.VF(other,i))*self.TAUW(i)*np.sum(self.inputSet.geometry.PERIM)
    def MINTCOND(self,other,i=None): return self.MINT(other,i)[0]
    def MINTEVAP(self,other,i=None): return self.MINT(other,i)[1]
    def HINTCOND(self,other,i=None): return self.HINT(other,i)[0]
    def HINTEVAP(self,other,i=None): return self.HINT(other,i)[1]
    def HTOT(self,other,i=None): return self.HINTCOND(other,i)+self.HINTEVAP(other,i)+self.HWALEVAP(other,i)+self.HWALHEAT(i)


class Liquid(_Phase):
    def VF(self,vapor,i=None): return 1-vapor.VF(self,i)
    def J(self,i=None): return self.W[_idx(i)]/self.fluid.RHOL(self.H[_idx(i)])/self.inputSet.geometry.AREA
    def S(self,vapor,i=None): return vapor.U[_idx(i)]/self.U[_idx(i)]
    def AREA(self,vapor,i=None): return self.VF(vapor,i)*self.inputSet.geometry.AREA
    def USLIP(self,vapor,i=None):
        rl,rv = self.fluid.RHOL(self.H[_idx(i)]),self.fluid.RHOV(vapor.H[_idx(i)])
        s = self.inputSet.model.SLIP
        vf = np.fmax(0,vapor.W[_idx(i)]/(s*self.W[_idx(i)]*rv/rl+vapor.W[_idx(i)]))
        return self.mix.W(i)/self.inputSet.geometry.AREA/(rl*(1-vf)+rv*vf*s)
    def VR(self,vapor,i=None):
        m = self.inputSet.model
        vr = vapor.U[_idx(i)]-self.U[_idx(i)]
        if m.LOCRELVEL=="AREAMEAN": return vr
        if m.LOCRELVEL=="SCALED": return m.RELVELCST*vr
        if m.LOCRELVEL=="DRIFT": return np.where(self.VF(vapor,i)<0.5,self.VF(vapor,i),vapor.VF(self,i))*vr
        raise NotImplementedError("LOCRELVEL=FLOWREGIME needs review of upstream scalar FLOWREGIME indexing")
    def RE(self,i=None): return 4*abs(self.W[_idx(i)])/self.fluid.MUL(self.H[_idx(i)])/np.sum(self.inputSet.geometry.PERIM)
    def REV(self,vapor,i=None):
        # Source deliberately passes liquid enthalpy to vapor properties.
        return self.fluid.RHOV(self.H[_idx(i)])*abs(self.VR(vapor,i))*self.L(i)/self.fluid.MUV(self.H[_idx(i)])
    def VISC(self,vapor,i=None):
        f = self.fluid
        rv,rl = f.RHOV(vapor.H[_idx(i)]),f.RHOL(self.H[_idx(i)])
        return f.MUV(vapor.H[_idx(i)])/np.sqrt(rv*f.SIGMA*np.sqrt(self.inputSet.model.G*f.SIGMA/abs(rl-rv)))
    def XTR_SUB(self): return self.inputSet.model.WBOILINGXSUB
    def XTR_SAT(self): return self.inputSet.model.WBOILINGXSAT
    def XTR_ITM(self): return 0.1
    def XTR_ANN(self): return np.min(self.mix.OAFX())
    def FLOWREGIME(self,i=None):
        if i is not None:
            raise NotImplementedError("Upstream FLOWREGIME subset indexing allocates a full mesh; use FLOWREGIME()")
        x = _col(self.mix.XEQ())
        out = np.zeros((self.NZ,self.inputSet.geometry.NWALL()),dtype=int)
        for threshold,number in ((self.XTR_SUB(),1),(self.XTR_SAT(),2),(0.1,3),(self.XTR_ANN(),4)):
            out = np.where(x>threshold,number,out)
        return np.where(self.mix.CBT(),5,out)
    def FLOWID(self,i=None): return self.FLOWREGIME(i)
    def L(self,i=None): return np.ones_like(self.W[_idx(i)])*self.inputSet.model.INTLENGTHLCST
    def INTAREA(self,vapor,i=None):
        aiv = 6*vapor.VF(self,i)/vapor.L(i)
        ail = 6*self.VF(vapor,i)/self.L(i)
        return np.fmax(0,self.mix.AFDISTR(aiv,ail,i))
    def HFLUXWALEVAP(self,i=None): return -self.WALEVAPRATIO(i)*self.mix.HFLUX(i)
    def HFLUX(self,i=None): return self.HWALHEAT(i)/self.inputSet.geometry.PERIM+self.HFLUXWALEVAP(i)
    def WALEVAPRATIO(self,i=None): return self.mix.WALEVAPRATIO(i)
    def MINT(self,vapor,i=None):
        m = self.inputSet.model
        hl,hv = self.H[_idx(i)],vapor.H[_idx(i)]
        if m.INTNU in ("CONSTANT","RANZMARSHALL"):
            evapflux,condflux = self.INTHFLUX(vapor,i)
            if m.INTTRANSH=="BULK":
                condflux,evapflux = condflux/(hv-hl),evapflux/(hv-hl)
            else:
                condflux,evapflux = condflux/(self.fluid.HG-hl),evapflux/(hv-self.fluid.HF)
            cond = _col(self.inputSet.geometry.AREA*self.INTAREA(vapor,i)*condflux)
            evap = _col(-self.inputSet.geometry.AREA*self.INTAREA(vapor,i)*evapflux)
        else:
            w = -(self.mix.W(i)*self.mix.XEQ(i)-vapor.W[_idx(i)])
            cond = np.fmax(0,_col(w/vapor.U[_idx(i)])/self.mix.RELAXTCOND(i))
            evap = np.fmin(0,_col(w/vapor.U[_idx(i)])/self.mix.RELAXTEVAP(i))
        cond = np.fmin(cond,_col(vapor.W[_idx(i)]/self.DZ))
        evap = -np.fmin(-evap,_col(self.W[_idx(i)]/self.DZ))
        r = self.inputSet.geometry.RWALL()
        return cond*r,evap*r
    def MWALEVAP(self,vapor,i=None):
        hv = vapor.H[_idx(i)] if self.inputSet.model.INTTRANSH=="BULK" else self.fluid.HG
        return self.inputSet.geometry.PERIM*self.HFLUXWALEVAP(i)/_col(hv-self.H[_idx(i)])
    def MTOT(self,vapor,i=None): return self.MINTCOND(vapor,i)+self.MINTEVAP(vapor,i)+self.MWALEVAP(vapor,i)
    def INTNU(self,vapor,i=None):
        m = self.inputSet.model
        if m.INTNU=="CONSTANT": return np.ones_like(self.W[_idx(i)])*m.INTNULCST
        if m.INTNU=="RELAXATION": return np.full_like(self.W[_idx(i)],np.nan)
        c = m.RANZMARSHALLLCST
        return c[0]+c[1]*self.REV(vapor,i)**c[2]*self.fluid.PRANDTLV(self.H[_idx(i)])**c[3]
    def INTHFLUX(self,vapor,i=None):
        lv,ll = vapor.L(i),self.L(i)
        hv = np.where(lv<=1e-6,0,vapor.INTNU(self,i)*self.fluid.KL(self.H[_idx(i)])/lv)
        hl = np.where(ll<=1e-6,0,self.INTNU(vapor,i)*self.fluid.KV(vapor.H[_idx(i)])/ll)
        h = np.fmax(0,self.mix.AFDISTR(hv,hl,i))
        return np.fmax(0,h*(vapor.T(i)-self.fluid.TSAT)),np.fmax(0,h*(self.fluid.TSAT-self.T(i)))
    def HINT(self,vapor,i=None):
        cond,evap = self.MINT(vapor,i)
        hl = _col(self.H[_idx(i)])
        if self.inputSet.model.INTTRANSH=="BULK": return cond*(_col(vapor.H[_idx(i)])-hl),np.zeros_like(evap)
        return cond*(self.fluid.HG-hl),evap*(self.fluid.HF-hl)
    def HWALEVAP(self,vapor,i=None):
        hv = vapor.H[_idx(i)] if self.inputSet.model.INTTRANSH=="BULK" else self.fluid.HG
        return self.MWALEVAP(vapor,i)*_col(hv-self.H[_idx(i)])
    def HWALHEAT(self,i=None): return (~self.mix.CBT(i))*self.mix.LHGR(i)
    def FGRAV(self,vapor,i=None):
        m,g = self.inputSet.model,self.inputSet.geometry
        return -m.G*np.cos(np.deg2rad(g.ANGLE))*self.fluid.RHOL(self.H[_idx(i)])*self.VF(vapor,i)*g.AREA
    def CD(self,vapor,i=None):
        m = self.inputSet.model
        re = np.where(self.REV(vapor,i)<=1e-3,1e-3,self.REV(vapor,i))
        if m.DROPDRAG=="CONSTANT": cd = np.ones_like(re)*m.DROPDRAGCOEF
        elif m.DROPDRAG=="STOKES": cd = 24/re
        elif m.DROPDRAG=="VISCOUS": cd = 24/re*(1+0.15*re**0.687)
        else: cd = self.VISC(vapor,i)*re*(np.sqrt(2)/3*(1-self.VF(vapor,i))**2)
        return np.fmin(cd,1)
    def FDRAG(self,vapor,i=None):
        a = self.inputSet.geometry.AREA*self.INTAREA(vapor,i)*0.5*self.VR(vapor,i)*abs(self.VR(vapor,i))
        fv = a*vapor.CD(self,i)*self.fluid.RHOL(self.H[_idx(i)])
        fl = a*self.CD(vapor,i)*self.fluid.RHOV(vapor.H[_idx(i)])
        return self.mix.AFDISTR(fv,fl,i)
    def FINTCOND(self,vapor,i=None): return np.sum(self.MINTCOND(vapor,i),axis=-1)*(vapor.U[_idx(i)]-self.U[_idx(i)])
    def FTOT(self,vapor,i=None):
        return _col(self.FGRAV(vapor,i)+self.FBUOY(vapor,i)+self.FDRAG(vapor,i)+self.FINTCOND(vapor,i))+self.FWALL(vapor,i)


class Vapor(_Phase):
    def XTR_SUB(self,liquid): return liquid.XTR_SUB()
    def XTR_SAT(self,liquid): return liquid.XTR_SAT()
    def XTR_ITM(self,liquid): return liquid.XTR_ITM()
    def XTR_ANN(self,liquid): return liquid.XTR_ANN()
    def XTR_CBT(self,liquid):
        raise NotImplementedError("Upstream Vapor.XTR_CBT calls Liquid.XTR_CBT, which is not defined; no transition-quality model substituted")
    def X(self,i=None):
        if i is not None: raise NotImplementedError("Upstream Vapor.X ignores requested indices (nargin < 3 typo); use X()")
        return super().X()
    def VF(self,liquid,i=None):
        rl,rv = self.fluid.RHOL(liquid.H[_idx(i)]),self.fluid.RHOV(self.H[_idx(i)])
        return np.fmax(0,self.W[_idx(i)]/(liquid.S(self,i)*liquid.W[_idx(i)]*rv/rl+self.W[_idx(i)]))
    def J(self,i=None): return self.W[_idx(i)]/self.fluid.RHOV(self.H[_idx(i)])/self.inputSet.geometry.AREA
    def S(self,liquid,i=None): raise NotImplementedError("Upstream Vapor.S calls Liquid.S without vapor argument; use liquid.S(vapor, i)")
    def AREA(self,liquid,i=None): return self.VF(liquid,i)*self.inputSet.geometry.AREA
    def USLIP(self,liquid,i=None): return liquid.USLIP(self,i)*self.inputSet.model.SLIP
    def RE(self,i=None): return 4*self.W[_idx(i)]/self.fluid.MUV(self.H[_idx(i)])/np.sum(self.inputSet.geometry.PERIM)
    def REL(self,liquid,i=None): return self.fluid.RHOL(self.H[_idx(i)])*abs(liquid.VR(self,i))*self.L(i)/self.fluid.MUL(self.H[_idx(i)])
    def VISC(self,liquid,i=None):
        f = self.fluid
        rv,rl = f.RHOV(self.H[_idx(i)]),f.RHOL(liquid.H[_idx(i)])
        return f.MUL(liquid.H[_idx(i)])/np.sqrt(rl*f.SIGMA*np.sqrt(self.inputSet.model.G*f.SIGMA/abs(rl-rv)))
    def L(self,i=None): return np.ones_like(self.W[_idx(i)])*self.inputSet.model.INTLENGTHVCST
    def INTAREA(self,liquid,i=None): return liquid.INTAREA(self,i)
    def FLOWREGIME(self,liquid,i=None): return liquid.FLOWREGIME(i)
    def HFLUXWALEVAP(self,liquid,i=None): return -liquid.HFLUXWALEVAP(i)
    def HFLUX(self,i=None): return self.HWALHEAT(i)/self.inputSet.geometry.PERIM
    def MINT(self,liquid,i=None):
        c,e = liquid.MINT(self,i)
        return -c,-e
    def WALEVAPRATIO(self,liquid,i=None): return liquid.WALEVAPRATIO(i)
    def MWALEVAP(self,liquid,i=None): return -liquid.MWALEVAP(self,i)
    def MTOT(self,liquid,i=None): return -liquid.MTOT(self,i)
    def INTNU(self,liquid,i=None):
        m = self.inputSet.model
        if m.INTNU=="CONSTANT": return np.ones_like(self.W[_idx(i)])*m.INTNUVCST
        if m.INTNU=="RELAXATION": return np.full_like(self.W[_idx(i)],np.nan)
        c = m.RANZMARSHALLVCST
        return c[0]+c[1]*self.REL(liquid,i)**c[2]*self.fluid.PRANDTLL(self.H[_idx(i)])**c[3]
    def INTHFLUX(self,liquid,i=None): return liquid.INTHFLUX(self,i)
    def HINT(self,liquid,i=None):
        c,e = self.MINT(liquid,i)
        hv = _col(self.H[_idx(i)])
        if self.inputSet.model.INTTRANSH=="BULK": return np.zeros_like(c),e*(_col(liquid.H[_idx(i)])-hv)
        return c*(self.fluid.HG-hv),e*(self.fluid.HF-hv)
    def HWALEVAP(self,liquid,i=None):
        if self.inputSet.model.INTTRANSH=="BULK": return np.zeros_like(self.mix.HFLUX(i))
        return self.MWALEVAP(liquid,i)*(self.fluid.HG-_col(self.H[_idx(i)]))
    def HWALHEAT(self,i=None): return self.mix.CBT(i)*self.mix.LHGR(i)
    def FGRAV(self,liquid,i=None):
        m,g = self.inputSet.model,self.inputSet.geometry
        return -m.G*np.cos(np.deg2rad(g.ANGLE))*self.fluid.RHOV(self.H[_idx(i)])*self.VF(liquid,i)*g.AREA
    def CD(self,liquid,i=None):
        m = self.inputSet.model
        re = np.where(self.REL(liquid,i)<=1e-3,1e-3,self.REL(liquid,i))
        if m.BUBBLEDRAG=="CONSTANT": cd = np.ones_like(re)*m.BUBBLEDRAGCOEF
        elif m.BUBBLEDRAG=="STOKES": cd = 24/re
        elif m.BUBBLEDRAG=="VISCOUS": cd = 24/re*(1+0.15*re**0.687)
        else: cd = self.VISC(liquid,i)*re*(np.sqrt(2)/3*liquid.VF(self,i)**2)
        return np.fmin(cd,1)
    def FDRAG(self,liquid,i=None): return -liquid.FDRAG(self,i)
    def FINTEVAP(self,liquid,i=None): return np.sum(self.MINTEVAP(liquid,i),axis=-1)*(liquid.U[_idx(i)]-self.U[_idx(i)])
    def FWALEVAP(self,liquid,i=None): return np.sum(self.MWALEVAP(liquid,i),axis=-1)*(liquid.U[_idx(i)]-self.U[_idx(i)])
    def FTOT(self,liquid,i=None):
        return _col(self.FGRAV(liquid,i)+self.FBUOY(liquid,i)+self.FDRAG(liquid,i)+self.FINTEVAP(liquid,i)+self.FWALEVAP(liquid,i))+self.FWALL(liquid,i)
