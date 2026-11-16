"""Verify deployed presentation assets; no solver runs or input edits.

Use the project Python environment. Set OPENSTREAM_VERIFY_PASSWORD and pass
the deployed Git commit and a new receipt filename as positional arguments.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
from verify_hosted_gui import HTTPClient

commit, output = sys.argv[1:]
destination = Path(output)
if destination.exists():
    raise SystemExit("Choose a new receipt path; existing evidence is preserved.")
client = HTTPClient("https://openstream-py.vercel.app", os.environ["OPENSTREAM_VERIFY_PASSWORD"])
status, _, _ = client.request("GET", "/assets/app.js")
assert status == 401
status, session, _ = client.json("GET", "/auth/session")
assert status == 200
client.set_csrf(session["csrf"])
status, session, _ = client.json("POST", "/auth/login", {"password": os.environ["OPENSTREAM_VERIFY_PASSWORD"]})
assert status == 200 and session["authenticated"]
client.set_csrf(session["csrf"])
checks = []
for asset in ("app.js", "style.css"):
    status, body, _ = client.request("GET", "/assets/" + asset)
    expected = subprocess.check_output(["git", "show", f"{commit}:src/openstream/gui_static/{asset}"], cwd=ROOT)
    assert status == 200 and body.replace(b"\r\n", b"\n") == expected.replace(b"\r\n", b"\n")
    checks.append({"asset": asset, "http_status": status, "matches_commit": True,
                   "served_sha256": hashlib.sha256(body).hexdigest()})
status, health, _ = client.json("GET", "/api/health")
assert status == 200
status, runs, _ = client.json("GET", "/api/runs")
assert status == 200
receipt = {"verified_at_utc": datetime.now(timezone.utc).isoformat(), "commit": commit,
           "origin": client.origin, "anonymous_assets_denied": True,
           "authenticated_api_available": True, "asset_checks": checks,
           "scope": "Authenticated source-asset equality and API availability; no new numerical calculation."}
destination.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
print(json.dumps(receipt, indent=2))
