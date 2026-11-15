"""Publication semantics plus a real 100-cell archived mixture regression.

All storage is in memory. These tests never call an external hosting service.
"""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
import pytest

import openstream
from openstream.cloud import worker
from openstream.cloud.storage import BlobConflictError
from openstream.gui_schema import assess_payload, baseline


RUN_ID = "1234567890abcdef1234567890abcdef"


class MemoryStore:
    def __init__(self):
        self.objects = {}
        self.events = []
        self.fail = lambda key: False
        self.lose_terminal_ack = False
        self.on_put = lambda key: None

    def put_bytes(self, key, body, content_type, overwrite=False):
        assert overwrite is False
        self.on_put(key)
        self.events.append(key)
        if self.fail(key):
            raise RuntimeError("SDK error with token=DO-NOT-LEAK and signed-private-url")
        if key in self.objects:
            raise BlobConflictError("already exists")
        self.objects[key] = bytes(body)
        meta = {"key": key, "url": "https://private.example/"+key,
                "sha256": hashlib.sha256(body).hexdigest(), "size": len(body)}
        if self.lose_terminal_ack and "/terminal/" in key:
            raise RuntimeError("lost acknowledgement")
        return meta

    def put_json(self, key, value, overwrite=False):
        return self.put_bytes(key, worker._json_bytes(value), "application/json", overwrite)

    def list(self, prefix):
        return [{"key": k, "url": "https://private.example/"+k, "size": len(v)}
                for k, v in self.objects.items() if k.startswith(prefix)]

    def read_bytes_by_url(self, url):
        return self.objects[url.removeprefix("https://private.example/")]

    def get_json_by_url(self, url):
        return json.loads(self.read_bytes_by_url(url))


def prepare_job(tmp_path, payload=None):
    directory = tmp_path/RUN_ID
    directory.mkdir()
    payload = payload or baseline("Mixture")
    inputs = worker._json_bytes(payload)
    (directory/"submitted_inputs.json").write_bytes(inputs)
    state = {"id": RUN_ID, "framework": payload["framework"], "status": "queued", "phase": "Starting",
             "created_at": "2026-11-15T00:00:00+00:00", "progress": [], "files": [],
             "converged": None, "error": None, **assess_payload(payload),
             "reference": {"status": "not_compared"}, "physical": {"status": "not_checked"}}
    module = Path(openstream.__file__).parent/"solver.py"
    manifest = {"schema": "openstream-cloud-job-v1", "id": RUN_ID, "created_at": state["created_at"],
                "framework": payload["framework"], "submitted_inputs_sha256": hashlib.sha256(inputs).hexdigest(),
                "source": {"git_commit": "a"*40, "module_sha256": {"src/openstream/solver.py": hashlib.sha256(module.read_bytes()).hexdigest()},
                           "package_version": openstream.__version__},
                "environment": {"python_requirement": "3.12", "dependency_lock_sha256": "b"*64},
                "runtime": {"sandbox_id": "test-box", "sandbox_name": "test-box", "session_id": "test-session", "timeout_seconds": 2400},
                "public_initial_state": deepcopy(state)}
    worker._write_json(directory/"status.json", state)
    worker._write_json(directory/"job_manifest.json", manifest)
    return directory, manifest


@pytest.fixture
def fake_job(tmp_path, monkeypatch):
    directory, manifest = prepare_job(tmp_path)
    def child(path):
        state = worker._read_json(path/"status.json")
        state.update(status="completed", phase="Completed", converged=True,
                     reference={"status": "passed"}, physical={"status": "passed"})
        worker._write_json(path/"status.json", state)
        (path/"worker.log").write_text("native calculation log\n", encoding="utf-8")
        (path/"output").mkdir()
        (path/"output/results.npz").write_bytes(b"retained numerical file")
        (path/"output/metadata.json").write_text('{}', encoding="utf-8")
        (path/"results.zip").write_bytes(b"retained complete archive")
        return 0
    monkeypatch.setattr(worker, "_run_child", child)
    import openstream.gui
    monkeypatch.setattr(openstream.gui, "plot_data", lambda *args: {"datasets": {"physical": {"z": [0, 1]}}})
    return directory, manifest, MemoryStore()


def execute(fake_job, **kwargs):
    directory, _, store = fake_job
    return worker.run_cloud_job(directory, RUN_ID, store=store, stop_callback=kwargs.pop("stop_callback", lambda: None), **kwargs)


def test_immutable_artifacts_precede_terminal_and_stop(fake_job):
    directory, manifest, store = fake_job
    def publishing(key):
        state = worker._read_json(directory/"cloud_status.json")
        assert state["status"] == "running" and state["phase"] == "Publishing"
    store.on_put = publishing
    stopped = []
    def stop():
        assert "/terminal/" in store.events[-1]
        assert worker._read_json(directory/"cloud_status.json")["status"] == "completed"
        stopped.append(True)
    terminal = execute(fake_job, stop_callback=stop)
    assert stopped == [True]
    assert terminal["status"]["status"] == "completed"
    assert terminal["publication"] == {"complete": True, "stage": "published", "child_exit_code": 0, "error_type": None}
    for name, receipt in terminal["artifacts"].items():
        body = (directory/name).read_bytes()
        assert receipt["sha256"] == hashlib.sha256(body).hexdigest()
        assert receipt["size"] == len(body)
        assert f"/artifacts/{receipt['sha256']}/{name}" in receipt["key"]
        assert store.read_bytes_by_url(receipt["url"]) == body
    assert terminal["plot_data"] == terminal["artifacts"]["plot_data.json"]
    for key in ("source", "environment", "runtime"):
        assert terminal[key] == manifest[key]
    assert "private.example" not in json.dumps(terminal["status"])
    assert all(item["url"].startswith(f"/files/{RUN_ID}/") for item in terminal["status"]["files"])
    assert not any(".lock" in key or "cloud_" in key for key in terminal["artifacts"])


@pytest.mark.parametrize("state_name,exit_code", [("failed", 1), ("cancelled", 0)])
def test_native_failure_and_cancellation_preserve_evidence_without_plots(fake_job, monkeypatch, state_name, exit_code):
    directory, _, store = fake_job
    def child(path):
        state = worker._read_json(path/"status.json")
        state.update(status=state_name, phase=state_name.title(), error="Native domain error" if state_name == "failed" else None)
        worker._write_json(path/"status.json", state)
        (path/"worker.log").write_text("native failure trace", encoding="utf-8")
        return exit_code
    monkeypatch.setattr(worker, "_run_child", child)
    import openstream.gui
    monkeypatch.setattr(openstream.gui, "plot_data", lambda *args: pytest.fail("must not generate plots"))
    terminal = execute(fake_job)
    assert terminal["status"]["status"] == state_name
    assert terminal["plot_data"] is None
    assert terminal["publication"]["complete"] is True
    assert "worker.log" in terminal["artifacts"] and "submitted_inputs.json" in terminal["artifacts"]


def test_nonzero_child_cannot_claim_completed(fake_job, monkeypatch):
    original = worker._run_child
    def child(path):
        original(path)
        return 2
    monkeypatch.setattr(worker, "_run_child", child)
    result = execute(fake_job)
    assert result["status"]["status"] == "failed"
    assert result["publication"]["child_exit_code"] == 2
    assert result["publication"]["complete"] is False
    assert result["plot_data"] is None
    assert "output/results.npz" in result["artifacts"]


def test_preexisting_failed_status_is_not_masked(fake_job, monkeypatch):
    directory, _, _ = fake_job
    state = worker._read_json(directory/"status.json")
    state.update(status="failed", error="Original failure", phase="Failed")
    worker._write_json(directory/"status.json", state)
    monkeypatch.setattr(worker, "_run_child", lambda path: 1)
    result = execute(fake_job)
    assert result["status"]["status"] == "failed"
    assert result["status"]["error"] == "Original failure"
    assert result["publication"]["child_exit_code"] == 1


def test_plot_failure_retains_scientific_files_and_failed_terminal(fake_job, monkeypatch):
    import openstream.gui
    monkeypatch.setattr(openstream.gui, "plot_data", lambda *args: (_ for _ in ()).throw(ValueError("plot fail")))
    result = execute(fake_job)
    assert result["status"]["status"] == "failed"
    assert result["publication"]["stage"] == "plot_data"
    assert result["plot_data"] is None
    assert {"results.zip", "output/results.npz", "worker.log"} <= result["artifacts"].keys()


def test_artifact_failure_never_publishes_success_or_sdk_secrets(fake_job, capsys):
    _, _, store = fake_job
    store.fail = lambda key: key.endswith("/output/results.npz")
    result = execute(fake_job)
    terminals = [json.loads(body) for key, body in store.objects.items() if "/terminal/" in key]
    assert len(terminals) == 1 and terminals[0]["status"]["status"] == "failed"
    assert result["publication"]["complete"] is False
    assert "output/results.npz" not in result["artifacts"]
    assert "worker.log" in result["artifacts"]
    assert "DO-NOT-LEAK" not in json.dumps(result)
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_terminal_failure_has_no_contradictory_terminal_and_does_not_stop(fake_job):
    directory, _, store = fake_job
    store.fail = lambda key: "/terminal/" in key
    stopped = []
    result = execute(fake_job, stop_callback=lambda: stopped.append(True))
    assert result["status"]["status"] == "failed"
    assert not any("/terminal/" in key for key in store.objects)
    assert len([key for key in store.events if "/terminal/" in key]) == 1
    assert any("/publication-failures/" in key for key in store.objects)
    assert not stopped
    assert worker._read_json(directory/"cloud_cleanup.json")["status"] == "not_stopped_publication_unconfirmed"


def test_lost_terminal_acknowledgement_is_verified_before_success(fake_job):
    _, _, store = fake_job
    store.lose_terminal_ack = True
    result = execute(fake_job)
    assert result["status"]["status"] == "completed"
    assert len([key for key in store.objects if "/terminal/" in key]) == 1
    assert not any("/publication-failures/" in key for key in store.objects)


def test_store_outage_keeps_local_failure_and_does_not_destroy_only_evidence(fake_job):
    directory, _, store = fake_job
    store.fail = lambda key: True
    result = execute(fake_job, stop_callback=lambda: pytest.fail("no durable publication"))
    assert result["status"]["status"] == "failed"
    assert worker._read_json(directory/"cloud_failure.json")["publication"]["complete"] is False
    assert (directory/"output/results.npz").is_file()


def test_cleanup_failure_is_separate_from_durable_scientific_status(fake_job):
    directory, _, store = fake_job
    def stop():
        raise RuntimeError("secret cleanup token")
    result = execute(fake_job, stop_callback=stop)
    assert result["status"]["status"] == "completed"
    cleanup = worker._read_json(directory/"cloud_cleanup.json")
    assert cleanup == {"status": "failed", "error_type": "RuntimeError"}
    assert "/terminal/" in store.events[-1]


def test_existing_terminal_does_not_run_or_publish_again(fake_job, monkeypatch):
    _, _, store = fake_job
    store.put_json(f"jobs/{RUN_ID}/terminal/existing.json", {"status": "original"})
    monkeypatch.setattr(worker, "_run_child", lambda path: pytest.fail("duplicate calculation"))
    with pytest.raises(worker.CloudWorkerError, match="already exists"):
        execute(fake_job)
    assert len(store.objects) == 1


def test_terminal_lookup_outage_retains_failure_without_duplicate_calculation(fake_job, monkeypatch):
    directory, _, store = fake_job
    def unavailable(prefix):
        raise RuntimeError("private SDK URL and secret")
    monkeypatch.setattr(store, "list", unavailable)
    monkeypatch.setattr(worker, "_run_child", lambda path: pytest.fail("cannot rule out an existing terminal"))
    result = execute(fake_job, stop_callback=lambda: pytest.fail("retain evidence for recovery"))
    assert result["status"]["status"] == "failed"
    assert result["publication"]["stage"] == "terminal_lookup"
    assert store.events == []
    assert worker._read_json(directory/"cloud_failure.json") == result
    assert "secret" not in json.dumps(result)


def test_identical_content_collision_reuses_only_verified_bytes():
    store = MemoryStore()
    first = worker._put_artifact(store, RUN_ID, "results.zip", b"evidence")
    assert worker._put_artifact(store, RUN_ID, "results.zip", b"evidence") == first
    store.objects[first["key"]] = b"corruption"
    with pytest.raises(worker.CloudWorkerError, match="differs"):
        worker._put_artifact(store, RUN_ID, "results.zip", b"evidence")


@pytest.mark.parametrize("field", ["inputs", "source"])
def test_hash_mismatch_fails_before_child(fake_job, monkeypatch, field):
    directory, manifest, _ = fake_job
    if field == "inputs":
        (directory/"submitted_inputs.json").write_bytes(b'{}')
    else:
        manifest["source"]["module_sha256"]["src/openstream/solver.py"] = "0"*64
        worker._write_json(directory/"job_manifest.json", manifest)
    monkeypatch.setattr(worker, "_run_child", lambda path: pytest.fail("unverified source/input"))
    result = execute(fake_job)
    assert result["status"]["status"] == "failed"
    assert result["publication"]["stage"] == "verification"
    assert result["publication"]["child_exit_code"] is None


@pytest.mark.parametrize("bad_id", ["../x", "a/b", "A"*32, "1"*31])
def test_invalid_identity_rejected_without_storage(tmp_path, bad_id):
    store = MemoryStore()
    with pytest.raises(worker.CloudWorkerError):
        worker.run_cloud_job(tmp_path, bad_id, store=store)
    assert store.events == []


def test_parent_traversal_and_manifest_mismatch_rejected(fake_job):
    directory, manifest, store = fake_job
    with pytest.raises(worker.CloudWorkerError):
        worker.run_cloud_job(directory.parent/"irrelevant"/".."/RUN_ID, RUN_ID, store=store)
    manifest["id"] = "0"*32
    worker._write_json(directory/"job_manifest.json", manifest)
    with pytest.raises(worker.CloudWorkerError, match="identity"):
        execute(fake_job)
    assert store.events == []


def test_symlink_artifact_rejected_before_any_publication(fake_job, tmp_path):
    directory, _, store = fake_job
    external = tmp_path/"external.txt"
    external.write_text("must not publish", encoding="utf-8")
    link = directory/"linked.txt"
    try:
        link.symlink_to(external)
    except OSError:
        # Windows normally disallows file symlinks without Developer Mode;
        # a directory junction exercises the same real traversal threat.
        if sys.platform != "win32":
            raise
        import _winapi
        target = tmp_path/"external-directory"
        target.mkdir()
        (target/"private.txt").write_text("must not publish", encoding="utf-8")
        _winapi.CreateJunction(str(target), str(link))
    with pytest.raises(worker.CloudWorkerError, match="links"):
        execute(fake_job)
    assert not store.objects


def test_child_receives_no_host_credentials(monkeypatch):
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "private")
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "private")
    monkeypatch.setenv("UNRELATED_SECRET", "private")
    monkeypatch.setenv("OMP_NUM_THREADS", "1")
    child = worker._child_environment()
    assert child["OMP_NUM_THREADS"] == "1"
    assert not {"VERCEL_OIDC_TOKEN", "BLOB_READ_WRITE_TOKEN", "UNRELATED_SECRET"} & child.keys()


def test_actual_storage_wrapper_contract_with_fake_blob(fake_job):
    from openstream.cloud.storage import CloudStore
    from test_cloud_storage import FakeBlob
    directory, _, _ = fake_job
    blob = FakeBlob()
    store = CloudStore("store_teststore", blob_client=blob)
    result = worker.run_cloud_job(directory, RUN_ID, store=store, stop_callback=lambda: None)
    assert result["status"]["status"] == "completed"
    keys = [name for operation, name, _ in blob.calls if operation == "put"]
    assert "/terminal/" in keys[-1]
    assert store.get_json_by_url(store.list(f"jobs/{RUN_ID}/terminal/")[0]["url"]) == result


@pytest.mark.parametrize("session_matches", [True, False])
def test_sdk_stop_is_session_bound_after_publication(monkeypatch, session_matches):
    from types import SimpleNamespace
    events = []
    sandbox = SimpleNamespace(current_session_id="test-session" if session_matches else "later-session",
                              stop=lambda: events.append("stop"))
    def get_sandbox(*, name):
        assert name == "test-box"
        events.append("passive-get")
        return sandbox
    monkeypatch.setitem(sys.modules, "vercel.sandbox.sync", SimpleNamespace(get_sandbox=get_sandbox))
    monkeypatch.setenv("VERCEL_OIDC_TOKEN", "not-printed")
    manifest = {"runtime": {"sandbox_name": "test-box", "session_id": "test-session"}}
    if session_matches:
        assert worker._stop_sandbox(manifest) == "stopped"
        assert events == ["passive-get", "stop"]
    else:
        with pytest.raises(worker.CloudWorkerError, match="different"):
            worker._stop_sandbox(manifest)
        assert events == ["passive-get"]


def test_real_child_acknowledges_cancellation_before_calculation(tmp_path):
    directory, _ = prepare_job(tmp_path)
    (directory/"cancel.request").touch()
    result = worker.run_cloud_job(directory, RUN_ID, store=MemoryStore(), stop_callback=lambda: None)
    assert result["status"]["status"] == "cancelled"
    assert result["publication"]["child_exit_code"] == 0
    assert result["plot_data"] is None
    assert not (directory/"output").exists()


def test_real_100_cell_mixture_wrapper_preserves_archive_equivalence(tmp_path):
    directory, manifest = prepare_job(tmp_path)
    assert baseline("Mixture")["inputs"]["model"]["NNODES"] == 100
    before = worker._verify_sources(manifest)
    store = MemoryStore()
    result = worker.run_cloud_job(directory, RUN_ID, store=store, stop_callback=lambda: None)
    assert result["status"]["status"] == "completed", result["status"]
    assert result["status"]["converged"] is True
    assert result["status"]["reference"]["status"] == "passed"
    assert result["status"]["physical"]["status"] == "passed"
    assert worker._verify_sources(manifest) == before
    from openstream.gui_reference import load_reference
    for dataset, filename in [("physical", "results.npz"), ("initialization", "initialization.npz")]:
        ref = load_reference("Mixture", dataset)
        uploaded = store.read_bytes_by_url(result["artifacts"]["output/"+filename]["url"])
        assert uploaded == (directory/"output"/filename).read_bytes()
        with np.load(io.BytesIO(uploaded), allow_pickle=False) as actual:
            assert actual["Z"].size == 101
            for key, data in ref["fields"].items():
                expected = np.asarray(data["values"])
                assert expected.shape == actual[key].shape
                np.testing.assert_allclose(actual[key], expected, rtol=1e-8, atol=0)
    plot = store.get_json_by_url(result["plot_data"]["url"])
    assert len(plot["datasets"]["physical"]["z"]) == 101
    assert len(plot["datasets"]["physical"]["reference_fields"]) == 9
    with zipfile.ZipFile(io.BytesIO(store.read_bytes_by_url(result["artifacts"]["results.zip"]["url"]))) as archive:
        assert "output/gui_verification.json" in archive.namelist()
    assert "/terminal/" in store.events[-1]
