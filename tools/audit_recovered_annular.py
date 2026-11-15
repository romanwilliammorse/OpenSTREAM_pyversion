"""Independent direct-MCOS comparison for the approved annular baselines.

No native numerical methods or exported reference NPZ files build references.
Four-field aggregate properties follow the original dependent getters exactly.
"""
import argparse
import hashlib
import json
from pathlib import Path

from recover_mcos_reference import ROOT, load_archive
import numpy as np


def direct_state(solver, suffix=""):
    films = np.asarray(solver.properties["film" + suffix], dtype=object).ravel(order="F")
    drops = np.asarray(solver.properties["drop" + suffix], dtype=object).ravel(order="F")
    out = {"Z": solver.properties["Z"][:, 0], "TIME": np.array([f.properties["TIME"].item() for f in films])}
    four = solver.classname == "Solvers.FourField.FourFieldSolver"
    for key in ("W", "U", "H"):
        out["drop." + key] = np.stack([obj.properties[key][:, 0] for obj in drops])
        if not four:
            out["film." + key] = np.stack([obj.properties[key] for obj in films])
        else:
            for name in ("base", "wave"):
                out["film." + name + "." + key] = np.stack([f.properties[name].properties[key] for f in films])
    if four:
        out["film.W"] = out["film.base.W"] + out["film.wave.W"]
        out["film.H"] = out["film.base.H"].copy()
        with np.errstate(divide="ignore", invalid="ignore"):
            out["film.U"] = out["film.W"] / (out["film.base.W"] / out["film.base.U"] + out["film.wave.W"] / out["film.wave.U"])
        empty = out["film.W"] == 0
        out["film.U"][empty] = out["film.base.U"][empty]
        out["film.wave.FREQUENCY"] = np.stack([f.properties["wave"].properties["FREQUENCY"] for f in films])
    return out


def audit(archive, native):
    solver = load_archive(archive)["solver"]
    framework = solver.classname.split(".")[-1].removesuffix("Solver")
    if framework not in ("ThreeField", "FourField"):
        raise ValueError("Expected an annular solver")
    report = {"framework": framework,
              "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
              "native_directory": str(native.resolve()),
              "scope": "Independent direct property extraction from MCOS and source dependent-getter formulas; no exported reference arrays or native field methods",
              "rtol": 1e-8, "atol": 0.0, "phases": {}}
    for phase, filename, suffix in (("physical", "results.npz", ""), ("initialization", "initialization.npz", "Init")):
        refs = direct_state(solver, suffix)
        with np.load(native / filename, allow_pickle=False) as data:
            for coordinate in ("Z", "TIME"):
                if refs[coordinate].shape != data[coordinate].shape or not np.allclose(refs[coordinate], data[coordinate], rtol=0, atol=1e-12):
                    raise ValueError(f"Coordinate mismatch: {phase}.{coordinate}")
            rows = {}
            for key, ref in refs.items():
                if key in ("Z", "TIME"):
                    continue
                actual = data[key]
                if actual.shape != ref.shape or not np.all(np.isfinite(ref)) or not np.all(np.isfinite(actual)):
                    raise ValueError(f"Shape/nonfinite mismatch: {phase}.{key}")
                absolute = np.abs(actual - ref)
                nonzero = ref != 0
                rows[key] = {"passed": bool(np.all(absolute <= 1e-8 * np.abs(ref))),
                             "max_absolute_error": float(np.max(absolute)),
                             "max_relative_error_nonzero": float(np.max(absolute[nonzero] / abs(ref[nonzero]))) if np.any(nonzero) else 0.0,
                             "zero_mismatches": int(np.count_nonzero(actual[~nonzero])),
                             "shape": list(ref.shape)}
            report["phases"][phase] = {"all_pass": all(v["passed"] for v in rows.values()), "comparisons": rows}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", choices=("ThreeField", "FourField"), required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--native", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; choose a new report path")
    archive = args.archive or ROOT / f"upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/tutorial1_{args.framework}Solver.mat"
    result = audit(archive, args.native)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"framework": result["framework"], "all_pass": all(v["all_pass"] for v in result["phases"].values()), "output": str(args.output)}, indent=2))
    raise SystemExit(0 if all(v["all_pass"] for v in result["phases"].values()) else 2)
