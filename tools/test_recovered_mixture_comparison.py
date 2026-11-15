"""Adversarial checks of archived-reference acceptance, separate from physics."""
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from verify_recovered_mixture import difference, compare_arrays, validate_reference, compare_effective_inputs, CORE

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "outputs/mixture-baseline-recovery/native-before"


def test_relative_policy_and_exact_reference_zeros():
    assert difference(np.array([0., 1.]), np.array([0., 1. + 0.5e-8]))["passed"]
    assert not difference(np.array([0., 1.]), np.array([1e-30, 1.]))["passed"]
    assert not difference(np.array([0., 1.]), np.array([0., 1. + 2e-8]))["passed"]


@pytest.mark.parametrize("reference,native", [
    (np.zeros((2, 1)), np.zeros(2)),
    (np.array([np.nan]), np.array([np.nan])),
    (np.array([np.inf]), np.array([np.inf])),
    (np.array([]), np.array([])),
])
def test_invalid_numeric_comparisons_rejected(reference, native):
    with pytest.raises(ValueError):
        difference(reference, native)


def fixture_arrays():
    # Synthetic acceptance fixture, never an upstream reference.
    return {"Z": np.array([0., 1.]), "TIME": np.array([0.]),
            **{key: np.array([[0., 1.]]) for key in CORE}}


@pytest.mark.parametrize("mutation", ["missing", "transpose", "grid", "time", "nan"])
def test_missing_fields_axes_and_nonfinite_rejected(tmp_path, mutation):
    ref, native = fixture_arrays(), fixture_arrays()
    if mutation == "missing":
        native.pop("vapor.H")
    elif mutation == "transpose":
        native["W"] = native["W"].T
    elif mutation == "grid":
        native["Z"][1] = 1.01
    elif mutation == "time":
        native["TIME"] = np.array([0., 1.])
    else:
        native["H"][0, 1] = np.nan
    np.savez(tmp_path / "ref.npz", **ref)
    np.savez(tmp_path / "native.npz", **native)
    with pytest.raises(ValueError):
        compare_arrays(tmp_path / "ref.npz", tmp_path / "native.npz")


def test_reports_diagnostic_disagreement_without_hiding_it(tmp_path):
    ref, native = fixture_arrays(), fixture_arrays()
    ref["ITR.DH"], native["ITR.DH"] = np.array([[0., 1e-10]]), np.array([[0., 2e-10]])
    np.savez(tmp_path / "ref.npz", **ref)
    np.savez(tmp_path / "native.npz", **native)
    result = compare_arrays(tmp_path / "ref.npz", tmp_path / "native.npz")
    assert result["core_passed"]
    assert result["supplemental_failures"] == ["ITR.DH"]


def test_actual_reference_hash_units_and_tampering(tmp_path):
    directory = ROOT / "reference_exports/recovered-mixture-02"
    manifest = json.loads((directory / "manifest.json").read_text())
    native_meta = json.loads((NATIVE / "metadata.json").read_text())
    validate_reference(directory, manifest, native_meta)
    bad = json.loads(json.dumps(manifest))
    bad["units"]["H"] = "kJ/kg"
    with pytest.raises(ValueError, match="Unit"):
        validate_reference(directory, bad, native_meta)
    copy = tmp_path / "copy"
    shutil.copytree(directory, copy)
    with (copy / "results.npz").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_reference(copy, manifest, native_meta)


def test_actual_archived_baseline_all_nine_and_initialization():
    directory = ROOT / "reference_exports/recovered-mixture-02"
    for name in ("results.npz", "initialization.npz"):
        result = compare_arrays(directory / name, NATIVE / name)
        assert result["core_passed"], result["core"]
        assert len(result["core"]) == 9


@pytest.mark.parametrize("changed", ["MFLOW", "KLOSS", "CBTMULT"])
def test_actual_input_changes_cannot_pass(changed):
    directory = ROOT / "reference_exports/recovered-mixture-02"
    manifest = json.loads((directory / "manifest.json").read_text())
    native = json.loads((NATIVE / "metadata.json").read_text())
    assert compare_effective_inputs(directory, manifest, native)["passed"]
    if changed == "MFLOW":
        native["inputs"]["bc"][0]["MFLOW"] = 0.08
    elif changed == "KLOSS":
        native["inputs"]["model"]["KLOSS"] = [0.001]
    else:
        native["function_samples"]["model.CBTMULT"][0] = 2
    with pytest.raises(ValueError):
        compare_effective_inputs(directory, manifest, native)
