"""Native equation/invariant checks, not MATLAB or experimental validation."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from openstream import InputSet
from openstream.fourfield import FourFieldSolver
from openstream.annular import Drop
from openstream.ff_fields import Film
from openstream.fields import Mixture
from openstream.properties import FluidProperties
from openstream.solver import SolverState


@pytest.fixture(scope="module")
def solver():
    return FourFieldSolver(InputSet.official_sample()).solve()


def test_original_inputs_converge_with_bounded_primary_fields(solver):
    assert solver.converged and solver.wave_frequency_converged
    f,d,m=solver.film[0],solver.drop[0],solver.mixSolver.mixture[0]
    for field in (f.base,f.wave,d):
        assert np.all(np.isfinite(field.W)) and np.all(field.W>=0)
        assert np.all(np.isfinite(field.U)) and np.all(field.U>0)
    assert np.all(np.isfinite(f.wave.FREQUENCY)) and np.all(f.wave.FREQUENCY>0)
    assert f.base.W.shape==f.wave.W.shape==(101,1)
    np.testing.assert_allclose(f.W.sum(axis=1)+d.W+m.vapor.W(),m.W,rtol=3e-15,atol=0)
    assert solver.history[-1]["point_converged"]
    assert all(d["converged"] for d in solver.onset_diagnostics)


def test_mass_exchanges_cancel_and_dimensions(solver):
    f,d=solver.film[0],solver.drop[0]
    for j in (20,50,80):
        # Internal base/wave transfer must cancel in the aggregate film mass
        # source, leaving only wall evaporation, entrainment and deposition.
        expected=f.MEVAP(j)+f.MENT(j)+d.MDEP(j)
        np.testing.assert_allclose(f.base.MTOT(d,j)+f.wave.MTOT(d,j),expected,atol=3e-14,rtol=3e-14)
        np.testing.assert_allclose(f.base.MEVAP(j)+f.wave.MEVAP(j),-f.HFLUX[j]/f.fluid.HFG)
        np.testing.assert_allclose(f.base.MDEP(d,j)+f.wave.MDEP(d,j),d.MDEP(j),rtol=3e-15)
        np.testing.assert_allclose(f.base.THICK(j),f.base.W[j]/(solver.inputSet.geometry.PERIM*f.fluid.RHOF*f.base.U[j]))
        np.testing.assert_allclose(f.wave.N(j)*f.wave.U[j],f.wave.FREQUENCY[j])
        np.testing.assert_allclose(f.wave.THICK(j),f.wave.AMPLITUDE(j)*f.wave.BETA(j))
        # Base-wave shear forces form an equal-and-opposite pair in N/m^2.
        np.testing.assert_allclose(f.base.FWAVE(d,j)+f.wave.FBASE(d,j),0,atol=0)


def test_matlab_min_nan_boundary_and_copy_semantics(solver):
    f=deepcopy(solver.film[0])
    j=70
    f.base.W[j]=f.wave.W[j]=0
    # MATLAB min(0/0,1) returns 1; NumPy minimum would return NaN.
    np.testing.assert_array_equal(f.EQUIL(np.zeros(1),j),[1])
    f.distributeOAFW(np.zeros(1),j)
    assert np.isfinite(f.W[j]).all()
    old=solver.filmInit[-1]
    assert old.base.film is old and old.wave.film is old
    assert old.base.mix is solver.film[0].mix
    assert not np.shares_memory(old.base.W,solver.film[0].base.W)
    dest=deepcopy(old)
    dest.base.W[0]=123
    dest.wave.FREQUENCY[0]=456
    old.copy_flow_properties(dest,all=True)  # source Film ignores opts.all
    assert dest.base.W[0,0]==123 and dest.wave.FREQUENCY[0,0]==456


def test_raw_residuals_report_clamping(solver):
    diagnostics=solver.diagnostics()
    assert diagnostics["nonfinite_state_count"]==0
    assert diagnostics["nested_closure_failures"]==[]
    assert diagnostics["all_fields_minus_mixture_max_kg_s"]<2e-17
    # Point convergence does not imply zero local residual after POSFILM.
    bound=solver.inputSet.options.ERRORWF*solver.inputSet.geometry.PERIM.max()*2
    assert diagnostics["base_mass_residual_max_kg_s"]>bound
    assert diagnostics["wave_mass_residual_max_kg_s"]>bound
    assert diagnostics["wave_unclamped_annular_mass_residual_max_kg_s"]<bound


def test_informational_area_residual_is_separate_from_numerical_convergence(solver):
    diagnostics = solver.diagnostics()
    assert solver.converged
    assert diagnostics["physical_consistency"] is None
    assert diagnostics["phase_volume_closure_role"] == "informational"
    assert diagnostics["area_closure_relative_tolerance"] is None
    assert diagnostics["phase_volume_closure_status"] == "reported"
    assert diagnostics["max_unblended_annular_area_closure_relative"] > 0.01
    f, d, m = solver.film[0], solver.drop[0], solver.mixSolver.mixture[0]
    # Independent four-field inventory, including both base and wave storage.
    liquid_inventory = np.sum(f.base.W/f.base.U+f.wave.W/f.wave.U, axis=1)+d.W/d.U
    occupied = liquid_inventory/f.fluid.RHOF+m.vapor.W()/m.vapor.U()/f.fluid.RHOV(m.vapor.H())
    annular = m.AFFNC() >= 1-1e-12
    error = np.max(abs(occupied[annular]/solver.inputSet.geometry.AREA-1))
    assert diagnostics["max_unblended_annular_area_closure_relative"] == pytest.approx(error, rel=1e-13)


def test_frequency_and_nested_failure_flags_are_not_hidden(solver):
    original=solver.wave_frequency_converged
    solver.wave_frequency_converged=False
    assert not solver.converged
    solver.wave_frequency_converged=original
    failures=solver.film[0].base.inner_failures
    failures.append({"model":"synthetic failure"})
    assert not solver.converged
    failures.pop()
    assert solver.converged


def test_indeterminate_area_inventory_remains_informational(solver,monkeypatch):
    drop=solver.drop[0]
    flow,speed=drop.W.copy(),drop.U.copy()
    flow[-1]=speed[-1]=0.
    monkeypatch.setattr(drop,'W',flow)
    monkeypatch.setattr(drop,'U',speed)
    diagnostics=solver.diagnostics()
    assert diagnostics['physical_consistency'] is None
    assert diagnostics['phase_volume_closure_role']=='informational'
    assert diagnostics['phase_volume_closure_status']=='indeterminate'
    assert diagnostics['inventory_by_time'][0]['nonfinite_unblended_annular_node_count']==1
    assert np.isinf(diagnostics['max_unblended_annular_area_closure_relative'])
    assert solver.converged


def test_zero_relaxation_rejected():
    obj=FourFieldSolver.__new__(FourFieldSolver)
    obj.inputSet=InputSet.official_sample().for_solver("FourField")
    obj.inputSet.model.RELAXTW=0
    with pytest.raises(ValueError,match="positive"):
        obj.initialize_solver()


def test_fourfield_portable_output(solver,tmp_path):
    solver.save(tmp_path/"case")
    with np.load(tmp_path/"case"/"results.npz") as arrays:
        assert arrays["film.base.W"].shape==(1,101,1)
        assert arrays["film.wave.FREQUENCY"].shape==(1,101,1)
    with np.load(tmp_path/"case"/"initialization.npz") as arrays:
        assert "film.wave.ITR.DF" in arrays
        assert np.isnan(arrays["film.wave.ITR.DF"][0]).all()
        assert np.max(arrays["film.wave.ITR.DF"][-1]) <= solver.inputSet.options.ERRORFW
    assert (tmp_path/"case"/"wave_frequency.png").stat().st_size > 100


def unequal_precursor_fields():
    """Two-node algebraic fixture with equal primary but unequal cached state.

    The synthetic cache separation exercises handle selection; it is not a
    physical calculation or a replacement closure model.
    """
    inputs = InputSet.official_sample().for_solver("FourField")
    inputs.model.NNODES = 1
    inputs.model.OAFFILMSPLIT, inputs.model.OAFBASERATIO = "RATIO", .5
    inputs.model.MOMENTBASE, inputs.model.MOMENTWAVE = "FULLNOP", "FULL"
    inputs.model.WAVEFREQUENCY = "EQUILIBRIUM"
    inputs.model.THINFILMTHICK = 1e-4
    inputs.options.MAXITER = 1
    inputs.options.RELAXUB, inputs.options.RELAXUW = .2, .4
    # One controlled update; convergence is not the assertion in this fixture.
    for key in ("ERRORWF", "ERRORUF", "ERRORFW", "ERRORUD"):
        setattr(inputs.options, key, 1e6)
    fluid = FluidProperties(7e6, inputs.model)
    physical = Mixture(inputs, fluid, [0., 1.])
    physical.W[:] = .01
    physical.H[:] = fluid.HF + .5*fluid.HFG
    physical.xeq[:] = .5
    physical.x[:], physical.vf[:] = .25, .5
    physical.oafidx_const, physical.sigm_const = 0, np.full(2, .25)
    initialized = deepcopy(physical)
    initialized.x[:], initialized.vf[:] = .5, .75
    initialized.sigm_const[:] = .75
    film, drop = Film(inputs, initialized), Drop(inputs, initialized)
    film.base.mix = film.wave.mix = physical
    film.base.W[:] = film.wave.W[:] = .001  # kg/s per wall
    film.base.U[:], film.wave.U[:], drop.U[:] = 2., 3., 4.  # m/s
    film.wave.FREQUENCY[:] = 10.  # Hz
    old_film, old_drop = deepcopy((film, drop))
    obj = FourFieldSolver.__new__(FourFieldSolver)
    obj.inputSet, obj.NZ, obj.DZ = inputs, 2, 1.
    return obj, physical, initialized, old_film, old_drop, film, drop


@pytest.mark.parametrize("drop_momentum", ["FULL", "SLIP"])
def test_outer_sweep_uses_physical_precursor_without_rebinding_closures(monkeypatch, drop_momentum):
    obj, physical, initialized, old_film, old_drop, film, drop = unequal_precursor_fields()
    obj.inputSet.model.MOMENTDROP = drop_momentum
    for phase in (film.base, film.wave):
        # Zero mass source keeps each field at 0.001 kg/s. A positive force
        # makes both momentum candidates hit their upstream velocity bounds.
        monkeypatch.setattr(phase, "MTOT", lambda drop, j: np.zeros(1))
        monkeypatch.setattr(phase, "FTOT", lambda drop, j: np.full(1, 1e6))
        monkeypatch.setattr(phase, "THICK", lambda j: np.full(1, 1e-3))
    monkeypatch.setattr(film.wave, "EQFREQUENCY", lambda j: np.full(1, 10.))
    monkeypatch.setattr(drop, "FTOT", lambda film, j: 0.)
    for key in ("W", "P", "H"):
        np.testing.assert_array_equal(getattr(physical, key), getattr(initialized, key))
    assert physical.liquid.U(1) != initialized.liquid.U(1)
    assert physical.vapor.U(1) != initialized.vapor.U(1)
    assert physical.liquid.W(1) != initialized.liquid.W(1)

    obj._advance(old_film, old_drop, film, drop, sweep_mix=physical)

    # These expectations follow MATLAB solve.m's local physical precursor.
    # r=1/4; base relaxation=1/5; wave relaxation=2/5.
    ul, uv = physical.liquid.U(1), physical.vapor.U(1)
    assert film.base.U[1, 0] == pytest.approx(.75*ul + .25*(1.6 + .2*ul))
    assert film.wave.U[1, 0] == pytest.approx(.75*ul + .25*(1.8 + .4*uv))
    assert drop.W[1] == pytest.approx(.0075 - .002, rel=1e-14)
    if drop_momentum == "FULL":
        assert drop.U[1] == pytest.approx(.75*ul + .25*4.)
    else:
        # The SLIP closure intentionally reads its own final-init precursor.
        expected = .25*initialized.liquid.U(1) + .75*obj.inputSet.model.DROPSLIP*initialized.vapor.U(1)
        assert drop.U[1] == pytest.approx(expected)
    assert film.mix is initialized and drop.mix is initialized
    assert film.base.mix is physical and film.wave.mix is physical
    assert film.base.film is film and film.wave.film is film


def test_solve_selects_time_zero_for_initialization_and_current_transient_precursor(monkeypatch):
    obj, physical, initialized, old_film, old_drop, film, drop = unequal_precursor_fields()
    physical1, physical2 = deepcopy(physical), deepcopy(physical)
    physical1.x[:] = .3
    physical2.x[:] = .4
    precursors = [physical, physical1, physical2]
    obj.mixSolver = SimpleNamespace(mixture=precursors)
    obj.film = [Film(obj.inputSet, mix) for mix in precursors]
    obj.drop = [Drop(obj.inputSet, mix) for mix in precursors]
    obj.filmInit, obj.dropInit = [old_film, film], [old_drop, drop]
    obj.STATE, obj.NTIME = SolverState.UNSOLVED, 3
    observed = []

    def observe(old_film, old_drop, film, drop, *, sweep_mix):
        observed.append((film, sweep_mix))
        return True, np.zeros(6)

    monkeypatch.setattr(obj, "_advance", observe)
    monkeypatch.setattr(obj, "_record", lambda *args: None)
    obj.solve()
    assert len(observed) == 3
    for (field, actual), expected in zip(observed, precursors):
        assert actual is expected
    assert observed[0][0] is film and film.mix is initialized
    assert observed[1][0] is obj.film[1] and observed[2][0] is obj.film[2]
