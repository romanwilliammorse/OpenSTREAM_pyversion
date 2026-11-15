"""Recover stored OpenSTREAM MCOS state without executing MATLAB code.

This is a verification-only tool. The numerical package does not import it.
The optional mat-io reader is pinned separately from runtime dependencies.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import warnings
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
READER_TARGET = ROOT / ".venv" / "reference-reader"
if READER_TARGET.is_dir():
    sys.path.insert(0, str(READER_TARGET))

import numpy as np
from matio import load_from_mat
from matio.subsystem import MatSubsystem
from matio.utils.matclass import MatlabOpaque


def _read_enum(self, metadata, type_system):
    """Preserve enumeration names without instantiating MATLAB enumeration code.

    mat-io 1.0.2 mutates ClassName into str and then calls .item() on it;
    it also assumes every enumeration has stored value objects. OpenSTREAM
    uses simple name-only enums. Read the structural names/indices directly.
    Original metadata and integer class ID remain untouched.
    """
    rec = metadata[0, 0]
    class_id = int(rec["ClassName"].item())
    names = [self.mcos_names[int(i) - 1] for i in rec["ValueNames"].ravel(order="F")]
    indices = np.asarray(rec["ValueIndices"])
    if np.any(indices < 0) or np.any(indices >= len(names)):
        raise ValueError("Enumeration name index is out of range")
    selected = np.asarray(names)[indices]
    return MatlabOpaque({"__enum_names__": selected, "__enum_metadata__": metadata.copy()},
                        self.get_classname(class_id), type_system,
                        self.get_class_alias(class_id))


def load_archive(path):
    original = MatSubsystem.load_mcos_enumeration
    MatSubsystem.load_mcos_enumeration = _read_enum
    try:
        return load_from_mat(str(path), raw_data=False)
    finally:
        MatSubsystem.load_mcos_enumeration = original


def _enum(value):
    return str(value.properties["__enum_names__"].item())


def _column(value, name):
    value = np.asarray(value)
    if value.ndim != 2 or value.shape[1] != 1 or value.dtype.kind not in "biuf":
        raise ValueError(f"Expected numeric MATLAB column at {name}: {value.shape}")
    return value[:, 0].copy()


def mixture_arrays(states):
    """Stored numeric state plus named methods evaluated from archived state.

    No solver or CoolProp import, no reevaluation of governing equations.
    Method reconstructions are restricted to the inspected baseline model.
    """
    states = list(np.asarray(states, dtype=object).ravel(order="F"))
    rows = []
    for state in states:
        p = state.properties
        model = p["inputSet"].properties["model"].properties
        geom = p["inputSet"].properties["geometry"].properties
        fluid = p["fluid"].properties
        if _enum(model["PROPERTIES"]) != "SATURATED" or _enum(model["THERMALNONEQ"]) != "EQUILIBRIUM":
            raise ValueError("Method reconstruction currently requires SATURATED/EQUILIBRIUM")
        for phase in ("liquid", "vapor"):
            if p[phase].properties["mix"] is not state:
                raise ValueError(f"{phase} refers to a different mixture object")
        area = float(geom["AREA"].item())
        hf, hg = float(fluid["HF"].item()), float(fluid["HG"].item())
        rhof, rhog = float(fluid["RHOF"].item()), float(fluid["RHOG"].item())
        row = {out: _column(p[key], key) for out, key in {
            "Z": "Z", "W": "W", "P": "P", "H": "H", "RHO": "rho",
            "X": "x", "XEQ": "xeq", "VF": "vf", "UP": "up"}.items()}
        row["TIME"] = float(p["TIME"].item())
        w, h, x, xeq, vf = (row[key] for key in ("W", "H", "X", "XEQ", "VF"))
        with np.errstate(divide="ignore", invalid="ignore"):
            u = w / row["RHO"] / area
            wv, wl = x * w, (1 - x) * w
            uv, ul = (wv / area) / vf / rhog, (wl / area) / (1 - vf) / rhof
            uv[np.isnan(uv)] = u[np.isnan(uv)]
            mask = np.isnan(ul) | (1 - x < 1e-2)
            ul[mask] = u[mask]
            q = np.fmin(x, xeq)
            hv = (h - (1 - q) * hf) / q
            hv[np.isnan(hv) | np.isinf(hv)] = hg
            hl = np.fmin((h - x * hv) / (1 - x), hf)
            hl[np.isnan(hl) | (1 - x < 1e-2)] = hf
        row.update({"U": u, "liquid.W": wl, "liquid.U": ul, "liquid.H": hl,
                    "vapor.W": wv, "vapor.U": uv, "vapor.H": hv})
        for key in ("HFLUX",):
            row[key] = np.asarray(p[key]).copy()
        for group in ("DP", "DPSUM", "MDER", "MRM", "NEARWALL", "ITR"):
            value = p[group]
            if value.shape != (1, 1) or not value.dtype.names:
                raise ValueError(f"Expected scalar struct {group}")
            for field in value.dtype.names:
                data = np.asarray(value[0, 0][field])
                if data.dtype.kind not in "biuf":
                    raise ValueError(f"Non-numeric {group}.{field}")
                wall_array = group == "MRM" or (group == "NEARWALL" and field not in ("WBULK", "HBULK", "XBULK")) or (group == "ITR" and field in ("DWV", "DHV"))
                row[f"{group}.{field}"] = data[:, 0] if not wall_array and data.ndim == 2 and data.shape[1] == 1 else data
        rows.append(row)
    result = {}
    for key in rows[0]:
        result[key] = rows[0][key] if key == "Z" else np.stack([r[key] for r in rows])
    if any(not np.array_equal(rows[0]["Z"], row["Z"]) for row in rows):
        raise ValueError("Changing axial grid cannot be exported as shared Z")
    return result


def plain_input(value):
    """JSON values with MATLAB shape retained except scalars; no evaluation."""
    if isinstance(value, MatlabOpaque):
        if isinstance(value.properties, dict) and "__enum_names__" in value.properties:
            return _enum(value)
        return {"matlab_class": value.classname, "not_evaluated": True}
    if isinstance(value, np.ndarray):
        if value.dtype.kind in "biufUST":
            return plain_input(value.item() if value.size == 1 else value.tolist())
        if value.size == 0:
            return []
        return {"serialized_matlab_value": type(value).__name__, "shape": list(value.shape), "not_evaluated": True}
    if isinstance(value, (list, tuple)):
        return [plain_input(item) for item in value]
    if isinstance(value, float) and not np.isfinite(value):
        return "NaN" if np.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    return value


def convergence(initial, options):
    point = {key: {"max": float(np.max(initial["ITR." + key][-1])), "threshold": float(options[opt].item())}
             for key, opt in (("DW", "ERRORW"), ("DP", "ERRORP"), ("DH", "ERRORH"), ("DWV", "ERRORW"), ("DHV", "ERRORH"))}
    temporal = {key: {"max": float(np.max(np.abs(initial[key][-1] - initial[key][-2]))), "threshold": float(options[opt].item())}
                for key, opt in (("W", "SSCONVW"), ("P", "SSCONVP"), ("H", "SSCONVH"), ("MRM.WV", "SSCONVW"), ("MRM.HV", "SSCONVH"))}
    for item in list(point.values()) + list(temporal.values()):
        item["passed"] = item["max"] < item["threshold"]
    return {"source_formula": "strict max < original option threshold", "final_point": point,
            "final_temporal": temporal, "point_passed": all(item["passed"] for item in point.values()),
            "temporal_passed": all(item["passed"] for item in temporal.values()),
            "max_point_iterations_by_state": [int(np.max(row)) for row in initial["ITR.N"]]}


def quantity_units():
    units = {"Z": "m", "TIME": "s", "W": "kg/s", "P": "Pa", "H": "J/kg", "U": "m/s", "UP": "m/s", "RHO": "kg/m^3", "X": "1", "XEQ": "1", "VF": "1", "HFLUX": "W/m^2"}
    for phase in ("liquid", "vapor"):
        for key in ("W", "U", "H"):
            units[phase + "." + key] = units[key]
    for group in ("DP", "DPSUM"):
        for key in ("Grav", "Wall", "Acc_z", "Acc_t", "Acc_s", "K", "Tot"):
            units[group + "." + key] = "Pa"
    groups = {"MDER": {"U_z": "m/s^2", "U_t": "m/s^2", "U": "m/s^2", "H_z": "J/kg/s", "H_t": "J/kg/s", "H": "J/kg/s"},
              "MRM": {"WV": "kg/s", "X": "1", "HV": "J/kg", "TV": "K", "TCOND": "s", "TEVAP": "s"},
              "NEARWALL": {"W": "kg/s", "H": "J/kg", "HFLUX": "W/m^2", "XEQ": "1", "WBULK": "kg/s", "HBULK": "J/kg", "XBULK": "1", "TRELAX": "s"},
              "ITR": {"N": "1", "DW": "kg/s", "DP": "Pa", "DPSUM": "Pa", "DH": "J/kg", "DWV": "kg/s", "DHV": "J/kg"}}
    for group, fields in groups.items():
        units.update({group + "." + key: unit for key, unit in fields.items()})
    return units


def export_reference(archive, output):
    """Export named arrays and complete serialized property graph, never overwrite."""
    archive, output = Path(archive).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    digest_before = hashlib.sha256(archive.read_bytes()).hexdigest()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        loaded = load_archive(archive)
    if caught:
        raise ValueError("Decoder emitted warnings; extraction is not trustworthy: " + "; ".join(str(w.message) for w in caught))
    solver = loaded["solver"]
    if solver.classname != "Solvers.Mixture.MixtureSolver":
        raise ValueError("Only mixture recovery is currently authorized and implemented")
    physical = mixture_arrays([solver.properties["mixture"]])
    initial = mixture_arrays(solver.properties["mixtureInit"])
    raw_arrays, graph, seen = {}, [], {}

    def walk(value, path):
        if isinstance(value, MatlabOpaque):
            if id(value) in seen:
                graph.append({"path": path, "kind": "object_reference", "target": seen[id(value)]})
                return
            seen[id(value)] = path
            graph.append({"path": path, "kind": "object", "class": value.classname,
                          "type_system": str(value.type_system)})
            walk(value.properties, path + ".properties")
        elif isinstance(value, Mapping):
            for key, item in value.items():
                walk(item, path + "." + str(key))
        elif isinstance(value, np.ndarray):
            if value.dtype.names:
                graph.append({"path": path, "kind": "struct", "shape": list(value.shape), "fields": list(value.dtype.names)})
                for idx in np.ndindex(value.shape):
                    suffix = "[" + ",".join(str(i + 1) for i in idx) + "]"
                    for key in value.dtype.names:
                        walk(value[idx][key], path + suffix + "." + key)
            elif value.dtype.kind == "O":
                graph.append({"path": path, "kind": "cell_or_object_array", "shape": list(value.shape)})
                for idx in np.ndindex(value.shape):
                    walk(value[idx], path + "[" + ",".join(str(i + 1) for i in idx) + "]")
            elif value.dtype.kind in "biufc":
                key = f"array_{len(raw_arrays):05d}"
                raw_arrays[key] = np.asarray(value).copy()
                graph.append({"path": path, "kind": "numeric_array", "key": key,
                              "dtype": str(value.dtype), "shape": list(value.shape)})
            elif value.dtype.kind in "UST":
                graph.append({"path": path, "kind": "text_array", "shape": list(value.shape),
                              "values": value.tolist()})
            else:
                raise ValueError(f"Unhandled array dtype {value.dtype} at {path}")
        elif value is None or isinstance(value, (str, int, float, bool)):
            graph.append({"path": path, "kind": "scalar", "value": value})
        else:
            raise ValueError(f"Unhandled {type(value)} at {path}")

    walk(solver, "solver")
    output.mkdir(parents=True)
    np.savez_compressed(output / "results.npz", **physical)
    np.savez_compressed(output / "initialization.npz", **initial)
    np.savez_compressed(output / "raw_arrays.npz", **raw_arrays)
    (output / "object_graph.json").write_text(json.dumps(graph, indent=2, allow_nan=False), encoding="utf-8")
    methods = ["U", "liquid.W", "liquid.U", "liquid.H", "vapor.W", "vapor.U", "vapor.H"]
    inputs = solver.properties["inputSet"].properties
    effective_inputs = {group: {key: plain_input(value) for key, value in inputs[group].properties.items()
                               if key not in ("warnings", "extra", "geometryObj")}
                        for group in ("model", "options", "geometry", "bc")}
    manifest = {
        "schema": "openstream-recovered-mcos-mixture-v1", "complete": True,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_kind": "original_approved_archive_decoded_without_matlab",
        "archive": {"file": str(archive), "sha256": digest_before, "bytes": archive.stat().st_size,
                    "header": archive.read_bytes()[:116].rstrip(b" \x00").decode("ascii")},
        "decoder": {"package": "mat-io", "version": importlib.metadata.version("mat-io"),
                    "repository": "https://github.com/foreverallama/matio",
                    "inspected_commit": "18d538d5657e4e32e25d90c53a80c05a522540ac", "license": "BSD-3-Clause",
                    "release_tag_commit": "f9be7123707c134292fbfb67fcacac14516f5f83",
                    "enum_workaround": "Read structural name/index table without mutation; preserve original enum metadata",
                    "warnings": [], "python": platform.python_version(),
                    "dependencies": {name: importlib.metadata.version(name) for name in ("numpy", "scipy", "pandas", "h5py")}},
        "producer_metadata": {"matlab_version": None, "coolprop_version": None, "source_commit": None,
                              "note": "Archive header gives platform/date; serialized anonymous-function path includes R2024b but is not independent runtime-version proof."},
        "framework": "Mixture", "state": _enum(solver.properties["STATE"]),
        "effective_inputs": effective_inputs,
        "fluid_constants": {key: plain_input(value) for key, value in solver.properties["fluid"].properties.items() if key != "coolpropH"},
        "convergence": convergence(initial, inputs["options"].properties),
        "array_layout": "Named exports: time,node[,wall]. Raw arrays retain original MATLAB dimensions; object graph indices are 1-based.",
        "physical_states": len(physical["TIME"]), "initialization_states": len(initial["TIME"]),
        "reconstructed_methods": {key: "Algebraic method from pinned source using recovered state and recovered fluid constants, no solver/CoolProp execution" for key in methods},
        "stored_quantity_mapping": {"W": "W", "P": "P", "H": "H", "RHO": "rho", "X": "x", "XEQ": "xeq", "VF": "vf", "UP": "up", "HFLUX": "HFLUX"},
        "units": quantity_units(),
        "raw_units_note": "Object-graph arrays preserve every numeric member including serialization metadata. Use named-export units only where the mapping exists; other raw metadata units are unresolved or not physical.",
        "limitations": ["Not a fresh MATLAB execution", "Unknown original CoolProp version and exact producer commit", "Method outputs reconstructed from archived values and source formulas are distinguished from directly stored arrays", "No experimental validation implied"],
    }
    manifest["files"] = {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in ("results.npz", "initialization.npz", "raw_arrays.npz", "object_graph.json")}
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest_before:
        raise ValueError("Archive changed during recovery")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ROOT / "upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/tutorial1_MixtureSolver.mat")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = export_reference(args.archive, args.output)
    print(json.dumps({"output": str(args.output), "state": report["state"], "physical_states": report["physical_states"], "initialization_states": report["initialization_states"]}))
