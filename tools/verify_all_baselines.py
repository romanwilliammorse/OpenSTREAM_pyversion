"""Recover, solve and compare all four original baselines in dependency order.

Run from the installed project environment. MATLAB is not required. Every run
uses a new directory. CLI status 3 is retained as a physical-consistency failure;
this runner's successful exit means archive comparison passed, not validation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    records = []
    def run(arguments, log, allowed=(0,)):
        with log.open("x", encoding="utf-8") as stream:
            result = subprocess.run([sys.executable, *map(str, arguments)], cwd=ROOT,
                                    stdout=stream, stderr=subprocess.STDOUT, check=False)
        if result.returncode not in allowed:
            raise RuntimeError(f"Stage failed with status {result.returncode}; see {log}")
        return result.returncode
    try:
        for framework in ("Mixture", "TwoFluid", "ThreeField", "FourField"):
            directory = output / framework
            directory.mkdir()
            reference, native, comparison = (directory / name for name in ("reference", "native", "comparison"))
            print(f"{framework}: recovering original archive", flush=True)
            if framework == "Mixture":
                recover = ["tools/recover_mcos_reference.py"]
                compare = "tools/verify_recovered_mixture.py"
            elif framework == "TwoFluid":
                recover = ["tools/recover_twofluid_reference.py"]
                compare = "tools/verify_recovered_framework.py"
            else:
                recover = ["tools/recover_annular_reference.py", "--framework", framework]
                compare = "tools/verify_recovered_framework.py"
            run([*recover, "--output", reference], directory / "recovery.log")
            print(f"{framework}: running native solver", flush=True)
            code = run(["-m", "openstream", "sample", "--framework", framework.lower(),
                        "--inputs", "upstream/inputs", "--output", native, "--quiet"],
                       directory / "native.log", allowed=(0, 3))
            run([compare, reference, native, comparison], directory / "comparison.log")
            result = json.loads((comparison / "comparison.json").read_text())
            metadata = json.loads((native / "metadata.json").read_text())
            if not result["upstream_regression_passed"] or not result["initialization_core_passed"]:
                raise RuntimeError(f"{framework} core/archive comparison failed")
            records.append({"framework": framework, "core_baseline_passed": result["upstream_regression_passed"],
                            "initialization_core_passed": result["initialization_core_passed"],
                            "expanded_profiles_passed": result.get("expanded_profiles_passed"),
                            "core_profiles": len(result["physical"]["core"]),
                            "max_physical_relative_error": max(x["max_relative_error_nonzero"] for x in result["physical"]["core"].values()),
                            "native_cli_exit_code": code,
                            "physical_consistency": metadata.get("physical_diagnostics", {}).get("physical_consistency"),
                            "comparison_report": str((comparison / "comparison.json").relative_to(output))})
            print(f"{framework}: core baseline PASS; native physical-diagnostic status {code}", flush=True)
    finally:
        summary = {"schema": "openstream-baseline-suite-v1", "baseline_cases_passed": len(records),
                   "baseline_cases_total": 4, "records": records,
                   "scope": "Original steady TUTORIAL1 archives, initializations and mixture precursors; no fresh MATLAB execution",
                   "limitation": "Passing archived baselines does not imply full option/API parity or experimental validation. Physical failures and supplementary diagnostic disagreements remain in each report."}
        (output / "summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
