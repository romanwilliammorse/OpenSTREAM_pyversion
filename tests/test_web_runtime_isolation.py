"""Exercise the standalone hosted-API dependency probe in a fresh process."""
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def test_hosted_routes_work_without_scientific_or_plotting_imports():
    result = subprocess.run([sys.executable, str(ROOT / "tools" / "verify_web_runtime.py")],
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    evidence = json.loads(result.stdout)
    assert evidence["four_baselines_validated"]
    assert evidence["actual_entrypoint_imported"]
    assert evidence["saved_artifacts_unchanged"]
    assert evidence["legacy_nonfinite_gap_preserved"]
    assert evidence["csv_types_checked"] == ["boundary-conditions", "geometry", "inputs", "results"]
    assert evidence["blocked_modules"] == ["CoolProp", "matplotlib", "plotly", "scipy"]
