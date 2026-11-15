"""Transient balance and physical limit tests, independent of MATLAB references."""
import numpy as np
import pytest

from openstream import InputSet, MixtureSolver
from tools.verify_sensitivity import make_adiabatic, make_multiwall, make_transient, physical_bounds, transient_balances


@pytest.fixture(scope="module")
def transient():
    inputs = make_transient(nodes=25, timestep=.25)
    # These are convergence controls, not altered physical-model coefficients.
    inputs.options.ERRORW = 1e-7
    inputs.options.ERRORP = 1e-3
    inputs.options.ERRORH = 1e-3
    return MixtureSolver(inputs).solve()


def test_full_original_transient_boundary_schedule_and_bounds(transient):
    assert transient.converged
    assert transient.NTIME == 21
    assert transient.TIME[0] == 0 and transient.TIME[-1] == 5
    np.testing.assert_allclose(transient.boundaryConditions["POWER"][:5], np.linspace(87500, 43750, 5), atol=1e-9)
    np.testing.assert_allclose(transient.boundaryConditions["POWER"][4:], 43750, atol=1e-9)
    for k, m in enumerate(transient.mixture):
        assert m.W[0] == .07 and m.H[0] == 1.1394e6 and m.P[0] == 6e6
        np.testing.assert_allclose(np.sum(m.LHGR()[1:])*transient.DZ, transient.boundaryConditions["POWER"][k], rtol=2e-15)
    bounds = physical_bounds(transient)
    assert bounds["all_finite"]
    assert bounds["min_pressure_Pa"] > 0 and bounds["min_density_kg_m3"] > 0
    assert bounds["min_mass_flow_kg_s"] > 0
    assert 0 <= bounds["min_quality"] <= bounds["max_quality"] <= 1
    assert 0 <= bounds["min_void"] <= bounds["max_void"] <= 1
    assert bounds["max_phase_mass_split_error_kg_s"] < 1e-14
    assert transient.mixture[-1].H[-1] < transient.mixture[0].H[-1]


def test_transient_discrete_balances_and_product_rule_identity(transient):
    rows = transient_balances(transient)
    assert len(rows) == 20
    assert max(r["mass_max_residual_kg_s"] for r in rows) < 1e-8
    assert max(r["energy_equation_max_residual_W_per_m"] for r in rows) < .01
    assert max(r["momentum_max_residual_Pa"] for r in rows) < transient.inputSet.options.ERRORP
    # Conservative and advective discrete equations are distinct: verify the
    # derived product identity, not a false claim of exact total-energy balance.
    assert max(abs(r["product_identity_residual_W"]) for r in rows) < 1e-6
    assert max(abs(r["conservative_enthalpy_defect_W"]) for r in rows) > 0


def test_adiabatic_subcooled_flow_has_analytic_pressure_drop():
    solver = MixtureSolver(make_adiabatic(nodes=25)).solve()
    assert solver.converged
    m, g, f = solver.mixture[0], solver.inputSet.geometry, solver.fluid[0]
    np.testing.assert_allclose(m.H, m.H[0], rtol=0, atol=1e-7)
    np.testing.assert_allclose(m.W, .07, rtol=0, atol=1e-12)
    np.testing.assert_array_equal(m.X(), np.zeros(solver.NZ))
    np.testing.assert_array_equal(m.VF(), np.zeros(solver.NZ))
    reynolds = 4*.07/(g.PERIM.sum()*f.MUF)
    darcy = .2*reynolds**-.2
    expected_drop = f.RHOF*9.81*g.LENGTH + darcy*g.LENGTH/g.HDIAM()*(.07/g.AREA)**2/(2*f.RHOF)
    np.testing.assert_allclose(m.P[0]-m.P[-1], expected_drop, rtol=1e-10, atol=1e-6)


def test_multiwall_partition_preserves_total_mixture_balance():
    single_inputs = InputSet.official_sample()
    single_inputs.model.NNODES = 25
    one = MixtureSolver(single_inputs).solve()
    two = MixtureSolver(make_multiwall(nodes=25)).solve()
    assert one.converged and two.converged
    assert two.mixture[0].HFLUX.shape == (26, 2)
    np.testing.assert_allclose(two.mixture[0].HFLUX[:, 1], 2*two.mixture[0].HFLUX[:, 0], rtol=1e-14)
    for name in ("W", "P", "H"):
        np.testing.assert_allclose(getattr(two.mixture[0], name), getattr(one.mixture[0], name), rtol=1e-11, atol=1e-7)
    np.testing.assert_allclose(np.sum(two.mixture[0].LHGR()[1:])*two.DZ, 87500, rtol=2e-15)
