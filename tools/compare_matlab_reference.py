"""Compare native results.npz against export_matlab_reference.m output.

No fixture is generated or changed. Default core tolerances reproduce upstream
SolverIntegrationTest (relative 1e-8, absolute zero), including exact reference
zeros. A passing result is implementation agreement for these fields only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

import numpy as np

CORE = {
    "W": "kg/s", "U": "m/s", "H": "J/kg",
    "liquid.W": "kg/s", "liquid.U": "m/s", "liquid.H": "J/kg",
    "vapor.W": "kg/s", "vapor.U": "m/s", "vapor.H": "J/kg",
}
STRICT_RTOL = 1e-8
STRICT_ATOL = 0.0
UPSTREAM_COMMIT = "a614c7173822a93c1e64ac28d1541cbac028cbd8"
WRAPPER_COMMIT = "a7c40902ff66faf6ed668986398bb1b9faa16e13"
FRAMEWORKS = {
    "Mixture": (("mixture", "", False), ("mixture.liquid", "liquid", False), ("mixture.vapor", "vapor", False)),
    "TwoFluid": (("liquid", "liquid", False), ("vapor", "vapor", False)),
    "ThreeField": (("film", "film", True), ("drop", "drop", False)),
    "FourField": (("film", "film", True), ("drop", "drop", False),
                  ("film.base", "film.base", True), ("film.wave", "film.wave", True)),
}
POINT_ERRORS = {
    "Mixture": {"mixture": (("DW", "ERRORW", "kg/s"), ("DP", "ERRORP", "Pa"),
                            ("DH", "ERRORH", "J/kg"), ("DWV", "ERRORW", "kg/s"), ("DHV", "ERRORH", "J/kg"))},
    "TwoFluid": {name: (("DW", "ERRORW", "kg/s"), ("DU", "ERRORU", "m/s"), ("DH", "ERRORH", "J/kg"))
                 for name in ("liquid", "vapor")},
    "ThreeField": {"film": (("DWL", "ERRORWF", "kg/s/m"), ("DU", "ERRORUF", "m/s")),
                   "drop": (("DU", "ERRORUD", "m/s"),)},
    "FourField": {"film.base": (("DWL", "ERRORWF", "kg/s/m"), ("DU", "ERRORUF", "m/s")),
                  "film.wave": (("DWL", "ERRORWF", "kg/s/m"), ("DU", "ERRORUF", "m/s"), ("DF", "ERRORFW", "Hz")),
                  "drop": (("DU", "ERRORUD", "m/s"),)},
}


def reference_status(manifest, prefix):
    records = manifest.get("convergence_records", [])
    # MATLAB jsonencode represents a one-element struct array as an object.
    if isinstance(records, dict): records = [records]
    matches = [item for item in records if item["path"] == prefix]
    if len(matches) > 1:
        raise ValueError("Duplicate convergence records")
    return matches[0] if matches else manifest.get("convergence", {}).get(prefix.replace(".", "_"), {})


def load_export(directory: Path):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != "openstream-portable-reference-v1" or not manifest.get("complete"):
        raise ValueError("Reference export is incomplete or has an unsupported schema")
    arrays = {item["path"]: item for item in manifest["arrays"]}
    if len(arrays) != len(manifest["arrays"]):
        raise ValueError("Duplicate array paths in reference manifest")
    return manifest, arrays


def reference_array(directory: Path, record: dict):
    path = (directory / record["file"]).resolve()
    if not path.is_relative_to(directory.resolve()):
        raise ValueError("Reference array path escapes export directory")
    shape = tuple(record["shape"])
    if len(shape) < 2 or any(not isinstance(n, int) or isinstance(n, bool) or n < 0 for n in shape):
        raise ValueError("Invalid MATLAB array shape")
    size = int(np.prod(shape))
    if size == 0:
        if path.read_text(encoding="utf-8").strip():
            raise ValueError("Empty-array record has nonempty CSV data")
        return np.empty(shape)
    matrix = np.loadtxt(path, delimiter=",", ndmin=2)
    if matrix.shape != (shape[0], int(np.prod(shape[1:]))):
        raise ValueError("CSV dimensions do not match declared MATLAB layout")
    return matrix.reshape(shape, order="F")


def validate_provenance(reference_dir: Path, native_dir: Path, manifest: dict,
                        records: dict, metadata: dict, *, prefix="solver", framework="Mixture"):
    """Reject a same-mesh comparison when physics, inputs or provenance differ.

    Numeric input comparisons permit only 16 machine epsilons of relative
    rounding, with exact zeros. This accommodates arithmetic/JSON conversion
    of identical coefficients; it is not a solver acceptance tolerance.
    """
    schema = metadata.get("schema")
    native_framework = metadata.get("framework", "Mixture")
    aliases = {name+"Solver": name for name in FRAMEWORKS}
    native_framework = aliases.get(native_framework, native_framework)
    legacy = schema is None and framework != "Mixture" and native_framework == framework
    if schema != "openstream-python-v1" and not legacy:
        raise ValueError("Unsupported native metadata schema")
    if native_framework != framework:
        raise ValueError("Native/reference framework mismatch")
    original = manifest.get("upstream", {})
    commit = original.get("git_commit", "")
    if commit != UPSTREAM_COMMIT or commit != metadata.get("upstream_commit") or commit != original.get("expected_commit"):
        raise ValueError("Source commit is missing, mismatched or not the pinned reference")
    if original.get("git_status") != "":
        raise ValueError("Reference source has uncommitted changes or an unavailable cleanliness check")
    wrapper = metadata.get("wrapper_commit")
    module_lines = original.get("submodules", "").splitlines()
    wrapper_lines = [line.strip().split() for line in module_lines if "+CoolPropWrapper" in line]
    if (wrapper != WRAPPER_COMMIT or len(wrapper_lines) != 1 or wrapper_lines[0][0] != wrapper
            or wrapper != original.get("expected_wrapper_commit")):
        raise ValueError("CoolPropWrapper source commit is missing or mismatched")
    coolprop = manifest.get("runtime", {}).get("coolprop")
    if not isinstance(coolprop, str) or not coolprop or coolprop != metadata.get("versions", {}).get("CoolProp"):
        raise ValueError("CoolProp versions differ or are not recorded")
    if not metadata.get("converged"):
        raise ValueError("Native solver did not satisfy its convergence checks")
    reference_state = reference_status(manifest, prefix).get("state_code")
    if reference_state not in (1, 3):
        raise ValueError("MATLAB solver is not in a converged state")
    # The old MATLAB state can hide a point-convergence failure; check stored
    # point errors for the selected physical state in compare() below.
    source_files = metadata.get("source_files", [])
    if len(source_files) != len(manifest.get("input_files", [])) or not source_files:
        raise ValueError("Original input file provenance is incomplete")
    expected_hashes = {}
    for item in manifest["input_files"]:
        path = (reference_dir / "inputs" / item["name"]).resolve()
        if not path.is_relative_to(reference_dir.resolve()):
            raise ValueError("Reference input path escapes export directory")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != item["sha256"]:
            raise ValueError(f"Reference input hash mismatch: {item['name']}")
        expected_hashes[item["name"]] = digest
    for item in source_files:
        path = (native_dir / item["copy"]).resolve()
        if not path.is_relative_to(native_dir.resolve()):
            raise ValueError("Native input path escapes result directory")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        # The native output prepends 00-, 01-, ... to copied input filenames.
        name = Path(item["source"].replace("\\", "/")).name
        if digest != item["sha256"] or expected_hashes.pop(name, None) != digest:
            raise ValueError(f"Native/reference input hash mismatch: {name}")
    if expected_hashes:
        raise ValueError("Not every original input file was compared")

    text_items = manifest.get("text_records", [])
    if isinstance(text_items, dict): text_items = [text_items]
    text_records = {item["path"]: item["values"] for item in text_items}
    if len(text_records) != len(text_items):
        raise ValueError("Duplicate effective-input text paths")
    inputs = metadata.get("inputs", {})
    if not all(key in inputs for key in ("model", "options", "geometry", "bc")):
        raise ValueError("Effective native inputs are missing")
    count = 0

    solver_prefix = prefix

    def check_object(prefix, values):
        nonlocal count
        for key, value in values.items():
            path = prefix + "." + key
            if key == "CBTMULT":
                rec = records.get(solver_prefix + ".function_samples.model.CBTMULT")
                sampled = metadata.get("function_samples", {}).get("model.CBTMULT")
                if rec is None or sampled is None:
                    raise ValueError("CBTMULT function samples are missing; callable descriptions are insufficient")
                a = reference_array(reference_dir, rec).reshape(-1)
                b = np.asarray(sampled, dtype=float).reshape(-1)
            elif path in records:
                a = reference_array(reference_dir, records[path])
                b = np.asarray(value, dtype=float)
                if b.ndim < 2:
                    # MATLAB scalar/row/column input -> native scalar/vector.
                    if a.ndim != 2 or (a.size != 0 and min(a.shape) != 1):
                        raise ValueError(f"Input dimensional structure mismatch: {path}")
                    a, b = a.reshape(-1), b.reshape(-1)
            else:
                reference_text = text_records.get(prefix, {}).get(key)
                if not isinstance(value, str) or not isinstance(reference_text, str) or value.upper() != reference_text.upper():
                    raise ValueError(f"Effective text/enum input mismatch or missing reference: {path}")
                count += 1
                continue
            if a.shape != b.shape or not np.allclose(a, b, rtol=16*np.finfo(float).eps, atol=0, equal_nan=True):
                raise ValueError(f"Effective numeric input mismatch: {path}")
            count += 1

    for group in ("model", "options", "geometry"):
        check_object(prefix + ".inputs." + group, inputs[group])
    reference_bc = {key.split("]", 1)[0] for key in records if key.startswith(prefix + ".inputs.bc[")}
    if len(reference_bc) != len(inputs["bc"]):
        raise ValueError("Boundary-condition record count differs")
    for i, record in enumerate(inputs["bc"]):
        check_object(f"{prefix}.inputs.bc[{i}]", record)
    gravity = records.get(prefix + ".inputs.model.G")
    if gravity is None or metadata.get("constants", {}).get("model.G") is None:
        raise ValueError("Gravity constant provenance is missing")
    if float(reference_array(reference_dir, gravity).item()) != metadata["constants"]["model.G"]:
        raise ValueError("Gravity constant differs")
    return {"effective_inputs_checked": count, "source_commits_match": True,
            "native_schema": schema or "legacy-multifield-v0",
            "input_hashes_match": True, "coolprop_version_matches": True,
            "note": "For approved archives, runtime describes loading/export, not the unknown original producer."}


def field_path(prefix, field, phase, index):
    root, *nested = field.split(".")
    path = f"{prefix}.{root}{'Init' if phase == 'initialization' else ''}[{index}]"
    return path + ("." + ".".join(nested) if nested else "")


def quantity(records, directory, path, unit=None):
    record = records.get(path)
    if record is None:
        raise ValueError(f"Missing reference array: {path}")
    if unit is not None and record.get("units") != unit:
        raise ValueError(f"Reference unit mismatch: {path}, expected {unit}")
    return reference_array(directory, record)


def state_indices(records, prefix, field, phase):
    root = field.split(".")[0] + ("Init" if phase == "initialization" else "")
    pattern = re.compile(re.escape(prefix + "." + root) + r"\[(\d+)\]\.")
    indices = sorted({int(match.group(1)) for key in records if (match := pattern.match(key))})
    if not indices or indices != list(range(indices[-1]+1)):
        raise ValueError(f"Missing or noncontiguous reference state indices: {prefix}.{root}")
    return indices


def scalar_parameter(metadata, key):
    value = metadata["inputs"]["options"].get(key)
    if value is None or not np.isfinite(value) or value <= 0:
        raise ValueError(f"Missing or invalid convergence threshold: {key}")
    return value


def validate_point_convergence(directory, records, metadata, framework, prefix, phase, index):
    checks = []
    for field, errors in POINT_ERRORS[framework].items():
        path = field_path(prefix, field, phase, index)
        counts = quantity(records, directory, path + ".ITR.N", "1")
        maximum = scalar_parameter(metadata, "MAXITER")
        if (counts.ndim != 2 or counts.shape[1] != 1 or counts.shape[0] < 2
                or not np.all(np.isfinite(counts)) or np.any(counts != np.floor(counts))
                or np.any(counts[1:] < 1) or np.any(counts > maximum) or np.any(counts < 0)):
            raise ValueError(f"Missing actual point-iteration evidence: {path}.ITR.N")
        for residual, tolerance, unit in errors:
            values = quantity(records, directory, path + ".ITR." + residual, unit)
            threshold = scalar_parameter(metadata, tolerance)
            if (not values.size or values.shape[0] != counts.shape[0] or not np.all(np.isfinite(values))
                    or np.any(values < 0) or not np.all(values < threshold)):
                raise ValueError(f"MATLAB point-convergence tolerance not met: {path}.{residual}")
            checks.append({"path": path + ".ITR." + residual, "maximum": float(np.max(values)),
                           "threshold": threshold, "units": unit})
    return checks


def validate_initialization(directory, records, metadata, framework, prefix):
    """Check final pseudo state, not physical-zero ITR that source may not copy."""
    roots = sorted({field.split(".")[0] for field, _, _ in FRAMEWORKS[framework]})
    lists = [state_indices(records, prefix, root, "initialization") for root in roots]
    if any(values != lists[0] for values in lists) or len(lists[0]) < 2:
        raise ValueError(f"Missing consistent solved initialization history: {prefix}")
    last = lists[0][-1]
    point = validate_point_convergence(directory, records, metadata, framework, prefix, "initialization", last)
    if framework == "Mixture":
        temporal = [("mixture", "W", "SSCONVW", "kg/s", False),
                    ("mixture", "P", "SSCONVP", "Pa", False),
                    ("mixture", "H", "SSCONVH", "J/kg", False),
                    ("mixture", "MRM.WV", "SSCONVW", "kg/s", False),
                    ("mixture", "MRM.HV", "SSCONVH", "J/kg", False)]
    elif framework == "TwoFluid":
        temporal = [(field, key, tolerance, unit, False) for field in ("liquid", "vapor")
                    for key, tolerance, unit in (("W", "SSCONVW", "kg/s"), ("U", "SSCONVU", "m/s"), ("H", "SSCONVH", "J/kg"))]
    else:
        fields = ("film",) if framework == "ThreeField" else ("film.base", "film.wave")
        temporal = [(field, key, tolerance, unit, divide) for field in fields
                    for key, tolerance, unit, divide in (("W", "SSCONVWF", "kg/s", True), ("U", "SSCONVUF", "m/s", False))]
        temporal.append(("drop", "U", "SSCONVUD", "m/s", False))
        if framework == "FourField":
            temporal.append(("film.wave", "FREQUENCY", "SSCONVFW", "Hz", False))
    changes = []
    for field, key, tolerance, unit, per_perimeter in temporal:
        before = quantity(records, directory, field_path(prefix, field, "initialization", last-1) + "." + key, unit)
        after = quantity(records, directory, field_path(prefix, field, "initialization", last) + "." + key, unit)
        if before.shape != after.shape or not np.all(np.isfinite(before)) or not np.all(np.isfinite(after)):
            raise ValueError(f"Invalid reference temporal convergence arrays: {field}.{key}")
        difference = abs(after-before)
        if per_perimeter:
            perimeter = np.asarray(metadata["inputs"]["geometry"]["PERIM"], dtype=float).reshape(-1)
            if (difference.ndim != 2 or difference.shape[1] != len(perimeter)
                    or not np.all(np.isfinite(perimeter)) or np.any(perimeter <= 0)):
                raise ValueError("Perimeter/wall dimensions do not match temporal mass convergence")
            difference = difference/perimeter[None, :]
            unit = "kg/s/m"
        threshold = scalar_parameter(metadata, tolerance)
        maximum = float(np.max(difference))
        if maximum >= threshold:
            raise ValueError(f"MATLAB initialization temporal criterion not met: {field}.{key}/{tolerance}")
        changes.append({"field": field+"."+key, "maximum": maximum, "threshold": threshold, "units": unit,
                        "criterion": "additional port acceptance: omitted upstream frequency stop" if key == "FREQUENCY" else "upstream stopping predicate"})
    return {"final_pseudo_index": last, "point": point, "temporal": changes}


def compare_array(original, candidate, *, key, phase, index, unit, scope):
    info = {"key": key, "phase": phase, "time_index": index, "units": unit, "scope": scope,
            "rtol": STRICT_RTOL, "atol": STRICT_ATOL}
    if original.shape != candidate.shape:
        return {**info, "passed": False, "reason": f"shape mismatch: reference {original.shape}, native {candidate.shape}"}
    if not original.size or not np.all(np.isfinite(original)) or not np.all(np.isfinite(candidate)):
        return {**info, "passed": False, "reason": "nonfinite or empty core array"}
    errors = np.abs(candidate-original)
    nonzero = original != 0
    return {**info, "passed": bool(np.all(errors <= STRICT_ATOL+STRICT_RTOL*np.abs(original))),
            "max_absolute_error": float(np.max(errors)),
            "max_relative_error_nonzero": float(np.max(errors[nonzero]/abs(original[nonzero]))) if np.any(nonzero) else 0.0,
            "mismatched_reference_zeros": int(np.count_nonzero(errors[~nonzero])),
            "worst_absolute_error_index": [int(i) for i in np.unravel_index(int(np.argmax(errors)), errors.shape)]}


def compare_framework(directory, native_dir, manifest, records, *, framework, prefix, phases, time_index):
    metadata = json.loads((native_dir/"metadata.json").read_text(encoding="utf-8"))
    provenance = validate_provenance(directory, native_dir, manifest, records, metadata, prefix=prefix, framework=framework)
    convergence = validate_initialization(directory, records, metadata, framework, prefix)
    checks, selected, transient_checks = [], {}, []
    reference_z = quantity(records, directory, prefix+".Z", "m").reshape(-1)
    if metadata.get("units", {}).get("Z") != "m" or metadata.get("units", {}).get("TIME") != "s":
        raise ValueError("Native coordinate units must be m and s")
    for phase in phases:
        archive = "initialization.npz" if phase == "initialization" else "results.npz"
        with np.load(native_dir/archive, allow_pickle=False) as native:
            if "Z" not in native or native["Z"].ndim != 1 or native["Z"].shape != reference_z.shape or not np.allclose(reference_z, native["Z"], rtol=0, atol=1e-12):
                raise ValueError(f"Z differs between results: {prefix}/{phase}; no interpolation is performed")
            if not np.all(np.isfinite(reference_z)) or "TIME" not in native or native["TIME"].ndim != 1 or not np.all(np.isfinite(native["TIME"])):
                raise ValueError("Invalid spatial/time coordinates")
            roots = sorted({field.split(".")[0] for field, _, _ in FRAMEWORKS[framework]})
            indices = state_indices(records, prefix, roots[0], phase)
            if any(state_indices(records, prefix, root, phase) != indices for root in roots[1:]):
                raise ValueError(f"Reference field state counts differ: {prefix}/{phase}")
            if len(native["TIME"]) != len(indices):
                raise ValueError(f"TIME differs between results: {prefix}/{phase}")
            if phase == "physical":
                times = quantity(records, directory, prefix+".TIME", "s").reshape(-1)
                if times.shape != native["TIME"].shape or not np.allclose(times, native["TIME"], rtol=0, atol=1e-12):
                    raise ValueError(f"TIME differs between results: {prefix}/{phase}")
            for root in roots:
                times = [quantity(records, directory, field_path(prefix, root, phase, i)+".TIME", "s") for i in indices]
                if any(value.size != 1 for value in times):
                    raise ValueError("Field TIME must be scalar per state")
                if not np.allclose(np.array([value.item() for value in times]), native["TIME"], rtol=0, atol=1e-12):
                    raise ValueError(f"TIME differs between results: {prefix}.{root}/{phase}")
            chosen = indices if time_index is None else [time_index]
            if any(i not in indices for i in chosen):
                raise ValueError(f"time_index out of range for {prefix}/{phase}")
            selected[phase] = chosen
            for index in chosen:
                # Initialization includes unconverged intermediate pseudo steps;
                # physical zero uses final-pseudo evidence checked above.
                if phase == "physical" and index > 0:
                    transient_checks.extend(validate_point_convergence(directory, records, metadata, framework, prefix, phase, index))
                for field, native_field, wall in FRAMEWORKS[framework]:
                    quantities = [(key, unit) for key, unit in (("W", "kg/s"), ("U", "m/s"), ("H", "J/kg"))]
                    if field == "film.wave": quantities.append(("FREQUENCY", "Hz"))
                    for key, unit in quantities:
                        native_key = (native_field+"." if native_field else "")+key
                        ref_path = field_path(prefix, field, phase, index)+"."+key
                        scope = ("additional frequency regression (provisional strict port criterion)" if key == "FREQUENCY"
                                 else "additional base-field regression (corrects upstream path omission)" if field == "film.base"
                                 else "upstream W/U/H fields" if phase == "physical" and index == 0
                                 else "additional history/transient W/U/H regression")
                        error = {"key": native_key, "phase": phase, "time_index": index, "scope": scope, "passed": False}
                        record = records.get(ref_path)
                        if record is None or native_key not in native:
                            checks.append({**error, "reason": "missing required array"}); continue
                        if record.get("units") != unit or metadata.get("units", {}).get(native_key) != unit:
                            checks.append({**error, "reason": f"unit mismatch: expected {unit}"}); continue
                        original = reference_array(directory, record)
                        expected_ndim = 3 if wall else 2
                        if (original.ndim != 2 or original.shape[0] != len(reference_z)
                                or (not wall and original.shape[1] != 1)
                                or native[native_key].ndim != expected_ndim
                                or native[native_key].shape[0] != len(indices)):
                            checks.append({**error, "reason": "dimension mismatch; no squeezing or broadcasting"}); continue
                        if not wall: original = original[:, 0]
                        checks.append(compare_array(original, native[native_key][index], key=native_key,
                                                    phase=phase, index=index, unit=unit, scope=scope))
    return {"framework": framework, "reference_prefix": prefix, "passed": bool(checks) and all(c["passed"] for c in checks),
            "provenance": provenance, "initialization_convergence": convergence,
            "physical_point_checks": transient_checks, "selected_indices": selected,
            "native_metadata": metadata, "checks": checks}


def compare(reference_dir: Path, native_dir: Path, *, time_index: int | None = None, phase="both"):
    """Compare all histories by default; explicit physical index reproduces narrower scope.

    Initial convergence and precursor provenance are always checked. There is
    no tolerance override, interpolation, partial-field success or fixture write.
    """
    reference_dir, native_dir = Path(reference_dir), Path(native_dir)
    if time_index is not None and (not isinstance(time_index, int) or isinstance(time_index, bool) or time_index < 0):
        raise ValueError("time_index must be a nonnegative integer or None")
    if phase not in ("physical", "initialization", "both"):
        raise ValueError("phase must be physical, initialization or both")
    manifest, records = load_export(reference_dir)
    framework = manifest.get("framework")
    if framework not in FRAMEWORKS:
        raise NotImplementedError(f"Unknown reference framework: {framework}")
    phases = ("physical", "initialization") if phase == "both" else (phase,)
    sections = [compare_framework(reference_dir, native_dir, manifest, records, framework=framework,
                                  prefix="solver", phases=phases, time_index=time_index)]
    if framework != "Mixture":
        sections.append(compare_framework(reference_dir, native_dir/"mixture", manifest, records, framework="Mixture",
                                          prefix="solver.mixSolver", phases=phases, time_index=time_index))
    physical = [{"reference_prefix": section["reference_prefix"],
                 "physical_diagnostics": section["native_metadata"].get("physical_diagnostics"),
                 "balance_diagnostics": section["native_metadata"].get("balances")}
                for section in sections]
    physical_failures = [item["reference_prefix"] for item in physical
                         if isinstance(item["physical_diagnostics"], dict)
                         and item["physical_diagnostics"].get("physical_consistency") is False]
    passed = all(section["passed"] for section in sections)
    return {"passed": passed, "numerical_agreement": passed, "framework": framework,
            "reported_physical_consistency_failures": physical_failures,
            "physical_checks": physical, "experimental_validation": "not performed by this comparator",
            "comparison": "portable primary fields with explicit initialization/precursor checks", "phase": phase,
            "time_index": time_index, "rtol": STRICT_RTOL, "atol": STRICT_ATOL,
            "tolerance_basis": "upstream SolverIntegrationTest.compareFieldProperty for physical-zero W/U/H; same strict provisional policy for additional fields/history",
            "supplemental_criteria": "film.base fixes omitted upstream path; frequency uses provisional 1e-8 relative/0 absolute, not a source-derived or physical validation tolerance",
            "reference_source_kind": manifest["source_kind"], "reference_runtime": manifest["runtime"],
            "reference_upstream": manifest["upstream"], "sections": sections,
            "claim_limit": "Agreement only for listed arrays and selections. No experimental validation, no full-port equivalence; approved archives have unknown original producer versions."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("native", type=Path)
    parser.add_argument("--phase", choices=("physical", "initialization", "both"), default="both")
    parser.add_argument("--time-index", type=int, help="Zero-based index within each selected phase; default compares all")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = compare(args.reference, args.native, time_index=args.time_index, phase=args.phase)
    encoded = json.dumps(report, indent=2, allow_nan=False)
    if args.report:
        with args.report.open("x", encoding="utf-8") as stream: stream.write(encoded+"\n")
    print(encoded)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

