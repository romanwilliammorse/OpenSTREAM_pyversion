"""Independent integration/semantics checks; not MATLAB-reference comparisons."""
import numpy as np
import pytest

from openstream import InputSet, MixtureSolver, SolverState, TwoFluidSolver, ThreeFieldSolver, FourFieldSolver
from openstream.numerics import colon, interpolate
from openstream.output import balances


@pytest.fixture(scope="module")
def sample():
    return MixtureSolver(InputSet.official_sample()).solve()


def test_sample_convergence_inlet_and_conservation(sample):
    assert sample.STATE == SolverState.INITIALSTEPCONVERGED
    assert sample.converged
    m = sample.mixture[0]
    assert (m.W[0], m.P[0], m.H[0]) == (0.07, 6e6, 1.1394e6)
    assert len(m.Z) == 101 and m.HFLUX.shape == (101, 1)
    b = balances(sample)
    # Same energy criterion as upstream integration suite (not regression).
    np.testing.assert_allclose(m.H[-1], 1.1394e6 + 87500 / 0.07, rtol=1e-3, atol=1e-6)
    np.testing.assert_allclose(b["discrete_wall_power_W"], 87500, rtol=1e-14)
    assert b["steady_mass_max_deviation_kg_s"] < 1e-7
    assert b["discrete_mass_max_residual_kg_s"] < 1e-7
    assert b["discrete_energy_max_residual_W_per_m"] < 0.1
    assert b["discrete_momentum_max_residual_Pa"] < sample.inputSet.options.ERRORP
    assert np.all((m.VF() >= 0) & (m.VF() <= 1))
    assert np.all((m.X() >= 0) & (m.X() <= 1))
    assert np.all(m.RHO() > 0) and np.all(m.P > 0)
    np.testing.assert_allclose(m.liquid.W()+m.vapor.W(), m.W, rtol=2e-15)
    for key in ("W", "P", "H"):
        np.testing.assert_array_equal(getattr(sample.mixtureInit[-1], key), getattr(m, key))


def test_independent_state_and_reinitialization(sample):
    a, b = sample.mixtureInit[-2:]
    assert not np.shares_memory(a.H, b.H)
    assert not np.shares_memory(a.MRM["WV"], b.MRM["WV"])
    with pytest.raises(RuntimeError, match="Reinitialize"):
        sample.solve()


def test_output_portable_and_no_overwrite(sample, tmp_path):
    target = tmp_path/"case"
    sample.save(target)
    import json
    meta = json.loads((target/"metadata.json").read_text())
    assert meta["converged"]
    assert meta["units"]["H"] == "J/kg"
    with np.load(target/"results.npz", allow_pickle=False) as data:
        assert data["H"].shape == (1, 101)
        assert data["HFLUX"].shape == (1, 101, 1)
    for filename in ("profiles.csv", "wall_profiles.csv", "convergence.csv", "axial.png", "initialization.npz"):
        assert (target/filename).stat().st_size > 100
    with pytest.raises(FileExistsError):
        sample.save(target)


def test_nonconvergence_is_explicit():
    s = InputSet.official_sample()
    s.options.SSMAXITER = 2
    solver = MixtureSolver(s).solve()
    assert solver.STATE == SolverState.INITIALSTEPNOTCONVERGED
    assert not solver.converged


def test_interpolation_shape_endpoint_and_midpoint_semantics():
    np.testing.assert_allclose(colon(0, .1, .3), [0, .1, .2, .3], atol=1e-15)
    np.testing.assert_array_equal(interpolate([0, 1], [2, 4], [.5], "nearest"), [4])
    np.testing.assert_array_equal(interpolate([3.5, 5.5], [[1, 2], [0, 0]], [0, 3.5, 3.6], "next", True), [[1, 2], [1, 2], [0, 0]])


def test_unsupported_model_does_not_substitute():
    inputs = InputSet.official_sample()
    inputs.model.SPHTM = "DITTUSBOELTERGEN"
    with pytest.raises(NotImplementedError):
        MixtureSolver(inputs)
