"""Publish an unchanged native GUI job from a disposable cloud worker.

The terminal manifest is the commit record. A local ``completed`` status is
only ``running / Publishing`` to the hosted application until that record is
durable. This module never changes a solver, closure, or convergence criterion.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import mimetypes
import os
from pathlib import Path, PurePosixPath
import platform
import re
import stat
import subprocess
import sys
from urllib.parse import quote
import uuid


TERMINAL = {"completed", "failed", "cancelled"}
ROOT_ARTIFACTS = {"submitted_inputs.json", "job_manifest.json", "status.json",
                  "worker.log", "results.zip", "plot_data.json"}


class CloudWorkerError(RuntimeError):
    """An infrastructure error with a deliberately non-sensitive message."""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _json_bytes(value):
    return (json.dumps(value, indent=2, allow_nan=False) + "\n").encode("utf-8")


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, value):
    from ..gui_worker import write_json
    write_json(path, value)


def _not_link(path):
    if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
        raise CloudWorkerError("Symbolic links and junctions are not allowed in jobs.")


def _directory(directory, run_id):
    if not isinstance(run_id, str) or re.fullmatch(r"[0-9a-f]{32}", run_id) is None:
        raise CloudWorkerError("Invalid run identifier.")
    path = Path(directory)
    if ".." in path.parts or path.name != run_id:
        raise CloudWorkerError("Invalid job directory.")
    path = path.absolute()
    for ancestor in (path, *path.parents):
        _not_link(ancestor)
    if not path.is_dir():
        raise CloudWorkerError("Job directory does not exist.")
    return path.resolve()


def _safe_tree(directory):
    """Inspect even excluded control files; never follow links or devices."""
    files = []
    for parent, dirs, names in os.walk(directory, followlinks=False):
        for name in dirs + names:
            path = Path(parent)/name
            _not_link(path)
            relative = path.relative_to(directory)
            if any(part in ("", ".", "..") or ":" in part or "\\" in part
                   for part in relative.parts):
                raise CloudWorkerError("Unsafe artifact filename.")
            mode = path.lstat().st_mode
            if not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
                raise CloudWorkerError("Only regular job files are supported.")
            if stat.S_ISREG(mode):
                files.append(path)
    return sorted(files)


def _load_manifest(directory, run_id):
    manifest = _read_json(directory/"job_manifest.json")
    state = _read_json(directory/"status.json")
    if (manifest.get("schema") != "openstream-cloud-job-v1"
            or manifest.get("id") != run_id or state.get("id") != run_id
            or manifest.get("public_initial_state", {}).get("id") != run_id):
        raise CloudWorkerError("Job identity does not match its manifest.")
    for key in ("source", "environment", "runtime", "public_initial_state"):
        if not isinstance(manifest.get(key), dict):
            raise CloudWorkerError("Job provenance is incomplete.")
    if state.get("framework") != manifest.get("framework"):
        raise CloudWorkerError("Job framework does not match its manifest.")
    # The server writes this credential-free manifest. Credentials belong only
    # in the wrapper environment, never in an artifact or public status.
    def check_keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if re.search(r"token|password|secret|credential|api.?key", key, re.I):
                    raise CloudWorkerError("Credentials must not be stored in job metadata.")
                check_keys(item)
        elif isinstance(value, list):
            for item in value:
                check_keys(item)
    check_keys(manifest)
    return manifest, state


def _verify_sources(manifest):
    import openstream
    package = Path(openstream.__file__).resolve().parent
    inventory = manifest["source"].get("module_sha256")
    if not isinstance(inventory, dict) or not inventory:
        raise CloudWorkerError("Source hash inventory is absent.")
    actual = {}
    for name, expected in inventory.items():
        relative = PurePosixPath(name)
        if (relative.is_absolute() or ".." in relative.parts or "\\" in name
                or relative.parts[:2] != ("src", "openstream")
                or len(relative.parts) < 3):
            raise CloudWorkerError("Invalid source inventory path.")
        path = package.joinpath(*relative.parts[2:])
        if not path.resolve().is_relative_to(package):
            raise CloudWorkerError("Source inventory escapes the installed package.")
        _not_link(path)
        actual[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual[name] != expected:
            raise CloudWorkerError("Installed scientific source differs from the job manifest.")
    return actual


def _actual_environment():
    import openstream
    packages = {}
    for name in ("openstream-python", "numpy", "scipy", "CoolProp", "matplotlib",
                 "vercel-sandbox", "vercel-blob"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    packages["openstream-python"] = openstream.__version__
    return {"python": platform.python_version(), "implementation": platform.python_implementation(),
            "platform": platform.platform(), "packages": packages}


def _child_environment():
    # Property calculations require no hosting credentials. An allowlist also
    # prevents a native exception/third-party logger exposing inherited secrets.
    allowed = {"PATH", "PYTHONPATH", "PYTHONHOME", "SYSTEMROOT", "WINDIR", "TEMP", "TMP",
               "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "LANG", "LC_ALL",
               "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
               "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"}
    return {key: value for key, value in os.environ.items() if key.upper() in allowed}


def _run_child(directory):
    python = Path(sys.executable)
    if python.name.lower() == "pythonw.exe":
        python = python.with_name("python.exe")
    # No shell, numerical modifications, or hidden child timeout. The sandbox
    # has an explicitly declared infrastructure deadline outside this process.
    with (directory/"worker.log").open("ab") as log:
        process = subprocess.Popen([str(python), "-m", "openstream.gui_worker", str(directory)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            env=_child_environment(), creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        return process.wait()


def _put_artifact(store, run_id, name, body):
    from .storage import BlobConflictError
    digest = hashlib.sha256(body).hexdigest()
    key = f"jobs/{run_id}/artifacts/{digest}/{name}"
    content_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    try:
        receipt = store.put_bytes(key, body, content_type, overwrite=False)
    except BlobConflictError:
        # A prior interrupted publisher may have already stored this content.
        # Never overwrite it, or accept a collision without reading its bytes.
        existing = next((item for item in store.list(key) if item["key"] == key), None)
        if existing is None or store.read_bytes_by_url(existing["url"]) != body:
            raise CloudWorkerError("Existing artifact differs from its content-addressed key.") from None
        receipt = {"key": key, "url": existing["url"], "sha256": digest, "size": len(body)}
    if (receipt.get("sha256") != digest or receipt.get("size") != len(body)
            or not isinstance(receipt.get("url"), str)):
        raise CloudWorkerError("Artifact publication receipt does not match its contents.")
    return receipt


def _artifact_paths(directory):
    return [(path.relative_to(directory).as_posix(), path) for path in _safe_tree(directory)
            if path.relative_to(directory).as_posix() in ROOT_ARTIFACTS
            or path.relative_to(directory).as_posix().startswith("output/")]


def _public_files(run_id, artifacts):
    return [{"name": name, "url": f"/files/{run_id}/{quote(name, safe='/')}"}
            for name in sorted(artifacts) if name != "plot_data.json"]


def _terminal(manifest, state, artifacts, exit_code, complete, stage, error_type=None):
    return {"schema": "openstream-cloud-terminal-v1", "id": manifest["id"],
            "status": deepcopy(state), "artifacts": deepcopy(artifacts),
            "plot_data": deepcopy(artifacts.get("plot_data.json")),
            "source": deepcopy(manifest["source"]),
            "environment": deepcopy(manifest["environment"]),
            "runtime": deepcopy(manifest["runtime"]), "actual_environment": _actual_environment(),
            "published_at": _now(),
            "publication": {"complete": complete, "stage": stage,
                            "child_exit_code": exit_code, "error_type": error_type}}


def _write_terminal(store, key, terminal):
    """Recover a lost acknowledgement only by reading the exact stored value."""
    try:
        return store.put_json(key, terminal)
    except Exception:
        for item in store.list(key):
            if item["key"].endswith("/" + key) or item["key"] == key:
                if store.get_json_by_url(item["url"]) == terminal:
                    return item
        raise CloudWorkerError("Terminal publication could not be confirmed.") from None


def _stop_sandbox(manifest):
    runtime = manifest["runtime"]
    name = runtime.get("sandbox_name")
    session_id = runtime.get("session_id")
    if not name or not session_id or not (os.environ.get("VERCEL_OIDC_TOKEN")
            or os.environ.get("VERCEL_OIDC_TOKEN_FILE") or os.environ.get("VERCEL_TOKEN")):
        return "not_configured"
    # This is the actual pinned Python SDK interface, not the JS Sandbox.get.
    from vercel.sandbox.sync import get_sandbox
    sandbox = get_sandbox(name=name)
    if sandbox.current_session_id != session_id:
        raise CloudWorkerError("Refusing to stop a different sandbox session.")
    sandbox.stop()
    return "stopped"


def run_cloud_job(directory, run_id, *, store, stop_callback=None):
    """Run one job and return the server-only durable terminal manifest.

    Test callers inject a private-store fake and a zero-argument stop callback.
    Publication URLs must not be returned directly by public HTTP endpoints.
    """
    from ..gui_lock import FileLock
    directory = _directory(directory, run_id)
    _safe_tree(directory)
    manifest, state = _load_manifest(directory, run_id)
    with FileLock(directory/"cloud_worker.lock"):
        try:
            existing_terminal = store.list(f"jobs/{run_id}/terminal/")
        except Exception as error:
            # When the commit inventory is unavailable, starting another run
            # or writing another terminal could contradict an existing result.
            # Preserve local recovery evidence and leave the sandbox available.
            state = {**state, "status": "failed", "phase": "Cloud worker failed",
                     "error": "Existing publication could not be checked; calculation was not started.",
                     "finished_at": _now(), "files": []}
            terminal = _terminal(manifest, state, {}, None, False, "terminal_lookup", type(error).__name__)
            _write_json(directory/"cloud_failure.json", terminal)
            _write_json(directory/"cloud_status.json", state)
            _write_json(directory/"cloud_cleanup.json", {"status": "not_stopped_publication_unconfirmed"})
            return terminal
        if existing_terminal:
            raise CloudWorkerError("A terminal manifest already exists for this run.")
        artifacts, exit_code = {}, None
        terminal_key = f"jobs/{run_id}/terminal/{uuid.uuid4().hex}.json"
        terminal_attempted = durable = False
        stage = "verification"
        try:
            inputs = (directory/"submitted_inputs.json").read_bytes()
            if hashlib.sha256(inputs).hexdigest() != manifest.get("submitted_inputs_sha256"):
                raise CloudWorkerError("Submitted inputs differ from their manifest.")
            # Sandbox file transfer assigns epoch-zero mtime. The unchanged
            # native ZIP writer requires a DOS-era timestamp. Adjust filesystem
            # metadata only, after verifying the input bytes, before execution.
            if (directory/"submitted_inputs.json").stat().st_mtime < 315532800:
                os.utime(directory/"submitted_inputs.json", None)
            source_hashes = _verify_sources(manifest)
            if manifest["environment"].get("python_requirement") != "3.12" or sys.version_info[:2] != (3, 12):
                raise CloudWorkerError("The declared Python 3.12 runtime is required.")
            _write_json(directory/"cloud_status.json", state)
            stage = "calculation"
            exit_code = _run_child(directory)
            _safe_tree(directory)
            state = _read_json(directory/"status.json")
            if state.get("id") != run_id:
                raise CloudWorkerError("Worker status changed its run identifier.")
            if _verify_sources(manifest) != source_hashes:
                raise CloudWorkerError("Scientific source changed during execution.")
            if state.get("status") not in TERMINAL or (state.get("status") == "completed" and exit_code != 0):
                raise CloudWorkerError("Worker exit code and terminal status disagree.")
            publishing = {**state, "status": "running", "phase": "Publishing", "files": []}
            _write_json(directory/"cloud_status.json", publishing)
            stage = "plot_data"
            if state["status"] == "completed":
                from ..gui import plot_data
                data = plot_data(directory, state["framework"], bool(state.get("is_reference")))
                _write_json(directory/"plot_data.json", data)
            stage = "artifacts"
            for name, path in _artifact_paths(directory):
                artifacts[name] = _put_artifact(store, run_id, name, path.read_bytes())
            if state["status"] == "completed" and not {"results.zip", "output/results.npz", "plot_data.json"} <= artifacts.keys():
                raise CloudWorkerError("Completed worker outputs are incomplete.")
            state["files"] = _public_files(run_id, artifacts)
            terminal = _terminal(manifest, state, artifacts, exit_code, True, "published")
            stage = "terminal"
            terminal_attempted = True
            _write_terminal(store, terminal_key, terminal)
            durable = True
        except Exception as error:
            # Exception messages can contain signed URLs/SDK authentication
            # details. Only a class name and fixed infrastructure text leave
            # this wrapper. Native numerical tracebacks remain in worker.log.
            if not terminal_attempted:
                # A plot/export/infrastructure failure must not discard an
                # otherwise useful numerical result or the original inputs.
                # Safe-tree validation still applies before every recovery.
                try:
                    for name, path in _artifact_paths(directory):
                        if name not in artifacts:
                            try:
                                artifacts[name] = _put_artifact(store, run_id, name, path.read_bytes())
                            except Exception:
                                pass
                except Exception:
                    pass
            detail = str(error) if isinstance(error, CloudWorkerError) else "Inspect the retained job evidence."
            state = {**state, "status": "failed", "phase": "Publication failed" if stage in {"artifacts", "terminal"} else "Cloud worker failed",
                     "error": f"Cloud worker failed during {stage}. {detail}",
                     "finished_at": _now(), "files": _public_files(run_id, artifacts)}
            terminal = _terminal(manifest, state, artifacts, exit_code, False, stage, type(error).__name__)
            _write_json(directory/"cloud_failure.json", terminal)
            try:
                if not terminal_attempted:
                    _write_terminal(store, terminal_key, terminal)
                    durable = True
                else:
                    # A failed terminal PUT has an uncertain remote outcome;
                    # never create a second contradictory terminal record.
                    store.put_json(f"jobs/{run_id}/publication-failures/{uuid.uuid4().hex}.json", terminal)
            except Exception:
                pass
        _write_json(directory/"cloud_status.json", state)
        _write_json(directory/"cloud_terminal.json", terminal)
        if durable:
            _write_json(directory/"cloud_cleanup.json", {"status": "stopping_after_publication"})
            try:
                result = stop_callback() if stop_callback is not None else _stop_sandbox(manifest)
                _write_json(directory/"cloud_cleanup.json", {"status": result if isinstance(result, str) else "stopped"})
            except Exception as error:
                _write_json(directory/"cloud_cleanup.json", {"status": "failed", "error_type": type(error).__name__})
        else:
            _write_json(directory/"cloud_cleanup.json", {"status": "not_stopped_publication_unconfirmed"})
        return terminal


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job_dir", type=Path)
    parser.add_argument("run_id")
    args = parser.parse_args(argv)
    try:
        from .storage import CloudStore
        terminal = run_cloud_job(args.job_dir, args.run_id, store=CloudStore.from_env())
        return 0 if terminal["publication"]["complete"] and terminal["status"]["status"] in {"completed", "cancelled"} else 1
    except Exception:
        # The manager owns recovery when startup fails before a safe job
        # identity/store can be established. Never print credentials/SDK URLs.
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
