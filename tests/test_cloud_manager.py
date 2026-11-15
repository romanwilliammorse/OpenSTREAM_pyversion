"""Cloud lifecycle contract checks; fake Sandbox and private Blob transport."""
from copy import deepcopy
import hashlib
import json
import time
import uuid

import pytest

from openstream.cloud.manager import CloudRunManager
from openstream.cloud.storage import CloudStore, CloudStoreError
from openstream.gui_schema import baseline
from test_cloud_storage import FakeBlob


class Handle:
    def __init__(self, run_id, gateway):
        self.gateway, self.run_id = gateway, run_id
        self.runtime = {"sandbox_name": "worker-" + run_id, "session_id": "session-" + run_id, "timeout_seconds": 2400}
        self.running, self.local, self.cloud = True, None, None
        self.files, self.launches, self.cancellations, self.stops = {}, 0, 0, 0

    def prepare(self, files):
        if self.gateway.failure == "prepare":
            raise RuntimeError("internal-secret-detail")
        self.files.update(files)
        self.local = json.loads(files[f"/vercel/sandbox/jobs/{self.run_id}/status.json"])

    def launch(self, job_dir):
        self.launches += 1
        assert self.gateway.store.get_json(f"runs/{self.run_id}.json")["id"] == self.run_id
        if self.gateway.failure == "launch":
            raise RuntimeError("internal-secret-detail")

    def status_files(self, job_dir):
        if not self.running:
            raise RuntimeError("inactive session")
        return deepcopy(self.local), deepcopy(self.cloud)

    def request_cancel(self, job_dir):
        self.cancellations += 1

    def is_running(self):
        return self.running

    def stop(self):
        self.stops += 1
        self.running = False


class Gateway:
    def __init__(self, store):
        self.store, self.handles, self.failure = store, {}, None
        self.creates, self.gets = 0, 0

    def create(self, run_id):
        self.creates += 1
        assert self.store.contains(f"jobs/{run_id}/submitted_inputs.json")
        if self.failure == "create":
            raise RuntimeError("internal-secret-detail")
        handle = Handle(run_id, self)
        self.handles[run_id] = handle
        return handle

    def get(self, runtime):
        self.gets += 1
        if self.failure == "get":
            raise RuntimeError("temporary API failure")
        return next(handle for handle in self.handles.values() if handle.runtime == runtime)


@pytest.fixture
def setup():
    provider = FakeBlob()
    store = CloudStore("store_teststore", blob_client=provider)
    gateway = Gateway(store)
    manager = CloudRunManager(store, gateway, source={"git_commit": "a" * 40, "module_sha256": {"module.py": "b" * 64}},
                              environment={"python_requirement": "3.12", "dependency_lock_sha256": "c" * 64})
    return manager, store, gateway, provider


def publish(setup, run_id, status="completed"):
    manager, store, gateway, _ = setup
    manifest = store.get_json(f"runs/{run_id}.json")
    bodies = {"submitted_inputs.json": store.read_bytes(f"jobs/{run_id}/submitted_inputs.json")}
    if status == "completed":
        bodies.update({"results.zip": b"zip-test-evidence", "output/results.npz": b"npz-test-evidence",
                       "plot_data.json": json.dumps({"datasets": {"physical": {"z": [0.0, 1.0], "fields": {}}}, "metadata": {}}).encode()})
    artifacts = {}
    for name, body in bodies.items():
        digest = hashlib.sha256(body).hexdigest()
        artifacts[name] = store.put_bytes(f"jobs/{run_id}/artifacts/{digest}/{name}", body, "application/octet-stream")
    state = {**manifest["public_initial_state"], "status": status, "phase": "Completed", "converged": status == "completed",
             "finished_at": "2026-11-15T20:00:00+00:00", "files": [{"name": "bad", "url": next(iter(artifacts.values()))["url"]}]}
    value = {"schema": "openstream-cloud-terminal-v1", "id": run_id, "status": state, "artifacts": artifacts,
             "plot_data": artifacts.get("plot_data.json"), "source": manifest["source"], "environment": manifest["environment"],
             "runtime": manifest["runtime"], "publication": {"complete": True, "stage": "published"}, "published_at": state["finished_at"]}
    store.put_json(f"jobs/{run_id}/terminal/{uuid.uuid4().hex}.json", value)
    return value


def test_start_persists_exact_input_and_manifest_before_launch(setup):
    manager, store, gateway, provider = setup
    submitted = baseline("FourField")
    state = manager.start(submitted)
    run_id = state["id"]
    manifest = store.get_json(f"runs/{run_id}.json")
    handle = gateway.handles[run_id]
    raw = handle.files[f"/vercel/sandbox/jobs/{run_id}/submitted_inputs.json"]
    assert json.loads(raw) == submitted
    assert raw == store.read_bytes(f"jobs/{run_id}/submitted_inputs.json")
    assert hashlib.sha256(raw).hexdigest() == manifest["submitted_inputs_sha256"]
    assert json.loads(handle.files[f"/vercel/sandbox/jobs/{run_id}/job_manifest.json"]) == manifest
    assert manifest["source"] == manager.source and manifest["environment"] == manager.environment
    assert handle.launches == 1 and state["status"] == "queued"
    assert ".private.blob." not in json.dumps(state) and "runtime" not in state
    assert all(not call[2]["allow_overwrite"] for call in provider.calls if call[0] == "put")


@pytest.mark.parametrize("stage", ["create", "prepare", "launch"])
def test_start_failures_preserve_evidence_stop_only_owned_session_and_never_retry(setup, stage):
    manager, store, gateway, _ = setup
    gateway.failure = stage
    state = manager.start(baseline())
    assert state["status"] == "failed" and "internal-secret" not in json.dumps(state)
    assert gateway.creates == 1
    run_id = state["id"]
    assert store.get_json(f"runs/{run_id}.json")["id"] == run_id
    assert store.read_bytes(f"jobs/{run_id}/submitted_inputs.json")
    prefix = "publication-failures" if stage == "launch" else "terminal"
    assert len(store.list(f"jobs/{run_id}/{prefix}/")) == 1
    if stage != "create":
        assert gateway.handles[run_id].stops == 1
        assert gateway.handles[run_id].launches == (1 if stage == "launch" else 0)


def test_two_active_jobs_limit_without_mutating_inputs(setup):
    manager, store, gateway, _ = setup
    manager.start(baseline()); manager.start(baseline())
    before = len(store.list())
    with pytest.raises(RuntimeError, match="already active"):
        manager.start(baseline())
    assert gateway.creates == 2 and len(store.list()) == before


def test_active_polling_does_not_consume_blob_inventory_operations(setup):
    manager, _, gateway, provider = setup
    state = manager.start(baseline())
    handle = gateway.handles[state["id"]]
    handle.local.update(status="running", phase="Initialization", progress=[{"iteration": 2}])
    provider.calls.clear()
    for _ in range(8):
        assert manager.status(state["id"])["phase"] == "Initialization"
    assert provider.calls == []


def test_local_completed_stays_publishing_until_durable_terminal_and_probes_are_throttled(setup, monkeypatch):
    manager, _, gateway, provider = setup
    state = manager.start(baseline())
    handle = gateway.handles[state["id"]]
    handle.local.update(status="completed", phase="Completed", converged=True)
    assert manager.status(state["id"])["status"] == "running"
    provider.calls.clear()
    for _ in range(8):
        pending = manager.status(state["id"])
        assert pending["phase"] == "Publishing" and pending["files"] == []
    assert provider.calls == []
    publish(setup, state["id"])
    future = time.monotonic() + 11
    monkeypatch.setattr("openstream.cloud.manager.time.monotonic", lambda: future)
    complete = manager.status(state["id"])
    assert complete["status"] == "completed"
    assert all(row["url"].startswith("/files/") for row in complete["files"])
    assert ".private.blob." not in json.dumps(complete)
    provider.calls.clear()
    complete["status"] = "corrupted browser copy"
    assert manager.status(state["id"])["status"] == "completed"
    assert provider.calls == []


def test_stopped_worker_checks_terminal_twice_and_retains_failure_without_claiming_success(setup):
    manager, _, gateway, provider = setup
    state = manager.start(baseline())
    gateway.handles[state["id"]].running = False
    provider.calls.clear()
    failed = manager.status(state["id"])
    assert failed["status"] == "failed" and failed["phase"] == "Interrupted"
    terminal_lists = [call for call in provider.calls if call[0] == "list" and "/terminal/" in call[1]]
    assert len(terminal_lists) == 2
    assert gateway.handles[state["id"]].launches == 1
    assert failed["files"][0]["name"] == "submitted_inputs.json"


def test_durable_terminal_wins_over_interruption_evidence(setup, monkeypatch):
    manager, _, gateway, _ = setup
    state = manager.start(baseline())
    gateway.handles[state["id"]].running = False
    assert manager.status(state["id"])["status"] == "failed"
    publish(setup, state["id"])
    future = time.monotonic() + 11
    monkeypatch.setattr("openstream.cloud.manager.time.monotonic", lambda: future)
    assert manager.status(state["id"])["status"] == "completed"


def test_provider_outage_does_not_become_false_numerical_failure(setup):
    manager, store, gateway, _ = setup
    state = manager.start(baseline())
    gateway.failure = "get"
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        manager.status(state["id"])
    assert not store.list(f"jobs/{state['id']}/publication-failures/")
    assert gateway.handles[state["id"]].running


@pytest.mark.parametrize("failure_point", ["get", "status_files"])
@pytest.mark.parametrize("terminal_status", ["completed", "failed", "cancelled", "publication-failure"])
def test_provider_outage_recovers_verified_durable_result_without_restarting(
        setup, monkeypatch, failure_point, terminal_status):
    manager, store, gateway, provider = setup
    run_id = manager.start(baseline())["id"]
    manifest = manager._manifest(run_id)
    # Existing negative inventory observations must not hide a new terminal.
    assert manager._terminal(manifest) is None
    assert manager._failure_record(manifest) is None
    if terminal_status == "publication-failure":
        manager._record_failure(manifest, manifest["public_initial_state"],
            phase="Publication failed", message="Retained test failure")
        manager._failures.clear()
        expected = "failed"
    else:
        publish(setup, run_id, terminal_status)
        expected = terminal_status
    if failure_point == "get":
        gateway.failure = "get"
    else:
        def unavailable(directory):
            raise RuntimeError("test lifecycle race")
        monkeypatch.setattr(gateway.handles[run_id], "status_files", unavailable)
    provider.calls.clear()
    recovered = manager.status(run_id)
    assert recovered["status"] == expected
    assert ".private.blob." not in json.dumps(recovered)
    assert all(row["url"].startswith("/files/") for row in recovered["files"])
    assert gateway.creates == 1 and gateway.handles[run_id].launches == 1
    assert gateway.handles[run_id].stops == 0
    assert not any(call[0] == "put" for call in provider.calls)
    # A genuinely cold request must recover the same result, too.
    cold = CloudRunManager(store, gateway, source=manager.source, environment=manager.environment)
    assert cold.status(run_id)["status"] == expected


def test_provider_outage_does_not_serve_invalid_terminal(setup):
    manager, store, gateway, provider = setup
    run_id = manager.start(baseline())["id"]
    terminal = publish(setup, run_id)
    terminal["runtime"] = {"different": "session"}
    row = store.list(f"jobs/{run_id}/terminal/")[0]
    provider.objects[store.prefix + row["key"]] = json.dumps(terminal).encode()
    gateway.failure = "get"
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        manager.status(run_id)
    assert not store.list(f"jobs/{run_id}/publication-failures/")
    assert gateway.handles[run_id].stops == 0


def test_combined_provider_and_inventory_outage_preserves_job_state(setup, monkeypatch):
    manager, store, gateway, provider = setup
    run_id = manager.start(baseline())["id"]
    gateway.failure = "get"
    def unavailable(prefix=""):
        raise CloudStoreError("test inventory unavailable")
    monkeypatch.setattr(store, "list", unavailable)
    provider.calls.clear()
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        manager.status(run_id)
    assert gateway.handles[run_id].running and gateway.handles[run_id].stops == 0
    assert not any(call[0] == "put" for call in provider.calls)


def test_cancel_is_request_only_until_worker_acknowledgement(setup):
    manager, _, gateway, _ = setup
    state = manager.start(baseline())
    requested = manager.cancel(state["id"])
    assert requested["status"] == "queued" and requested["phase"] == "Cancellation requested"
    handle = gateway.handles[state["id"]]
    assert handle.cancellations == 1 and handle.stops == 0
    assert manager.status(state["id"])["status"] == "queued"
    publish(setup, state["id"], "cancelled"); handle.running = False
    assert manager.cancel(state["id"])["status"] == "cancelled"
    assert handle.cancellations == 1


def test_profiles_and_streamed_downloads_require_verified_durable_receipts(setup):
    manager, _, gateway, _ = setup
    state = manager.start(baseline())
    with pytest.raises(RuntimeError, match="not ready"):
        manager.download(state["id"], "submitted_inputs.json")
    terminal = publish(setup, state["id"])
    gateway.handles[state["id"]].running = False
    assert manager.data(state["id"])["datasets"]["physical"]["z"] == [0.0, 1.0]
    chunks, mime = manager.download(state["id"], "results.zip")
    assert mime == "application/zip" and b"".join(chunks) == b"zip-test-evidence"
    assert ".private.blob." not in json.dumps(manager.status(state["id"]))
    assert terminal["plot_data"]["sha256"]


@pytest.mark.parametrize("filename", ["../secrets", "/secrets", "output/../secrets", "output\\secrets", "https://example.com/a", "output/\x00x"])
def test_download_path_escape_rejected_before_storage_or_gateway(setup, filename):
    manager, _, gateway, provider = setup
    provider.calls.clear()
    with pytest.raises(KeyError):
        manager.download("a" * 32, filename)
    assert provider.calls == [] and gateway.gets == 0


@pytest.mark.parametrize("corruption", ["url", "key", "hash", "size", "source"])
def test_terminal_receipt_or_provenance_tampering_is_rejected(setup, corruption):
    manager, store, gateway, provider = setup
    state = manager.start(baseline()); run_id = state["id"]
    terminal = publish(setup, run_id)
    if corruption == "source":
        terminal["source"] = {"different": True}
    else:
        receipt = terminal["artifacts"]["results.zip"]
        if corruption == "url": receipt["url"] = "https://example.com/private"
        if corruption == "key": receipt["key"] = receipt["key"].replace(run_id, "b" * 32)
        if corruption == "hash": receipt["sha256"] = "invalid"
        if corruption == "size": receipt["size"] = -1
    row = store.list(f"jobs/{run_id}/terminal/")[0]
    provider.objects[store.prefix + row["key"]] = json.dumps(terminal).encode()
    gateway.handles[run_id].running = False
    with pytest.raises(CloudStoreError):
        manager.status(run_id)


def test_corrupted_artifact_delivers_no_bytes(setup):
    manager, store, gateway, provider = setup
    state = manager.start(baseline()); run_id = state["id"]
    terminal = publish(setup, run_id)
    gateway.handles[run_id].running = False
    receipt = terminal["artifacts"]["results.zip"]
    provider.objects[store.prefix + receipt["key"]] = b"corrupted"
    chunks, _ = manager.download(run_id, "results.zip")
    with pytest.raises(CloudStoreError, match="hash or size"):
        next(chunks)


def test_multiple_terminal_records_are_not_silently_selected(setup):
    manager, store, gateway, _ = setup
    state = manager.start(baseline()); run_id = state["id"]
    second = publish(setup, run_id)
    second["status"]["status"] = "cancelled"
    store.put_json(f"jobs/{run_id}/terminal/{uuid.uuid4().hex}.json", second)
    gateway.handles[run_id].running = False
    with pytest.raises(CloudStoreError, match="Multiple terminal"):
        manager.status(run_id)


def test_new_manager_restores_history_without_resuming_workers(setup):
    manager, store, gateway, _ = setup
    state = manager.start(baseline()); run_id = state["id"]
    publish(setup, run_id); gateway.handles[run_id].running = False
    fresh = CloudRunManager(store, gateway, source=manager.source, environment=manager.environment)
    assert fresh.history()[0]["status"] == "completed"
    assert gateway.handles[run_id].launches == 1 and gateway.creates == 1


@pytest.mark.parametrize("stage", ["prepare", "launch"])
def test_cold_queued_probe_recovers_startup_failure_when_sandbox_stop_also_failed(setup, monkeypatch, stage):
    manager, store, gateway, _ = setup
    gateway.failure = stage
    def stop_failure(self):
        self.stops += 1
        raise RuntimeError("provider stop failed")
    monkeypatch.setattr(Handle, "stop", stop_failure)
    state = manager.start(baseline()); run_id = state["id"]
    assert state["status"] == "failed" and gateway.handles[run_id].running
    fresh = CloudRunManager(store, gateway, source=manager.source, environment=manager.environment)
    restored = fresh.status(run_id)
    assert restored["status"] == "failed" and restored["phase"] == "Worker could not start"
    assert gateway.handles[run_id].launches == (1 if stage == "launch" else 0)


def test_cold_queued_negative_probe_is_performed_only_once(setup):
    manager, store, gateway, provider = setup
    state = manager.start(baseline()); run_id = state["id"]
    fresh = CloudRunManager(store, gateway, source=manager.source, environment=manager.environment)
    provider.calls.clear()
    assert fresh.status(run_id)["status"] == "queued"
    terminal_lists = [call for call in provider.calls if call[0] == "list" and "/terminal/" in call[1]]
    assert len(terminal_lists) == 1
    provider.calls.clear()
    for _ in range(5):
        assert fresh.status(run_id)["status"] == "queued"
    assert provider.calls == []


def bootstrap_failure(setup):
    manager, _, gateway, _ = setup
    state = manager.start(baseline()); run_id = state["id"]
    handle = gateway.handles[run_id]
    handle.cloud = {**handle.local, "status": "failed", "phase": "Worker setup failed", "error": "Environment could not start"}
    handle.bootstrap_log = lambda job_dir: b"test dependency resolution failure\n"
    return run_id, handle


def test_bootstrap_log_and_failure_are_durable_before_stop(setup, monkeypatch):
    manager, store, _, provider = setup
    run_id, handle = bootstrap_failure(setup)
    original = handle.stop
    def ordered_stop():
        assert any(key.endswith("/bootstrap.log") for key in provider.objects)
        records = store.list(f"jobs/{run_id}/publication-failures/")
        assert len(records) == 1
        assert "bootstrap.log" in store.get_json_by_url(records[0]["url"])["artifacts"]
        original()
    monkeypatch.setattr(handle, "stop", ordered_stop)
    failed = manager.status(run_id)
    assert failed["status"] == "failed" and failed["phase"] == "Worker setup failed"
    assert {row["name"] for row in failed["files"]} == {"bootstrap.log", "submitted_inputs.json"}
    chunks, _ = manager.download(run_id, "bootstrap.log")
    assert b"".join(chunks) == b"test dependency resolution failure\n"
    assert handle.stops == 1 and not handle.running


@pytest.mark.parametrize("failure", ["retrieve", "upload"])
def test_missing_or_failed_bootstrap_log_upload_is_not_claimed_as_an_artifact(setup, monkeypatch, failure):
    manager, store, _, _ = setup
    run_id, handle = bootstrap_failure(setup)
    if failure == "retrieve":
        def missing(job_dir):
            raise OSError("test log unavailable")
        handle.bootstrap_log = missing
    else:
        original = store.put_bytes
        def rejected(key, *args, **kwargs):
            if key.endswith("/bootstrap.log"):
                raise CloudStoreError("test upload unavailable")
            return original(key, *args, **kwargs)
        monkeypatch.setattr(store, "put_bytes", rejected)
    failed = manager.status(run_id)
    assert failed["status"] == "failed" and "could not be retrieved or published" in failed["error"]
    assert [row["name"] for row in failed["files"]] == ["submitted_inputs.json"]
    assert handle.stops == 1


def test_bootstrap_failure_receipt_outage_does_not_destroy_ephemeral_evidence(setup, monkeypatch):
    manager, store, _, _ = setup
    run_id, handle = bootstrap_failure(setup)
    original = store.put_json
    def rejected(key, *args, **kwargs):
        if "/publication-failures/" in key:
            raise CloudStoreError("test failure receipt unavailable")
        return original(key, *args, **kwargs)
    monkeypatch.setattr(store, "put_json", rejected)
    with pytest.raises(CloudStoreError, match="receipt unavailable"):
        manager.status(run_id)
    assert handle.stops == 0 and handle.running
