"""Authenticated hosted adapter; the local GUI and numerical modules are untouched.

``manager`` supplies start/history/status/cancel/data/download. Download returns
``(bytes_or_iterable_of_bytes, mimetype)``. The manager must authorize file names
against its recorded artifact manifest, and durably own all calculation state.
``limiter(key)`` must atomically admit a login attempt across instances, returning
True to admit or False to reject. Storage errors fail closed. No in-memory
fallback is supplied. The entrypoint, not this module, owns trusted proxy setup.
"""
from __future__ import annotations

from datetime import timedelta
import hmac
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import time
from urllib.parse import urlsplit

from flask import Flask, Response, abort, jsonify, redirect, request, send_from_directory, session
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash

from .. import __version__
from ..gui_schema import assess_payload, baseline, schema, validate_payload


GUI_STATIC = Path(__file__).resolve().parents[1] / "gui_static"
CLOUD_STATIC = Path(__file__).resolve().parent / "static"
PUBLIC_BRANDING = {"logo-transparent.png", "lato-normal.woff2", "lato-bold.woff2", "Roboto-Slab-Bold.woff2"}


def create_app(manager, config=None, *, limiter=None):
    """Build the HTTPS-only hosted app with explicitly injected infrastructure.

    Configuration uses OPENSTREAM_PASSWORD_HASH, OPENSTREAM_SESSION_SECRET,
    OPENSTREAM_PUBLIC_ORIGIN and OPENSTREAM_SESSION_SECONDS. The password hash
    must be a Werkzeug scrypt hash. Config values override environment values.
    Signed sessions expire at a fixed time; logout clears the browser cookie.
    Previously copied cookies are not individually revoked server-side.
    """
    app = Flask(__name__, static_folder=None)
    app.config.update(
        OPENSTREAM_PASSWORD_HASH=os.getenv("OPENSTREAM_PASSWORD_HASH"),
        OPENSTREAM_SESSION_SECRET=os.getenv("OPENSTREAM_SESSION_SECRET"),
        OPENSTREAM_PUBLIC_ORIGIN=os.getenv("OPENSTREAM_PUBLIC_ORIGIN", "https://openstream-py.vercel.app"),
        OPENSTREAM_SESSION_SECONDS=8 * 60 * 60,
    )
    if config:
        app.config.update(config)
    password_hash = app.config["OPENSTREAM_PASSWORD_HASH"]
    secret = app.config["OPENSTREAM_SESSION_SECRET"]
    # Refuse missing/malformed credentials instead of accidentally exposing the app.
    if not isinstance(password_hash, str) or not re.fullmatch(
        r"scrypt:32768:8:1\$[A-Za-z0-9]{16,64}\$[0-9a-f]{128}", password_hash
    ):
        raise RuntimeError("OPENSTREAM_PASSWORD_HASH must be a valid Werkzeug scrypt hash")
    if not isinstance(secret, str) or len(secret) < 32:
        raise RuntimeError("OPENSTREAM_SESSION_SECRET must contain at least 32 characters")
    if not callable(limiter):
        raise RuntimeError("A distributed login limiter is required")
    origin = app.config["OPENSTREAM_PUBLIC_ORIGIN"]
    parsed = urlsplit(origin) if isinstance(origin, str) else None
    if (parsed is None or parsed.scheme != "https" or not parsed.hostname
            or parsed.username or parsed.password or parsed.path not in ("", "/")
            or parsed.query or parsed.fragment or "*" in parsed.netloc):
        raise RuntimeError("OPENSTREAM_PUBLIC_ORIGIN must be one explicit HTTPS origin")
    origin = f"https://{parsed.netloc}"
    duration = app.config["OPENSTREAM_SESSION_SECONDS"]
    if isinstance(duration, bool) or not isinstance(duration, int) or not 60 <= duration <= 8 * 60 * 60:
        raise RuntimeError("OPENSTREAM_SESSION_SECONDS must be between 60 and 28800")
    app.config.update(
        SECRET_KEY=secret, SESSION_COOKIE_NAME="__Host-openstream_session",
        SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_PATH="/", SESSION_COOKIE_DOMAIN=None,
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=duration), SESSION_REFRESH_EACH_REQUEST=False,
        TRUSTED_HOSTS=[parsed.hostname], MAX_CONTENT_LENGTH=2 * 1024 * 1024,
        DEBUG=False,
    )
    app.extensions["runs"] = manager
    app.extensions["login_limiter"] = limiter

    def authenticated():
        issued = session.get("authenticated_at")
        valid = (isinstance(issued, (int, float)) and not isinstance(issued, bool)
                 and math.isfinite(issued) and 0 <= time.time() - issued < duration)
        if not valid and issued is not None:
            session.clear()
        return valid

    def csrf_token():
        if "csrf" not in session:
            session["csrf"] = secrets.token_urlsafe(32)
        return session["csrf"]

    @app.before_request
    def security_boundary():
        # Do not infer trust from caller-controlled X-Forwarded-* headers.
        if request.scheme != "https" or request.host != parsed.netloc:
            abort(400, "Unrecognized HTTPS host")
        public = request.path in ("/login", "/auth/session", "/auth/login")
        public = public or (request.path.startswith("/login-assets/") and
                            request.path.removeprefix("/login-assets/") in
                            PUBLIC_BRANDING | {"login.css", "login.js"})
        if not public and not authenticated():
            if request.path == "/" and request.method in ("GET", "HEAD"):
                return redirect("/login", code=303)
            abort(401, "Sign in to continue")
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            if request.headers.get("Origin") != origin or request.headers.get("Sec-Fetch-Site") == "cross-site":
                abort(403, "Request could not be verified")
            if not request.is_json:
                abort(415, "Use application/json requests")
            supplied, expected = request.headers.get("X-CSRF-Token", ""), session.get("csrf", "")
            if not supplied or not expected or not hmac.compare_digest(supplied, expected):
                abort(403, "Request could not be verified")

    @app.after_request
    def security_headers(response):
        response.headers["Cache-Control"] = "no-store, private"
        response.headers["Pragma"] = "no-cache"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; "
            "object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.errorhandler(Exception)
    def errors(exc):
        if isinstance(exc, HTTPException):
            code, message = exc.code, exc.description
        elif isinstance(exc, KeyError):
            code, message = 404, "Unknown run or file"
        elif isinstance(exc, (ValueError, TypeError, NotImplementedError)):
            code, message = 400, str(exc)
        elif isinstance(exc, RuntimeError):
            code, message = 409, str(exc)
        else:
            app.logger.exception("Hosted GUI request failed")
            code, message = 500, "Request could not be completed"
        return jsonify(valid=False, error=message), code

    @app.get("/login")
    def login_page():
        if authenticated():
            return redirect("/", code=303)
        csrf_token()
        return send_from_directory(CLOUD_STATIC, "login.html")

    @app.get("/login-assets/<filename>")
    def login_asset(filename):
        if filename in PUBLIC_BRANDING:
            return send_from_directory(GUI_STATIC, filename)
        if filename in {"login.css", "login.js"}:
            return send_from_directory(CLOUD_STATIC, filename)
        abort(404)

    @app.get("/auth/session")
    def auth_session():
        valid = authenticated()
        return jsonify(authenticated=valid, csrf=csrf_token())

    @app.post("/auth/login")
    def login():
        try:
            allowed = limiter(f"login:{request.remote_addr or 'unknown'}")
        except Exception:
            app.logger.warning("Login limiter unavailable")
            abort(503, "Sign-in is temporarily unavailable")
        if allowed is not True:
            abort(429, "Sign-in is temporarily unavailable; try again later")
        payload = request.get_json(silent=True)
        password = payload.get("password") if isinstance(payload, dict) else None
        if not isinstance(password, str) or not 1 <= len(password) <= 1024 or not check_password_hash(password_hash, password):
            abort(401, "Sign-in failed")
        session.clear()
        session.permanent = True
        session["authenticated_at"] = time.time()
        return jsonify(authenticated=True, csrf=csrf_token())

    @app.post("/auth/logout")
    def logout():
        session.clear()
        return jsonify(authenticated=False)

    @app.get("/")
    def index():
        html = (GUI_STATIC / "index.html").read_text(encoding="utf-8")
        script = '<script src="/assets/app.js" defer></script>'
        toolbar = '<div class="workspace-toolbar">'
        if html.count(script) != 1 or html.count(toolbar) != 1:
            abort(500, "Hosted interface could not be prepared")
        html = html.replace(script, '<script src="/cloud-assets/cloud.js" defer></script>\n  ' + script)
        html = html.replace(toolbar, toolbar + '<button id="cloud-logout" class="text-button" type="button">Log out</button>')
        return Response(html, mimetype="text/html")

    @app.get("/cloud-assets/<filename>")
    def cloud_asset(filename):
        if filename != "cloud.js":
            abort(404)
        return send_from_directory(CLOUD_STATIC, filename)

    @app.get("/assets/<path:filename>")
    def asset(filename):
        if filename == "plotly.min.js":
            import plotly
            return send_from_directory(Path(plotly.__file__).parent / "package_data", filename)
        return send_from_directory(GUI_STATIC, filename)

    @app.get("/api/health")
    def health():
        return jsonify(app="openstream-gui", version=__version__, output_root="Private hosted storage")

    @app.get("/api/schema")
    def get_schema():
        return jsonify(schema(request.args.get("framework", "Mixture")))

    @app.get("/api/baseline/<framework>")
    def get_baseline(framework):
        return jsonify(baseline(framework))

    @app.post("/api/validate")
    def validate():
        payload = request.get_json()
        validate_payload(payload)
        return jsonify(valid=True, **assess_payload(payload))

    @app.get("/api/runs")
    def history():
        return jsonify(runs=manager.history())

    @app.post("/api/runs")
    def start():
        payload = request.get_json()
        validate_payload(payload)
        return jsonify(manager.start(payload)), 202

    def check_run_id(run_id):
        if not re.fullmatch(r"[0-9a-f]{32}", run_id):
            abort(404)

    @app.get("/api/runs/<run_id>")
    def status(run_id):
        check_run_id(run_id)
        return jsonify(manager.status(run_id))

    @app.post("/api/runs/<run_id>/cancel")
    def cancel(run_id):
        check_run_id(run_id)
        return jsonify(manager.cancel(run_id))

    @app.get("/api/runs/<run_id>/data")
    def data(run_id):
        check_run_id(run_id)
        value = manager.data(run_id)
        def chunks():
            # Batch encoder fragments, avoiding one transport event per number.
            pending, size = [], 0
            for part in json.JSONEncoder(allow_nan=False, separators=(",", ":")).iterencode(value):
                pending.append(part)
                size += len(part)
                if size >= 65536:
                    yield "".join(pending).encode("utf-8")
                    pending, size = [], 0
            if pending:
                yield "".join(pending).encode("utf-8")
        return Response(chunks(), mimetype="application/json")

    @app.get("/files/<run_id>/<path:filename>")
    def download(run_id, filename):
        check_run_id(run_id)
        if "\\" in filename or any(part in ("", ".", "..") for part in filename.split("/")) or any(ord(char) < 32 for char in filename):
            abort(404)
        body, mimetype = manager.download(run_id, filename)
        chunks = (body,) if isinstance(body, bytes) else body
        response = Response(iter(chunks), mimetype=mimetype)
        response.headers.set("Content-Disposition", "attachment", filename=PurePosixPath(filename).name)
        return response

    return app
