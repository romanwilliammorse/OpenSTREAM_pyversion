"""Verify hosted routes in an environment containing only requirements-web.lock.

Run directly with that environment's Python; pytest is not required. Scientific
and plotting package imports are actively blocked. All storage uses synthetic
in-memory artifacts and test-only configuration; no network requests occur.
This checks API dependency isolation, not scientific or deployment equivalence.
"""
from contextlib import contextmanager
import csv
import hashlib
import importlib.abc
import importlib.util
import io
import json
import os
from pathlib import Path
import secrets
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / "src"))
blocked = {"scipy", "CoolProp", "matplotlib", "plotly"}
class RejectScientificImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in blocked:
            raise ImportError("Scientific import forbidden in hosted API: " + fullname)
sys.meta_path.insert(0, RejectScientificImports())

import openstream
assert not blocked.intersection(sys.modules)
assert not {"openstream.solver", "openstream.properties", "openstream.plotting"}.intersection(sys.modules)
import numpy as np
from werkzeug.security import generate_password_hash
from openstream.cloud.app import create_app
from openstream.cloud.manager import CloudRunManager
from openstream.gui_schema import baseline

origin = "https://openstream-py.vercel.app"
run_id = "b" * 32
payload = baseline("FourField")
artifacts = {
    "submitted_inputs.json": json.dumps(payload).encode(),
    "output/metadata.json": json.dumps({"units": {"film.U": "m/s"}}).encode(),
    "output/mixture/metadata.json": json.dumps({"units": {"vapor.X": "1"}}).encode(),
    "plot_data.json": json.dumps({"datasets": {"physical": {"z": [0, 1], "fields": {}}}}).encode(),
}
def npz(**arrays):
    value = io.BytesIO()
    np.savez_compressed(value, **arrays)
    return value.getvalue()
artifacts["output/results.npz"] = npz(Z=np.array([0., 1.]), TIME=np.array([0.]), **{"film.U": np.array([[1.25, 2.5]])})
artifacts["output/mixture/initialization.npz"] = npz(Z=np.array([0., 1.]), TIME=np.array([0.]), **{"vapor.X": np.array([[0.2, np.nan]])})
before = {name: hashlib.sha256(body).hexdigest() for name, body in artifacts.items()}
manifest = {"framework": "FourField"}
terminal = {"status": {"status": "completed"}, "publication": {"complete": True},
            "artifacts": {name: {} for name in artifacts}, "plot_data": {}}
manager = CloudRunManager(None, None, source={}, environment={})
manager._result = lambda identity: (manifest, terminal)
manager._verified_bytes = lambda saved, name, receipt: artifacts[name]
@contextmanager
def read_artifact(saved, complete, name):
    yield io.BytesIO(artifacts[name])
manager._export_reader = read_artifact
password = secrets.token_urlsafe(24)
config = {"TESTING": True, "OPENSTREAM_PASSWORD_HASH": generate_password_hash(password),
          "OPENSTREAM_SESSION_SECRET": secrets.token_urlsafe(48), "OPENSTREAM_PUBLIC_ORIGIN": origin}
app = create_app(manager, config, limiter=lambda key: True)
client = app.test_client()
def get(path):
    return client.get(path, base_url=origin)
def post(path, csrf, body):
    return client.post(path, json=body, base_url=origin, headers={"Origin": origin, "X-CSRF-Token": csrf})

assert get("/").status_code == 303
assert get("/login").status_code == 200
assert get("/assets/plotly.min.js").status_code == 401
csrf = get("/auth/session").json["csrf"]
login = post("/auth/login", csrf, {"password": password})
assert login.status_code == 200
csrf = login.json["csrf"]
assert get("/").status_code == 200
assert get("/api/health").status_code == 200
plotly_js = get("/assets/plotly.min.js")
assert plotly_js.status_code == 200 and b"plotly.js" in plotly_js.data[:1000]
plotly_js.close()
for framework in ("Mixture", "TwoFluid", "ThreeField", "FourField"):
    shape = get("/api/schema?framework=" + framework)
    reference = get("/api/baseline/" + framework)
    assert shape.status_code == reference.status_code == 200
    assert shape.json["framework"] == reference.json["framework"] == framework
    assert len(shape.json["fields"]) == 163
    valid = post("/api/validate", csrf, reference.json)
    assert valid.status_code == 200 and valid.json["valid"] and valid.json["is_reference"]
bad = baseline("FourField")
bad["inputs"]["geometry"]["AREA"] = -1
assert post("/api/validate", csrf, bad).status_code == 400
exports = {}
for kind in ("inputs", "boundary-conditions", "geometry", "results"):
    response = get(f"/api/runs/{run_id}/export/{kind}.csv")
    assert response.status_code == 200
    exports[kind] = list(csv.DictReader(io.StringIO(response.data.decode("utf-8-sig"))))
    response.close()
pressure = next(row for row in exports["boundary-conditions"] if row["parameter"] == "PRESSURE")
assert pressure["unit"] == "Pa" and json.loads(pressure["value_json"]) == 6000000
area = next(row for row in exports["geometry"] if row["parameter"] == "AREA")
assert area["unit"] == "m^2" and json.loads(area["value_json"]) == payload["inputs"]["geometry"]["AREA"]
velocity = [row for row in exports["results"] if row["quantity"] == "film.U"]
assert [float(row["value"]) for row in velocity] == [1.25, 2.5]
assert all(row["unit"] == "m/s" and row["array_shape"] == "[1,2]" for row in velocity)
legacy = get(f"/api/runs/{run_id}/data")
assert legacy.status_code == 200
recovered = legacy.json["datasets"]["precursor_initialization"]
assert recovered["fields"]["vapor.X"]["values"] == [[0.2, None]]
assert recovered["fields"]["vapor.X"]["unit"] == "1"
assert before == {name: hashlib.sha256(body).hexdigest() for name, body in artifacts.items()}

# Import the actual Vercel entrypoint with synthetic configuration. Construction
# must not access the network, load the solver, or require scientific packages.
os.environ.update({"VERCEL": "0", "BLOB_STORE_ID": "store_teststore",
                   "OPENSTREAM_PASSWORD_HASH": config["OPENSTREAM_PASSWORD_HASH"],
                   "OPENSTREAM_SESSION_SECRET": config["OPENSTREAM_SESSION_SECRET"],
                   "OPENSTREAM_PUBLIC_ORIGIN": origin})
spec = importlib.util.spec_from_file_location("web_entrypoint_probe", root / "app.py")
entrypoint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entrypoint)
assert entrypoint.app.test_client().get("/login", base_url=origin).status_code == 200
assert not blocked.intersection(sys.modules)
assert not {"openstream.solver", "openstream.properties", "openstream.plotting"}.intersection(sys.modules)
print(json.dumps({"blocked_modules": sorted(blocked), "four_baselines_validated": True,
                  "csv_types_checked": sorted(exports), "saved_artifacts_unchanged": True,
                  "legacy_nonfinite_gap_preserved": True, "actual_entrypoint_imported": True}))
