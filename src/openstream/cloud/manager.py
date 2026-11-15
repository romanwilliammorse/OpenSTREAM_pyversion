"""Durable hosted job orchestration; never executes or changes solver equations."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import mimetypes
from pathlib import PurePosixPath
import re
import tempfile
import threading
import time
from urllib.parse import quote, urlsplit
import uuid

from ..gui_schema import assess_payload, framework_name, validate_payload
from .storage import BlobMissingError, CloudStoreError


TERMINAL = {"completed", "failed", "cancelled"}
PUBLIC_FIELDS = {"id", "framework", "status", "phase", "created_at", "finished_at", "progress",
                 "files", "converged", "error", "is_reference", "changes", "change_count", "reference", "physical"}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _id(value):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise KeyError("Unknown run")
    return value


def _filename(value):
    if (not isinstance(value, str) or not value or "\\" in value or ":" in value
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or any(part in ("", ".", "..") for part in value.split("/"))):
        raise KeyError("Unknown file")
    return value


class CloudRunManager:
    """One-shot jobs with immutable manifests and a best-effort admission cap.

    The gateway may attach to an existing session, never resume it. No automatic
    calculation retries are performed. Immutable records are cached per process;
    active status polling reads Sandbox files without inventorying Blob objects.
    The application cap is not an atomic distributed quota; the provider's hard
    sandbox cap is an additional, separately configured constraint.
    """
    def __init__(self, store, gateway, *, source, environment, max_active=2,
                 cache_size=128, terminal_probe_seconds=10):
        if type(max_active) is not int or not 1 <= max_active <= 2:
            raise ValueError("max_active must be one or two")
        if type(cache_size) is not int or cache_size < 1:
            raise ValueError("cache_size must be positive")
        self.store, self.gateway = store, gateway
        self.source, self.environment = deepcopy(source), deepcopy(environment)
        self.max_active, self.cache_size = max_active, cache_size
        self.terminal_probe_seconds = terminal_probe_seconds
        self._manifests, self._terminals = OrderedDict(), OrderedDict()
        self._probes, self._failures, self._failure_probes = OrderedDict(), OrderedDict(), OrderedDict()
        self._queued_observed = OrderedDict()
        self._lock = threading.RLock()

    def _cache(self, cache, key, value):
        with self._lock:
            cache[key] = deepcopy(value)
            cache.move_to_end(key)
            while len(cache) > self.cache_size:
                cache.popitem(last=False)

    def _cached(self, cache, key):
        with self._lock:
            if key not in cache:
                return None
            cache.move_to_end(key)
            return deepcopy(cache[key])

    def _manifest(self, run_id):
        _id(run_id)
        cached = self._cached(self._manifests, run_id)
        if cached is not None:
            return cached
        try:
            value = self.store.get_json(f"runs/{run_id}.json")
        except BlobMissingError:
            raise KeyError("Unknown run") from None
        return self._remember_manifest(run_id, value)

    def _remember_manifest(self, run_id, value):
        if (not isinstance(value, dict) or value.get("schema") != "openstream-cloud-job-v1"
                or value.get("id") != run_id or not isinstance(value.get("runtime"), dict)
                or value.get("public_initial_state", {}).get("id") != run_id):
            raise CloudStoreError("Stored job manifest is invalid.")
        self._cache(self._manifests, run_id, value)
        return deepcopy(value)

    @staticmethod
    def _directory(run_id):
        return f"/vercel/sandbox/jobs/{_id(run_id)}"

    def _public(self, state, *, artifacts=None):
        # Transport receipts are server-only, even if a stored status is malformed.
        value = {key: deepcopy(item) for key, item in state.items() if key in PUBLIC_FIELDS}
        def redact(item):
            if isinstance(item, str):
                return re.sub(r"https://[^\s\"<>]*\.private\.blob\.vercel-storage\.com[^\s\"<>]*", "[private storage]", item)
            if isinstance(item, list):
                return [redact(part) for part in item]
            if isinstance(item, dict):
                return {key: redact(part) for key, part in item.items()}
            return item
        value = redact(value)
        value["files"] = [] if artifacts is None else [
            {"name": name, "url": f"/files/{value['id']}/{quote(name, safe='/')}"}
            for name in sorted(artifacts) if name != "plot_data.json"]
        return value

    def _receipt(self, manifest, name, receipt):
        _filename(name)
        if not isinstance(receipt, dict):
            raise CloudStoreError("Artifact receipt is invalid.")
        digest, size, key, url = (receipt.get(field) for field in ("sha256", "size", "key", "url"))
        if (not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or type(size) is not int or size < 0):
            raise CloudStoreError("Artifact hash or size is invalid.")
        allowed = {f"jobs/{manifest['id']}/artifacts/{digest}/{name}"}
        # Inputs are durably stored before a sandbox can exist. This receipt is
        # retained if provisioning fails, and has the same integrity guarantee.
        if name == "submitted_inputs.json" and digest == manifest["submitted_inputs_sha256"]:
            allowed.add(f"jobs/{manifest['id']}/submitted_inputs.json")
        if key not in allowed:
            raise CloudStoreError("Artifact key does not match this job and its hash.")
        try:
            self.store._url(url)
            if urlsplit(url).path != "/" + self.store.prefix + key:
                raise ValueError("Receipt URL differs from key")
        except (ValueError, TypeError):
            raise CloudStoreError("Artifact URL is outside its private namespace.") from None
        return deepcopy(receipt)

    def _validate_terminal(self, manifest, value, *, failure=False):
        run_id = manifest["id"]
        if (not isinstance(value, dict) or value.get("schema") != "openstream-cloud-terminal-v1"
                or value.get("id") != run_id or not isinstance(value.get("status"), dict)
                or value["status"].get("id") != run_id
                or value["status"].get("framework") != manifest["framework"]
                or value["status"].get("status") not in TERMINAL
                or any(value.get(key) != manifest.get(key) for key in ("source", "environment", "runtime"))
                or not isinstance(value.get("artifacts"), dict)
                or not isinstance(value.get("publication"), dict)):
            raise CloudStoreError("Stored terminal manifest is invalid.")
        if failure and value["status"]["status"] != "failed":
            raise CloudStoreError("Failure evidence cannot declare a successful calculation.")
        for name, receipt in value["artifacts"].items():
            self._receipt(manifest, name, receipt)
        plot = value.get("plot_data")
        if plot != value["artifacts"].get("plot_data.json"):
            raise CloudStoreError("Plot receipt differs from the artifact manifest.")
        if value["status"]["status"] == "completed":
            if value["publication"].get("complete") is not True or not {
                    "submitted_inputs.json", "results.zip", "output/results.npz", "plot_data.json"} <= value["artifacts"].keys():
                raise CloudStoreError("Completed calculation has no complete durable output manifest.")
        return deepcopy(value)

    def _terminal(self, manifest, *, force=False):
        run_id = manifest["id"]
        cached = self._cached(self._terminals, run_id)
        if cached is not None:
            return cached
        previous = self._cached(self._probes, run_id)
        if not force and previous is not None and time.monotonic() - previous < self.terminal_probe_seconds:
            return None
        prefix = f"jobs/{run_id}/terminal/"
        rows = self.store.list(prefix)
        if len(rows) > 1:
            raise CloudStoreError("Multiple terminal manifests require manual review.")
        self._cache(self._probes, run_id, time.monotonic())
        if rows:
            value = self._validate_terminal(manifest, self.store.get_json_by_url(rows[0]["url"]))
            self._cache(self._terminals, run_id, value)
            return value
        return None

    def _failure_record(self, manifest):
        run_id = manifest["id"]
        cached = self._cached(self._failures, run_id)
        if cached is not None:
            return cached
        previous = self._cached(self._failure_probes, run_id)
        if previous is not None and time.monotonic() - previous < self.terminal_probe_seconds:
            return None
        rows = self.store.list(f"jobs/{run_id}/publication-failures/")
        self._cache(self._failure_probes, run_id, time.monotonic())
        if not rows:
            return None
        row = sorted(rows, key=lambda item: (item.get("uploaded_at", ""), item["key"]))[-1]
        value = self._validate_terminal(manifest, self.store.get_json_by_url(row["url"]), failure=True)
        self._cache(self._failures, manifest["id"], value)
        return value

    def _input_receipt(self, manifest):
        key = f"jobs/{manifest['id']}/submitted_inputs.json"
        matches = [item for item in self.store.list(key) if item["key"] == key]
        if len(matches) != 1:
            raise CloudStoreError("Retained submitted inputs could not be located.")
        item = matches[0]
        return {"key": key, "url": item["url"], "size": item["size"], "sha256": manifest["submitted_inputs_sha256"]}

    def _record_failure(self, manifest, state, *, phase, message, canonical=False, input_receipt=None, extra_artifacts=None):
        run_id = manifest["id"]
        existing = self._cached(self._failures, run_id)
        if existing is not None and not canonical:
            return existing
        state = {**state, "status": "failed", "phase": phase, "error": message, "finished_at": _now(), "files": []}
        receipt = input_receipt or self._input_receipt(manifest)
        value = {"schema": "openstream-cloud-terminal-v1", "id": run_id,
                 "status": self._public(state), "artifacts": {"submitted_inputs.json": receipt, **(extra_artifacts or {})},
                 "plot_data": None, "source": manifest["source"], "environment": manifest["environment"],
                 "runtime": manifest["runtime"], "published_at": _now(),
                 "publication": {"complete": False, "stage": phase, "child_exit_code": None, "error_type": "CloudExecutionFailure"}}
        self._validate_terminal(manifest, value, failure=True)
        prefix = "terminal" if canonical else "publication-failures"
        self.store.put_json(f"jobs/{run_id}/{prefix}/{uuid.uuid4().hex}.json", value)
        self._cache(self._terminals if canonical else self._failures, run_id, value)
        return value

    def start(self, payload):
        payload = deepcopy(payload)
        validate_payload(payload)
        payload["framework"] = framework_name(payload["framework"])
        assessment = assess_payload(payload)
        # This process lock prevents local duplicate admission. Other instances
        # can race: the documented cap is best effort, never an atomic claim.
        with self._lock:
            if sum(item["status"] not in TERMINAL for item in self.history()) >= self.max_active:
                raise RuntimeError("Two calculations are already active. Wait or cancel a run before starting another.")
            run_id, created = uuid.uuid4().hex, _now()
            input_bytes = _bytes(payload)
            receipt = self.store.put_bytes(f"jobs/{run_id}/submitted_inputs.json", input_bytes, "application/json")
            state = {"id": run_id, "framework": payload["framework"], "status": "queued", "phase": "Starting",
                     "created_at": created, "progress": [], "files": [], "converged": None, "error": None,
                     **assessment, "reference": {"status": "not_compared", "message": "Comparison runs after the calculation."},
                     "physical": {"status": "not_checked", "message": "Consistency checks run after the calculation."}}
            manifest = {"schema": "openstream-cloud-job-v1", "id": run_id, "created_at": created,
                        "framework": payload["framework"], "submitted_inputs_sha256": hashlib.sha256(input_bytes).hexdigest(),
                        "source": deepcopy(self.source), "environment": deepcopy(self.environment),
                        "runtime": {}, "public_initial_state": deepcopy(state)}
            handle, launched, persisted = None, False, False
            try:
                handle = self.gateway.create(run_id)
                manifest["runtime"] = deepcopy(handle.runtime)
                self.store.put_json(f"runs/{run_id}.json", manifest)
                persisted = True
                self._remember_manifest(run_id, manifest)
                self._cache(self._queued_observed, run_id, True)
                directory = self._directory(run_id)
                handle.prepare({f"{directory}/submitted_inputs.json": input_bytes,
                                f"{directory}/status.json": _bytes(state),
                                f"{directory}/job_manifest.json": _bytes(manifest)})
                # An exception during launch may mean the command started but
                # its acknowledgement was lost. Never issue a second launch.
                launched = True
                handle.launch(directory)
                return self._public(state)
            except Exception:
                if handle is not None:
                    try:
                        handle.stop()  # Gateway checks the actual session identity.
                    except Exception:
                        pass
                if not persisted:
                    try:
                        stored = self.store.get_json(f"runs/{run_id}.json")
                    except BlobMissingError:
                        self.store.put_json(f"runs/{run_id}.json", manifest)
                        stored = manifest
                    if stored != manifest:
                        raise CloudStoreError("Run manifest publication could not be confirmed.") from None
                    self._remember_manifest(run_id, stored)
                failed = self._record_failure(manifest, state, phase="Worker could not start",
                    message="Cloud worker could not start. Submitted inputs and job provenance are retained.",
                    canonical=not launched, input_receipt=receipt)
                return self._public(failed["status"], artifacts=failed["artifacts"])

    def history(self):
        rows = self.store.list("runs/")
        rows = sorted(rows, key=lambda item: (item.get("uploaded_at", ""), item["key"]), reverse=True)[:20]
        states = []
        for item in rows:
            match = re.fullmatch(r"runs/([0-9a-f]{32})\.json", item["key"])
            if match is None:
                continue
            run_id = match.group(1)
            if self._cached(self._manifests, run_id) is None:
                self._remember_manifest(run_id, self.store.get_json_by_url(item["url"]))
            states.append(self.status(run_id))
        return sorted(states, key=lambda item: item["created_at"], reverse=True)

    def status(self, run_id):
        manifest = self._manifest(run_id)
        terminal = self._cached(self._terminals, run_id)
        if terminal is not None:
            return self._public(terminal["status"], artifacts=terminal["artifacts"])
        initial = manifest["public_initial_state"]
        if not manifest["runtime"]:
            terminal = self._terminal(manifest, force=True) or self._failure_record(manifest)
            if terminal:
                return self._public(terminal["status"], artifacts=terminal["artifacts"])
            return self._public({**initial, "status": "failed", "phase": "Provisioning interrupted", "error": "No worker runtime was created."})
        try:
            handle = self.gateway.get(manifest["runtime"])
            running = handle.is_running()
            local, cloud = None, None
            if running:
                try:
                    local, cloud = handle.status_files(self._directory(run_id))
                except Exception:
                    if handle.is_running():
                        raise
                    running = False  # Session stopped during the file read.
        except Exception:
            # A provider/network outage is not evidence that the solver stopped.
            raise RuntimeError("Cloud worker status is temporarily unavailable; job state has not been changed.") from None
        for state in (local, cloud):
            if state is not None and (not isinstance(state, dict) or state.get("id") != run_id
                    or state.get("framework") != manifest["framework"]
                    or state.get("status") not in TERMINAL | {"queued", "running"}):
                raise CloudStoreError("Worker status identity differs from its run manifest.")
        live = local or cloud or initial
        if running and live.get("status") == "queued" and not self._cached(self._queued_observed, run_id):
            # A cache-cold instance may be observing a setup failure whose
            # sandbox stop failed. Its immutable failure record must win over
            # a stale queued file. One negative observation is remembered.
            terminal = self._terminal(manifest)
            if terminal is None:
                terminal = self._failure_record(manifest)
            self._cache(self._queued_observed, run_id, True)
            if terminal is not None:
                return self._public(terminal["status"], artifacts=terminal["artifacts"])
        needs_publication = live.get("status") in TERMINAL or (cloud or {}).get("status") in TERMINAL or (cloud or {}).get("phase") == "Publishing"
        if running and not needs_publication:
            return self._public(live)
        terminal = self._terminal(manifest)
        if terminal is not None:
            return self._public(terminal["status"], artifacts=terminal["artifacts"])
        if not running and self._cached(self._failures, run_id) is None:
            # Re-read after the stopped observation; a successful upload can
            # have completed immediately before the sandbox stopped.
            terminal = self._terminal(manifest, force=True)
            if terminal is not None:
                return self._public(terminal["status"], artifacts=terminal["artifacts"])
        failure = self._failure_record(manifest)
        if failure:
            return self._public(failure["status"], artifacts=failure["artifacts"])
        if running and (cloud or {}).get("status") == "failed" and cloud.get("phase") == "Worker setup failed":
            artifacts = {}
            try:
                body = handle.bootstrap_log(self._directory(run_id))
                if not isinstance(body, bytes) or len(body) > 1024 * 1024:
                    raise ValueError("Bootstrap log exceeds retrieval contract")
                digest = hashlib.sha256(body).hexdigest()
                receipt = self.store.put_bytes(f"jobs/{run_id}/artifacts/{digest}/bootstrap.log", body, "text/plain")
                artifacts["bootstrap.log"] = self._receipt(manifest, "bootstrap.log", receipt)
                message = "Pinned cloud environment could not start. Bootstrap log and submitted inputs are retained."
            except Exception:
                message = "Pinned cloud environment could not start. Bootstrap log could not be retrieved or published; submitted inputs are retained."
            failure = self._record_failure(manifest, cloud, phase="Worker setup failed",
                message=message, extra_artifacts=artifacts)
            # Preserve the log and failure receipt before stopping its only VM.
            # If publication fails, the exception leaves the worker allocated
            # for evidence recovery until its declared infrastructure deadline.
            try:
                handle.stop()
            except Exception:
                pass  # Durable failure evidence remains; deadline bounds allocation.
            return self._public(failure["status"], artifacts=failure["artifacts"])
        if not running or (cloud or {}).get("status") == "failed":
            failure = self._record_failure(manifest, cloud or live,
                phase="Interrupted" if not running else "Cloud worker failed",
                message="Worker stopped without a confirmed durable terminal result. Retained inputs remain available.")
            return self._public(failure["status"], artifacts=failure["artifacts"])
        return self._public({**live, "status": "running", "phase": "Publishing"})

    def cancel(self, run_id):
        state = self.status(run_id)
        if state["status"] in TERMINAL:
            return state
        manifest = self._manifest(run_id)
        self.gateway.get(manifest["runtime"]).request_cancel(self._directory(run_id))
        # Return a request acknowledgement, never claim that the child stopped.
        return {**state, "phase": "Cancellation requested"}

    def _result(self, run_id):
        manifest = self._manifest(run_id)
        terminal = self._terminal(manifest, force=True)
        if terminal is None:
            terminal = self._failure_record(manifest)
        if terminal is None:
            raise RuntimeError("Durable results are not ready.")
        return manifest, terminal

    def _verified_bytes(self, manifest, name, receipt):
        receipt = self._receipt(manifest, name, receipt)
        body = self.store.read_bytes_by_url(receipt["url"])
        if len(body) != receipt["size"] or hashlib.sha256(body).hexdigest() != receipt["sha256"]:
            raise CloudStoreError("Artifact bytes differ from the recorded hash or size.")
        return body

    def data(self, run_id):
        manifest, terminal = self._result(run_id)
        if terminal["status"]["status"] != "completed" or terminal["publication"].get("complete") is not True:
            raise RuntimeError("Completed durable plot data are not available.")
        body = self._verified_bytes(manifest, "plot_data.json", terminal["plot_data"])
        def invalid_constant(_):
            raise ValueError("Nonfinite plot JSON")
        value = json.loads(body.decode("utf-8"), parse_constant=invalid_constant)
        if not isinstance(value, dict) or not isinstance(value.get("datasets"), dict):
            raise CloudStoreError("Plot data have an invalid schema.")
        return value

    def download(self, run_id, filename):
        _filename(filename)
        manifest, terminal = self._result(run_id)
        if filename not in terminal["artifacts"]:
            raise KeyError("Unknown file")
        receipt = self._receipt(manifest, filename, terminal["artifacts"][filename])
        def chunks():
            # Verify the entire object before delivering any numerical bytes.
            # Large downloads spill to ephemeral disk, not unbounded RAM.
            with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b") as spool:
                digest, size = hashlib.sha256(), 0
                for chunk in self.store.iter_bytes_by_url(receipt["url"]):
                    size += len(chunk)
                    if size > receipt["size"]:
                        raise CloudStoreError("Artifact exceeds its recorded size.")
                    digest.update(chunk)
                    spool.write(chunk)
                if size != receipt["size"] or digest.hexdigest() != receipt["sha256"]:
                    raise CloudStoreError("Artifact bytes differ from the recorded hash or size.")
                spool.seek(0)
                while body := spool.read(65536):
                    yield body
        suffix = PurePosixPath(filename).suffix.lower()
        standard = {".zip": "application/zip", ".json": "application/json", ".csv": "text/csv",
                    ".png": "image/png", ".pdf": "application/pdf", ".npz": "application/octet-stream"}
        return chunks(), standard.get(suffix) or mimetypes.guess_type(filename)[0] or "application/octet-stream"
