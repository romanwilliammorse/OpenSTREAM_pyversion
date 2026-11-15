"""Hosted security and API contract checks, with no solver or cloud services."""
from __future__ import annotations

import secrets
from pathlib import Path
import shutil
import subprocess
import time

import pytest
from werkzeug.security import generate_password_hash

from openstream.cloud.app import create_app
from openstream.gui_schema import baseline


ORIGIN = "https://openstream-py.vercel.app"
RUN_ID = "a" * 32


class Manager:
    def __init__(self):
        self.calls = []

    def start(self, payload):
        self.calls.append(("start", payload))
        return {"id": RUN_ID, "status": "queued"}

    def history(self):
        self.calls.append(("history",))
        return [{"id": RUN_ID, "status": "completed"}]

    def status(self, run_id):
        self.calls.append(("status", run_id))
        return {"id": run_id, "status": "completed"}

    def cancel(self, run_id):
        self.calls.append(("cancel", run_id))
        return {"id": run_id, "status": "cancelled"}

    def data(self, run_id):
        self.calls.append(("data", run_id))
        return {"datasets": {"physical": {"z": [0.0, 1.0], "fields": {}}}, "metadata": {"framework": "Mixture"}}

    def download(self, run_id, filename):
        self.calls.append(("download", run_id, filename))
        if filename == "results.zip":
            return iter([b"archive", b" chunks"]), "application/zip"
        if filename == "submitted_inputs.json":
            return b"{}", "application/json"
        raise KeyError(filename)


@pytest.fixture(scope="module")
def credentials():
    # These are random test-only credentials; no real deployment secret is read.
    password = secrets.token_urlsafe(30)
    return password, generate_password_hash(password, method="scrypt")


@pytest.fixture
def configured(credentials):
    return {
        "TESTING": True,
        "OPENSTREAM_PASSWORD_HASH": credentials[1],
        "OPENSTREAM_SESSION_SECRET": secrets.token_urlsafe(48),
        "OPENSTREAM_PUBLIC_ORIGIN": ORIGIN,
    }


@pytest.fixture
def app(configured):
    return create_app(Manager(), configured, limiter=lambda key: True)


def get(client, path, **kwargs):
    return client.get(path, base_url=ORIGIN, **kwargs)


def post(client, path, csrf, payload=None, **kwargs):
    return client.post(path, json={} if payload is None else payload, base_url=ORIGIN,
                       headers={"Origin": ORIGIN, "X-CSRF-Token": csrf, **kwargs.pop("headers", {})}, **kwargs)


def login(client, credentials):
    csrf = get(client, "/auth/session").json["csrf"]
    response = post(client, "/auth/login", csrf, {"password": credentials[0]})
    assert response.status_code == 200
    return response.json["csrf"], response


@pytest.mark.parametrize("field,value", [
    ("OPENSTREAM_PASSWORD_HASH", None), ("OPENSTREAM_PASSWORD_HASH", "not-a-password-hash"),
    ("OPENSTREAM_SESSION_SECRET", None), ("OPENSTREAM_SESSION_SECRET", "short"),
    ("OPENSTREAM_PUBLIC_ORIGIN", "http://openstream-py.vercel.app"),
    ("OPENSTREAM_PUBLIC_ORIGIN", "https://*.vercel.app"),
    ("OPENSTREAM_PUBLIC_ORIGIN", "https://user@openstream-py.vercel.app"),
    ("OPENSTREAM_PUBLIC_ORIGIN", ORIGIN + "/anything"),
    ("OPENSTREAM_SESSION_SECONDS", 0), ("OPENSTREAM_SESSION_SECONDS", 28801),
])
def test_configuration_fails_closed(configured, field, value):
    with pytest.raises(RuntimeError):
        create_app(Manager(), {**configured, field: value}, limiter=lambda key: True)


def test_limiter_is_required(configured):
    with pytest.raises(RuntimeError, match="limiter"):
        create_app(Manager(), configured)


@pytest.mark.parametrize("path", [
    "/api/health", "/api/schema", "/api/baseline/Mixture", "/api/runs",
    f"/api/runs/{RUN_ID}", f"/api/runs/{RUN_ID}/data",
    f"/files/{RUN_ID}/results.zip", f"/files/{RUN_ID}/submitted_inputs.json",
    "/assets/app.js", "/assets/plotly.min.js", "/cloud-assets/cloud.js",
])
def test_anonymous_requests_never_reach_backend(app, path):
    client = app.test_client()
    response = get(client, path)
    assert response.status_code == 401
    assert response.json["error"] == "Sign in to continue"
    assert app.extensions["runs"].calls == []
    assert "no-store" in response.headers["Cache-Control"]


def test_login_page_public_branding_and_no_open_redirect(app):
    client = app.test_client()
    response = get(client, "/?next=https://example.com")
    assert response.status_code == 303 and response.location == "/login"
    response = get(client, "/login?next=https://example.com")
    assert response.status_code == 200 and b'current-password' in response.data
    for path in ("/login-assets/login.css", "/login-assets/login.js", "/login-assets/logo-transparent.png"):
        assert get(client, path).status_code == 200
    assert get(client, "/login-assets/../app.py").status_code != 200
    assert app.extensions["runs"].calls == []


def test_login_requires_csrf_and_exact_origin(app, credentials):
    client = app.test_client()
    csrf = get(client, "/auth/session").json["csrf"]
    for token, origin in [("", ORIGIN), ("wrong", ORIGIN), (csrf, "https://example.com"), (csrf, "http://openstream-py.vercel.app"), (csrf, "")]:
        response = post(client, "/auth/login", token, {"password": credentials[0]}, headers={"Origin": origin})
        assert response.status_code == 403
    assert get(client, "/auth/session").json["authenticated"] is False


def test_wrong_password_is_generic_and_correct_login_rotates_csrf(app, credentials):
    client = app.test_client()
    csrf = get(client, "/auth/session").json["csrf"]
    response = post(client, "/auth/login", csrf, {"password": secrets.token_urlsafe(30)})
    assert response.status_code == 401 and response.json["error"] == "Sign-in failed"
    response = post(client, "/auth/login", csrf, {"password": credentials[0]})
    assert response.status_code == 200 and response.json["csrf"] != csrf
    cookie = response.headers["Set-Cookie"]
    assert cookie.startswith("__Host-openstream_session=")
    for expected in ("Secure", "HttpOnly", "SameSite=Lax", "Path=/", "Expires="):
        assert expected in cookie
    assert "Domain=" not in cookie
    assert credentials[0] not in cookie and credentials[1] not in cookie
    assert get(client, "/auth/session").json["authenticated"] is True
    assert get(client, "/login?next=https://example.com").location == "/"


def test_authentication_is_not_settable_by_payload_or_forged_cookie(app):
    client = app.test_client()
    client.set_cookie("__Host-openstream_session", "authenticated_at=9999999999", domain="openstream-py.vercel.app", secure=True)
    assert get(client, "/api/runs").status_code == 401
    assert app.extensions["runs"].calls == []


def test_authenticated_index_reuses_local_gui_and_adds_hosted_controls(app, credentials):
    client = app.test_client()
    login(client, credentials)
    response = get(client, "/")
    text = response.get_data(as_text=True)
    assert response.status_code == 200 and 'id="cloud-logout"' in text
    assert text.index("/cloud-assets/cloud.js") < text.index("/assets/app.js")
    assert 'id="model-picker"' in text and 'id="input-editor"' in text
    assert credentials[0] not in text and credentials[1] not in text
    health = get(client, "/api/health").json
    assert "pid" not in health and health["output_root"] == "Private hosted storage"
    assert "Set-Cookie" not in get(client, "/api/health").headers


@pytest.mark.parametrize("path", ["/api/runs", f"/api/runs/{RUN_ID}/cancel", "/api/validate", "/auth/logout"])
def test_every_authenticated_post_requires_csrf(app, credentials, path):
    client = app.test_client()
    login(client, credentials)
    response = post(client, path, "wrong", baseline())
    assert response.status_code == 403
    assert app.extensions["runs"].calls == []
    assert get(client, "/auth/session").json["authenticated"] is True


def test_logout_and_fixed_expiry(app, credentials, monkeypatch):
    client = app.test_client()
    csrf, _ = login(client, credentials)
    assert post(client, "/auth/logout", csrf).status_code == 200
    assert get(client, "/api/runs").status_code == 401
    csrf, _ = login(client, credentials)
    future = time.time() + 28801
    monkeypatch.setattr("openstream.cloud.app.time.time", lambda: future)
    assert get(client, "/api/runs").status_code == 401
    assert get(client, "/auth/session").json["authenticated"] is False
    assert app.extensions["runs"].calls == []


@pytest.mark.parametrize("kind,expected", [("deny", 429), ("failure", 503), ("invalid", 429)])
def test_limiter_failure_or_denial_never_checks_password(configured, credentials, monkeypatch, kind, expected):
    seen = []
    def limiter(key):
        seen.append(key)
        if kind == "failure":
            raise OSError("test storage unavailable")
        return 1 if kind == "invalid" else False
    app = create_app(Manager(), configured, limiter=limiter)
    def must_not_check(*args):
        pytest.fail("password was evaluated after limiter rejection")
    monkeypatch.setattr("openstream.cloud.app.check_password_hash", must_not_check)
    client = app.test_client()
    csrf = get(client, "/auth/session").json["csrf"]
    response = post(client, "/auth/login", csrf, {"password": credentials[0]})
    assert response.status_code == expected and seen == ["login:127.0.0.1"]
    assert get(client, "/auth/session").json["authenticated"] is False


def test_https_host_and_forwarded_headers_are_not_trusted(app):
    client = app.test_client()
    for url in ("http://openstream-py.vercel.app", "https://example.com", "https://openstream-py.vercel.app:444"):
        response = client.get("/login", base_url=url, headers={"X-Forwarded-Host": "openstream-py.vercel.app", "X-Forwarded-Proto": "https"})
        assert response.status_code == 400


def test_manager_contract_and_streamed_private_outputs(app, credentials):
    client = app.test_client()
    csrf, _ = login(client, credentials)
    assert len(get(client, "/api/schema").json["fields"]) == 163
    inputs = get(client, "/api/baseline/Mixture").json
    assert post(client, "/api/validate", csrf, inputs).json["valid"] is True
    assert post(client, "/api/runs", csrf, inputs).status_code == 202
    assert get(client, "/api/runs").json["runs"][0]["id"] == RUN_ID
    assert get(client, f"/api/runs/{RUN_ID}").json["status"] == "completed"
    data = get(client, f"/api/runs/{RUN_ID}/data")
    assert "Content-Length" not in data.headers
    assert data.json["datasets"]["physical"]["z"] == [0.0, 1.0]
    for name, expected in [("results.zip", b"archive chunks"), ("submitted_inputs.json", b"{}")]:
        response = get(client, f"/files/{RUN_ID}/{name}")
        assert response.data == expected and "Content-Length" not in response.headers
        assert response.headers["Content-Disposition"].startswith("attachment;")
        assert "no-store" in response.headers["Cache-Control"]
    assert post(client, f"/api/runs/{RUN_ID}/cancel", csrf).json["status"] == "cancelled"
    assert [call[0] for call in app.extensions["runs"].calls] == ["start", "history", "status", "data", "download", "download", "cancel"]


def test_invalid_input_run_id_and_traversal_cannot_reach_manager(app, credentials):
    client = app.test_client()
    csrf, _ = login(client, credentials)
    invalid = baseline()
    invalid["inputs"]["bc"][0]["PRESSURE"] = -1
    assert post(client, "/api/runs", csrf, invalid).status_code == 400
    for path in ("/api/runs/not-a-run", f"/files/{RUN_ID}/../secrets", f"/files/{RUN_ID}/output%5Csecrets"):
        assert get(client, path).status_code == 404
    assert app.extensions["runs"].calls == []


def test_hosted_browser_adapter_csrf_expiry_resume_and_logout():
    """Exercise the real hosted script with browser primitives and a fake server."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for the hosted browser adapter check")
    source = Path(__file__).resolve().parent / 'cloud_frontend.test.cjs'
    result = subprocess.run([node, str(source)], capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
