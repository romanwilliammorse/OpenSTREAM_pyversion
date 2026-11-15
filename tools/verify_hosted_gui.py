"""Reproduce authenticated hosted-GUI checks without changing solver inputs.

Run with the project's Python environment. Password comes from getpass or the
OPENSTREAM_VERIFY_PASSWORD environment variable. Each invocation creates a new
evidence directory. Authentication payloads, headers, cookies and CSRF tokens
are never recorded. No POST, including a run submission, is automatically
retried. Downloaded scientific artifacts retain their original bytes.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import http.cookiejar
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import secrets
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
FRAMEWORKS = ("Mixture", "TwoFluid", "ThreeField", "FourField")
TERMINAL = {"completed", "failed", "cancelled"}
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024


class VerificationError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def checked_origin(value):
    parsed = urllib.parse.urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("--origin must be one explicit HTTPS origin")
    return f"https://{parsed.netloc}"


class SameOriginRedirects(urllib.request.HTTPRedirectHandler):
    def __init__(self, origin):
        self.origin = origin

    def redirect_request(self, request, fp, code, message, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if request.get_method() not in ("GET", "HEAD") or f"{parsed.scheme}://{parsed.netloc}" != self.origin:
            raise VerificationError("Redirect rejected; credentials and POSTs are never forwarded.")
        return super().redirect_request(request, fp, code, message, headers, newurl)


class HTTPClient:
    def __init__(self, origin, password, *, timeout=60, opener=None):
        self.origin, self.timeout = checked_origin(origin), timeout
        self.jar = http.cookiejar.CookieJar()
        self.opener = opener or urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar), SameOriginRedirects(self.origin))
        self.csrf = None
        self._password = password
        self.secrets = {password} if password else set()

    def redact(self, value):
        if isinstance(value, dict):
            return {key: "[redacted]" if key.lower() in {"password", "csrf", "cookie", "set-cookie", "authorization"}
                    else self.redact(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, str):
            if value == self._password:
                return "[redacted]"
            for secret in sorted(self.secrets, key=len, reverse=True):
                if len(secret) >= 16:
                    value = value.replace(secret, "[redacted]")
            if self._password:
                pattern = r"(?i)(password\s*[:=]\s*)([\"']?)" + re.escape(self._password) + r"\2(?=$|[\s,;}])"
                value = re.sub(pattern, lambda match: match.group(1) + "[redacted]", value)
            return value
        return value

    def check_evidence_bytes(self, body):
        # Short numeric passwords can occur in perfectly valid scientific data
        # or hashes. Never substring-match them against numerical artifacts.
        sensitive = any(secret.encode("utf-8") in body for secret in self.secrets if len(secret) >= 16)
        if self._password and body.strip() in (self._password.encode("utf-8"), json.dumps(self._password).encode("utf-8")):
            sensitive = True
        try:
            decoded = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            decoded = None
        def auth_field(value):
            if isinstance(value, dict):
                return any((key.lower() in {"password", "csrf", "cookie", "set-cookie", "authorization"} and bool(item))
                           or auth_field(item) for key, item in value.items())
            return isinstance(value, list) and any(auth_field(item) for item in value)
        sensitive = sensitive or auth_field(decoded)
        if sensitive:
            raise VerificationError("Artifact contains an authentication secret; it was not saved.")

    def request(self, method, path, payload=None, *, csrf=True, headers=None):
        if not isinstance(path, str) or not path.startswith("/") or path.startswith("//"):
            raise VerificationError("Only same-origin relative API paths are allowed.")
        request_headers = {"Accept": "application/json", "User-Agent": "OpenSTREAM-hosted-verification/1"}
        body = None
        if payload is not None:
            body = json.dumps(payload, allow_nan=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        if method not in ("GET", "HEAD"):
            request_headers["Origin"] = self.origin
            if csrf and self.csrf:
                request_headers["X-CSRF-Token"] = self.csrf
        request_headers.update(headers or {})
        request = urllib.request.Request(self.origin + path, data=body, headers=request_headers, method=method)
        try:
            response = self.opener.open(request, timeout=self.timeout)
        except urllib.error.HTTPError as error:
            response = error
        except (urllib.error.URLError, OSError, TimeoutError):
            raise VerificationError(f"{method} {path}: transport failed; request was not retried.") from None
        with response:
            data = response.read(MAX_ARTIFACT_BYTES + 1)
            status = response.code
            cookie_headers = response.headers.get_all("Set-Cookie", [])
            cookie_policy = [{"host_prefix": item.startswith("__Host-"),
                              "secure": "; secure" in item.lower(), "httponly": "; httponly" in item.lower(),
                              "samesite_lax": "samesite=lax" in item.lower(), "domain_absent": "domain=" not in item.lower()}
                             for item in cookie_headers]
        self.secrets.update(cookie.value for cookie in self.jar if isinstance(cookie.value, str) and cookie.value)
        if len(data) > MAX_ARTIFACT_BYTES:
            raise VerificationError(f"{method} {path}: response exceeds the verification download limit.")
        return status, data, cookie_policy

    def json(self, method, path, payload=None, **kwargs):
        code, body, policy = self.request(method, path, payload, **kwargs)
        try:
            value = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            raise VerificationError(f"{method} {path}: HTTP {code} returned invalid JSON.") from None
        return code, value, policy

    def set_csrf(self, value):
        if not isinstance(value, str) or not value:
            raise VerificationError("Server did not provide a CSRF token.")
        self.csrf = value
        self.secrets.add(value)


class Evidence:
    def __init__(self, directory, client):
        self.directory, self.client = Path(directory), client
        self.directory.mkdir(parents=True, exist_ok=False)

    def json(self, name, value):
        target = self.directory / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.client.redact(value), indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")

    def transition(self, value):
        with (self.directory / "status_changes.ndjson").open("a", encoding="utf-8") as output:
            output.write(json.dumps(self.client.redact({"observed_at": now(), **value}), allow_nan=False) + "\n")


def safe_relative_name(name):
    parts = name.split("/")
    if (not name or "\\" in name or ":" in name or any(ord(char) < 32 for char in name)
            or any(part in ("", ".", "..") or part.endswith((" ", ".")) for part in parts)
            or any(re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", part) for part in parts)):
        raise VerificationError("Unsafe artifact path; nothing was extracted outside the evidence directory.")
    return name


def safe_zip_members(archive):
    names, members, total = set(), [], 0
    for item in archive.infolist():
        name = item.filename.rstrip("/") if item.is_dir() else item.filename
        safe_relative_name(name)
        canonical = name.casefold()
        if canonical in names:
            raise VerificationError("Duplicate ZIP path; archive was not extracted.")
        names.add(canonical)
        mode = stat.S_IFMT(item.external_attr >> 16)
        if mode not in (0, stat.S_IFREG, stat.S_IFDIR):
            raise VerificationError("ZIP links/devices are not accepted.")
        total += item.file_size
        if total > MAX_ARTIFACT_BYTES or item.flag_bits & 1:
            raise VerificationError("Encrypted or oversized ZIP was not extracted.")
        members.append((item, name))
    return members


def save_zip(body, evidence):
    evidence.client.check_evidence_bytes(body)
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        members = safe_zip_members(archive)
        # Inspect before saving/extracting, so an unexpected echoed credential
        # is not written into the evidence bundle, even inside compressed data.
        for item, _ in members:
            if not item.is_dir():
                evidence.client.check_evidence_bytes(archive.read(item))
        (evidence.directory / "results.zip").write_bytes(body)
        destination = evidence.directory / "extracted"
        destination.mkdir(exist_ok=False)
        for item, name in members:
            target = destination.joinpath(*PurePosixPath(name).parts)
            if not target.resolve().is_relative_to(destination.resolve()):
                raise VerificationError("ZIP destination escaped the evidence directory.")
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb") as output:
                    output.write(archive.read(item))
    return destination


def inspect_arrays(directory):
    import numpy as np
    from openstream.gui_reference import CORE, EXTRA
    report = {"shape_and_core_finite_passed": True, "all_arrays_finite": True, "files": []}
    files = sorted(directory.rglob("*.npz"))
    if not files:
        raise VerificationError("No numerical NPZ files were downloaded.")
    for path in files:
        metadata = json.loads((path.parent / "metadata.json").read_text(encoding="utf-8"))
        framework = metadata["framework"].removesuffix("Solver")
        core = set(CORE[framework]) | set(EXTRA.get(framework, ()))
        record = {"file": path.relative_to(directory).as_posix(), "arrays": []}
        with np.load(path, allow_pickle=False) as arrays:
            z, t = arrays["Z"], arrays["TIME"]
            axes_ok = (z.ndim == t.ndim == 1 and z.size > 0 and t.size > 0 and np.isfinite(z).all()
                       and np.isfinite(t).all() and np.all(np.diff(z) > 0) and np.all(np.diff(t) >= 0))
            record["axes_passed"] = bool(axes_ok)
            report["shape_and_core_finite_passed"] &= bool(axes_ok)
            for key in arrays.files:
                values = arrays[key]
                numeric = values.dtype.kind in "buif"
                finite = np.isfinite(values) if numeric else np.zeros(values.shape, dtype=bool)
                shape_ok = values.ndim == 1 if key in ("Z", "TIME") else values.ndim >= 2 and values.shape[:2] == (len(t), len(z))
                shape_ok = shape_ok and all(size > 0 for size in values.shape)
                nonfinite = int(values.size - np.count_nonzero(finite))
                primary = key in core or key in ("Z", "TIME")
                row = {"key": key, "shape": list(values.shape), "dtype": str(values.dtype), "shape_passed": bool(shape_ok),
                       "nonfinite_count": nonfinite, "primary_or_coordinate": primary, "unit": metadata.get("units", {}).get(key)}
                record["arrays"].append(row)
                report["all_arrays_finite"] &= nonfinite == 0
                report["shape_and_core_finite_passed"] &= bool(numeric and shape_ok and (not primary or nonfinite == 0))
        report["files"].append(record)
    report["scope"] = "All array shapes and numeric types; finite primary/archive profiles and coordinates. Nonfinite diagnostic entries are reported, not silently removed or made a new solver criterion."
    return report


def check_auth(client, password, checks=None):
    checks = [] if checks is None else checks
    for path in ("/api/health", "/api/schema", "/api/runs", "/assets/app.js", "/cloud-assets/cloud.js",
                 "/files/" + "0" * 32 + "/results.zip"):
        code, _, _ = client.request("GET", path)
        checks.append({"check": "anonymous " + path, "http_status": code, "passed": code == 401})
    code, session, _ = client.json("GET", "/auth/session")
    if code != 200:
        raise VerificationError(f"Authentication bootstrap returned HTTP {code}.")
    client.set_csrf(session.get("csrf"))
    code, _, _ = client.json("POST", "/auth/login", {"password": password}, csrf=False)
    checks.append({"check": "login without CSRF", "http_status": code, "passed": code == 403})
    wrong = secrets.token_urlsafe(40)
    client.secrets.add(wrong)
    code, _, _ = client.json("POST", "/auth/login", {"password": wrong})
    checks.append({"check": "wrong password", "http_status": code, "passed": code == 401})
    code, session, policies = client.json("POST", "/auth/login", {"password": password})
    checks.append({"check": "correct password", "http_status": code, "passed": code == 200 and session.get("authenticated") is True})
    checks.append({"check": "secure cookie attributes", "passed": bool(policies) and all(all(row.values()) for row in policies), "policies": policies})
    if code != 200 or session.get("authenticated") is not True:
        raise VerificationError(f"Correct-password sign-in failed with HTTP {code}.")
    client.set_csrf(session.get("csrf"))
    code, _, _ = client.json("POST", "/api/validate", {}, csrf=False)
    checks.append({"check": "authenticated POST without CSRF", "http_status": code, "passed": code == 403})
    code, _, _ = client.json("POST", "/api/validate", {}, headers={"Origin": "https://example.invalid"})
    checks.append({"check": "cross-origin POST", "http_status": code, "passed": code == 403})
    code, _, _ = client.json("GET", "/api/health")
    checks.append({"check": "authenticated API", "http_status": code, "passed": code == 200})
    return {"passed": all(row["passed"] for row in checks), "checks": checks}


def poll(client, run_id, evidence, *, interval, timeout):
    deadline = time.monotonic() + timeout
    previous = None
    while time.monotonic() < deadline:
        code, state, _ = client.json("GET", f"/api/runs/{run_id}")
        if code != 200:
            raise VerificationError(f"Run status returned HTTP {code}; run was not resubmitted.")
        if state.get("id") != run_id:
            raise VerificationError("Status identity differs from the submitted run.")
        current = (state.get("status"), state.get("phase"))
        if current != previous:
            evidence.transition(state)
            print(client.redact(f"{run_id}: {current[0]} / {current[1]}"), flush=True)
            previous = current
        if state.get("status") in TERMINAL:
            evidence.json("status.json", state)
            return state
        time.sleep(interval)
    raise VerificationError("Polling deadline reached; job outcome remains unresolved and no new run was submitted.")


def run_case(client, framework, evidence, *, interval, timeout, cancel=False):
    from openstream.gui_reference import compare_reference
    from openstream.gui_schema import assess_payload
    report = {"framework": framework, "started_at": now(), "kind": "cancellation" if cancel else "baseline",
              "passed": False, "run_id": None, "terminal_observed": False, "failures": [], "downloads": []}
    try:
        code, payload, _ = client.json("GET", f"/api/baseline/{framework}")
        if code != 200 or payload.get("framework") != framework:
            raise VerificationError(f"Baseline retrieval failed with HTTP {code}.")
        evidence.json("submitted_inputs.json", payload)
        if not assess_payload(payload)["is_reference"]:
            raise VerificationError("Hosted baseline differs from the local archived-reference inputs; nothing was submitted.")
        code, validation, _ = client.json("POST", "/api/validate", payload)
        evidence.json("input_validation.json", validation)
        if code != 200 or validation.get("is_reference") is not True:
            raise VerificationError("Hosted baseline validation did not confirm reference inputs.")
        report["submission_attempted"] = True
        code, state, _ = client.json("POST", "/api/runs", payload)
        evidence.json("submission_response.json", {"http_status": code, "state": state})
        if code != 202 or not re.fullmatch(r"[0-9a-f]{32}", str(state.get("id", ""))):
            report["submission_rejected"] = code in (400, 401, 403, 409, 413, 415, 422, 429)
            raise VerificationError(f"Run submission returned HTTP {code}; it was not retried.")
        run_id = report["run_id"] = state["id"]
        if cancel:
            code, acknowledged, _ = client.json("POST", f"/api/runs/{run_id}/cancel", {})
            evidence.json("cancellation_request.json", {"http_status": code, "state": acknowledged})
            if code != 200:
                raise VerificationError(f"Cancellation request returned HTTP {code}; it was not retried.")
        state = poll(client, run_id, evidence, interval=interval, timeout=timeout)
        report["terminal_observed"] = True
        report["status"] = state.get("status")
        report["converged"] = state.get("converged")
        report["reference"] = state.get("reference")
        report["physical"] = state.get("physical")
        if cancel:
            report["passed"] = state["status"] == "cancelled"
            if not report["passed"]:
                report["failures"].append("Worker did not acknowledge cancellation; terminal status was " + state["status"])
        else:
            if state["status"] != "completed": report["failures"].append("Hosted worker did not complete successfully.")
            if state.get("converged") is not True: report["failures"].append("Native convergence was not confirmed.")
            if state.get("reference", {}).get("status") != "passed": report["failures"].append("Hosted archive comparison did not pass.")
        extraction = None
        for item in state.get("files", []):
            name = item.get("name", "")
            selected = name in {"results.zip", "worker.log", "bootstrap.log", "submitted_inputs.json"} or (
                name.endswith(".json") and any(word in name for word in ("verification", "metadata", "diagnostic")))
            if not selected:
                continue
            safe_relative_name(name)
            code, body, _ = client.request("GET", f"/files/{run_id}/{urllib.parse.quote(name, safe='/')}")
            if code != 200:
                report["failures"].append(f"Artifact {name} returned HTTP {code}.")
                continue
            client.check_evidence_bytes(body)
            report["downloads"].append({"name": name, "sha256": hashlib.sha256(body).hexdigest(), "size": len(body)})
            if name == "results.zip":
                extraction = save_zip(body, evidence)
            else:
                target = evidence.directory / "downloads" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
        if not cancel and state["status"] == "completed":
            code, plot_data, _ = client.json("GET", f"/api/runs/{run_id}/data")
            evidence.json("plot_data.json", plot_data)
            if code != 200 or not isinstance(plot_data.get("datasets"), dict):
                report["failures"].append("Hosted plot-data endpoint did not return the expected datasets.")
            if extraction is None:
                report["failures"].append("No complete results ZIP was downloaded.")
            else:
                extracted_inputs = json.loads((extraction / "submitted_inputs.json").read_text(encoding="utf-8"))
                if extracted_inputs != payload:
                    raise VerificationError("Downloaded ZIP inputs differ from the submitted baseline.")
                arrays = inspect_arrays(extraction)
                evidence.json("array_checks.json", arrays)
                comparison = compare_reference(framework, extraction / "output")
                evidence.json("independent_archive_comparison.json", comparison)
                report["array_checks"] = {key: value for key, value in arrays.items() if key != "files"}
                report["independent_archive_comparison"] = {key: value for key, value in comparison.items() if key != "records"}
                if not arrays["shape_and_core_finite_passed"]: report["failures"].append("Array shape or primary-profile finite-value checks failed.")
                if comparison["status"] != "passed": report["failures"].append("Independent downloaded-array archive comparison failed.")
        report["passed"] = bool(report["passed"] and not report["failures"]) if cancel else not report["failures"]
    except Exception as error:
        report["passed"] = False
        report["failures"].append(client.redact(f"{type(error).__name__}: {error}"))
    report["finished_at"] = now()
    evidence.json("verification.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--origin", default="https://openstream-py.vercel.app")
    parser.add_argument("--output", type=Path, required=True, help="Parent folder; each invocation creates a new evidence subfolder")
    parser.add_argument("--frameworks", nargs="+", choices=FRAMEWORKS, default=list(FRAMEWORKS))
    parser.add_argument("--cancel", action="store_true", help="Also submit and immediately cancel a separate FourField job")
    parser.add_argument("--poll-seconds", type=float, default=5)
    parser.add_argument("--timeout-seconds", type=float, default=3000)
    args = parser.parse_args(argv)
    if not 1 <= args.poll_seconds <= 10 or args.timeout_seconds <= 0:
        parser.error("poll interval must be 1–10 seconds and timeout must be positive")
    try:
        origin = checked_origin(args.origin)
    except ValueError as error:
        parser.error(str(error))
    password = os.environ.pop("OPENSTREAM_VERIFY_PASSWORD", None) or getpass.getpass("OpenSTREAM password: ")
    if not password:
        parser.error("A password is required")
    client = HTTPClient(origin, password)
    label = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    evidence = Evidence(args.output.resolve() / label, client)
    summary = {"origin": origin, "started_at": now(), "python": platform.python_version(), "cases": [],
               "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "scope": "Hosted HTTP functionality and unchanged archived TUTORIAL1 profiles; not experimental validation or full parity.",
               "artifacts": "Authentication payloads, headers, cookies and CSRF tokens are not recorded. Numerical artifacts are preserved byte-for-byte."}
    print(f"Evidence: {evidence.directory}", flush=True)
    auth_checks = []
    try:
        summary["authentication"] = check_auth(client, password, auth_checks)
        evidence.json("authentication_checks.json", summary["authentication"])
        if not summary["authentication"]["passed"]:
            raise VerificationError("Authentication boundary checks failed; no calculations were submitted.")
        plan = [(framework, False) for framework in args.frameworks] + ([("FourField", True)] if args.cancel else [])
        for number, (framework, cancel) in enumerate(plan, 1):
            case = Evidence(evidence.directory / f"{number:02d}-{framework}{'-cancel' if cancel else ''}", client)
            result = run_case(client, framework, case, interval=args.poll_seconds, timeout=args.timeout_seconds, cancel=cancel)
            summary["cases"].append(result)
            evidence.json("summary.json", summary)
            if result.get("submission_attempted") and not result["terminal_observed"] and not result.get("submission_rejected"):
                summary["remaining_cases_not_attempted"] = "Prior submission outcome is unresolved; sequential execution stopped without retrying or creating another run."
                break
        code, _, _ = client.json("POST", "/auth/logout", {})
        after, _, _ = client.request("GET", "/api/health")
        summary["logout"] = {"passed": code == 200 and after == 401, "logout_http_status": code, "anonymous_api_http_status": after}
    except Exception as error:
        summary["error"] = client.redact(f"{type(error).__name__}: {error}")
    if "authentication" not in summary:
        summary["authentication"] = {"passed": False, "checks": auth_checks}
        evidence.json("authentication_checks.json", summary["authentication"])
    summary["finished_at"] = now()
    summary["passed"] = bool(summary.get("authentication", {}).get("passed") and summary.get("logout", {}).get("passed")
                             and len(summary["cases"]) == len(args.frameworks) + int(args.cancel)
                             and all(case["passed"] for case in summary["cases"]) and "error" not in summary)
    evidence.json("summary.json", summary)
    print("Hosted verification passed." if summary["passed"] else "Hosted verification failed or remains incomplete; retained evidence contains the failures.", flush=True)
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
