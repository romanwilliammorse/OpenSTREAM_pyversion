"""Adversarial framework-comparison tests; synthetic fixtures are not references."""
import copy
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from verify_recovered_framework import (FIELDS, EXTRA, UNITS, compare_phase,
                                       check_convergence, validate, compare)

ROOT = Path(__file__).resolve().parents[1]


def case(framework):
    reference = ROOT / f"reference_exports/recovered-{framework.lower()}-01"
    native = ROOT / f"outputs/baseline-parity-01/{framework}Solver"
    manifest = json.loads((reference / "manifest.json").read_text())
    metadata = json.loads((native / "metadata.json").read_text())
    return reference, native, manifest, metadata


def synthetic_arrays(framework):
    data = {"Z": np.array([0., 1.]), "TIME": np.array([0.])}
    keys = [p + "." + k for p in FIELDS[framework] for k in ("W", "U", "H")]
    keys += list(EXTRA.get(framework, ()))
    units = {}
    for key in keys:
        shape = (1, 2, 1) if key.startswith("film.") else (1, 2)
        data[key] = np.ones(shape)
        units[key] = UNITS[key.rsplit(".", 1)[-1]]
    return data, units


def save_pair(tmp_path, a, b):
    ref, native = tmp_path / "reference.npz", tmp_path / "native.npz"
    np.savez(ref, **a)
    np.savez(native, **b)
    return ref, native


@pytest.mark.parametrize("framework", ["TwoFluid", "ThreeField", "FourField"])
def test_synthetic_scope_and_exact_zero(framework, tmp_path):
    a, units = synthetic_arrays(framework)
    b = copy.deepcopy(a)
    key = next(k for k in a if k.endswith(".W"))
    a[key].flat[0] = 0
    b[key].flat[0] = 1e-30
    ref, native = save_pair(tmp_path, a, b)
    report = compare_phase(ref, native, framework, units)
    assert not report["core_passed"]
    assert report["core"][key]["nonmatching_reference_zeros"] == 1
    assert len(report["core"]) == (9 if framework == "FourField" else 6)


@pytest.mark.parametrize("key", ["film.base.W", "film.base.U", "film.base.H", "film.wave.FREQUENCY"])
def test_fourfield_extra_cannot_silently_pass_or_be_called_original(key, tmp_path):
    a, units = synthetic_arrays("FourField")
    b = copy.deepcopy(a)
    b[key].flat[1] += 2e-8
    ref, native = save_pair(tmp_path, a, b)
    report = compare_phase(ref, native, "FourField", units)
    assert report["core_passed"]
    assert not report["expanded_passed"]
    assert key in report["expanded"] and key not in report["core"]


@pytest.mark.parametrize("mutation", ["missing", "wall_axis", "transposed", "grid", "time", "nonfinite"])
def test_core_shape_missing_and_coordinate_failures(mutation, tmp_path):
    a, units = synthetic_arrays("FourField")
    b = copy.deepcopy(a)
    if mutation == "missing":
        b.pop("film.base.H")
    elif mutation == "wall_axis":
        b["film.W"] = b["film.W"][:, :, 0]
    elif mutation == "transposed":
        b["drop.W"] = b["drop.W"].T
    elif mutation == "grid":
        b["Z"][1] += 1e-4
    elif mutation == "time":
        b["TIME"][0] = 1
    else:
        b["film.wave.U"].flat[1] = np.nan
    ref, native = save_pair(tmp_path, a, b)
    with pytest.raises(ValueError):
        compare_phase(ref, native, "FourField", units)


@pytest.mark.parametrize("bad_value", [np.nan, np.inf, -np.inf])
def test_matching_undefined_diagnostics_require_explicit_absence(bad_value, tmp_path):
    a, units = synthetic_arrays("ThreeField")
    a["film.ITR.DWL"] = np.full((1, 2, 1), bad_value)
    units["film.ITR.DWL"] = "kg/s/m"
    ref, native = save_pair(tmp_path, a, copy.deepcopy(a))
    try:
        result = compare_phase(ref, native, "ThreeField", units)
    except ValueError:
        return
    assert not result["diagnostics"]["film.ITR.DWL"]["passed"]


@pytest.mark.parametrize("field,value", [
    ("wrapper_commit", "wrong"),
    ("gravity", 9.80),
    ("point_units", "kg/s"),
    ("core_units", "kJ/kg"),
    ("framework", "FourField"),
])
def test_wrong_provenance_and_units_rejected(field, value):
    ref, native, manifest, metadata = case("ThreeField")
    if field == "gravity":
        metadata["constants"]["model.G"] = value
    elif field == "point_units":
        metadata["units"]["film.ITR.DWL"] = value
    elif field == "core_units":
        metadata["units"]["film.H"] = value
    else:
        metadata[field] = value
    with pytest.raises(ValueError):
        validate(ref, native, manifest, metadata)


@pytest.mark.parametrize("name", ["mixture/results.npz", "mixture/initialization.npz", "mixture/manifest.json"])
def test_precursor_integrity_records_required(name):
    ref, native, manifest, metadata = case("TwoFluid")
    manifest["files"].pop(name)
    with pytest.raises(ValueError):
        validate(ref, native, manifest, metadata)


def test_original_and_extracted_hashes_rejected(tmp_path):
    ref, native, manifest, metadata = case("TwoFluid")
    original = copy.deepcopy(manifest)
    manifest["archive"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="archive hash"):
        validate(ref, native, manifest, metadata)
    copied = tmp_path / "reference"
    shutil.copytree(ref, copied)
    with (copied / "mixture/results.npz").open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate(copied, native, original, metadata)


@pytest.mark.parametrize("mutate", ["missing_df", "nan_df", "failed_df"])
def test_fourfield_uses_actual_df_not_unused_dfw(tmp_path, mutate):
    reference = ROOT / "reference_exports/recovered-fourfield-01"
    manifest = json.loads((reference / "manifest.json").read_text())
    inputs = copy.deepcopy(manifest["effective_inputs"])
    # check_convergence accepts this source-shaped PERIM row, as well as the
    # native one-dimensional PERIM, and maintains kg/(s m) film increments.
    with np.load(reference / "initialization.npz") as arrays:
        data = {k: arrays[k].copy() for k in arrays.files}
    assert np.all(data["film.wave.ITR.DFW"] == 0)
    if mutate == "missing_df":
        data.pop("film.wave.ITR.DF")
    elif mutate == "nan_df":
        data["film.wave.ITR.DF"][-1] = np.nan
    else:
        data["film.wave.ITR.DF"][-1] = inputs["options"]["ERRORFW"]
    path = tmp_path / "modified.npz"
    np.savez(path, **data)
    if mutate == "failed_df":
        assert not check_convergence(path, "FourField", inputs)["point_passed"]
    else:
        with pytest.raises((KeyError, ValueError)):
            check_convergence(path, "FourField", inputs)


@pytest.mark.parametrize("framework", ["TwoFluid", "ThreeField", "FourField"])
def test_real_recovered_frameworks(framework):
    ref, native, manifest, metadata = case(framework)
    result = compare(ref, native)
    assert result["upstream_regression_passed"]
    assert result["initialization_core_passed"]
    assert result["expanded_profiles_passed"]
    assert result["native_physical_diagnostics"] is not None
    if framework == "FourField":
        assert "film.base.W" not in result["physical"]["core"]
        assert result["reference_convergence"]["point"]["film.wave.DF"]["passed"]
        assert "additional_frequency_stopping_check" in result["reference_convergence"]


@pytest.mark.parametrize("key", ["film.ITR.DWL", "Z", "TIME"])
def test_missing_declared_units_rejected(key):
    ref, native, manifest, metadata = case("ThreeField")
    metadata["units"].pop(key)
    with pytest.raises(ValueError):
        validate(ref, native, manifest, metadata)


def test_native_input_copy_hash_is_checked(tmp_path):
    ref, native, manifest, metadata = case("TwoFluid")
    copied = tmp_path / "native"
    shutil.copytree(native, copied)
    first = copied / metadata["source_files"][0]["copy"]
    with first.open("ab") as stream:
        stream.write(b"changed")
    with pytest.raises(ValueError):
        validate(ref, copied, manifest, metadata)


@pytest.mark.parametrize("mutation", ["state", "inputs", "point"])
def test_precursor_acceptance_is_independent_of_parent(mutation, tmp_path):
    ref, native, _, _ = case("TwoFluid")
    copied = tmp_path / "native"
    shutil.copytree(native, copied)
    metadata_file = copied / "mixture/metadata.json"
    metadata = json.loads(metadata_file.read_text())
    if mutation == "state":
        metadata["converged"] = False
    elif mutation == "inputs":
        metadata["inputs"]["bc"][0]["MFLOW"] = 0.08
    else:
        data_file = copied / "mixture/initialization.npz"
        with np.load(data_file) as arrays:
            data = {k: arrays[k].copy() for k in arrays.files}
        data["ITR.DH"][-1, 4] = metadata["inputs"]["options"]["ERRORH"]
        np.savez(data_file, **data)
    metadata_file.write_text(json.dumps(metadata))
    if mutation == "point":
        assert not compare(ref, copied)["upstream_regression_passed"]
    else:
        with pytest.raises(ValueError):
            compare(ref, copied)


@pytest.mark.parametrize("mutation", [None, "wrong_mask", "partial_nan", "infinity"])
def test_only_exact_declared_absent_iteration_rows_are_accepted(mutation, tmp_path):
    a, units = synthetic_arrays("FourField")
    a = {k: np.concatenate([v, v], axis=0) if k not in ("Z", "TIME") else v for k, v in a.items()}
    a["TIME"] = np.array([0., 1.])
    a["film.wave.ITR.DF"] = np.array([[[np.nan], [np.nan]], [[0.], [0.]]])
    units["film.wave.ITR.DF"] = "Hz"
    flags = {"film.wave.ITR.DF": [False, True]}
    if mutation == "wrong_mask":
        flags = {"film.wave.ITR.DF": [True, False]}
    elif mutation == "partial_nan":
        a["film.wave.ITR.DF"][0, 0, 0] = 0
    elif mutation == "infinity":
        a["film.wave.ITR.DF"][0] = np.inf
    ref, native = save_pair(tmp_path, a, copy.deepcopy(a))
    if mutation is None:
        row = compare_phase(ref, native, "FourField", units, flags)["diagnostics"]["film.wave.ITR.DF"]
        assert row["passed"] and row["undefined_value_count"] == 2
    else:
        with pytest.raises(ValueError):
            compare_phase(ref, native, "FourField", units, flags)


def test_film_temporal_mass_threshold_uses_perimeter_not_total_mass(tmp_path):
    data, _ = synthetic_arrays("ThreeField")
    data = {k: np.concatenate([v, v], axis=0) if k not in ("Z", "TIME") else v for k, v in data.items()}
    data["TIME"] = np.array([0., 1.])
    data["film.W"][-1] += 5e-5  # kg/s: below 1e-4 but WL exceeds 1e-4 kg/(s m)
    data["film.ITR.DWL"] = data["film.ITR.DU"] = np.zeros((2, 2, 1))
    data["drop.ITR.DU"] = np.zeros((2, 2))
    inputs = {"geometry": {"PERIM": [0.01]}, "options": {
        "ERRORWF": 1e-4, "ERRORUF": .01, "ERRORUD": .01,
        "SSCONVWF": 1e-4, "SSCONVUF": .01, "SSCONVUD": .01}}
    path = tmp_path / "initialization.npz"
    np.savez(path, **data)
    result = check_convergence(path, "ThreeField", inputs)
    assert result["point_passed"] and not result["temporal_passed"]
    assert result["temporal"]["film.WL"]["unit"] == "kg/s/m"
    assert result["temporal"]["film.WL"]["maximum"] == pytest.approx(.005)
