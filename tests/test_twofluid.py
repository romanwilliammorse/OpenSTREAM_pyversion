"""Two-fluid source balances, copy semantics and official-input executions."""
from pathlib import Path
from copy import deepcopy
import numpy as np
import pytest
from openstream.inputs import InputSet,Model,Options,Geometry
from openstream.properties import FluidProperties
from openstream.fields import Mixture
from openstream.tf_fields import Liquid,Vapor,TwoFluidMixture
from openstream.twofluid import TwoFluidSolver


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def fluid(): return FluidProperties(6e6,Model())


def pair(fluid,**model_options):
    inp = InputSet(Model(NNODES=4,**model_options),Options(),Geometry(LENGTH=2,AREA=1e-4,PERIM=[0.04]),[])
    z = np.linspace(0,2,5)
    precursor = Mixture(inp,fluid,z)
    precursor.W[:] = 0.07
    precursor.H[:] = fluid.HF+0.3*fluid.HFG
    precursor.HFLUX[:] = 5e5
    precursor.DP = {"Tot":np.ones(5)*1000}
    precursor.update()
    l,v = Liquid(inp,fluid,z),Vapor(inp,fluid,z)
    l.W[:],v.W[:] = 0.04,0.03
    l.U[:],v.U[:] = 12,20
    l.H[:],v.H[:] = fluid.HF-1e4,fluid.HG+2e4
    l.mix = v.mix = TwoFluidMixture(precursor,l,v)
    return l,v


@pytest.mark.parametrize("transfer",["BULK","SATURATED"])
@pytest.mark.parametrize("heat",["RELAXATION","CONSTANT","RANZMARSHALL"])
def test_instantaneous_interphase_mass_energy_conservation(fluid,transfer,heat):
    l,v = pair(fluid,INTTRANSH=transfer,INTNU=heat)
    ml,mv = l.MTOT(v),v.MTOT(l)
    np.testing.assert_allclose(ml+mv,0,atol=1e-15)
    total = l.HTOT(v)+v.HTOT(l)+l.H[:,None]*ml+v.H[:,None]*mv
    # Source HTOT is a material-enthalpy source. Reintroducing H*dW
    # produces the conservative energy source, which must equal heating.
    np.testing.assert_allclose(total,l.mix.LHGR(),rtol=1e-13,atol=1e-8)


def test_interfacial_momentum_cancels_in_conservative_form(fluid):
    l,v = pair(fluid)
    np.testing.assert_allclose(l.FDRAG(v)+v.FDRAG(l),0,atol=1e-14)
    ml,mv = l.MTOT(v).sum(axis=1),v.MTOT(l).sum(axis=1)
    total = (l.FTOT(v)+v.FTOT(l)).ravel()+l.U*ml+v.U*mv
    external = l.FGRAV(v)+v.FGRAV(l)+l.FBUOY(v)+v.FBUOY(l)+(l.FWALL(v)+v.FWALL(l)).ravel()
    np.testing.assert_allclose(total,external,rtol=1e-13,atol=1e-10)


def test_pressure_and_gravity_dimensional_identity(fluid):
    l,v = pair(fluid)
    area = l.inputSet.geometry.AREA
    np.testing.assert_allclose(l.FBUOY(v)+v.FBUOY(l),area*l.mix.DPDZ(),rtol=1e-14)
    np.testing.assert_allclose(l.FGRAV(v)+v.FGRAV(l),-9.81*area*l.mix.RHO(),rtol=1e-14)
    np.testing.assert_allclose(l.VF(v)+v.VF(l),1,rtol=1e-14)


def test_prescribed_slip_pair_satisfies_area_and_ratio(fluid):
    l,v = pair(fluid,SLIP=2)
    ul,uv = l.USLIP(v),v.USLIP(l)
    np.testing.assert_allclose(uv/ul,2,rtol=1e-14)
    occupied = l.W/(fluid.RHOL(l.H)*ul)+v.W/(fluid.RHOV(v.H)*uv)
    np.testing.assert_allclose(occupied,l.inputSet.geometry.AREA,rtol=1e-14)


def test_phase_clone_preserves_matlab_shallow_mixture_links(fluid):
    l,v = pair(fluid)
    copy = l.clone()
    assert copy.mix is l.mix
    assert copy.mix.liquid is l
    original_total = l.mix.W().copy()
    copy.W[2] *= 2
    np.testing.assert_array_equal(copy.mix.W(),original_total)
    assert copy.W[2]!=l.W[2]
    copy.W[0] = 0.001
    l.copy_flow_properties(copy)
    assert copy.W[0]==0.001
    np.testing.assert_array_equal(copy.W[1:],l.W[1:])


@pytest.mark.parametrize("name",["TUTORIAL3A","TUTORIAL3B"])
def test_official_twofluid_inputs_converge(name):
    inputs = ROOT/"upstream"/"inputs"
    inp = InputSet.from_files(inputs/"models.inp",name,inputs/"options.inp","DEFAULT",inputs/"geom.inp","TUTORIAL1",inputs/"tutorial1.inp")
    solver = TwoFluidSolver(inp).solve()
    assert solver.converged
    assert solver.liquid[-1].W.shape==(101,)
    l,v = solver.liquid[-1],solver.vapor[-1]
    assert np.all(l.W>=0) and np.all(v.W>=0)
    assert np.all(l.U>0) and np.all(v.U>0)
    np.testing.assert_allclose(l.MTOT(v)+v.MTOT(l),0,atol=1e-14)
    if name=="TUTORIAL3B":
        f=solver.fluid[-1]
        area=l.W/(f.RHOL(l.H)*l.U)+v.W/(f.RHOV(v.H)*v.U)
        mismatch=np.max(abs(area/inp.geometry.AREA-1))
        diagnostics=solver.diagnostics()
        assert diagnostics["max_area_closure_relative"]==pytest.approx(mismatch)
        assert mismatch>0.01  # expose a material failure, do not endorse it
        assert diagnostics["physical_consistency"] is False
        incompatible=deepcopy(inp)
        incompatible.bc[0].POWER*=0.9
        with pytest.raises(ValueError,match="boundary conditions"):
            TwoFluidSolver(incompatible,solver.mixSolver)
    # No assertion of exact global energy conservation: the source discretizes
    # mass and material enthalpy separately; report its product-rule defect.


def test_unavailable_flow_regime_selector_fails_before_running():
    # The MATLAB switch branch exists, but its own enumeration omits it.
    with pytest.raises(ValueError,match="LOCRELVEL"):
        Model(LOCRELVEL="FLOWREGIME")


def test_unavailable_multiwall_full_momentum_fails_before_running():
    inp = InputSet(Model(MOMENTLIQUID="FULL"),Options(),Geometry(PERIM=[0.01,0.02]),[])
    with pytest.raises(NotImplementedError,match="multiple walls"):
        TwoFluidSolver(inp)


def test_enum_simple_relative_velocity_has_no_upstream_equation():
    inp = InputSet(Model(LOCRELVEL="SIMPLE"),Options(),Geometry(),[])
    with pytest.raises(NotImplementedError,match="LOCRELVEL"):
        TwoFluidSolver(inp)
