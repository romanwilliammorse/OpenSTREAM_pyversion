"""Source diagnostics, subset semantics and explicit upstream defects."""
import numpy as np
import pytest

from openstream.inputs import InputSet, Model, Options, Geometry
from openstream.fields import Mixture
from openstream.properties import FluidProperties
from openstream.tf_fields import Liquid, Vapor, TwoFluidMixture
from openstream.annular import Drop
from openstream.ff_fields import Drop as FourFieldDrop


@pytest.fixture(scope="module")
def fluid():
    return FluidProperties(6e6, Model())


def mixture(fluid, walls=2):
    perimeters = [.01,.03] if walls == 2 else [.04]
    inputs = InputSet(Model(NNODES=4, KLOC=[.25, .9, 1.1, 1.5], KLOSS=[0,0,0,0]), Options(),
                      Geometry(LENGTH=2, AREA=1e-4, PERIM=perimeters), [])
    mix = Mixture(inputs, fluid, np.linspace(0,2,5), time=2.5, dt=.2)
    mix.W[:] = .1
    mix.H[:] = fluid.HF+.3*fluid.HFG
    mix.update()
    return mix


def test_obstruction_indices_filter_subsets_preserve_order_duplicates_and_ties(fluid):
    mix = mixture(fluid)
    # 0.25 m is exactly between nodes 0 and 1: MATLAB min selects first.
    np.testing.assert_array_equal(mix.KIDX(), [0,2,2,3])
    np.testing.assert_array_equal(mix.KIDX([2,3]), [2,2,3])
    np.testing.assert_array_equal(mix.KIDX(2), [2,2])
    np.testing.assert_array_equal(mix.KIDX(slice(3,None)), [3])
    np.testing.assert_array_equal(mix.KIDX(-2), [3])
    assert mix.KIDX(1).size == 0
    # Returned positions are actual computational-node positions in metres.
    np.testing.assert_array_equal(mix.KLOCZ(), [0,1,1,1.5])
    np.testing.assert_array_equal(mix.KLOCZ([2,3]), [1,1,1.5])


def test_transverse_exchange_units_conservation_and_scalar_wall_dimensions(fluid):
    mix = mixture(fluid)
    mix.MRM["WV"][:] = [.015,.015]  # total0.03kg/s, consistent with quality0.3
    rates = mix.MTRANSV()
    assert rates.shape == (5,2) and mix.MTRANSV(2).shape == (2,)
    assert mix.MTRANSV([1,3]).shape == (2,2)
    # Target flow [.0075,.0225]kg/s follows perimeter fractions[.25,.75].
    # Source is deltaW/(U_v * 0.01s), giving kg/(s m), not kg/s.
    transferred_flow = rates*mix.vapor.U()[:,None]*.01
    np.testing.assert_allclose(transferred_flow, np.tile([-.0075,.0075],(5,1)), rtol=3e-15, atol=1e-17)
    np.testing.assert_allclose(rates.sum(axis=1), 0, rtol=0, atol=2e-16)
    np.testing.assert_allclose(mix.MTRANSV([1,3]), rates[[1,3]])
    np.testing.assert_allclose(mix.MTRANSV(2), rates[2])
    mix.MRM["WV"][:] = [.0075,.0225]
    np.testing.assert_allclose(mix.MTRANSV(), 0, atol=2e-16)
    single = mixture(fluid,walls=1)
    single.MRM["WV"][:] = .03
    np.testing.assert_array_equal(single.MTRANSV(), np.zeros((5,1)))


def test_transverse_diagnostic_is_not_inserted_in_total_source(fluid):
    mix = mixture(fluid)
    before = mix.MTOT().copy()
    mix.MTRANSV = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Unused source was evaluated"))
    np.testing.assert_array_equal(mix.MTOT(), before)


def test_phase_coordinates_follow_parent_without_exposing_mutable_mesh(fluid):
    mix = mixture(fluid)
    for phase in (mix.liquid,mix.vapor):
        assert phase.TIME() == 2.5
        np.testing.assert_array_equal(phase.Z([1,3]), [.5,1.5])
        assert phase.Z(-1) == 2
        returned = phase.Z()
        returned[0] = 99
        assert mix.Z[0] == 0
    mix.TIME = 4.5
    assert mix.liquid.TIME() == mix.vapor.TIME() == 4.5


def test_twofluid_transition_forwarders_and_missing_cbt_model(fluid):
    mix = mixture(fluid)
    liquid = Liquid(mix.inputSet,fluid,mix.Z)
    vapor = Vapor(mix.inputSet,fluid,mix.Z)
    liquid.mix = vapor.mix = TwoFluidMixture(mix,liquid,vapor)
    for method in ("XTR_SUB","XTR_SAT","XTR_ITM","XTR_ANN"):
        assert getattr(vapor,method)(liquid) == getattr(liquid,method)()
    with pytest.raises(NotImplementedError,match="Liquid.XTR_CBT"):
        vapor.XTR_CBT(liquid)


def test_drop_reynolds_diagnostic_does_not_invent_missing_viscosity(fluid):
    mix = mixture(fluid)
    for cls in (Drop,FourFieldDrop):
        drop = cls(mix.inputSet,mix)
        with pytest.raises(NotImplementedError,match="undefined Drop.MU"):
            drop.RE(2)
        # The separate implemented vapor-relative Reynolds number remains usable.
        assert np.isfinite(drop.REV(2))
