"""Independent identities, dimensional balance checks and MATLAB semantics.

These are not comparisons to executed MATLAB reference results.
"""
from copy import deepcopy
import numpy as np
import pytest

from openstream.inputs import Model, Options, Geometry, InputSet
from openstream.properties import FluidProperties
from openstream.fields import Mixture


@pytest.fixture(scope="module")
def fluid():
    return FluidProperties(6e6, Model())


def field(fluid, walls=1, **models):
    geom = Geometry(LENGTH=2.0, AREA=1e-4, PERIM=np.full(walls,0.04/walls))
    model = Model(NNODES=4, **models)
    mix = Mixture(InputSet(model,Options(),geom,[]),fluid,np.linspace(0,2,5),dt=0.2)
    mix.W[:] = 0.1
    mix.H[:] = fluid.HF+np.array([-0.05,0.0,0.1,0.5,0.98])*fluid.HFG
    mix.update()
    mix.update()  # first upstream H assignment intentionally uses equilibrium
    return mix


def test_homogeneous_phase_mass_energy_volume_identities(fluid):
    mix = field(fluid)
    np.testing.assert_allclose(mix.liquid.W()+mix.vapor.W(),mix.W,rtol=1e-14)
    np.testing.assert_allclose(mix.liquid.W()*mix.liquid.H()+mix.vapor.W()*mix.vapor.H(),mix.W*mix.H,rtol=2e-14)
    expected_density = 1/((1-mix.X())/fluid.RHOF+mix.X()/fluid.RHOG)
    np.testing.assert_allclose(mix.RHO(),expected_density,rtol=2e-14)
    np.testing.assert_allclose(mix.liquid.U(),mix.U(),rtol=3e-14)
    np.testing.assert_allclose(mix.vapor.U(),mix.U(),rtol=3e-14)
    np.testing.assert_allclose(mix.UP(),mix.U(),rtol=3e-14)
    np.testing.assert_allclose(mix.ECT(),0,atol=1e-8)
    np.testing.assert_allclose(mix.MCT(),0,atol=1e-14)
    assert np.all((mix.VF()>=0)&(mix.VF()<=1))


def test_slip_corrections_and_phase_reconstruction(fluid):
    mix = field(fluid,VOID="SLIP",SLIP=2.0)
    # interior two-phase nodes avoid upstream's liquid-velocity 1% cutoff
    ids = np.array([2,3])
    np.testing.assert_allclose(mix.vapor.U(ids)/mix.liquid.U(ids),2,rtol=1e-14)
    area = mix.inputSet.geometry.AREA
    density = (1-mix.VF(ids))*fluid.RHOF+mix.VF(ids)*fluid.RHOG
    velocity_mass_moment = (1-mix.VF(ids))*fluid.RHOF*mix.liquid.U(ids)+mix.VF(ids)*fluid.RHOG*mix.vapor.U(ids)
    np.testing.assert_allclose(density*mix.U(ids),velocity_mass_moment,rtol=1e-14)
    energy_inventory = area*((1-mix.VF(ids))*fluid.RHOF*mix.liquid.H(ids)+mix.VF(ids)*fluid.RHOG*mix.vapor.H(ids))
    np.testing.assert_allclose(mix.ECT(ids),energy_inventory-area*density*mix.H[ids],rtol=2e-14)


def test_pressure_components_independent_darcy_and_hydrostatics(fluid):
    mix = field(fluid)
    mix.H[:] = fluid.HF-0.03*fluid.HFG
    mix.update()
    g = mix.inputSet.geometry
    rho,u,dz = fluid.RHOF,mix.U(),mix.DZ
    re = rho*u*g.HDIAM()/fluid.MUF
    f = 0.2*re**-0.2
    expected_wall = -f*dz/g.HDIAM()*rho*u**2/2
    np.testing.assert_allclose(mix.DPWALL(),expected_wall,rtol=2e-14)
    np.testing.assert_allclose(mix.DPGRAV(),-rho*9.81*dz,rtol=2e-14)
    np.testing.assert_allclose(mix.DPACCZ(),0,atol=1e-12)
    parts = mix.DPPARTS(mix.UP(),mix.MCT())
    np.testing.assert_allclose(parts["TOT"],expected_wall-rho*9.81*dz,rtol=2e-14)


def test_temporal_momentum_terms_reduce_to_mixture_inventory(fluid):
    mix = field(fluid,VOID="SLIP",SLIP=2.0)
    old_up = 0.8*mix.UP()
    old_mct = 0.7*mix.MCT()
    expected = -(mix.RHO()*mix.UP()-mix.RHO()*old_up+(mix.MCT()-old_mct)/mix.inputSet.geometry.AREA)*mix.DZ/mix.DT
    np.testing.assert_allclose(mix.DPACCT(old_up)+mix.DPACCS(old_mct),expected,rtol=1e-14)


def test_state_caches_match_upstream_setter_order(fluid):
    mix = field(fluid,VOID="BESTION")
    oldrho,oldup = mix.RHO().copy(),mix.UP().copy()
    oldg = mix.MFLUX().copy()
    mix.W[2] *= 1.5
    assert mix.MFLUX(2)==pytest.approx(1.5*oldg[2])
    np.testing.assert_array_equal(mix.RHO(),oldrho)
    np.testing.assert_array_equal(mix.UP(),oldup)
    mix.update(2)
    assert mix.RHO(2)!=oldrho[2]


def test_wall_dimensions_copy_and_no_shared_mutation(fluid):
    mix = field(fluid,walls=2)
    target = field(fluid,walls=2)
    assert mix.LHGR().shape==(5,2)
    assert mix.LHGR(1).shape==(2,)
    np.testing.assert_allclose(mix.WWALL().sum(axis=1),mix.W)
    mix.MRM["HV"][:] = fluid.HG+np.arange(10).reshape(5,2)
    target.MRM["HV"][0] = fluid.HG+100
    mix.copy_flow_properties(target)
    assert target.MRM["HV"][0,0]==fluid.HG+100
    # MATLAB (2:end) means column-major linear entries, not rows 2:end.
    assert target.MRM["HV"][0,1]==mix.MRM["HV"][0,1]
    target.MRM["HV"][2,0] += 500
    assert target.MRM["HV"][2,0]!=mix.MRM["HV"][2,0]
    target.W[2] += 1
    assert target.W[2]!=mix.W[2]


@pytest.mark.parametrize("option,value",[("SPHTM","DITTUSBOELTERGEN")])
def test_unported_options_are_explicit(fluid,option,value):
    with pytest.raises(NotImplementedError,match=option):
        field(fluid,**{option:value})


def test_delorme_multiwall_rejected(fluid):
    with pytest.raises(NotImplementedError,match="DELORME"):
        field(fluid,walls=2,BTHTM="DELORME")


def test_relaxation_units_endpoint_bounds_and_local_override(fluid):
    mix = field(fluid,RELAXX=[-0.5,1.0],RELAXCONDT=[0.5,0.5],RELAXEVAPT=[0.3,0.3],KLOC=[1.0],KLOSS=[0],KTRELAX=[0.07])
    np.testing.assert_allclose(mix.RELAXTCOND()[[0,1,3,4]],0.5,rtol=2e-14)
    np.testing.assert_allclose(mix.RELAXTEVAP()[[0,1,3,4]],0.3,rtol=2e-14)
    np.testing.assert_allclose(mix.RELAXTCOND(2),0.07,rtol=2e-14)
    np.testing.assert_allclose(mix.RELAXTEVAP(2),0.07,rtol=2e-14)


def test_saha_zuber_zero_heat_flux_limit_and_subcooled_boiling(fluid):
    mix = field(fluid,THERMALNONEQ="SAHAZUBER")
    np.testing.assert_allclose(mix.X(),np.maximum(0,mix.XEQ()),rtol=1e-14)
    mix.H[1] = fluid.HF-0.005*fluid.HFG
    mix.HFLUX[:] = 1e6
    mix.update()
    assert mix.X(1)>0
    assert mix.X(1)<0.1
    assert mix.liquid.H(1)<mix.H[1]


def test_nodal_annular_sigmoid_and_frozen_upstream_cache(fluid):
    mix = field(fluid,OAFTRANSITION=[0.1,0])
    center = mix.OAFIDX()
    expected = 1/(1+np.exp(-0.1*4/2*(np.arange(5)-center)))
    np.testing.assert_allclose(mix.AFFNC(),expected,rtol=1e-14)
    mix.H[:] = fluid.HF+0.9*fluid.HFG
    mix.update()
    np.testing.assert_array_equal(mix.AFFNC(),expected)
    for walls in (1,2):
        a,b = np.zeros((5,walls)),np.ones((5,walls))
        result = mix.AFDISTR(a,b)
        assert result.shape==(5,walls)
        np.testing.assert_allclose(result,np.broadcast_to(expected[:,None],(5,walls)))


def test_wall_energy_partition_and_thom_temperature(fluid):
    mix = field(fluid,walls=2)
    mix.HFLUX[:] = 5e5
    mix.update()
    np.testing.assert_allclose(mix.liquid.HFLUX()+mix.vapor.HFLUX()+mix.vapor.HFLUXWALEVAP(),mix.HFLUX,rtol=1e-14)
    tw = mix.TWALL()
    assert tw.shape==(5,2)
    assert np.all(np.isfinite(tw))
    assert np.all(tw>=mix.liquid.T()[:,None])
    h, _ = mix.HWALL(tw)
    np.testing.assert_allclose((tw-mix.liquid.T()[:,None])*h,mix.HFLUX,rtol=1e-12)


@pytest.mark.parametrize("model",["VAPOR","DOUGALL","BISHOP","MOECK","DELORME","CONDIEIV"])
def test_post_boiling_heat_transfer_closures_finite_positive(fluid,model):
    mix = field(fluid,BTHTM=model,CBT="ELEVATION",CBTELEVATION=0.25)
    mix.H[:] = fluid.HF+0.6*fluid.HFG
    mix.HFLUX[:] = 1e5
    mix.update()
    h,t = mix.HWALLPOSTCBT(np.full((5,1),fluid.TSAT+100))
    assert h.shape==(5,1) and t.shape==(5,1)
    assert np.all(np.isfinite(h)) and np.all(h>0)
    assert np.all(np.isfinite(t)) and np.all(t>=fluid.TSAT)


@pytest.mark.parametrize("model",["DITTUSBOELTER","GNIELINSKI","SIEDERTATE"])
def test_single_phase_heat_transfer_closures_both_phases(fluid,model):
    mix = field(fluid,SPHTM=model)
    mix.H[:] = fluid.HF+0.3*fluid.HFG
    mix.update()
    for phase in (mix.liquid,mix.vapor):
        h = phase.HWALL(np.full((5,1),fluid.TSAT+30))
        assert np.all(np.isfinite(h)) and np.all(h>0)


@pytest.mark.parametrize("model",["FOURIERX","TIMEX","VOID","HOMOGENEOUS","FOURIER"])
def test_relaxation_closures_finite_positive_in_two_phase_region(fluid,model):
    mix = field(fluid,THERMALRELAX=model)
    mix.H[:] = fluid.HF+0.3*fluid.HFG
    mix.MRM["X"][:] = 0.25
    mix.update()
    assert np.all(np.isfinite(mix.RELAXTCOND())) and np.all(mix.RELAXTCOND()>0)
    assert np.all(np.isfinite(mix.RELAXTEVAP())) and np.all(mix.RELAXTEVAP()>0)


def test_epri_quality_and_void_closure_limits(fluid):
    mix = field(fluid,THERMALNONEQ="EPRI",VOID="EPRI")
    mix.HFLUX[:] = 1e6
    mix.update()
    assert np.all(np.isfinite(mix.X()))
    assert np.all((mix.X()>=0)&(mix.X()<=1))
    assert np.all(np.isfinite(mix.VF()))
    assert np.all((mix.VF()>=0)&(mix.VF()<=1))


def test_matlab_nan_omission_in_pure_vapor_relaxation_bound(fluid):
    mix=field(fluid,THERMALRELAX="HOMOGENEOUS")
    mix.H[:]=fluid.HG
    # Liquid fraction / its reference fraction is 0/0 at all-vapor onset.
    # MATLAB max(1e-6, NaN) returns 1e-6. This is a source compatibility
    # check, not a physical justification of the homogeneous closure limit.
    with np.errstate(invalid="ignore",divide="ignore"):
        mix.update()
    np.testing.assert_array_equal(mix.RELAXTEVAP(),np.full((5,1),1e-6))


@pytest.mark.parametrize("ratio",[0,1])
def test_singular_nearwall_endpoint_is_explicit(fluid,ratio):
    with pytest.raises(NotImplementedError,match="NEARWALLRATIO"):
        field(fluid,NEARWALLRATIO=ratio)
