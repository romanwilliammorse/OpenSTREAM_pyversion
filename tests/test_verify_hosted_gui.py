"""Offline verification-driver checks. These never contact the deployment."""
from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
import secrets
import stat
import urllib.error
import urllib.request
import zipfile

import numpy as np
import pytest

from openstream.gui_schema import baseline


SPEC = importlib.util.spec_from_file_location("verify_hosted_gui", Path(__file__).resolve().parents[1] / "tools/verify_hosted_gui.py")
driver = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(driver)
ORIGIN = "https://openstream-py.vercel.app"
RUN_ID = "d" * 32


class Reply(io.BytesIO):
    def __init__(self, status, value):
        super().__init__(json.dumps(value).encode())
        self.code = status
        self.headers = Message()


class Opener:
    def __init__(self, *, cancellation=False):
        self.calls = []
        self.cancellation = cancellation

    def open(self, request, timeout):
        method, path = request.get_method(), urllib.parse.urlsplit(request.full_url).path
        self.calls.append((method, path))
        if path == "/api/baseline/Mixture":
            return Reply(200, baseline("Mixture"))
        if path == "/api/validate":
            return Reply(200, {"valid": True, "is_reference": True})
        if path == "/api/runs":
            return Reply(202, {"id": RUN_ID, "status": "queued"})
        if path.endswith("/cancel"):
            return Reply(200, {"id": RUN_ID, "status": "queued", "phase": "Cancellation requested"})
        if path == f"/api/runs/{RUN_ID}":
            if self.cancellation:
                return Reply(200, {"id": RUN_ID, "status": "cancelled", "phase": "Cancelled", "files": []})
            raise urllib.error.URLError("injected transport failure with sensitive detail")
        raise AssertionError("Unexpected offline request: " + path)


def test_submission_transport_failure_is_retained_without_retry(tmp_path):
    opener = Opener()
    secret = secrets.token_urlsafe(32)
    client = driver.HTTPClient(ORIGIN, secret, opener=opener)
    evidence = driver.Evidence(tmp_path / "case", client)
    result = driver.run_case(client, "Mixture", evidence, interval=1, timeout=5)
    assert result["passed"] is False and result["run_id"] == RUN_ID
    assert result["submission_attempted"] and not result["terminal_observed"]
    assert opener.calls.count(("POST", "/api/runs")) == 1
    assert "sensitive detail" not in json.dumps(result)
    assert json.loads((evidence.directory / "verification.json").read_text())["passed"] is False


def test_cancellation_is_a_separate_post_followed_by_terminal_acknowledgement(tmp_path):
    opener = Opener(cancellation=True)
    client = driver.HTTPClient(ORIGIN, secrets.token_urlsafe(32), opener=opener)
    evidence = driver.Evidence(tmp_path / "cancel", client)
    result = driver.run_case(client, "Mixture", evidence, interval=1, timeout=5, cancel=True)
    assert result["passed"] and result["status"] == "cancelled" and result["terminal_observed"]
    assert opener.calls[-3:] == [("POST", "/api/runs"), ("POST", f"/api/runs/{RUN_ID}/cancel"), ("GET", f"/api/runs/{RUN_ID}")]
    assert (evidence.directory / "cancellation_request.json").is_file()


def test_redaction_covers_password_csrf_cookie_and_echoed_values(tmp_path):
    secret = secrets.token_urlsafe(32)
    client = driver.HTTPClient(ORIGIN, secret)
    token = secrets.token_urlsafe(32)
    client.set_csrf(token)
    evidence = driver.Evidence(tmp_path / "redaction", client)
    evidence.json("report.json", {"password": secret, "csrf": token, "cookie": "anything", "message": f"echo: {secret} {token}"})
    text = (evidence.directory / "report.json").read_text()
    assert secret not in text and token not in text and "anything" not in text
    with pytest.raises(driver.VerificationError, match="secret"):
        client.check_evidence_bytes(secret.encode())


@pytest.mark.parametrize("method,url", [("POST", ORIGIN + "/other"), ("GET", "https://example.com/other"), ("GET", "http://openstream-py.vercel.app/other")])
def test_redirects_never_forward_posts_or_cross_origin_credentials(method, url):
    handler = driver.SameOriginRedirects(ORIGIN)
    request = urllib.request.Request(ORIGIN + "/auth/login", method=method)
    with pytest.raises(driver.VerificationError, match="Redirect rejected"):
        handler.redirect_request(request, None, 302, "redirect", Message(), url)


@pytest.mark.parametrize("name", ["../outside.txt", "/absolute.txt", "C:/outside.txt", "output/NUL.txt", "output/trailing."])
def test_zip_traversal_and_windows_aliases_are_rejected(tmp_path, name):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(name, b"test")
    evidence = driver.Evidence(tmp_path / "unsafe", driver.HTTPClient(ORIGIN, secrets.token_urlsafe(32)))
    with pytest.raises(driver.VerificationError, match="Unsafe artifact"):
        driver.save_zip(data.getvalue(), evidence)
    assert not list(evidence.directory.iterdir())


def test_literal_backslash_names_are_rejected_before_filesystem_use():
    # Windows zipfile normalizes its own separator at ZipInfo construction.
    with pytest.raises(driver.VerificationError, match="Unsafe artifact"):
        driver.safe_relative_name("output\\evil")


def test_short_numeric_secret_does_not_change_scientific_numbers_or_hashes(tmp_path):
    secret = str(secrets.randbelow(9000) + 1000)
    client = driver.HTTPClient(ORIGIN, secret)
    decimal = "0." + secret + "234"
    digest = "ab9f" + secret + "fa35"
    client.check_evidence_bytes(decimal.encode())
    client.check_evidence_bytes(json.dumps({"value": float(decimal), "hash": digest}).encode())
    assert client.redact({"value": decimal, "sha256": digest}) == {"value": decimal, "sha256": digest}
    assert client.redact("password=" + secret) == "password=[redacted]"
    with pytest.raises(driver.VerificationError, match="secret"):
        client.check_evidence_bytes(json.dumps({"password": secret}).encode())


def test_zip_link_and_duplicate_case_paths_are_rejected(tmp_path):
    for name, link in (("link", True), ("duplicate", False)):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            if link:
                item = zipfile.ZipInfo("output/link")
                item.create_system = 3
                item.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(item, "../../outside")
            else:
                archive.writestr("Output/file.txt", "one")
                archive.writestr("output/FILE.txt", "two")
        evidence = driver.Evidence(tmp_path / name, driver.HTTPClient(ORIGIN, secrets.token_urlsafe(32)))
        with pytest.raises(driver.VerificationError):
            driver.save_zip(data.getvalue(), evidence)


def test_secret_inside_compressed_artifact_is_not_saved(tmp_path):
    secret = secrets.token_urlsafe(32)
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("output/log.txt", secret)
    evidence = driver.Evidence(tmp_path / "secret", driver.HTTPClient(ORIGIN, secret))
    with pytest.raises(driver.VerificationError, match="secret"):
        driver.save_zip(data.getvalue(), evidence)
    assert not list(evidence.directory.iterdir())


def test_valid_zip_preserves_bytes_and_rejects_overwriting_extraction(tmp_path):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("output/metadata.json", '{"framework":"Mixture"}')
    evidence = driver.Evidence(tmp_path / "valid", driver.HTTPClient(ORIGIN, secrets.token_urlsafe(32)))
    destination = driver.save_zip(data.getvalue(), evidence)
    assert (evidence.directory / "results.zip").read_bytes() == data.getvalue()
    assert (destination / "output/metadata.json").read_text() == '{"framework":"Mixture"}'
    with pytest.raises(FileExistsError):
        driver.save_zip(data.getvalue(), evidence)


def test_array_check_reports_nonfinite_diagnostics_without_inventing_convergence_rule(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "metadata.json").write_text(json.dumps({"framework": "Mixture", "units": {"W": "kg/s"}}))
    np.savez(output / "results.npz", Z=[0.0, 1.0], TIME=[0.0], W=[[1.0, 1.0]], **{"ITR.DP": [[np.nan, 0.0]]})
    report = driver.inspect_arrays(tmp_path)
    assert report["shape_and_core_finite_passed"] is True
    assert report["all_arrays_finite"] is False
    row = next(row for row in report["files"][0]["arrays"] if row["key"] == "ITR.DP")
    assert row["nonfinite_count"] == 1 and row["primary_or_coordinate"] is False
    np.savez(output / "results.npz", Z=[0.0, 1.0], TIME=[0.0], W=[[1.0, np.nan]])
    assert driver.inspect_arrays(tmp_path)["shape_and_core_finite_passed"] is False
    np.savez(output / "results.npz", Z=[0.0, 1.0], TIME=[0.0], W=[[1.0]])
    assert driver.inspect_arrays(tmp_path)["shape_and_core_finite_passed"] is False


@pytest.mark.parametrize("origin", ["http://openstream-py.vercel.app", "https://user@openstream-py.vercel.app", "https://openstream-py.vercel.app/other", "https://openstream-py.vercel.app?secret=bad"])
def test_origin_must_be_explicit_https_without_credentials_or_path(origin):
    with pytest.raises(ValueError):
        driver.checked_origin(origin)
