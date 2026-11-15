"""Recovery tests use the preserved archive, never generated solver references."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from recover_mcos_reference import ROOT, _read_enum, export_reference, load_archive, mixture_arrays

ARCHIVE = ROOT / "upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/tutorial1_MixtureSolver.mat"
ARCHIVE_SHA = "43311c4c2ec3440cc3366f94df1216b425d4270268887b7fb7bf921c0fb9ccb0"


@pytest.fixture(scope="module")
def saved():
    return load_archive(ARCHIVE)["solver"]


def test_original_archive_identity_and_complete_graph(saved):
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == ARCHIVE_SHA
    p = saved.properties
    assert saved.classname == "Solvers.Mixture.MixtureSolver"
    assert p["Z"].shape == (101, 1)
    assert p["mixtureInit"].shape == (1, 10)
    for state in [p["mixture"], *p["mixtureInit"].ravel(order="F")]:
        assert state.properties["liquid"].properties["mix"] is state
        assert state.properties["vapor"].properties["mix"] is state
        assert state.properties["W"].shape == (101, 1)


def test_named_arrays_preserve_original_stored_values_and_dimensions(saved):
    p = saved.properties
    arrays = mixture_arrays([p["mixture"]])
    for public, private in (("W", "W"), ("H", "H"), ("P", "P"), ("RHO", "rho"), ("VF", "vf")):
        np.testing.assert_array_equal(arrays[public][0], p["mixture"].properties[private][:, 0])
    for name in ("HFLUX", "MRM.WV", "NEARWALL.W", "ITR.DWV", "ITR.DHV"):
        assert arrays[name].shape == (1, 101, 1)
    assert arrays["NEARWALL.WBULK"].shape == (1, 101)
    initial = mixture_arrays(p["mixtureInit"])
    np.testing.assert_array_equal(initial["TIME"], np.arange(10.0))
    assert initial["W"].shape == (10, 101)


def test_reconstructed_phase_methods_obey_saved_mass_energy_identities(saved):
    p = saved.properties["mixture"].properties
    a = mixture_arrays([saved.properties["mixture"]])
    np.testing.assert_allclose(a["liquid.W"] + a["vapor.W"], a["W"], rtol=2e-16, atol=0)
    energy = a["liquid.W"] * a["liquid.H"] + a["vapor.W"] * a["vapor.H"]
    np.testing.assert_allclose(energy, a["W"] * a["H"], rtol=5e-16, atol=0)
    area = p["inputSet"].properties["geometry"].properties["AREA"].item()
    np.testing.assert_array_equal(a["U"][0], p["W"][:, 0] / p["rho"][:, 0] / area)


def test_repeated_read_is_stable_without_enum_metadata_mutation(saved):
    second = load_archive(ARCHIVE)["solver"]
    for key in ("W", "H", "P", "rho", "x"):
        np.testing.assert_array_equal(second.properties["mixture"].properties[key], saved.properties["mixture"].properties[key])
    enum = saved.properties["inputSet"].properties["model"].properties["PROPERTIES"]
    assert enum.properties["__enum_names__"].item() == "SATURATED"
    assert enum.properties["__enum_metadata__"][0, 0]["ClassName"].dtype.kind in "ui"


def test_export_provenance_raw_arrays_convergence_and_no_overwrite(tmp_path):
    target = tmp_path / "reference"
    manifest = export_reference(ARCHIVE, target)
    assert manifest["archive"]["sha256"] == ARCHIVE_SHA
    assert manifest["convergence"]["point_passed"]
    assert manifest["convergence"]["temporal_passed"]
    assert manifest["effective_inputs"]["model"]["THERMALNONEQ"] == "EQUILIBRIUM"
    assert manifest["effective_inputs"]["geometry"]["AREA"] > 0
    assert manifest["producer_metadata"]["coolprop_version"] is None
    with np.load(target / "results.npz", allow_pickle=False) as arrays:
        assert set(arrays.files) <= set(manifest["units"])
    graph = json.loads((target / "object_graph.json").read_text())
    raw = np.load(target / "raw_arrays.npz", allow_pickle=False)
    for node in graph:
        if node["kind"] == "numeric_array":
            assert list(raw[node["key"]].shape) == node["shape"]
    for filename, digest in manifest["files"].items():
        assert hashlib.sha256((target / filename).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        export_reference(ARCHIVE, target)
    assert hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() == ARCHIVE_SHA


def test_reconstruction_rejects_other_physics(saved):
    state = saved.properties["mixture"]
    enum = state.properties["inputSet"].properties["model"].properties["PROPERTIES"]
    names = enum.properties["__enum_names__"]
    enum.properties["__enum_names__"] = np.array([["OTHER"]])
    try:
        with pytest.raises(ValueError, match="SATURATED/EQUILIBRIUM"):
            mixture_arrays([state])
    finally:
        enum.properties["__enum_names__"] = names
