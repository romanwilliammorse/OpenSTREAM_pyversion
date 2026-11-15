"""Analytic tests of independent transient-audit arithmetic, without rerunning a case."""
import importlib.util
from pathlib import Path
import numpy as np
from types import SimpleNamespace
from openstream.threefield import ThreeFieldSolver


spec = importlib.util.spec_from_file_location("threefield_audit", Path(__file__).parents[1]/"tools/verify_threefield_transient.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def test_film_transient_mass_storage_and_multiple_wall_units():
    # kg/s flow, m/s speed, m perimeter: steady accumulation plus storage
    # requires the source below in kg/(m² s), independently per wall.
    w = np.array([[.02, .03], [.03, .05], [.04, .06]])
    previous = w*.8
    velocity = np.full_like(w, 2.)
    perimeter, dz, dt = np.array([.1, .2]), .5, .25
    source = (np.diff(w, axis=0)+dz/dt*(w[1:]-previous[1:])/2)/(perimeter*dz)
    residual = audit.film_mass_residual(w, previous, velocity, velocity, source, perimeter, dz, dt)
    np.testing.assert_allclose(residual, 0, atol=7e-18)
    no_source = audit.film_mass_residual(w, previous, velocity, velocity, np.zeros_like(source), perimeter, dz, dt)
    np.testing.assert_allclose(no_source, [[.016, .030], [.018, .022]], rtol=1e-14)


def test_momentum_material_derivative_with_time_and_space_terms():
    u, previous = np.array([2., 3., 4.]), np.array([1., 2., 3.])
    # u*du/dz + du/dt: 3*2+4 =10 and 4*2+4 =12 m/s².
    residual = audit.material_momentum_residual(u, previous, np.array([10., 12.]), .5, .25)
    np.testing.assert_array_equal(residual, np.zeros(2))


def test_maximum_does_not_hide_nan_or_empty_applicability():
    assert audit.maxabs(np.array([0., -3.])) == 3
    assert audit.maxabs(np.ones((2, 2)), np.zeros((2, 1), dtype=bool)) is None
    assert np.isnan(audit.maxabs(np.array([0., np.nan])))


def test_fixed_annular_control_volume_storage_does_not_include_preonset():
    # Two 1 m cells, only the downstream cell and both its faces annular.
    # Drop speed doubles2->4m/s at unchanged.02kg/s: downstream inventory
    # decreases by.005kg in.25s, giving-.02kg/s net mass residual.
    fluid = SimpleNamespace(RHOF=1000., RHOV=lambda h: np.full(3, 10.))
    vapor = SimpleNamespace(W=lambda: np.full(3, .02), U=lambda: np.full(3, 10.), H=lambda: np.ones(3))
    mixes = [SimpleNamespace(vapor=vapor, AFFNC=lambda: np.array([0., 1., 1.])) for _ in range(2)]
    films = [SimpleNamespace(W=np.full((3, 1), .03), U=np.full((3, 1), 2.), fluid=fluid, DT=.25) for _ in range(2)]
    drops = [SimpleNamespace(W=np.full(3, .02), U=np.full(3, u)) for u in (2., 4.)]
    obj = SimpleNamespace(inputSet=SimpleNamespace(geometry=SimpleNamespace(AREA=.000225)),
                          film=films, drop=drops, mixSolver=SimpleNamespace(mixture=mixes),
                          NZ=3, Z=np.array([0., 1., 2.]), DZ=1., TIME=np.array([0., .25]))
    result = ThreeFieldSolver._physical_inventory_diagnostics(obj)
    assert result["common_annular_cell_count"] == 1
    assert result["common_annular_upstream_face_z_m"] == 1
    last = result["inventory_by_time"][1]
    np.testing.assert_allclose(last["common_annular_mass_residual_kg_s"], -.02, rtol=1e-14)
    np.testing.assert_allclose(last["global_all_phase_mass_residual_kg_s"], -.04, rtol=1e-14)
