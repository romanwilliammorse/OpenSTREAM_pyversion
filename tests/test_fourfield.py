"""Native equation/invariant checks, not MATLAB or experimental validation."""
from copy import deepcopy
import numpy as np
import pytest
from openstream import InputSet
from openstream.fourfield import FourFieldSolver


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


def test_physical_area_failure_is_separate_from_numerical_convergence(solver):
    diagnostics = solver.diagnostics()
    assert solver.converged
    assert diagnostics["physical_consistency"] is False
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
