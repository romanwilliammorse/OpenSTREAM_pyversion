"""CSV and legacy-vector checks against saved artifacts, not fresh physics."""
from contextlib import contextmanager
import csv
import hashlib
import io
import json
from pathlib import Path
import secrets

import numpy as np
import pytest
from werkzeug.security import generate_password_hash

from openstream.gui import create_app as local_app, plot_data
from openstream.gui_exports import csv_response, local_reader, prepare_csv
from openstream.gui_schema import baseline
from openstream.cloud.app import create_app as cloud_app
from openstream.cloud.storage import CloudStoreError
from test_cloud_manager import setup

RUN = "a" * 32
ORIGIN = "https://openstream-py.vercel.app"


def rows(body):
    return list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))


@pytest.fixture
def saved(tmp_path):
    directory = tmp_path / RUN
    output = directory / "output"
    (output / "mixture").mkdir(parents=True)
    payload = baseline("FourField")
    payload["inputs"]["model"]["ID"] = '=HYPERLINK("https://example.invalid")'
    payload["inputs"]["geometry"]["ANGLE"] = -0.25
    (directory / "submitted_inputs.json").write_text(json.dumps(payload), encoding="utf-8")
    metadata = {"units": {"film.U": "m/s", "vapor.X": "1", "HFLUX": "W/m^2", "diagnostic": "1"}}
    for folder in (output, output / "mixture"):
        (folder / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
    z = np.array([0.0, 0.5, 1.0])
    values = np.array([[0.0, -1.0, 2.0], [3.0, 4.0, 5.0]])
    np.savez_compressed(output / "results.npz", Z=z, TIME=np.array([0.0, 2.0]),
                        **{"film.U": values, "diagnostic": np.array([[np.nan, np.inf, -np.inf], [0.0, -0.0, 1.0]]),
                           "HFLUX": np.arange(12.0).reshape(2, 3, 2)})
    np.savez_compressed(output / "initialization.npz", Z=z, TIME=np.array([0.0, 0.125]), **{"film.U": values + 20})
    np.savez_compressed(output / "mixture/results.npz", Z=z, TIME=np.array([0.0]), **{"vapor.X": np.array([[0.2, 0.4, 0.6]])})
    np.savez_compressed(output / "mixture/initialization.npz", Z=z, TIME=np.array([0.0, 0.0625]), **{"vapor.X": values / 10})
    state = {"id": RUN, "framework": "FourField", "status": "completed", "created_at": "2026-11-15T00:00:00Z",
             "is_reference": False, "files": []}
    (directory / "status.json").write_text(json.dumps(state))
    return directory


def available(directory):
    return {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file()}


def export(directory, kind):
    with prepare_csv(kind, "FourField", lambda name: local_reader(directory, name), available(directory)) as result:
        return rows(result.read())


def test_separate_input_csvs_preserve_types_arrays_units_and_saved_values(saved):
    inputs = export(saved, "inputs")
    assert {row["section"] for row in inputs} == {"model", "options"}
    named = next(row for row in inputs if row["section"] == "model" and row["parameter"] == "ID")
    assert json.loads(named["value_json"]) == '=HYPERLINK("https://example.invalid")'
    # JSON text begins with a quote, never a spreadsheet formula character.
    assert named["value_json"].startswith('"')
    geom = export(saved, "geometry")
    assert {row["section"] for row in geom} == {"geometry"}
    angle = next(row for row in geom if row["parameter"] == "ANGLE")
    assert angle["value_json"] == "-0.25" and angle["element_indices"] == "[]"
    bc = export(saved, "boundary-conditions")
    power = [row for row in bc if row["parameter"] == "WPOWER"]
    assert [row["element_indices"] for row in power] == ["[0,0]", "[1,0]"]
    assert all(row["shape"] == "[2,1]" for row in power)
    assert [json.loads(row["value_json"]) for row in power] == [1.0, 0.0]
    pressure = next(row for row in bc if row["parameter"] == "PRESSURE")
    assert pressure["unit"] == "Pa" and json.loads(pressure["value_json"]) == 6000000


def test_results_round_trip_every_scalar_coordinate_component_and_nonfinite(saved):
    result = export(saved, "results")
    assert {row["dataset"] for row in result} == {"physical", "initialization", "precursor", "precursor_initialization"}
    archives = {"physical": "output/results.npz", "initialization": "output/initialization.npz",
                "precursor": "output/mixture/results.npz", "precursor_initialization": "output/mixture/initialization.npz"}
    for dataset, name in archives.items():
        with np.load(saved / name) as original:
            subset = [row for row in result if row["dataset"] == dataset]
            assert len(subset) == sum(original[key].size for key in original.files)
            for key in original.files:
                recovered = np.empty(original[key].shape)
                records = [row for row in subset if row["quantity"] == key]
                for row in records:
                    index = tuple(json.loads(row["array_indices"]))
                    assert json.loads(row["array_shape"]) == list(original[key].shape)
                    recovered[index] = float(row["value"])
                np.testing.assert_array_equal(recovered, original[key])
    wall = next(row for row in result if row["dataset"] == "physical" and row["quantity"] == "HFLUX" and row["array_indices"] == "[1,2,1]")
    assert wall["component_indices"] == "[1]" and wall["time_s"] == "2.0" and wall["z_m"] == "1.0"
    assert wall["unit"] == "W/m^2" and wall["value"] == "11.0"
    initial = [row for row in result if row["dataset"] == "precursor_initialization"]
    assert all(row["time_kind"] == "pseudo" for row in initial)
    nonfinite = [row["value"] for row in result if row["quantity"] == "diagnostic"]
    assert nonfinite[:3] == ["NaN", "Infinity", "-Infinity"] and nonfinite[4] == "-0.0"


def test_exports_do_not_mutate_saved_inputs_outputs_or_status(saved):
    before = {name: hashlib.sha256((saved / name).read_bytes()).hexdigest() for name in available(saved)}
    for kind in ("inputs", "boundary-conditions", "geometry", "results"):
        assert export(saved, kind)
    after = {name: hashlib.sha256((saved / name).read_bytes()).hexdigest() for name in available(saved)}
    assert before == after


def test_local_routes_only_export_completed_runs_and_reject_unknown_kinds(saved):
    app = local_app(saved.parent)
    try:
        client = app.test_client()
        response = client.get(f"/api/runs/{RUN}/export/results.csv")
        assert response.status_code == 200 and response.mimetype == "text/csv"
        assert response.headers["Content-Disposition"] == "attachment; filename=OpenSTREAM-FourField-results.csv"
        assert rows(response.data)
        response.close()
        assert client.get(f"/api/runs/{RUN}/export/unknown.csv").status_code == 404
        assert client.get("/api/runs/not-a-run/export/inputs.csv").status_code == 404
        state = json.loads((saved / "status.json").read_text())
        state["status"] = "failed"
        (saved / "status.json").write_text(json.dumps(state))
        assert client.get(f"/api/runs/{RUN}/export/results.csv").status_code == 409
        assert client.get(f"/api/runs/{RUN}/export/inputs.csv").status_code == 409
    finally:
        app.extensions["runs"].server_lock.close()


def test_local_plot_data_exposes_saved_precursor_initialization(saved):
    data = plot_data(saved, "FourField", False)
    precursor = data["datasets"]["precursor_initialization"]
    assert precursor["time"] == [0.0, 0.0625]
    assert "pseudo-time" in precursor["time_label"]
    assert precursor["fields"]["vapor.X"]["values"] == [[0.0, -0.1, 0.2], [0.3, 0.4, 0.5]]


def test_csv_output_limit_fails_before_returning_a_partial_download(saved, monkeypatch):
    monkeypatch.setattr("openstream.gui_exports.MAX_CSV_BYTES", 10)
    with pytest.raises(ValueError, match="export size limit"):
        export(saved, "results")


def test_non_numeric_arrays_are_explicitly_rejected(saved):
    np.savez(saved / "output/results.npz", Z=np.array([0.0]), TIME=np.array([0.0]), bad=np.array([["not numeric"]]))
    with pytest.raises(ValueError, match="real numeric"):
        export(saved, "results")


def test_csv_response_closes_spool_even_without_consumption():
    spool = io.BytesIO(b"test")
    response = csv_response(spool, "Mixture", "results")
    response.close()
    assert spool.closed


def test_csv_response_closes_spool_after_partial_consumption():
    spool = io.BytesIO(b"x" * 100000)
    response = csv_response(spool, "Mixture", "results")
    iterator = iter(response.response)
    assert len(next(iterator)) == 65536
    response.close()
    assert spool.closed


def test_csv_expansion_limit_and_unknown_framework_fail_explicitly(saved, monkeypatch):
    monkeypatch.setattr("openstream.gui_exports.MAX_ARRAY_BYTES", 10)
    with pytest.raises(ValueError, match="export size limit"):
        export(saved, "results")
    with pytest.raises(ValueError, match="Unknown framework"):
        prepare_csv("results", "not-a-model", lambda name: local_reader(saved, name), available(saved))


def cloud_saved(setup, saved):
    manager, store, gateway, provider = setup
    payload = json.loads((saved / "submitted_inputs.json").read_text())
    state = manager.start(payload)
    run_id = state["id"]
    manifest = store.get_json(f"runs/{run_id}.json")
    bodies = {name: (saved / name).read_bytes() for name in available(saved) if name != "status.json"}
    bodies["submitted_inputs.json"] = store.read_bytes(f"jobs/{run_id}/submitted_inputs.json")
    bodies["results.zip"] = b"original archive unchanged"
    data = plot_data(saved, "FourField", False)
    del data["datasets"]["precursor_initialization"]  # An actual old schema.
    bodies["plot_data.json"] = json.dumps(data, allow_nan=False).encode()
    artifacts = {name: store.put_bytes(f"jobs/{run_id}/artifacts/{hashlib.sha256(body).hexdigest()}/{name}", body, "application/octet-stream") for name, body in bodies.items()}
    terminal = {"schema": "openstream-cloud-terminal-v1", "id": run_id,
                "status": {**manifest["public_initial_state"], "status": "completed"},
                "artifacts": artifacts, "plot_data": artifacts["plot_data.json"],
                "source": manifest["source"], "environment": manifest["environment"], "runtime": manifest["runtime"],
                "publication": {"complete": True}, "published_at": "2026-11-15T00:00:00Z"}
    store.put_json(f"jobs/{run_id}/terminal/test.json", terminal)
    return run_id, terminal


def test_cloud_exports_match_local_and_leave_all_blob_bytes_unchanged(setup, saved):
    manager, _, _, provider = setup
    run_id, _ = cloud_saved(setup, saved)
    before = dict(provider.objects)
    for kind in ("inputs", "boundary-conditions", "geometry", "results"):
        spool, framework = manager.csv_export(run_id, kind)
        with spool:
            assert framework == "FourField" and rows(spool.read()) == export(saved, kind)
    assert provider.objects == before


def test_cloud_old_plot_json_gains_precursor_initialization_without_publication(setup, saved):
    manager, _, _, provider = setup
    run_id, _ = cloud_saved(setup, saved)
    before = dict(provider.objects)
    assert manager.data(run_id) == plot_data(saved, "FourField", False)
    assert provider.objects == before


def test_cloud_export_checks_source_hash_before_any_csv_is_returned(setup, saved):
    manager, _, _, provider = setup
    run_id, terminal = cloud_saved(setup, saved)
    path = "openstream/v1/" + terminal["artifacts"]["output/results.npz"]["key"]
    provider.objects[path] = b"corrupt"
    with pytest.raises(CloudStoreError, match="hash or size"):
        manager.csv_export(run_id, "results")


def test_cloud_endpoint_requires_authentication_and_completed_saved_artifacts(setup, saved):
    manager, _, _, _ = setup
    run_id, _ = cloud_saved(setup, saved)
    password = secrets.token_urlsafe(24)
    app = cloud_app(manager, {"TESTING": True, "OPENSTREAM_PASSWORD_HASH": generate_password_hash(password),
                             "OPENSTREAM_SESSION_SECRET": secrets.token_urlsafe(48), "OPENSTREAM_PUBLIC_ORIGIN": ORIGIN},
                    limiter=lambda key: True)
    client = app.test_client()
    path = f"/api/runs/{run_id}/export/geometry.csv"
    assert client.get(path, base_url=ORIGIN).status_code == 401
    csrf = client.get("/auth/session", base_url=ORIGIN).json["csrf"]
    assert client.post("/auth/login", base_url=ORIGIN, json={"password": password},
                       headers={"Origin": ORIGIN, "X-CSRF-Token": csrf}).status_code == 200
    response = client.get(path, base_url=ORIGIN)
    assert response.status_code == 200 and rows(response.data) == export(saved, "geometry")
    response.close()
    assert client.get(f"/api/runs/{run_id}/export/unknown.csv", base_url=ORIGIN).status_code == 404
    queued = manager.start(baseline())["id"]
    assert client.get(f"/api/runs/{queued}/export/results.csv", base_url=ORIGIN).status_code == 409
