"""Check restored assets and the failing validation route without starting a run.

Use the project environment and OPENSTREAM_VERIFY_PASSWORD. No secrets are
written to the receipt. Existing evidence is not overwritten.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from verify_hosted_gui import HTTPClient

destination = Path(sys.argv[1])
if destination.exists():
    raise SystemExit("Use a new receipt path.")
client = HTTPClient("https://openstream-py.vercel.app", os.environ["OPENSTREAM_VERIFY_PASSWORD"])
receipt = {"checked_at": datetime.now(timezone.utc).isoformat(),
           "restored_source": "ce67394295ac5b5de4a2cbb54b9c533e387dcd7d",
           "release_commit": "253951f27de772989edaf7777df303889f88e2d8",
           "checks": [], "limitation": "Observed requests only; no guarantee of independent cold-start reliability or total performance recovery."}
def record(name, code, started, passed):
    receipt["checks"].append({"check": name, "http_status": code,
                              "elapsed_seconds": round(time.perf_counter() - started, 3), "passed": bool(passed)})
    assert passed, name
try:
    started = time.perf_counter()
    code, _, _ = client.request("GET", "/assets/app.js")
    record("anonymous asset denied", code, started, code == 401)
    code, session, _ = client.json("GET", "/auth/session")
    assert code == 200
    client.set_csrf(session["csrf"])
    code, session, _ = client.json("POST", "/auth/login", {"password": os.environ["OPENSTREAM_VERIFY_PASSWORD"]})
    assert code == 200 and session["authenticated"]
    client.set_csrf(session["csrf"])
    for asset in ("app.js", "style.css"):
        started = time.perf_counter()
        code, body, _ = client.request("GET", "/assets/" + asset)
        expected = subprocess.check_output(["git", "show", f"{receipt['restored_source']}:src/openstream/gui_static/{asset}"], cwd=ROOT)
        record("restored " + asset, code, started, code == 200 and body.replace(b"\r\n",b"\n") == expected.replace(b"\r\n",b"\n"))
    code, payload, _ = client.json("GET", "/api/baseline/FourField")
    assert code == 200
    for index in range(3):
        started = time.perf_counter()
        code, validation, _ = client.json("POST", "/api/validate", payload)
        record(f"FourField reference validation {index + 1}", code, started, code == 200 and validation.get("valid") is True and validation.get("is_reference") is True)
finally:
    destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt, indent=2))
