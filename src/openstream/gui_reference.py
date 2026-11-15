"""Portable, immutable-value subsets of the recovered MATLAB steady baselines.

This is an archived profile comparison, not a new MATLAB execution or physical
validation. Inputs must have been checked against the baseline by the caller.
The solver never reads these arrays; they are used only after saving its output.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

RTOL = 1e-8
ATOL = 0.0
COORDINATE_ATOL = 1e-12
BUNDLE = Path(__file__).parent / "data" / "gui_baselines"
FRAMEWORKS = ("Mixture", "TwoFluid", "ThreeField", "FourField")
ARCHIVE_HASHES = {
    "Mixture": "43311c4c2ec3440cc3366f94df1216b425d4270268887b7fb7bf921c0fb9ccb0",
    "TwoFluid": "40f0c9a8f080d6ffe3887947dc5794eb756b5fa0e2ce650ff37a88003e69798d",
    "ThreeField": "eabaef27d5b94dce4506783675d90563def40db1a491b8a16b982b9de070e884",
    "FourField": "fd28edab74cad654721572c4644461dc20fef27ed4a3d617458b9717e13eacf1",
}
CORE = {
    "Mixture": tuple(p + k for p in ("", "liquid.", "vapor.") for k in ("W", "U", "H")),
    "TwoFluid": tuple(p + "." + k for p in ("liquid", "vapor") for k in ("W", "U", "H")),
    "ThreeField": tuple(p + "." + k for p in ("film", "drop") for k in ("W", "U", "H")),
    "FourField": tuple(p + "." + k for p in ("film", "drop", "film.wave") for k in ("W", "U", "H")),
}
EXTRA = {"FourField": ("film.base.W", "film.base.U", "film.base.H", "film.wave.FREQUENCY")}
UNITS = {"W": "kg/s", "U": "m/s", "H": "J/kg", "FREQUENCY": "Hz", "Z": "m", "TIME": "s"}
SCOPE = ("Archived TUTORIAL1 steady W/U/H profiles and their initialization histories; "
         "FourField additionally includes actual base-film W/U/H and wave frequency. "
         "Supplementary diagnostics and mixture precursor histories are outside this GUI comparison.")


def _framework(framework):
    for name in FRAMEWORKS:
        if str(framework).lower() == name.lower():
            return name
    raise ValueError(f"Unknown framework: {framework}")


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _bundle(framework, dataset):
    framework = _framework(framework)
    if dataset not in ("physical", "initialization"):
        raise ValueError("dataset must be physical or initialization")
    manifest = json.loads((BUNDLE / f"{framework}.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "openstream-gui-reference-v1" or manifest["framework"] != framework:
        raise ValueError("Invalid GUI reference manifest")
    if manifest["archive"]["sha256"] != ARCHIVE_HASHES[framework]:
        raise ValueError("Unknown MATLAB archive fingerprint")
    filename = f"{framework}.{dataset}.npz"
    path = BUNDLE / filename
    if _sha(path) != manifest["files"][filename]:
        raise ValueError("Bundled reference fingerprint differs")
    with np.load(path, allow_pickle=False) as saved:
        arrays = {key: saved[key].copy() for key in saved.files}
    return framework, manifest, arrays


def load_reference(framework, dataset="physical"):
    """Return read-only source data as JSON-compatible lists for plot overlays."""
    framework, manifest, arrays = _bundle(framework, dataset)
    return {"z": arrays["Z"].tolist(), "time": arrays["TIME"].tolist(),
            "fields": {key: {"values": arrays[key].tolist(), "unit": manifest["units"][key],
                              "units": manifest["units"][key]}
                       for key in (*CORE[framework], *EXTRA.get(framework, ()))},
            "provenance": {"archive": manifest["archive"], "scope": SCOPE,
                           "producer_metadata": manifest["producer_metadata"]}}


def _difference(reference, native, unit):
    """Never broadcast, resample, omit NaNs, or soften a zero reference value."""
    if reference.shape != native.shape:
        raise ValueError(f"Shape mismatch: expected {reference.shape}, received {native.shape}")
    if not reference.size or not np.isfinite(reference).all() or not np.isfinite(native).all():
        raise ValueError("Compared profiles must be nonempty and finite")
    delta = np.abs(native - reference)
    allowed = RTOL * np.abs(reference)
    nonzero = reference != 0
    relative = np.divide(delta, np.abs(reference), out=np.zeros_like(delta, dtype=float), where=nonzero)
    return {"passed": bool(np.all(delta <= allowed)), "unit": unit, "shape": list(reference.shape),
            "max_absolute_error": float(np.max(delta)),
            "max_relative_error": float(np.max(relative)),
            "nonmatching_reference_zeros": int(np.count_nonzero((~nonzero) & (delta != 0))),
            "failed_values": int(np.count_nonzero(delta > allowed))}


def compare_reference(framework, output_directory):
    """Compare saved outputs with the matching archived baseline; return a report.

    Call only for a baseline-identical effective input set. Missing or invalid
    native files are a failed comparison, never silently skipped. Run metadata
    provides units and convergence; neither is inferred from profile agreement.
    """
    framework = _framework(framework)
    output_directory = Path(output_directory)
    report = {"status": "failed", "message": "Archived profile comparison failed.",
              "scope": SCOPE, "rtol": RTOL, "atol": ATOL,
              "coordinate_atol": COORDINATE_ATOL, "records": [],
              "max_relative_error": None, "experimental_validation": "not performed",
              "limitations": ["The archive producer's MATLAB, CoolProp and source versions are unknown.",
                              "Agreement does not establish physical consistency or full OpenSTREAM parity.",
                              "Supplementary iteration/diagnostic disagreements remain documented separately."]}
    try:
        metadata = json.loads((output_directory / "metadata.json").read_text(encoding="utf-8"))
        if metadata.get("framework", "").removesuffix("Solver") != framework:
            raise ValueError("Native framework differs from selected reference")
        if metadata.get("converged") is not True:
            raise ValueError("Native solver has not converged")
        for dataset, filename in (("physical", "results.npz"), ("initialization", "initialization.npz")):
            _, manifest, reference = _bundle(framework, dataset)
            report["archive"] = manifest["archive"]
            report["producer_metadata"] = manifest["producer_metadata"]
            with np.load(output_directory / filename, allow_pickle=False) as native:
                for axis in ("Z", "TIME"):
                    a, b = reference[axis], native[axis]
                    if a.ndim != 1 or a.shape != b.shape or not np.isfinite(a).all() or not np.isfinite(b).all():
                        raise ValueError(f"{dataset} {axis} dimensions or finite values differ")
                    if not np.allclose(a, b, atol=COORDINATE_ATOL, rtol=0):
                        raise ValueError(f"{dataset} {axis} differs; no interpolation is allowed")
                    if metadata["units"].get(axis) != UNITS[axis]:
                        raise ValueError(f"Native coordinate unit mismatch: {axis}")
                for key in (*CORE[framework], *EXTRA.get(framework, ())):
                    if key not in native:
                        raise ValueError(f"Missing {dataset} profile {key}")
                    unit = UNITS[key.rsplit(".", 1)[-1]]
                    if metadata["units"].get(key) != unit or manifest["units"].get(key) != unit:
                        raise ValueError(f"Unit mismatch for {key}")
                    expected_shape = (len(reference["TIME"]), len(reference["Z"]))
                    if key.startswith("film."):
                        expected_shape += (1,)
                    if reference[key].shape != expected_shape:
                        raise ValueError(f"Unexpected reference dimensions for {key}")
                    row = _difference(reference[key], native[key], unit)
                    row.update({"dataset": dataset, "key": key,
                                "group": "core" if key in CORE[framework] else "expanded"})
                    report["records"].append(row)
        report["max_relative_error"] = max(row["max_relative_error"] for row in report["records"])
        if all(row["passed"] for row in report["records"]):
            report.update(status="passed", message="Archived steady and initialization profiles agree at rtol 1e-8, atol 0.")
        else:
            failed = [f"{r['dataset']}:{r['key']}" for r in report["records"] if not r["passed"]]
            report["message"] = "Archived profile comparison failed: " + ", ".join(failed)
    except (OSError, KeyError, ValueError, TypeError) as error:
        report["message"] = str(error)
    return report
