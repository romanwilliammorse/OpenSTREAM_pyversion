"""Guard against misleading archived comparisons in the GUI."""
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

from openstream import gui_reference as reference


def native_case(tmp_path, framework="Mixture"):
    manifest = json.loads((reference.BUNDLE / f"{framework}.json").read_text())
    for dataset, filename in (("physical", "results.npz"), ("initialization", "initialization.npz")):
        shutil.copyfile(reference.BUNDLE / f"{framework}.{dataset}.npz", tmp_path / filename)
    metadata = {"framework": framework, "converged": True, "units": manifest["units"]}
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))
    return tmp_path


def mutate(path, function):
    with np.load(path) as saved:
        data = dict(saved)
    function(data)
    np.savez_compressed(path, **data)


@pytest.mark.parametrize("framework", reference.FRAMEWORKS)
def test_exact_archived_arrays_and_overlay_dimensions(tmp_path, framework):
    result = reference.compare_reference(framework, native_case(tmp_path, framework))
    assert result["status"] == "passed"
    assert result["max_relative_error"] == 0
    assert result["atol"] == 0 and result["rtol"] == 1e-8
    assert len(result["records"]) == 2 * (len(reference.CORE[framework]) + len(reference.EXTRA.get(framework, ())))
    for dataset in ("physical", "initialization"):
        data = reference.load_reference(framework, dataset)
        assert len(data["z"]) == 101
        assert len(data["fields"]) == len(reference.CORE[framework]) + len(reference.EXTRA.get(framework, ()))
        for key, field in data["fields"].items():
            expected = (len(data["time"]), 101) + ((1,) if key.startswith("film.") else ())
            assert np.asarray(field["values"]).shape == expected
            assert field["unit"] == reference.UNITS[key.rsplit(".", 1)[-1]]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("filename", ["results.npz", "initialization.npz"])
@pytest.mark.parametrize("fault", ["large", "nan", "inf", "shape", "missing", "axis", "axis_shape", "zero"])
def test_invalid_data_cannot_pass(tmp_path, filename, fault):
    case = native_case(tmp_path)
    def damage(data):
        if fault == "large":
            data["W"] *= 1.01
        elif fault == "nan":
            data["W"][0, 2] = np.nan
        elif fault == "inf":
            data["W"][0, 2] = np.inf
        elif fault == "shape":
            data["W"] = data["W"][..., None]
        elif fault == "missing":
            del data["liquid.H"]
        elif fault == "axis":
            data["Z"][1] += 1e-6
        elif fault == "axis_shape":
            data["Z"] = data["Z"][None, :]
        elif fault == "zero":
            assert data["vapor.W"][0, 0] == 0
            data["vapor.W"][0, 0] = 1e-100
    mutate(case / filename, damage)
    assert reference.compare_reference("Mixture", case)["status"] == "failed"


def test_reference_relative_tolerance_has_exact_boundary(tmp_path):
    # Direct arithmetic uses exactly representable values to avoid boundary rounding.
    a = np.array([0., 1., 100.])
    assert reference._difference(a, a.copy(), "1")["passed"]
    assert reference._difference(a, a + np.array([0., 0.5e-8, 0.5e-6]), "1")["passed"]
    assert not reference._difference(a, a + np.array([0., 2e-8, 0.]), "1")["passed"]
    assert not reference._difference(a, a + np.array([1e-100, 0., 0.]), "1")["passed"]


@pytest.mark.parametrize("fault", ["units", "axis_units", "framework", "converged", "missing"])
def test_metadata_is_required(tmp_path, fault):
    case = native_case(tmp_path)
    path = case / "metadata.json"
    if fault == "missing":
        path.unlink()
    else:
        meta = json.loads(path.read_text())
        if fault == "units":
            meta["units"]["W"] = "kg/h"
        elif fault == "axis_units":
            meta["units"]["Z"] = "mm"
        elif fault == "framework":
            meta["framework"] = "TwoFluid"
        elif fault == "converged":
            meta["converged"] = False
        path.write_text(json.dumps(meta))
    assert reference.compare_reference("Mixture", case)["status"] == "failed"


def test_four_field_base_and_frequency_are_required(tmp_path):
    case = native_case(tmp_path, "FourField")
    mutate(case / "results.npz", lambda data: data.pop("film.wave.FREQUENCY"))
    assert reference.compare_reference("FourField", case)["status"] == "failed"


def test_bundle_tampering_rejected(tmp_path, monkeypatch):
    folder = tmp_path / "bundle"
    shutil.copytree(reference.BUNDLE, folder)
    path = folder / "Mixture.physical.npz"
    path.write_bytes(path.read_bytes() + b"changed")
    monkeypatch.setattr(reference, "BUNDLE", folder)
    with pytest.raises(ValueError, match="fingerprint"):
        reference.load_reference("Mixture")


def test_bad_framework_and_dataset_rejected():
    with pytest.raises(ValueError, match="framework"):
        reference.load_reference("../../secret")
    with pytest.raises(ValueError, match="dataset"):
        reference.load_reference("Mixture", "../../secret")
