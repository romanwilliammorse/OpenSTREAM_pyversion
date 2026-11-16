"""Audit startup repair boundaries and acceptance evidence without running physics.

Run with the project Python and pass a new output JSON path. The only permitted
tracked package-module changes are the lazy export initializer and the hosted
app's renderer-asset route. All
other package modules, scientific worker dependencies, frontend assets and
acceptance criteria/statuses must match the retained formatting release.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
BASELINE = "935c03ed4b95aa5ee8457a957110c6db74d6ff86"

def old(path):
    return subprocess.check_output(["git", "show", f"{BASELINE}:{path}"], cwd=ROOT)

def digest(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()

def run(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError("Existing evidence is preserved; choose a new path.")
    tracked = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", BASELINE, "src/openstream"], cwd=ROOT, text=True).splitlines()
    python = [path for path in tracked if path.endswith(".py")]
    allowed = {"src/openstream/__init__.py", "src/openstream/cloud/app.py"}
    unchanged = {}
    changed = []
    for path in python:
        a, b = old(path), (ROOT/path).read_bytes()
        if digest(a) != digest(b):
            changed.append(path)
            if path not in allowed:
                raise AssertionError(f"Unexpected native module change: {path}")
        else:
            unchanged[path] = digest(b)
    preserved = {}
    for path in ["requirements-cloud.lock", "requirements.lock", "requirements-gui.lock", "pyproject.toml", "src/openstream/gui_static/app.js", "src/openstream/gui_static/index.html", "src/openstream/gui_static/style.css", "examples/sawai_oscillation_diagnostic.json", "tools/trace_sawai_oscillation.py"]:
        a, b = old(path), (ROOT/path).read_bytes()
        assert digest(a) == digest(b), f"Preserved dependency/frontend contract changed: {path}"
        preserved[path] = digest(b)
    before, after = [], []
    for part in ("core", "interfaces", "experimental"):
        path = f"docs/acceptance/{part}.json"
        before.extend(json.loads(old(path)))
        after.extend(json.loads((ROOT/path).read_bytes()))
    a, b = {row["id"]: row for row in before}, {row["id"]: row for row in after}
    assert len(a) == 81 and set(a) == set(b), "Acceptance inventory changed"
    fixed = ("track", "component", "requirement", "scope", "upstream", "implementation", "native_tests", "matlab", "physical", "experimental", "priority", "acceptance_criteria", "depends_on")
    for row_id in a:
        for key in fixed:
            assert a[row_id].get(key) == b[row_id].get(key), f"Acceptance criterion/status changed: {row_id}/{key}"
    check = subprocess.run([sys.executable, str(ROOT/"tools/build_acceptance_matrix.py"), "--check"], cwd=ROOT, capture_output=True, text=True, check=True)
    receipt = {"schema": "openstream-hosted-startup-scope-v1", "checked_at": datetime.now(timezone.utc).isoformat(),
               "baseline_commit": BASELINE, "changed_package_modules": changed,
               "unchanged_package_module_count": len(unchanged), "unchanged_package_module_sha256_lf": unchanged,
               "preserved_dependency_and_frontend_sha256_lf": preserved,
               "acceptance_requirements": len(a), "unchanged_acceptance_fields": fixed,
               "updated_ledger_rows": [row_id for row_id in a if a[row_id] != b[row_id]],
               "matrix_check_stdout": check.stdout,
               "limitation": "Source and ledger integrity; lazy-export behavior requires separate tests. No new MATLAB or experimental-validation claim."}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2); stream.write("\n")
    print(f"PASS: {len(unchanged)} unchanged package modules, {len(a)} unchanged acceptance criteria/status sets; changed modules: {changed}")

if __name__ == "__main__":
    run(sys.argv[1])
