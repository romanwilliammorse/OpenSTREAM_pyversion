"""Save all original-input framework samples and their actual status to a new folder."""
import argparse
import json
from pathlib import Path
from openstream import InputSet, MixtureSolver, TwoFluidSolver, ThreeFieldSolver, FourFieldSolver
from openstream.output import source_hashes

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("directory", type=Path)
args = parser.parse_args()
args.directory.mkdir(parents=True, exist_ok=False)
report = {"native_source_sha256": source_hashes(), "cases": {}}
for cls in (MixtureSolver, TwoFluidSolver, ThreeFieldSolver, FourFieldSolver):
    name = cls.__name__
    try:
        solver = cls(InputSet.official_sample()).solve()
        output = solver.save(args.directory/name)
        report["cases"][name] = {"state": solver.STATE.name, "numerically_converged": bool(solver.converged),
                                 "output": str(output), "diagnostics": solver.diagnostics() if hasattr(solver, "diagnostics") else None}
    except Exception as error:
        report["cases"][name] = {"failed": True, "error": repr(error)}
    (args.directory/"manifest.json").write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    print(name, json.dumps(report["cases"][name]), flush=True)
if any(x.get("failed") for x in report["cases"].values()): raise SystemExit(2)
if any(not x.get("numerically_converged") for x in report["cases"].values()): raise SystemExit(2)
if any((x.get("diagnostics") or {}).get("physical_consistency") is False for x in report["cases"].values()): raise SystemExit(3)
