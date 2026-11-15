import numpy as np
import pytest
from openstream import InputSet, MixtureSolver
from openstream.threefield import ThreeFieldSolver
from openstream.annular import Film, Drop


@pytest.fixture(scope="module")
def solver():
    return ThreeFieldSolver(InputSet.official_sample()).solve()


def test_original_sample_converges_and_partitions_mass(solver):
    assert solver.converged
    film, drop, mix = solver.film[0], solver.drop[0], solver.mixSolver.mixture[0]
    np.testing.assert_allclose(film.W.sum(axis=1)+drop.W, mix.liquid.W(), rtol=2e-15)
    np.testing.assert_allclose(film.W.sum(axis=1)+drop.W+mix.vapor.W(), mix.W, rtol=2e-15)
    assert np.all(film.W >= 0) and np.all(drop.W >= 0)
    assert np.all(film.U > 0) and np.all(drop.U > 0)
    assert film.W.shape == (101, 1) and drop.W.shape == (101,)
    assert solver.onset_diagnostics[0]["converged"]
    assert not np.shares_memory(solver.filmInit[-1].W, solver.film[0].W)


def test_annular_force_dimensions_and_mass_sources(solver):
    film, drop, mix = solver.film[0], solver.drop[0], solver.mixSolver.mixture[0]
    g, f = solver.inputSet.geometry, solver.fluid[0]
    j = 70
    # tau/rho has dimensions velocity squared; W/(perimeter*rho*U) is metres.
    np.testing.assert_allclose(film.THICK(j), film.W[j]/(g.PERIM*f.RHOF*film.U[j]))
    np.testing.assert_allclose(film.FWALL(j), -.5*film.CW(j)*f.RHOF*film.U[j]**2)
    np.testing.assert_allclose(film.MEVAP(j)*f.HFG, -film.HFLUX[j])
    assert np.all(film.MENT(j) <= 0) and drop.MDEP(j) >= 0
    np.testing.assert_allclose(drop.AREA(j)/drop.VOLUME(j), 6/drop.DIAM(j))
    # Full film mass equation residual after the final pseudo-time sweep.
    cur, prev = solver.filmInit[-1], solver.filmInit[-2]
    dcur = solver.dropInit[-1]
    # The solver evaluates the iterative Okawa closure pointwise. A vector
    # diagnostic has a different global ENTNUM stopping test upstream.
    sources = np.stack([cur.MTOT(dcur, j) for j in range(1, solver.NZ)])
    residual = cur.W[1:]-cur.W[:-1]+solver.DZ/cur.DT*(cur.W[1:]/cur.U[1:]-prev.W[1:]/prev.U[1:])-g.PERIM*sources*solver.DZ
    # POSFILM imposes W>=0 after the equation update. The unconstrained
    # equation fails at dryout; retain and expose that upstream consequence.
    bound = solver.inputSet.options.ERRORWF*np.max(g.PERIM)*2
    positive = cur.W[1:] > 0
    assert np.max(abs(residual[positive])) < bound
    assert np.all(residual[~positive] >= -bound)
    assert np.max(residual[~positive]) > bound


def test_explicit_broken_drag_option():
    inputs = InputSet.official_sample()
    inputs.model.DROPDRAG = "DISTORDED"
    with pytest.raises(NotImplementedError, match="undefined"):
        ThreeFieldSolver(inputs)


def test_annular_area_residual_is_informational_independently_of_convergence(solver):
    diagnostic = solver._physical_inventory_diagnostics()
    assert solver.converged
    assert diagnostic["physical_consistency"] is None
    assert diagnostic["phase_volume_closure_role"] == "informational"
    assert diagnostic["area_closure_relative_tolerance"] is None
    assert diagnostic["phase_volume_closure_status"] == "reported"
    assert diagnostic["max_unblended_annular_area_closure_relative"] > .01
    film, drop, mix = solver.film[0], solver.drop[0], solver.mixSolver.mixture[0]
    occupied = (film.W/film.U).sum(axis=1)/film.fluid.RHOF+drop.W/(drop.U*film.fluid.RHOF)+mix.vapor.W()/(mix.vapor.U()*film.fluid.RHOV(mix.vapor.H()))
    np.testing.assert_allclose(diagnostic["max_area_closure_relative"], np.max(abs(occupied/solver.inputSet.geometry.AREA-1)))
    assert diagnostic["inventory_by_time"][0]["nonfinite_inventory_or_area_node_count"] == 0


def test_informational_area_diagnostic_respects_annular_applicability(solver, monkeypatch):
    mix = solver.mixSolver.mixture[0]
    monkeypatch.setattr(mix, "sigm_const", np.zeros(solver.NZ))
    diagnostic = solver._physical_inventory_diagnostics()
    assert diagnostic["physical_consistency"] is None
    assert diagnostic["phase_volume_closure_role"] == "informational"
    assert diagnostic["phase_volume_closure_status"] == "no_applicable_region"
    assert diagnostic["max_unblended_annular_area_closure_relative"] is None
    assert diagnostic["common_annular_cell_count"] == 0
    assert diagnostic["max_common_annular_cell_mass_residual_kg_s"] is None


def test_zero_over_zero_annular_inventory_remains_indeterminate(solver, monkeypatch):
    drop = solver.drop[0]
    w, u = drop.W.copy(), drop.U.copy()
    w[-1], u[-1] = 0, 0
    monkeypatch.setattr(drop, "W", w)
    monkeypatch.setattr(drop, "U", u)
    diagnostic = solver._physical_inventory_diagnostics()
    assert diagnostic["physical_consistency"] is None
    assert diagnostic["phase_volume_closure_status"] == "indeterminate"
    assert diagnostic["phase_volume_closure_role"] == "informational"
    assert diagnostic["inventory_by_time"][0]["nonfinite_unblended_annular_node_count"] == 1
    assert np.isinf(diagnostic["max_unblended_annular_area_closure_relative"])
    assert solver.converged  # Reporting an indeterminate diagnostic adds no gate.


def test_annular_portable_output(solver, tmp_path):
    solver.save(tmp_path/"case")
    with np.load(tmp_path/"case"/"results.npz") as data:
        assert data["film.W"].shape == (1, 101, 1)
        assert data["drop.U"].shape == (1, 101)
