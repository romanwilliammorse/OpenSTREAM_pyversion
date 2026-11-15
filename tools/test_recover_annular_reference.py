"""Actual-archive extraction integrity tests; no native annular solver runs."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from recover_annular_reference import (ROOT, ARCHIVES, objects, load_archive,
                                      annular_arrays, film_values, graph_arrays,
                                      export_reference, annular_convergence,
                                      physical_checks)


@pytest.fixture(scope="module", params=["ThreeField", "FourField"])
def archive(request):
    framework = request.param
    path = ROOT / f"upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/tutorial1_{framework}Solver.mat"
    return framework, path, load_archive(path)["solver"]


def test_direct_stored_profiles_and_wall_axes(archive):
    framework, path, solver = archive
    assert hashlib.sha256(path.read_bytes()).hexdigest() == ARCHIVES[framework]
    data, _ = annular_arrays(solver)
    fields = {"drop": solver.properties["drop"]}
    if framework == "ThreeField":
        fields["film"] = solver.properties["film"]
    else:
        for name in ("base", "wave"):
            fields["film." + name] = solver.properties["film"].properties[name]
    for name, field in fields.items():
        for key in ("W", "U", "H"):
            recovered = data[name + "." + key][0]
            if name == "drop":
                assert recovered.shape == (101,)
                np.testing.assert_array_equal(recovered, field.properties[key][:, 0])
            else:
                assert recovered.shape == (101, 1)
                np.testing.assert_array_equal(recovered, field.properties[key])
    assert data["film.W"].shape == (1, 101, 1)


def test_exact_graph_mapping_and_handle_links(archive):
    framework, _, solver = archive
    arrays, graph = graph_arrays(solver)
    path = "solver.properties.drop.properties.W"
    record = next(item for item in graph if item["path"] == path)
    np.testing.assert_array_equal(arrays[record["key"]], solver.properties["drop"].properties["W"])
    assert record["shape"] == [101, 1]
    if framework == "FourField":
        for film in [solver.properties["film"]] + objects(solver.properties["filmInit"]):
            for name in ("base", "wave"):
                assert film.properties[name].properties["film"] is film
    assert any(row["kind"] == "object_reference" for row in graph)


def test_convergence_uses_final_initialization(archive):
    framework, _, solver = archive
    initial, presence = annular_arrays(solver, "Init")
    result = annular_convergence(initial, solver, framework)
    assert result["point_passed"] and result["temporal_passed"]
    assert len(initial["TIME"]) == (6 if framework == "ThreeField" else 9)
    if framework == "FourField":
        assert presence["film.wave.ITR.DF"] == [False] + [True] * 8
        assert np.all(np.isnan(initial["film.wave.ITR.DF"][0]))
        assert np.max(initial["film.wave.ITR.DF"][-1]) > 0
        assert np.all(initial["film.wave.ITR.DFW"] == 0)
        assert not result["additional_wave_frequency_temporal"]["source_stopping_predicate_includes_this"]


def test_archive_physical_area_failure_is_not_hidden(archive):
    framework, _, solver = archive
    arrays, _ = annular_arrays(solver)
    result = physical_checks(solver, arrays)
    assert result["physical_consistency"] is False
    assert result["records"][0]["annular_node_count"] == 72
    expected = 0.07485259436858871 if framework == "ThreeField" else 0.11241051742104902
    assert result["max_unblended_annular_area_closure_relative"] == pytest.approx(expected, rel=1e-12)
    assert result["records"][0]["phase_partition_max_error_kg_s"] < 1e-15


def test_export_is_complete_immutable_and_nonoverwriting(archive, tmp_path):
    framework, path, _ = archive
    out = tmp_path / framework
    report = export_reference(path, out)
    assert report["complete"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == ARCHIVES[framework]
    for name, digest in report["files"].items():
        assert hashlib.sha256((out / name).read_bytes()).hexdigest() == digest
    assert (out / "mixture/results.npz").exists()
    assert report["producer_metadata"]["coolprop_version"] is None
    with pytest.raises(FileExistsError):
        export_reference(path, out)


def test_fourfield_aggregate_getters_and_zero_fallback():
    path = ROOT / "upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/tutorial1_FourFieldSolver.mat"
    film = load_archive(path)["solver"].properties["film"]
    base, wave = film.properties["base"].properties, film.properties["wave"].properties
    values = film_values(film)
    np.testing.assert_array_equal(values["W"], base["W"] + wave["W"])
    np.testing.assert_array_equal(values["H"], base["H"])
    np.testing.assert_allclose(values["W"] / values["U"], base["W"] / base["U"] + wave["W"] / wave["U"], rtol=2e-15)
    base["W"][0] = wave["W"][0] = 0
    assert film_values(film)["U"][0] == base["U"][0]
    wave["film"] = None
    with pytest.raises(ValueError, match="wrong aggregate"):
        film_values(film)
