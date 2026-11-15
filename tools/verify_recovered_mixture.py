"""Compare an extracted original mixture archive with saved native results.

This compares a preserved MATLAB-produced archive, not a new MATLAB execution.
Core acceptance is exactly upstream's nine W/U/H profiles, rtol=1e-8, atol=0.
No interpolation, fitting, reference rewriting or tolerance option is provided.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

CORE = tuple(p + k for p in ("", "liquid.", "vapor.") for k in ("W", "U", "H"))
RTOL = 1e-8
ARCHIVE_SHA256 = "43311c4c2ec3440cc3366f94df1216b425d4270268887b7fb7bf921c0fb9ccb0"
UNITS = {"W": "kg/s", "U": "m/s", "H": "J/kg", "P": "Pa",
         "RHO": "kg/m^3", "X": "1", "XEQ": "1", "VF": "1", "UP": "m/s",
         "HFLUX": "W/m^2"}


def validate_reference(directory, manifest, native_meta):
    if manifest.get("schema") != "openstream-recovered-mcos-mixture-v1" or not manifest.get("complete"):
        raise ValueError("Incomplete or unsupported recovered reference")
    if manifest.get("framework") != "Mixture" or manifest.get("state") != "INITIALSTEPCONVERGED":
        raise ValueError("Reference is not a converged mixture archive")
    if manifest["archive"]["sha256"] != ARCHIVE_SHA256:
        raise ValueError("Reference is not the preserved approved mixture archive")
    archive = Path(manifest["archive"]["file"])
    if hashlib.sha256(archive.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Original archive hash has changed")
    for name in ("results.npz", "initialization.npz", "raw_arrays.npz", "object_graph.json"):
        if hashlib.sha256((directory / name).read_bytes()).hexdigest() != manifest["files"][name]:
            raise ValueError(f"Extracted reference hash mismatch: {name}")
    if native_meta.get("framework") != "Mixture" or not native_meta.get("converged"):
        raise ValueError("Native mixture run has not converged")
    for key in CORE:
        expected = UNITS[key.rsplit(".", 1)[-1]]
        if manifest["units"].get(key) != expected or native_meta["units"].get(key) != expected:
            raise ValueError(f"Unit mismatch for {key}")


def compare_effective_inputs(directory, manifest, native_meta):
    """Check saved inputs, explicitly disclosing harmless historical defaults."""
    ref = manifest["effective_inputs"]
    native = dict(native_meta["inputs"])
    if len(native["bc"]) != 1:
        raise ValueError("This archive contains one boundary-condition record")
    native["bc"] = native["bc"][0]
    differences, count = [], 0
    for group in ("model", "options", "geometry", "bc"):
        if set(ref[group]) != set(native[group]):
            raise ValueError(f"Effective input keys differ for {group}")
        for key, value in ref[group].items():
            if key == "CBTMULT":
                continue
            a, b = np.asarray(value).ravel(order="F"), np.asarray(native[group][key]).ravel(order="F")
            count += 1
            path = group + "." + key
            if a.shape == b.shape and np.array_equal(a, b):
                continue
            if a.shape == b.shape and a.dtype.kind in "biuf" and b.dtype.kind in "biuf":
                if np.allclose(a, b, atol=0, rtol=16*np.finfo(float).eps, equal_nan=True):
                    continue
            explanation = None
            if path in {"model.KLOC", "model.KLOSS", "model.KBLOCKRATIO", "model.KTUNING"}:
                if a.shape == (2,) and b.shape == (1,) and np.all(a == 0) and np.all(b == 0):
                    explanation = "Archived duplicate zero default; pinned source single zero. Local loss is zero; annular parameters inactive."
            elif path in {"options.AXIALINTERP", "options.TIMEINTERP"} and a.shape == b.shape:
                if np.array_equal(np.char.upper(a.astype(str)), np.char.upper(b.astype(str))):
                    explanation = "Case-only interpolation spelling; identical selected method."
            if explanation is None:
                raise ValueError(f"Unexplained effective input mismatch: {path}: {a} != {b}")
            differences.append({"path": path, "archived": a.tolist(), "native": b.tolist(), "explanation": explanation})
    graph = json.loads((directory / "object_graph.json").read_text(encoding="utf-8"))
    function_path = "solver.properties.inputSet.properties.model.properties.CBTMULT[2,1][1,1].function_handle[1,1].function"
    functions = [record.get("values") for record in graph if record["path"] == function_path]
    if functions != [["sf%0@(z)1"]] or not np.all(np.asarray(native_meta["function_samples"]["model.CBTMULT"]) == 1):
        raise ValueError("CBTMULT constant-one function has not been established")
    return {"passed": True, "compared_inputs": count, "disclosed_differences": differences,
            "CBTMULT": "Serialized @(z)1 recognized without execution; native sampled values equal one; CBT=NONE.",
            "orientation": "MATLAB input row/column vectors converted explicitly, preserving element order. Field axes are never squeezed."}


def convergence(reference_file, options):
    with np.load(reference_file, allow_pickle=False) as ref:
        point = {key: float(np.max(ref["ITR." + key][-1, 1:]))
                 for key in ("DW", "DP", "DH", "DWV", "DHV")}
        temporal = {key: float(np.max(np.abs(ref[key][-1] - ref[key][-2])))
                    for key in ("W", "P", "H", "MRM.WV", "MRM.HV")}
        thresholds = {"DW": "ERRORW", "DP": "ERRORP", "DH": "ERRORH", "DWV": "ERRORW", "DHV": "ERRORH"}
        time_thresholds = {"W": "SSCONVW", "P": "SSCONVP", "H": "SSCONVH", "MRM.WV": "SSCONVW", "MRM.HV": "SSCONVH"}
        return {"point_maxima": point, "temporal_maxima": temporal,
                "point_passed": all(np.isfinite(v) and 0 <= v < options[thresholds[k]] for k, v in point.items()),
                "temporal_passed": all(np.isfinite(v) and 0 <= v < options[time_thresholds[k]] for k, v in temporal.items()),
                "max_iterations": int(np.max(ref["ITR.N"][-1])),
                "states": len(ref["TIME"]), "last_pseudo_time_s": float(ref["TIME"][-1])}


def difference(reference, native, unit="1"):
    """Reference-relative error with exact zeros, finite data and equal shapes."""
    reference, native = np.asarray(reference), np.asarray(native)
    if reference.shape != native.shape:
        raise ValueError(f"Array shapes differ: {reference.shape} != {native.shape}")
    if reference.size == 0 or not np.all(np.isfinite(reference)) or not np.all(np.isfinite(native)):
        raise ValueError("Numerical comparison requires nonempty finite arrays")
    delta = np.abs(native - reference)
    nz = reference != 0
    rel = np.divide(delta, np.abs(reference), out=np.zeros_like(delta, dtype=float), where=nz)
    zero_fail = (~nz) & (delta != 0)
    return {"passed": bool(np.all(delta <= RTOL * np.abs(reference))),
            "shape": list(reference.shape), "unit": unit,
            "max_absolute_error": float(np.max(delta)),
            "max_relative_error_nonzero": float(np.max(rel)),
            "reference_zero_count": int(np.count_nonzero(~nz)),
            "nonmatching_reference_zeros": int(np.count_nonzero(zero_fail)),
            "failed_values": int(np.count_nonzero(delta > RTOL * np.abs(reference))),
            "max_absolute_error_index": list(np.unravel_index(int(np.argmax(delta)), delta.shape))}


def compare_arrays(reference_file, native_file, units=None):
    with np.load(reference_file, allow_pickle=False) as ref, np.load(native_file, allow_pickle=False) as native:
        for coordinate in ("Z", "TIME"):
            if ref[coordinate].ndim != 1 or ref[coordinate].shape != native[coordinate].shape:
                raise ValueError(f"{coordinate} axes differ")
            if not np.all(np.isfinite(ref[coordinate])) or not np.all(np.isfinite(native[coordinate])):
                raise ValueError(f"{coordinate} has nonfinite values")
            if not np.allclose(ref[coordinate], native[coordinate], rtol=0, atol=1e-12):
                raise ValueError(f"{coordinate} differs; no resampling is allowed")
        expected_shape = (len(ref["TIME"]), len(ref["Z"]))
        rows = {}
        for key in CORE:
            if key not in ref or key not in native:
                raise ValueError(f"Missing required profile {key}")
            if ref[key].shape != expected_shape or native[key].shape != expected_shape:
                raise ValueError(f"Invalid time/node layout for {key}")
            rows[key] = difference(ref[key], native[key], UNITS[key.rsplit(".", 1)[-1]])
        supplemental = {}
        for key in sorted(set(ref.files) & set(native.files) - set(CORE) - {"Z", "TIME"}):
            # Stored diagnostic counters and tiny residuals are reported using
            # the same strict policy; their failure cannot be silently hidden.
            supplemental[key] = difference(ref[key], native[key], (units or UNITS).get(key, "see extraction manifest"))
        return {"core": rows, "core_passed": all(r["passed"] for r in rows.values()),
                "supplemental": supplemental,
                "supplemental_failures": [k for k, r in supplemental.items() if not r["passed"]]}


def plot_overlay(reference_file, native_file, report, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with np.load(reference_file, allow_pickle=False) as ref, np.load(native_file, allow_pickle=False) as native:
        with plt.rc_context({"font.size": 10, "axes.grid": True, "grid.alpha": .2}):
            fig, axes = plt.subplots(3, 3, figsize=(13.5, 9.2), sharey="col", layout="constrained")
            for row, phase in enumerate(("", "liquid.", "vapor.")):
                for col, key in enumerate(("W", "U", "H")):
                    name, ax = phase + key, axes[row, col]
                    scale = 1e-6 if key == "H" else 1
                    unit = "MJ/kg" if key == "H" else UNITS[key]
                    ax.plot(native["Z"], native[name][0] * scale, color="#1261a0", lw=1.8, label="Native Python")
                    ax.plot(ref["Z"], ref[name][0] * scale, "o", color="#c45425", mfc="none", ms=4,
                            markevery=5, label="MATLAB archive")
                    ax.set(xlabel="Axial position [m]", ylabel=f"{key} [{unit}]", xlim=(0, float(ref["Z"][-1])))
                    label = phase[:-1].capitalize() if phase else "Mixture"
                    metric = report["physical"]["core"][name]
                    ax.set_title(f"{label}: {dict(W='mass flow', U='velocity', H='enthalpy')[key]}")
                    ax.text(.03, .96, f"Max relative error: {metric['max_relative_error_nonzero']:.2e}",
                            transform=ax.transAxes, va="top", fontsize=8.5,
                            bbox={"facecolor": "white", "alpha": .85, "edgecolor": "none"})
                    if row == 0 and col == 0:
                        ax.legend(loc="lower left", fontsize=8)
            for col in (0, 1):
                axes[0, col].set_ylim(bottom=0)
            status = "PASS" if report["physical"]["core_passed"] else "FAIL"
            fig.suptitle(f"OpenSTREAM mixture baseline: Python vs original MATLAB archive — {status}\n"
                         "TUTORIAL1 · 6 MPa · 0.07 kg/s · 87.5 kW · 100 cells · relative tolerance 1e−8, absolute tolerance 0",
                         fontsize=13)
            fig.supxlabel("Reference symbols every fifth node; comparison uses all 101 nodes. "
                          "Velocity and phase profiles use upstream methods on recovered state.\n"
                          "Agreement with this archive does not establish experimental validation.", fontsize=9)
            fig.savefig(output / "mixture_baseline_overlay.png", dpi=170)
            fig.savefig(output / "mixture_baseline_overlay.svg")
            plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("native", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    manifest = json.loads((args.reference / "manifest.json").read_text(encoding="utf-8"))
    native_meta = json.loads((args.native / "metadata.json").read_text(encoding="utf-8"))
    validate_reference(args.reference, manifest, native_meta)
    report = {"schema": "openstream-recovered-mixture-comparison-v1",
              "scope": "Stored approved MATLAB mixture archive; no MATLAB execution",
              "rtol": RTOL, "atol": 0.0,
              "reference_manifest": manifest,
              "native_source_sha256": native_meta["native_source_sha256"],
              "native_versions": native_meta["versions"],
              "comparison_tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "effective_input_comparison": compare_effective_inputs(args.reference, manifest, native_meta),
              "physical": compare_arrays(args.reference / "results.npz", args.native / "results.npz", manifest["units"]),
              "initialization": compare_arrays(args.reference / "initialization.npz", args.native / "initialization.npz", manifest["units"]),
              "native_balances": native_meta["balances"],
              "reference_convergence": convergence(args.reference / "initialization.npz", native_meta["inputs"]["options"]),
              "producer_runtime_fully_identified": False,
              "experimental_validation": "not performed"}
    report["upstream_regression_passed"] = (report["physical"]["core_passed"]
                                            and report["reference_convergence"]["point_passed"]
                                            and report["reference_convergence"]["temporal_passed"])
    report["initialization_core_passed"] = report["initialization"]["core_passed"]
    report["input_files"] = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                              for directory in (args.reference, args.native)
                              for p in (directory / "results.npz", directory / "initialization.npz")}
    args.output.mkdir(parents=True)
    (args.output / "comparison.json").write_text(json.dumps(report, indent=2, default=int) + "\n", encoding="utf-8")
    plot_overlay(args.reference / "results.npz", args.native / "results.npz", report, args.output)
    print(json.dumps({"upstream_regression_passed": report["upstream_regression_passed"],
                      "initialization_core_passed": report["initialization_core_passed"],
                      "physical_supplemental_failures": report["physical"]["supplemental_failures"],
                      "initialization_supplemental_failures": report["initialization"]["supplemental_failures"],
                      "output": str(args.output.resolve())}, indent=2))
    return 0 if report["upstream_regression_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
