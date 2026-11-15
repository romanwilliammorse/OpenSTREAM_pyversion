"""Stored two-fluid reference checks; physical-failure checks are intentional."""
import hashlib
import json

import numpy as np
import pytest

from recover_twofluid_reference import (
    ARCHIVE, ROOT, CORE, load_archive, phase_arrays, validate_object_graph,
    export_reference, physical_checks, convergence,
)
from audit_recovered_twofluid import audit


@pytest.fixture(scope="module")
def solver():
    return load_archive(ARCHIVE)["solver"]


def test_original_archive_unchanged_and_handle_relationships(solver):
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == "40f0c9a8f080d6ffe3887947dc5794eb756b5fa0e2ce650ff37a88003e69798d"
    links = validate_object_graph(solver)
    assert links["all_initial_groups_reference_physical_time_zero"]
    assert links["initial_phase_shared_group_links"] == 30


def test_exact_saved_arrays_and_node_time_dimensions(solver):
    actual = phase_arrays(solver)
    initial = phase_arrays(solver, "Init")
    for key in CORE:
        phase, name = key.split(".")
        np.testing.assert_array_equal(actual[key][0], solver.properties[phase].properties[name][:, 0])
        assert actual[key].shape == (1, 101)
        assert initial[key].shape == (15, 101)
        np.testing.assert_array_equal(initial[key][-1], actual[key][0])
    np.testing.assert_array_equal(initial["TIME"], np.arange(15.))


def test_convergence_uses_actual_final_initialization_residuals(solver):
    data = phase_arrays(solver, "Init")
    options = solver.properties["inputSet"].properties["options"].properties
    result = convergence(data, options)
    assert result["point_passed"] and result["temporal_passed"]
    data["liquid.ITR.DH"][-1, 20] = options["ERRORH"].item()
    assert not convergence(data, options)["point_passed"]  # Strict <, not <=.


def test_original_matlab_area_failure_is_preserved(solver):
    result = physical_checks(solver, phase_arrays(solver))
    assert result["max_occupied_area_relative_error"] == pytest.approx(0.410561070690042, abs=1e-13)
    assert result["worst_z_m"] == pytest.approx(0.22)
    # This assertion exposes the archived physical inconsistency; it is not
    # an acceptance condition for physically valid predictions.
    assert result["max_occupied_area_relative_error"] > 0.4


def test_complete_export_preserves_original_hashes_and_refuses_overwrite(tmp_path):
    before = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    out = tmp_path / "reference"
    manifest = export_reference(ARCHIVE, out)
    assert manifest["complete"] and manifest["reconstructed_methods"] == {}
    assert manifest["convergence"]["point_passed"]
    assert manifest["convergence"]["temporal_passed"]
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == before
    with pytest.raises(FileExistsError):
        export_reference(ARCHIVE, out)
    graph = json.loads((out / "object_graph.json").read_text())
    assert any(r["kind"] == "object_reference" and "liquidInit" in r["path"] for r in graph)


def test_wrong_framework_is_rejected(tmp_path):
    wrong = ARCHIVE.with_name("tutorial1_MixtureSolver.mat")
    with pytest.raises(ValueError, match="two-fluid"):
        export_reference(wrong, tmp_path / "wrong")


def test_fresh_native_core_and_embedded_precursor_match():
    result = audit(ROOT / "reference_exports/recovered-twofluid-01", ROOT / "outputs/baseline-parity-01/TwoFluidSolver")
    assert result["all_core_comparisons_passed"]
    assert len(result["physical"]["profiles"]) == 6
    assert len(result["precursor_physical"]["profiles"]) == 9
