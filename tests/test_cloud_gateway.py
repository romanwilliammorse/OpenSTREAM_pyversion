"""Gateway/session and deployed WSGI boundaries, without cloud or solver runs."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tomllib
from types import SimpleNamespace
import zipfile

import pytest

from openstream.cloud import gateway


RUN_ID = "a" * 32
DIRECTORY = "/vercel/sandbox/jobs/" + RUN_ID
RUNTIME = {"sandbox_name": "openstream-" + RUN_ID, "session_id": "session-1"}


def api_error(status, code=None):
    from vercel.sandbox.sync import SandboxApiError
    return SandboxApiError(SimpleNamespace(status_code=status), "private provider detail",
                           data={"error": {"code": code}} if code else None)


class Files:
    def __init__(self):
        self.values, self.calls, self.failure = {}, [], None

    def call(self, operation, path, *args, **kwargs):
        self.calls.append((operation, path, args, kwargs))
        if self.failure:
            raise self.failure

    def mkdir(self, path, **kwargs):
        self.call("mkdir", path, **kwargs)

    def write_bytes(self, path, body):
        self.call("write_bytes", path, body)
        self.values[path] = body

    def write_text(self, path, body):
        self.call("write_text", path, body)
        self.values[path] = body

    def read_text(self, path):
        self.call("read_text", path)
        if path not in self.values:
            from vercel.sandbox.sync import SandboxPathNotFoundError
            raise SandboxPathNotFoundError(path, operation="read", cwd=None, cause=api_error(404))
        return self.values[path]

    def read_bytes(self, path):
        self.call("read_bytes", path)
        return self.values[path]


class Session:
    def __init__(self, identity="session-1"):
        self.id, self.fs, self.calls, self.failure = identity, Files(), [], None

    def create_process(self, *args, **kwargs):
        self.calls.append(("create_process", args, kwargs))
        if self.failure:
            raise self.failure
        return SimpleNamespace(id="command-1")

    def stop(self):
        self.calls.append(("stop",))
        if self.failure:
            raise self.failure


class Sandbox:
    def __init__(self):
        self.name = RUNTIME["sandbox_name"]
        self.status, self.current_session_id = "running", "session-1"
        self.current_session = Session()

    @property
    def fs(self):
        raise AssertionError("Top-level fs can auto-resume; use the fixed session")

    def create_process(self, *args, **kwargs):
        raise AssertionError("Top-level process can auto-resume")

    def stop(self):
        raise AssertionError("Stop must bind the exact session")


def test_source_bundle_preserves_exact_numerical_bytes_and_excludes_assets():
    with zipfile.ZipFile(io.BytesIO(gateway.source_bundle())) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        assert any(name.endswith(".npz") for name in names)
        assert "openstream/__init__.py" in names
        assert archive.read("LICENSE") == (gateway.ROOT / "LICENSE").read_bytes()
        metadata_bytes = gateway.PACKAGE.joinpath("cloud/worker-project.toml").read_bytes()
        assert archive.read("pyproject.toml") == metadata_bytes
        metadata = tomllib.loads(metadata_bytes.decode())
        project = tomllib.loads((gateway.ROOT / "pyproject.toml").read_text())["project"]
        assert metadata["project"]["name"] == project["name"]
        assert metadata["project"]["dependencies"] == project["dependencies"]
        assert metadata["project"]["requires-python"] == project["requires-python"]
        assert metadata["project"]["dynamic"] == ["version"]
        assert metadata["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "openstream.__version__"
        for name in names:
            if name in {"pyproject.toml", "LICENSE"}:
                continue
            relative = Path(name).relative_to("openstream")
            assert not {"__pycache__", "gui_static", "static"}.intersection(relative.parts)
            assert relative.suffix in {".py", ".npz", ".json", ".inp"}
            assert archive.read(name) == (gateway.PACKAGE / relative).read_bytes()
        for path in gateway.PACKAGE.glob("*.py"):
            assert archive.read("openstream/" + path.name) == path.read_bytes()


def test_provenance_matches_source_lock_and_pinned_image(monkeypatch):
    monkeypatch.setenv("VERCEL_GIT_COMMIT_SHA", "b" * 40)
    source, environment = gateway.provenance()
    assert source["git_commit"] == "b" * 40
    assert source["module_sha256"] == {
        "src/openstream/" + path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in gateway.PACKAGE.glob("*.py")
    }
    assert environment["dependency_lock_sha256"] == hashlib.sha256(
        (gateway.ROOT / "requirements-cloud.lock").read_bytes()).hexdigest()
    assert environment["python_version"] == "3.12.16"
    assert environment["sandbox_image"] == gateway.IMAGE
    assert "@sha256:" in gateway.IMAGE


def test_function_requirements_are_exact_flattened_web_subset_of_worker_lock():
    def pins(name):
        return [line.strip() for line in (gateway.ROOT / name).read_text().splitlines()
                if line.strip() and not line.lstrip().startswith("#")]
    web = pins("requirements-web.lock")
    worker = pins("requirements-cloud.lock")
    assert pins("requirements.txt") == web
    assert set(web) < set(worker)
    assert all("==" in line and not line.startswith("-") for line in web)
    names = {line.split("==", 1)[0].lower() for line in web}
    worker_names = {line.split("==", 1)[0].lower() for line in worker}
    assert "numpy" in names  # Original input validation and saved-array exports.
    scientific = {"coolprop", "scipy", "matplotlib", "plotly"}
    assert not names & scientific
    assert scientific <= worker_names


def test_create_pins_private_nonpersistent_environment(monkeypatch):
    import vercel.oidc.credentials as oidc
    import vercel.sandbox.sync as sdk
    sandbox, calls = Sandbox(), []
    monkeypatch.setenv("BLOB_STORE_ID", "store_fixture")
    monkeypatch.setattr(oidc, "get_credentials", lambda: SimpleNamespace(
        token="test-only-oidc", project_id="project-fixture", team_id="team-fixture"))
    monkeypatch.setattr(sdk, "create_sandbox", lambda **kw: calls.append(kw) or sandbox)
    handle = gateway.SandboxGateway(2400).create(RUN_ID)
    options = calls[0]
    assert options["image"] == gateway.IMAGE
    assert options["persistent"] is False and options["ports"] == []
    assert options["execution_time_limit"] == 2400
    assert options["resources"].vcpus == 2
    assert options["region"] == "iad1"
    assert options["env"] == {
        "VERCEL_OIDC_TOKEN": "test-only-oidc", "VERCEL_PROJECT_ID": "project-fixture",
        "VERCEL_TEAM_ID": "team-fixture", "BLOB_STORE_ID": "store_fixture",
        "MPLBACKEND": "Agg", "MPLCONFIGDIR": "/vercel/sandbox/.matplotlib",
        "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
    }
    assert "test-only-oidc" not in json.dumps(handle.runtime)
    assert handle.fresh and handle.session is sandbox.current_session


@pytest.mark.parametrize("duration", [True, 59, 2701, 2400.0, "2400"])
def test_duration_rejects_invalid_values(duration):
    with pytest.raises(ValueError):
        gateway.SandboxGateway(duration)


@pytest.mark.parametrize("run_id", ["../bad", "A" * 32, "a" * 31])
def test_create_rejects_invalid_run_id(run_id):
    with pytest.raises(ValueError):
        gateway.SandboxGateway().create(run_id)


def test_get_is_passive_and_404_means_absence(monkeypatch):
    import vercel.sandbox.sync as sdk
    calls = []
    def missing(**kwargs):
        calls.append(kwargs)
        raise api_error(404)
    monkeypatch.setattr(sdk, "get_sandbox", missing)
    handle = gateway.SandboxGateway().get(RUNTIME)
    assert calls == [{"name": RUNTIME["sandbox_name"]}]
    assert not handle.is_running()
    handle.stop()
    with pytest.raises(RuntimeError, match="no longer active"):
        handle.request_cancel(DIRECTORY)


@pytest.mark.parametrize("status", [401, 429, 503])
def test_get_other_provider_failure_is_sanitized_not_absence(monkeypatch, status):
    import vercel.sandbox.sync as sdk
    calls = []
    def unavailable(**kwargs):
        calls.append(kwargs)
        raise api_error(status)
    monkeypatch.setattr(sdk, "get_sandbox", unavailable)
    with pytest.raises(RuntimeError, match="temporarily unavailable") as caught:
        gateway.SandboxGateway().get(RUNTIME)
    assert "private provider detail" not in str(caught.value)
    assert caught.value.__suppress_context__ is True and len(calls) == 1


@pytest.mark.parametrize("status,code", [(410, None), (410, "sandbox_stopped"), (409, "sandbox_stopped")])
def test_get_explicit_stopped_lifecycle_is_passive(monkeypatch, status, code):
    import vercel.sandbox.sync as sdk
    calls = []
    def stopped(**kwargs):
        calls.append(kwargs)
        raise api_error(status, code)
    monkeypatch.setattr(sdk, "get_sandbox", stopped)
    handle = gateway.SandboxGateway().get(RUNTIME)
    assert not handle.is_running() and handle.session is None
    handle.stop()
    assert calls == [{"name": RUNTIME["sandbox_name"]}]


def test_get_closed_stream_410_does_not_establish_stopped(monkeypatch):
    import vercel.sandbox.sync as sdk
    def closed(**kwargs):
        raise api_error(410, "sandbox_stream_closed")
    monkeypatch.setattr(sdk, "get_sandbox", closed)
    with pytest.raises(RuntimeError, match="temporarily unavailable"):
        gateway.SandboxGateway().get(RUNTIME)


def test_exact_session_files_launch_cancel_and_stop(monkeypatch):
    sandbox = Sandbox()
    handle = gateway.SandboxHandle(sandbox, RUNTIME, fresh=True)
    monkeypatch.setattr(gateway, "source_bundle", lambda: b"unchanged source bundle")
    handle.prepare({DIRECTORY + "/status.json": b'{"status":"queued"}'})
    fs = sandbox.current_session.fs
    assert fs.values["/vercel/sandbox/source.zip"] == b"unchanged source bundle"
    assert fs.values["/vercel/sandbox/bootstrap.py"] == gateway.BOOTSTRAP
    assert fs.values["/vercel/sandbox/requirements-cloud.lock"] == (
        gateway.ROOT / "requirements-cloud.lock").read_bytes()
    # No installation or solver command runs in prepare; launch is detached.
    assert sandbox.current_session.calls == []
    handle.launch(DIRECTORY)
    assert sandbox.current_session.calls == [("create_process", ("python3", [
        "/vercel/sandbox/bootstrap.py", DIRECTORY]), {"cwd": "/vercel/sandbox"})]
    fs.values[DIRECTORY + "/status.json"] = '{"status":"running"}'
    assert handle.status_files(DIRECTORY) == ({"status": "running"}, None)
    handle.request_cancel(DIRECTORY)
    assert fs.values[DIRECTORY + "/cancel.request"] == ""
    handle.stop()
    assert sandbox.current_session.calls[-1] == ("stop",)


@pytest.mark.parametrize("change", ["stopped", "different_current_id", "different_session", "missing_session"])
def test_inactive_or_replaced_session_never_operated(change):
    sandbox = Sandbox()
    if change == "stopped":
        sandbox.status = "stopped"
    elif change == "different_current_id":
        sandbox.current_session_id = "session-2"
    elif change == "different_session":
        sandbox.current_session = Session("session-2")
    else:
        sandbox.current_session = None
    handle = gateway.SandboxHandle(sandbox, RUNTIME)
    assert not handle.is_running()
    for operation in (lambda: handle.prepare({}), lambda: handle.launch(DIRECTORY),
                      lambda: handle.status_files(DIRECTORY), lambda: handle.request_cancel(DIRECTORY),
                      lambda: handle.bootstrap_log(DIRECTORY)):
        with pytest.raises(RuntimeError, match="no longer active"):
            operation()
    handle.stop()
    if sandbox.current_session:
        assert sandbox.current_session.calls == [] and sandbox.current_session.fs.calls == []


def test_observed_lifecycle_change_does_not_stop_later_session():
    sandbox = Sandbox()
    handle = gateway.SandboxHandle(sandbox, RUNTIME)
    original = sandbox.current_session
    sandbox.current_session_id, sandbox.current_session = "session-2", Session("session-2")
    handle.stop()
    assert original.calls == [] and sandbox.current_session.calls == []


@pytest.mark.parametrize("operation", ["prepare", "launch", "status_files", "request_cancel", "bootstrap_log", "stop"])
def test_410_lifecycle_race_propagates_without_retry_or_resume(operation):
    sandbox = Sandbox()
    handle = gateway.SandboxHandle(sandbox, RUNTIME)
    failure = api_error(410)
    sandbox.current_session.failure = sandbox.current_session.fs.failure = failure
    arguments = {"prepare": ({DIRECTORY + "/status.json": b"{}"},), "stop": ()}
    with pytest.raises(type(failure)) as caught:
        getattr(handle, operation)(*arguments.get(operation, (DIRECTORY,)))
    assert caught.value is failure
    assert len(sandbox.current_session.calls) + len(sandbox.current_session.fs.calls) == 1


@pytest.mark.parametrize("path", ["/tmp/other/status.json", DIRECTORY + "/../other.json", "/vercel/sandbox/jobs-evil/x"])
def test_prepare_rejects_outside_paths(path):
    sandbox = Sandbox()
    with pytest.raises(ValueError, match="Invalid cloud job path"):
        gateway.SandboxHandle(sandbox, RUNTIME).prepare({path: b"{}"})
    assert sandbox.current_session.fs.calls == []


def test_bootstrap_log_capture_has_one_megabyte_limit():
    sandbox = Sandbox()
    handle = gateway.SandboxHandle(sandbox, RUNTIME)
    sandbox.current_session.fs.values[DIRECTORY + "/bootstrap.log"] = b"x" * (1024 * 1024)
    assert len(handle.bootstrap_log(DIRECTORY)) == 1024 * 1024
    sandbox.current_session.fs.values[DIRECTORY + "/bootstrap.log"] += b"x"
    with pytest.raises(RuntimeError, match="capture limit"):
        handle.bootstrap_log(DIRECTORY)


@pytest.fixture
def entrypoint(monkeypatch):
    from openstream.cloud.storage import CloudStore
    from vercel.headers import set_headers
    # A syntactically valid test-only hash avoids importing any real credentials.
    monkeypatch.setenv("OPENSTREAM_PASSWORD_HASH", "scrypt:32768:8:1$" + "x" * 16 + "$" + "0" * 128)
    monkeypatch.setenv("OPENSTREAM_SESSION_SECRET", "test-only-session-secret-" * 3)
    monkeypatch.setenv("OPENSTREAM_PUBLIC_ORIGIN", "https://openstream-py.vercel.app")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(CloudStore, "from_env", classmethod(lambda cls: SimpleNamespace()))
    spec = importlib.util.spec_from_file_location("gateway_test_entrypoint", gateway.ROOT / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    yield module
    set_headers(None)


def test_https_forwarding_only_when_on_vercel(entrypoint, monkeypatch):
    from vercel.headers import get_headers
    observed = []
    def wrapped(environ, start):
        observed.append((environ.copy(), dict(get_headers())))
        return [b"ok"]
    middleware = entrypoint.VercelRequestContext(wrapped)
    original = {"REMOTE_ADDR": "127.0.0.1", "wsgi.url_scheme": "http",
                "HTTP_X_FORWARDED_FOR": "192.0.2.1", "HTTP_X_VERCEL_FORWARDED_FOR": "192.0.2.2",
                "HTTP_X_FORWARDED_PROTO": "https", "HTTP_X_VERCEL_OIDC_TOKEN": "test-only"}
    assert list(middleware(dict(original), lambda *a: None)) == [b"ok"]
    assert observed[-1][0]["REMOTE_ADDR"] == "127.0.0.1"
    assert observed[-1][0]["wsgi.url_scheme"] == "http"
    monkeypatch.setenv("VERCEL", "1")
    assert list(middleware(dict(original), lambda *a: None)) == [b"ok"]
    assert observed[-1][0]["REMOTE_ADDR"] == "192.0.2.2"
    assert observed[-1][0]["wsgi.url_scheme"] == "https"
    assert observed[-1][1]["x-vercel-oidc-token"] == "test-only"
    assert get_headers() is None


@pytest.mark.parametrize("address", ["", "not-an-address", "192.0.2.1, 192.0.2.2"])
def test_vercel_rejects_invalid_client_address_before_app(entrypoint, monkeypatch, address):
    monkeypatch.setenv("VERCEL", "1")
    statuses = []
    def forbidden(*args):
        pytest.fail("Invalid address reached app")
    result = entrypoint.VercelRequestContext(forbidden)(
        {"HTTP_X_VERCEL_FORWARDED_FOR": address}, lambda status, headers: statuses.append((status, headers)))
    assert b"".join(result) == b"Unrecognized client address"
    assert statuses[0][0] == "400 Bad Request"


def test_actual_app_rejects_http_and_unknown_host(entrypoint, monkeypatch):
    client = entrypoint.app.test_client()
    assert client.get("/auth/session", base_url="http://openstream-py.vercel.app").status_code == 400
    assert client.get("/auth/session", base_url="https://untrusted.example").status_code == 400
    monkeypatch.setenv("VERCEL", "1")
    response = client.get("/auth/session", base_url="http://openstream-py.vercel.app", headers={
        "X-Vercel-Forwarded-For": "192.0.2.3", "X-Forwarded-Proto": "https"})
    assert response.status_code == 200 and response.json["authenticated"] is False


class ContextStream:
    def __init__(self, *, fail_next=False, fail_close=False):
        self.closed, self.index = False, 0
        self.fail_next, self.fail_close = fail_next, fail_close

    def __iter__(self):
        return self

    def __next__(self):
        from vercel.headers import get_headers
        assert get_headers()["x-vercel-oidc-token"] == "test-only"
        if self.fail_next:
            raise RuntimeError("stream failure")
        self.index += 1
        if self.index > 2:
            raise StopIteration
        return b"part"

    def close(self):
        from vercel.headers import get_headers
        assert get_headers()["x-vercel-oidc-token"] == "test-only"
        self.closed = True
        if self.fail_close:
            raise RuntimeError("close failure")


@pytest.mark.parametrize("mode", ["complete", "early_close", "before_iteration", "iterate_error", "close_error"])
def test_oidc_context_lives_through_stream_and_always_cleans(entrypoint, mode):
    from vercel.headers import get_headers
    body = ContextStream(fail_next=mode == "iterate_error", fail_close=mode == "close_error")
    stream = entrypoint.VercelRequestContext(lambda environ, start: body)(
        {"HTTP_X_VERCEL_OIDC_TOKEN": "test-only"}, lambda *args: None)
    if mode in {"iterate_error", "close_error"}:
        with pytest.raises(RuntimeError):
            list(stream)
    elif mode == "before_iteration":
        stream.close()
    elif mode == "early_close":
        assert next(stream) == b"part"
        stream.close()
    else:
        assert list(stream) == [b"part", b"part"]
    assert body.closed
    assert get_headers() is None


def test_oidc_context_cleans_if_app_raises_before_iterable(entrypoint):
    from vercel.headers import get_headers
    def failure(environ, start):
        assert get_headers()["x-vercel-oidc-token"] == "test-only"
        raise RuntimeError("app failure")
    with pytest.raises(RuntimeError, match="app failure"):
        entrypoint.VercelRequestContext(failure)({"HTTP_X_VERCEL_OIDC_TOKEN": "test-only"}, lambda *args: None)
    assert get_headers() is None
