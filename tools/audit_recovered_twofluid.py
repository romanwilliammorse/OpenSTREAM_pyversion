"""Independent direct-array audit of recovered approved two-fluid state."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from recover_twofluid_reference import CORE, ROOT
from verify_recovered_mixture import compare_effective_inputs


def compare(reference_path, native_path, keys):
    rows = {}
    with np.load(reference_path, allow_pickle=False) as ref, np.load(native_path, allow_pickle=False) as native:
        for key in ("Z", "TIME"):
            if ref[key].shape != native[key].shape or not np.allclose(ref[key], native[key], rtol=0, atol=1e-12):
                raise ValueError("Coordinate mismatch: " + key)
        for key in keys:
            expected, actual = ref[key], native[key]
            if expected.shape != actual.shape:
                raise ValueError("Array shape mismatch: " + key)
            if not np.all(np.isfinite(expected)) or not np.all(np.isfinite(actual)):
                raise ValueError("Nonfinite data: " + key)
            error = abs(actual - expected)
            nonzero = expected != 0
            relative = np.divide(error, abs(expected), out=np.zeros_like(error), where=nonzero)
            rows[key] = {"passed": bool(np.all(error <= 1e-8 * abs(expected))),
                         "max_absolute_error": float(np.max(error)),
                         "max_relative_error_nonzero": float(np.max(relative)),
                         "reference_zero_count": int(np.count_nonzero(~nonzero)),
                         "nonmatching_reference_zeros": int(np.count_nonzero(error[~nonzero])),
                         "shape": list(expected.shape)}
    return {"all_passed": all(v["passed"] for v in rows.values()), "profiles": rows}


def audit(reference, native):
    reference, native = Path(reference), Path(native)
    manifest = json.loads((reference / "manifest.json").read_text())
    metadata = json.loads((native / "metadata.json").read_text())
    if manifest["schema"] != "openstream-recovered-twofluid-v1" or not manifest["complete"]:
        raise ValueError("Invalid recovered reference")
    if manifest["archive"]["sha256"] != "40f0c9a8f080d6ffe3887947dc5794eb756b5fa0e2ce650ff37a88003e69798d":
        raise ValueError("Unexpected reference archive")
    for name, expected in manifest["files"].items():
        if hashlib.sha256((reference / name).read_bytes()).hexdigest() != expected:
            raise ValueError("Reference hash mismatch: " + name)
    if not metadata["converged"] or not manifest["convergence"]["point_passed"] or not manifest["convergence"]["temporal_passed"]:
        raise ValueError("Convergence criterion failed")
    for key in CORE:
        if manifest["units"][key] != metadata["units"][key]:
            raise ValueError("Units mismatch: " + key)
    result = {"archive_sha256": manifest["archive"]["sha256"], "rtol": 1e-8, "atol": 0,
              "scope": "Six phase W/U/H profiles directly stored in original MATLAB archive; no method reconstruction",
              "effective_inputs": compare_effective_inputs(reference, manifest, metadata),
              "physical": compare(reference / "results.npz", native / "results.npz", CORE),
              "initialization": compare(reference / "initialization.npz", native / "initialization.npz", CORE),
              "archived_physical_checks": manifest["physical_checks"], "reference_convergence": manifest["convergence"],
              "object_link_checks": manifest["object_link_checks"], "experimental_validation": "not performed"}
    mix_keys = tuple(p + k for p in ("", "liquid.", "vapor.") for k in ("W", "U", "H"))
    result["precursor_physical"] = compare(reference / "mixture/results.npz", native / "mixture/results.npz", mix_keys)
    result["precursor_initialization"] = compare(reference / "mixture/initialization.npz", native / "mixture/initialization.npz", mix_keys)
    result["all_core_comparisons_passed"] = all(result[key]["all_passed"] for key in ("physical", "initialization", "precursor_physical", "precursor_initialization"))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("native", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    report = audit(args.reference, args.native)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"all_core_comparisons_passed": report["all_core_comparisons_passed"], "output": str(args.output)}, indent=2))
    raise SystemExit(0 if report["all_core_comparisons_passed"] else 2)
