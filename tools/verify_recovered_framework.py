"""Strict comparison of the recovered TwoFluid/ThreeField/FourField baselines.

This is verification tooling, independent of the numerical implementation.
Original W/U/H tolerance: relative 1e-8, absolute zero, with exact reference zeros.
FourField's actual base and frequency extend the upstream regression, whose
basefilm spelling skips the base. Physical defects remain separate findings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from verify_recovered_mixture import difference, compare_effective_inputs, compare_arrays as mixture_compare, convergence as mixture_convergence

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {"TwoFluid": ("liquid", "vapor"), "ThreeField": ("film", "drop"),
          "FourField": ("film", "drop", "film.wave")}
EXTRA = {"FourField": ("film.base.W", "film.base.U", "film.base.H", "film.wave.FREQUENCY")}
UNITS = {"W": "kg/s", "U": "m/s", "H": "J/kg", "FREQUENCY": "Hz"}
ITR_UNITS = {"N": "1", "DW": "kg/s", "DU": "m/s", "DH": "J/kg", "DWL": "kg/s/m", "DF": "Hz", "DFW": "Hz"}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate(reference, native, manifest, metadata):
    framework = manifest["framework"].removesuffix("Solver")
    if framework not in FIELDS or not manifest.get("complete"):
        raise ValueError("Incomplete or unsupported recovered reference")
    if manifest.get("schema") not in {"openstream-recovered-twofluid-v1", "openstream-recovered-mcos-annular-v1"}:
        raise ValueError("Unknown recovery schema")
    if metadata.get("framework", "").removesuffix("Solver") != framework:
        raise ValueError("Framework mismatch")
    original = json.loads((ROOT / "docs/reference_archive_inspection.json").read_text())
    expected = next(r["sha256"] for r in original["records"] if Path(r["file"]).name == f"tutorial1_{framework}Solver.mat")
    if manifest["archive"]["sha256"] != expected or digest(manifest["archive"]["file"]) != expected:
        raise ValueError("Original archive hash mismatch")
    for name, expected_hash in manifest["files"].items():
        path = (reference / name).resolve()
        if not path.is_relative_to(reference.resolve()) or digest(path) != expected_hash:
            raise ValueError(f"Recovered file hash mismatch: {name}")
    for required in ("results.npz", "initialization.npz", "raw_arrays.npz", "object_graph.json",
                     "mixture/results.npz", "mixture/initialization.npz", "mixture/manifest.json"):
        if required not in manifest["files"]:
            raise ValueError(f"Missing integrity record: {required}")
    if manifest["state"] not in ("INITIALSTEPCONVERGED", "SOLVEDCONVERGED") or not metadata["converged"]:
        raise ValueError("Reference or native solver is not converged")
    if metadata["upstream_commit"] != "a614c7173822a93c1e64ac28d1541cbac028cbd8":
        raise ValueError("Native source target differs")
    if metadata.get("wrapper_commit") != "a7c40902ff66faf6ed668986398bb1b9faa16e13":
        raise ValueError("Native property wrapper source target differs")
    if metadata.get("constants", {}).get("model.G") != 9.81:
        raise ValueError("Gravity differs from pinned source constant")
    if not metadata.get("source_files"):
        raise ValueError("Native input provenance is missing")
    for item in metadata["source_files"]:
        path = (native / item["copy"]).resolve()
        if not path.is_relative_to(native.resolve()) or digest(path) != item["sha256"]:
            raise ValueError("Native copied input hash/path mismatch")
    required_keys = [p + "." + k for p in FIELDS[framework] for k in ("W", "U", "H")] + list(EXTRA.get(framework, ()))
    for key in required_keys:
        unit = UNITS[key.rsplit(".", 1)[-1]]
        if manifest["units"].get(key) != unit or metadata["units"].get(key) != unit:
            raise ValueError(f"Unit mismatch: {key}")
    for key, unit in manifest["units"].items():
        if key in metadata["units"]:
            expected = ITR_UNITS.get(key.rsplit(".", 1)[-1]) if ".ITR." in key else {"Z": "m", "TIME": "s"}.get(key, UNITS.get(key.rsplit(".", 1)[-1]))
            if unit != metadata["units"][key] or (expected is not None and unit != expected):
                raise ValueError(f"Diagnostic/convergence unit mismatch: {key}")
    for filename in ("results.npz", "initialization.npz"):
        with np.load(reference / filename) as a, np.load(native / filename) as b:
            for key in set(a.files) & set(b.files):
                if key not in manifest["units"] or key not in metadata["units"]:
                    raise ValueError(f"Missing compared unit: {key}")
                if manifest["units"][key] != metadata["units"][key] or manifest["units"][key] == "UNRESOLVED":
                    raise ValueError(f"Compared unit mismatch: {key}")
    inputs = compare_effective_inputs(reference, manifest, metadata)
    for item in inputs["disclosed_differences"]:
        if item["path"] in ("model.KBLOCKRATIO", "model.KTUNING"):
            if manifest["effective_inputs"]["model"]["DEPENHANCEMENT"] != "NONE":
                raise ValueError("Historical zero defaults require inactive deposition enhancement")
            item["explanation"] = "Archived duplicate zero versus single zero; deposition enhancement is NONE in both."
    return framework, inputs


def compare_phase(ref_file, native_file, framework, units, presence=None):
    keys = [p + "." + k for p in FIELDS[framework] for k in ("W", "U", "H")]
    expanded = list(EXTRA.get(framework, ()))
    with np.load(ref_file, allow_pickle=False) as ref, np.load(native_file, allow_pickle=False) as native:
        for axis in ("Z", "TIME"):
            if ref[axis].ndim != 1 or ref[axis].shape != native[axis].shape:
                raise ValueError(f"{axis} layout mismatch")
            if not np.isfinite(ref[axis]).all() or not np.isfinite(native[axis]).all() or not np.allclose(ref[axis], native[axis], rtol=0, atol=1e-12):
                raise ValueError(f"{axis} mismatch; interpolation is forbidden")
        expected = (len(ref["TIME"]), len(ref["Z"]))
        groups = {"core": {}, "expanded": {}, "diagnostics": {}}
        for group, names in (("core", keys), ("expanded", expanded)):
            for key in names:
                if key not in ref or key not in native:
                    raise ValueError(f"Missing required {key}")
                shape = expected + ((1,) if key.startswith("film.") else ())
                if ref[key].shape != shape or native[key].shape != shape:
                    raise ValueError(f"Wrong node/wall dimensions: {key}")
                groups[group][key] = difference(ref[key], native[key], units[key])
        for key in sorted(set(ref.files) & set(native.files) - set(keys) - set(expanded) - {"Z", "TIME"}):
            a, b = ref[key], native[key]
            if a.shape != b.shape:
                raise ValueError(f"Diagnostic dimensions differ: {key}")
            finite = np.isfinite(a) & np.isfinite(b)
            if np.isinf(a).any() or np.isinf(b).any():
                raise ValueError(f"Infinite diagnostic is not an absent iteration field: {key}")
            same_missing = np.array_equal(np.isnan(a), np.isnan(b))
            if finite.all():
                row = difference(a, b, units[key])
            else:
                flags = np.asarray((presence or {}).get(key, []))
                if flags.dtype != np.dtype(bool) or flags.shape != (len(a),) or ".ITR." not in key:
                    raise ValueError(f"Undeclared missing diagnostic values: {key}")
                expected_missing = np.broadcast_to((~flags).reshape((-1,) + (1,)*(a.ndim-1)), a.shape)
                if not same_missing or not np.array_equal(np.isnan(a), expected_missing):
                    raise ValueError(f"Missing diagnostic layout differs from archived presence records: {key}")
                row = difference(a[finite], b[finite], units[key]) if finite.any() else {"passed": True, "unit": units[key]}
                row.update({"shape": list(a.shape), "missing_value_patterns_equal": same_missing,
                            "undefined_value_count": int(np.count_nonzero(~finite)),
                            "note": "Absent diagnostic fields are not numeric observations; only finite entries compared."})
                row["passed"] = bool(row["passed"] and same_missing)
            groups["diagnostics"][key] = row
        groups["core_passed"] = all(r["passed"] for r in groups["core"].values())
        groups["expanded_passed"] = all(r["passed"] for r in groups["expanded"].values())
        groups["diagnostic_failures"] = [k for k, r in groups["diagnostics"].items() if not r["passed"]]
        return groups


def check_convergence(file, framework, inputs):
    options = inputs["options"]
    perim = np.asarray(inputs["geometry"]["PERIM"]).reshape(-1)
    point, temporal = {}, {}
    def record(value, threshold, unit):
        value = np.asarray(value)
        if not np.isfinite(value).all() or np.any(value < 0):
            raise ValueError("Invalid convergence increments")
        maximum = float(np.max(value))
        return {"maximum": maximum, "threshold": float(threshold), "unit": unit, "passed": maximum < threshold}
    with np.load(file, allow_pickle=False) as a:
        if len(a["TIME"]) < 2:
            raise ValueError("Insufficient initialization history")
        if framework == "TwoFluid":
            for phase in ("liquid", "vapor"):
                for key in ("W", "U", "H"):
                    point[phase + ".D" + key] = record(a[f"{phase}.ITR.D{key}"][-1], options["ERROR" + key], UNITS[key])
                    temporal[phase + "." + key] = record(abs(a[phase + "." + key][-1] - a[phase + "." + key][-2]), options["SSCONV" + key], UNITS[key])
        else:
            for film in (("film",) if framework == "ThreeField" else ("film.base", "film.wave")):
                for key, opt, unit in (("DWL", "ERRORWF", "kg/s/m"), ("DU", "ERRORUF", "m/s")):
                    point[film + "." + key] = record(a[film + ".ITR." + key][-1], options[opt], unit)
                temporal[film + ".WL"] = record(abs(a[film + ".W"][-1] / perim - a[film + ".W"][-2] / perim), options["SSCONVWF"], "kg/s/m")
                temporal[film + ".U"] = record(abs(a[film + ".U"][-1] - a[film + ".U"][-2]), options["SSCONVUF"], "m/s")
            point["drop.DU"] = record(a["drop.ITR.DU"][-1], options["ERRORUD"], "m/s")
            temporal["drop.U"] = record(abs(a["drop.U"][-1] - a["drop.U"][-2]), options["SSCONVUD"], "m/s")
            if framework == "FourField":
                point["film.wave.DF"] = record(a["film.wave.ITR.DF"][-1], options["ERRORFW"], "Hz")
        result = {"point": point, "temporal": temporal,
                  "point_passed": all(r["passed"] for r in point.values()),
                  "temporal_passed": all(r["passed"] for r in temporal.values()),
                  "states": len(a["TIME"]), "last_pseudo_time_s": float(a["TIME"][-1])}
        if framework == "FourField":
            result["additional_frequency_stopping_check"] = record(abs(a["film.wave.FREQUENCY"][-1] - a["film.wave.FREQUENCY"][-2]), options["SSCONVFW"], "Hz")
            result["frequency_note"] = "Upstream temporal stopping omits this criterion; reported separately."
        return result


def plot_comparison(reference, native, framework, report, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fields = list(FIELDS[framework])
    if framework == "FourField": fields.insert(2, "film.base")
    with np.load(reference / "results.npz") as a, np.load(native / "results.npz") as b:
        with plt.rc_context({"font.size": 10, "axes.grid": True, "grid.alpha": .2}):
            fig, axes = plt.subplots(len(fields), 3, figsize=(13.5, 2.8*len(fields)+1), layout="constrained", sharey="col")
            for row, field in enumerate(fields):
                for col, key in enumerate(("W", "U", "H")):
                    name, ax = field + "." + key, axes[row, col]
                    scale = 1e-6 if key == "H" else 1
                    ax.plot(a["Z"], b[name][0].reshape(len(a["Z"]), -1)*scale, color="#1261a0", label="Native Python")
                    ax.plot(a["Z"], a[name][0].reshape(len(a["Z"]), -1)*scale, "o", color="#c45425", mfc="none", ms=4, markevery=5, label="MATLAB archive")
                    metric = report["physical"]["core"].get(name, report["physical"]["expanded"].get(name))
                    ax.set(title=f"{field}: {key} | max relative error {metric['max_relative_error_nonzero']:.2e}", xlabel="Axial position [m]", ylabel="H [MJ/kg]" if key == "H" else f"{key} [{UNITS[key]}]", xlim=(a["Z"][0], a["Z"][-1]))
            axes[0, 0].legend(fontsize=8)
            for col in (0, 1): axes[0, col].set_ylim(bottom=0)
            axes[0, 2].ticklabel_format(axis="y", style="plain", useOffset=False)
            # Display nearly constant saturated H on a meaningful scale.
            hvals = np.concatenate([a[f + ".H"].ravel()*1e-6 for f in fields])
            if np.ptp(hvals) < 1e-6: axes[0, 2].set_ylim(0.95*hvals.min(), 1.05*hvals.max())
            status = "PASS" if report["upstream_regression_passed"] else "FAIL"
            fig.suptitle(f"OpenSTREAM {framework} baseline — archived W/U/H comparison {status}\n"
                         "TUTORIAL1 · 6 MPa · 0.07 kg/s · 87.5 kW · relative tolerance 1e−8; absolute tolerance 0", fontsize=13)
            fig.supxlabel("Agreement with archived calculations is separate from physical consistency; reported area-closure failures remain.\n"
                          "All 101 nodes compared. Reference symbols shown every fifth node. No experimental validation claimed.", fontsize=9)
            fig.savefig(output / "baseline_overlay.png", dpi=170)
            fig.savefig(output / "baseline_overlay.svg")
            plt.close(fig)
            if framework == "FourField":
                fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
                ax.plot(a["Z"], b["film.wave.FREQUENCY"][0], label="Native Python")
                ax.plot(a["Z"], a["film.wave.FREQUENCY"][0], "o", mfc="none", markevery=5, label="MATLAB archive")
                ax.set(xlabel="Axial position [m]", ylabel="Wave frequency [Hz]", title="Four-field wave frequency: supplementary reference comparison")
                ax.legend(); fig.savefig(output / "wave_frequency_overlay.png", dpi=170); plt.close(fig)


def compare(reference, native):
    reference, native = Path(reference), Path(native)
    manifest = json.loads((reference / "manifest.json").read_text(encoding="utf-8"))
    metadata = json.loads((native / "metadata.json").read_text(encoding="utf-8"))
    framework, inputs = validate(reference, native, manifest, metadata)
    report = {"schema": "openstream-recovered-framework-comparison-v1", "framework": framework,
              "scope": "Preserved MATLAB-produced TUTORIAL1 archive, not a fresh MATLAB execution",
              "rtol": 1e-8, "atol": 0, "reference_manifest": manifest,
              "effective_input_comparison": inputs,
              "native_source_sha256": metadata["native_source_sha256"], "native_versions": metadata["versions"],
              "comparison_tool_sha256": digest(__file__),
              "physical": compare_phase(reference / "results.npz", native / "results.npz", framework, manifest["units"], manifest.get("missing_iteration_fields", {}).get("physical")),
              "initialization": compare_phase(reference / "initialization.npz", native / "initialization.npz", framework, manifest["units"], manifest.get("missing_iteration_fields", {}).get("initialization")),
              "reference_convergence": check_convergence(reference / "initialization.npz", framework, metadata["inputs"]),
              "native_convergence": check_convergence(native / "initialization.npz", framework, metadata["inputs"]),
              "precursor": {phase: mixture_compare(reference / "mixture" / file, native / "mixture" / file)
                            for phase, file in (("physical", "results.npz"), ("initialization", "initialization.npz"))},
              "native_physical_diagnostics": metadata.get("physical_diagnostics"),
              "producer_runtime_fully_identified": False, "experimental_validation": "not performed"}
    precursor_manifest = json.loads((reference / "mixture/manifest.json").read_text())
    precursor_metadata = json.loads((native / "mixture/metadata.json").read_text())
    if precursor_manifest["state"] != "INITIALSTEPCONVERGED" or not precursor_metadata["converged"]:
        raise ValueError("Precursor state is not converged")
    for key, unit in precursor_manifest["units"].items():
        if key not in precursor_metadata["units"] or unit != precursor_metadata["units"][key]:
            raise ValueError(f"Precursor unit mismatch: {key}")
    report["precursor_inputs"] = compare_effective_inputs(reference, {**manifest, "effective_inputs": precursor_manifest["effective_inputs"]}, precursor_metadata)
    report["precursor_convergence"] = {
        "reference": mixture_convergence(reference / "mixture/initialization.npz", precursor_metadata["inputs"]["options"]),
        "native": mixture_convergence(native / "mixture/initialization.npz", precursor_metadata["inputs"]["options"])}
    report["upstream_regression_passed"] = (report["physical"]["core_passed"]
        and all(report[s][k] for s in ("reference_convergence", "native_convergence") for k in ("point_passed", "temporal_passed"))
        and all(r["core_passed"] for r in report["precursor"].values())
        and all(r[k] for r in report["precursor_convergence"].values() for k in ("point_passed", "temporal_passed")))
    report["expanded_profiles_passed"] = report["physical"]["expanded_passed"] and report["initialization"]["expanded_passed"]
    report["initialization_core_passed"] = report["initialization"]["core_passed"]
    report["input_files"] = {str(p.resolve()): digest(p) for d in (reference, native) for p in (d / "results.npz", d / "initialization.npz")}
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("native", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    report = compare(args.reference, args.native)
    args.output.mkdir(parents=True)
    (args.output / "comparison.json").write_text(json.dumps(report, indent=2, default=int)+"\n", encoding="utf-8")
    plot_comparison(args.reference, args.native, report["framework"], report, args.output)
    print(json.dumps({k: report[k] for k in ("framework", "upstream_regression_passed", "initialization_core_passed", "expanded_profiles_passed")}, indent=2))
    raise SystemExit(0 if report["upstream_regression_passed"] and report["expanded_profiles_passed"] and report["initialization_core_passed"] else 2)
