"""Compare actual matched MATLAB/native point traces; diagnostic differences, no tolerance pass.

Requires a hash-verified kit and actual MATLAB receipt. Synthetic tests never create evidence.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path

KEY = ("time_s", "node_zero_based", "iteration")
COMMON = ("dt_s", "node_one_based", "z_m", "all_point_criteria_pass")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def number(value):
    if value in ("True", "true"):
        return 1.0
    if value in ("False", "false"):
        return 0.0
    if value is None or value.strip() == "":
        raise ValueError("Empty numeric trace cell")
    return float(value)


def read_trace(path):
    rows = {}
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = reader.fieldnames
        if not columns or len(columns) != len(set(columns)) or not set(KEY).issubset(columns):
            raise ValueError("Missing or duplicate trace column names")
        for line, row in enumerate(reader, 2):
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f"Wrong trace row shape at line {line}")
            values = {k: number(v) for k, v in row.items()}
            key = tuple(values[k] for k in KEY)
            if any(not math.isfinite(x) for x in key) or key[0] < 0:
                raise ValueError("Nonfinite or negative trace key")
            if key[1] < 0 or key[1] != int(key[1]) or key[2] < 1 or key[2] != int(key[2]):
                raise ValueError("Noninteger node/iteration trace key")
            if "node_one_based" in values and values["node_one_based"] != key[1]+1:
                raise ValueError("One-based/zero-based node identity mismatch")
            if "all_point_criteria_pass" in values and values["all_point_criteria_pass"] not in (0, 1):
                raise ValueError("Invalid point-criterion flag")
            if key in rows:
                raise ValueError(f"Duplicate trace key: {key}")
            rows[key] = values
    if not rows:
        raise ValueError("Empty trace")
    return columns, rows


def portable(value):
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else "Inf" if value > 0 else "-Inf"
    if isinstance(value, dict):
        return {k: portable(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [portable(v) for v in value]
    return value


def compare_tables(native_path, matlab_path, columns):
    ncols, native = read_trace(native_path)
    mcols, matlab = read_trace(matlab_path)
    missing_columns = {"native": sorted(set(columns)-set(ncols)), "matlab": sorted(set(columns)-set(mcols))}
    compared = [c for c in columns if c in ncols and c in mcols]
    common = sorted(set(native)&set(matlab))
    stats = {c: {"exact_finite_count": 0, "different_finite_count": 0, "nonfinite_count": 0,
                 "max_absolute_difference": 0., "max_relative_to_matlab": 0., "first_difference": None} for c in compared}
    first = None
    for key in common:
        for c in compared:
            n, m = native[key][c], matlab[key][c]
            s = stats[c]
            if not math.isfinite(n) or not math.isfinite(m):
                s["nonfinite_count"] += 1
                kind = "nonfinite_same" if (n == m or math.isnan(n) and math.isnan(m)) else "nonfinite_mismatch"
                detail = {"key":key,"column":c,"native":n,"matlab":m,"kind":kind}
            elif n == m:
                s["exact_finite_count"] += 1
                continue
            else:
                s["different_finite_count"] += 1
                delta = abs(n-m)
                relative = delta/abs(m) if m != 0 else None
                s["max_absolute_difference"] = max(s["max_absolute_difference"], delta)
                if relative is not None:
                    s["max_relative_to_matlab"] = max(s["max_relative_to_matlab"],relative)
                detail = {"key":key,"column":c,"native":n,"matlab":m,"kind":"finite_difference","absolute_difference":delta,"relative_to_matlab":relative}
            if s["first_difference"] is None:
                s["first_difference"] = detail
            if first is None:
                first = detail
    return portable({"native_rows":len(native),"matlab_rows":len(matlab),"matched_rows":len(common),
                     "missing_columns":missing_columns,"missing_from_matlab":sorted(set(native)-set(matlab)),
                     "missing_from_native":sorted(set(matlab)-set(native)),"first_difference":first,"columns":stats,
                     "uncompared_native_columns":sorted(set(ncols)-set(compared)-set(KEY)),
                     "uncompared_matlab_columns":sorted(set(mcols)-set(compared)-set(KEY)),
                     "policy":"Exact join; no interpolation, rounding, row dropping, fitted alignment, or acceptance tolerances. Nonfinite values always reported, even if matching. Relative difference undefined for zero MATLAB value."})


def compare(kit: Path, native: Path, matlab: Path, case_id: str):
    kit, native, matlab = kit.resolve(), native.resolve(), matlab.resolve()
    manifest = load_json(kit/"kit_manifest.json")
    for entry in load_json(kit/"checksums.json"):
        path = (kit/entry["path"]).resolve()
        if not path.is_relative_to(kit) or digest(path) != entry["sha256"]:
            raise ValueError(f"Kit checksum mismatch: {entry['path']}")
    matches = [c for c in manifest["cases"] if c["run_id"] == case_id]
    if len(matches) != 1:
        raise ValueError("Missing/duplicate case in kit")
    case = matches[0]
    receipt = load_json(matlab/"receipt.json")
    if receipt.get("run_id") != case_id or receipt.get("kit_manifest_sha256") != digest(kit/"kit_manifest.json"):
        raise ValueError("MATLAB receipt is not bound to selected kit/case")
    artifacts = receipt.get("artifacts", [])
    if isinstance(artifacts, dict): artifacts = [artifacts]
    if not artifacts: raise ValueError("MATLAB receipt has no output hashes")
    artifact_names = [x["path"] for x in artifacts]
    if len(artifact_names) != len(set(artifact_names)) or not {"trace/point_trace.csv","portable/manifest.json"}.issubset(artifact_names):
        raise ValueError("Missing/duplicate MATLAB artifact identity")
    for entry in artifacts:
        path = (matlab/entry["path"]).resolve()
        if not path.is_relative_to(matlab) or digest(path) != entry["sha256"]:
            raise ValueError(f"MATLAB output hash changed: {entry['path']}")
    runtime = receipt.get("runtime",{})
    if runtime.get("coolprop") != manifest["runtime"]["required_coolprop"] or not runtime.get("matlab") or not runtime.get("python"):
        raise ValueError("Missing/mismatched MATLAB runtime metadata")
    exported = load_json(matlab/"portable/manifest.json")
    if exported.get("runtime",{}).get("backend") != manifest["runtime"]["required_backend"]:
        raise ValueError("Missing/mismatched actual MATLAB fluid backend")
    input_entries = exported.get("input_files", [])
    if isinstance(input_entries, dict): input_entries = [input_entries]
    if {i["name"]:i["sha256"] for i in input_entries} != case["input_sha256"]:
        raise ValueError("Actual MATLAB input-file hashes differ from frozen kit")
    report = load_json(native.parent/"report.json")
    if report.get("manifest_sha256") != manifest["frozen_manifest_sha256"]:
        raise ValueError("Native replay uses a different frozen manifest")
    if not any(c["run_id"] == case_id for c in report["cases"]):
        raise ValueError("Native case has no execution receipt")
    if load_json(native/"effective_inputs.json") != load_json(kit/"cases"/case_id/"effective_inputs.json"):
        raise ValueError("Native effective inputs differ")
    nschema = load_json(native/"trace_schema.json")
    mschema = load_json(kit/"cases"/case_id/"trace_schema.json")
    if nschema.get("framework") != case["framework"] or nschema.get("trace_nodes_zero_based") != case["trace_nodes_zero_based"]:
        raise ValueError("Native trace scope mismatch")
    if nschema.get("source_sha256") not in report["native_source_sha256"].values():
        raise ValueError("Native traced source is absent from recorded runtime source hashes")
    native_meta = load_json(native/"numerical/metadata.json")
    if native_meta["versions"]["CoolProp"] != runtime["coolprop"]:
        raise ValueError("CoolProp version mismatch")
    # Only a documented spelling alias; never silently convert units.
    aliases = {"kg/(s m)":"kg/s/m"}
    columns = [c for c in mschema["point_columns"] if c in COMMON or c.startswith(("base_","wave_","drop_","liquid_","vapor_","dW","dU","dH","dF","threshold_"))]
    for c in columns:
        nunit = nschema["point_units"].get(c, "1" if c=="all_point_criteria_pass" else None)
        munit = mschema["units"][c]
        if aliases.get(nunit,nunit) != munit:
            raise ValueError(f"Missing/mismatched units for {c}: {nunit!r} vs {munit!r}")
    comparison = compare_tables(native/"point_trace.csv",matlab/"trace/point_trace.csv",columns)
    evidence = {"kit_manifest":kit/"kit_manifest.json", "frozen_manifest":kit/"frozen_manifest.json", "matlab_receipt":matlab/"receipt.json", "matlab_export_manifest":matlab/"portable/manifest.json", "native_report":native.parent/"report.json", "native_schema":native/"trace_schema.json", "matlab_schema":kit/"cases"/case_id/"trace_schema.json", "native_trace":native/"point_trace.csv", "matlab_trace":matlab/"trace/point_trace.csv", "native_inputs":native/"effective_inputs.json"}
    return {"schema":"openstream-matched-point-diagnostic-v1","run_id":case_id,"matlab_receipt_complete":receipt.get("complete",False),
            "evidence_sha256":{k:digest(p) for k,p in evidence.items()},"source_origin_pins":manifest["pins"],
            "matlab_runtime":runtime,"native_versions":native_meta["versions"],"native_source_sha256":report["native_source_sha256"],
            "comparison":comparison,"interpretation":"Diagnostic numerical comparison only. No acceptance threshold, MATLAB-equivalence pass, or physical-validation claim is produced. Source gates and incomplete/failed runtime status remain separate."}


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kit",type=Path); parser.add_argument("native_case",type=Path)
    parser.add_argument("matlab_result",type=Path); parser.add_argument("case_id")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    result=compare(args.kit,args.native_case,args.matlab_result,args.case_id)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(f"Diagnostic comparison saved to {args.output}")
