"""Recover the approved two-fluid MATLAB archive without executing MATLAB.

All six phase W/U/H arrays are directly stored. The embedded mixture precursor
uses the already audited source-method reconstruction. No native solver or
CoolProp method is used to create reference values.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import warnings

from recover_mcos_reference import (
    ROOT, MatlabOpaque, _column, _enum, load_archive, mixture_arrays,
    plain_input, quantity_units, convergence as mixture_convergence,
)
import numpy as np

CORE = tuple(p + "." + k for p in ("liquid", "vapor") for k in ("W", "U", "H"))
ARCHIVE = ROOT / "upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/tutorial1_TwoFluidSolver.mat"


def object_list(value):
    return list(np.asarray(value, dtype=object).ravel(order="F"))


def graph_arrays(solver):
    """Retain complete numeric storage and structural paths, including aliases."""
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
                graph.append({"path": path, "kind": "text_array", "shape": list(value.shape), "values": value.tolist()})
            else:
                raise ValueError(f"Unhandled dtype {value.dtype} at {path}")
        elif value is None or isinstance(value, (str, int, float, bool)):
            graph.append({"path": path, "kind": "scalar", "value": value})
        else:
            raise ValueError(f"Unhandled {type(value)} at {path}")

    walk(solver, "solver")
    return raw_arrays, graph


def effective_inputs(solver):
    inputs = solver.properties["inputSet"].properties
    return {group: {key: plain_input(value) for key, value in inputs[group].properties.items()
                    if key not in ("warnings", "extra", "geometryObj")}
            for group in ("model", "options", "geometry", "bc")}


def phase_arrays(solver, suffix=""):
    data = {"Z": _column(solver.properties["Z"], "solver.Z")}
    times = None
    for phase in ("liquid", "vapor"):
        states = object_list(solver.properties[phase + suffix])
        current_times = np.array([float(s.properties["TIME"].item()) for s in states])
        if times is None:
            times = current_times
        elif not np.array_equal(times, current_times):
            raise ValueError("Phase time grids differ")
        for state in states:
            if state.classname != "Solvers.TwoFluid." + phase.capitalize():
                raise ValueError("Unexpected phase class")
            if not np.array_equal(_column(state.properties["Z"], phase + ".Z"), data["Z"]):
                raise ValueError("Phase axial grids differ")
        for key in ("W", "U", "H"):
            values = [_column(s.properties[key], phase + "." + key) for s in states]
            data[phase + "." + key] = np.stack(values)
            if not np.all(np.isfinite(data[phase + "." + key])):
                raise ValueError("Nonfinite core archive values")
        fields = states[0].properties["ITR"].dtype.names
        for key in fields:
            data[phase + ".ITR." + key] = np.stack([
                _column(s.properties["ITR"][0, 0][key], phase + ".ITR." + key) for s in states])
    data["TIME"] = times
    return data


def validate_object_graph(solver):
    p = solver.properties
    liquids, vapors = object_list(p["liquid"]), object_list(p["vapor"])
    precursors = object_list(p["mixSolver"].properties["mixture"])
    if not len(liquids) == len(vapors) == len(precursors):
        raise ValueError("Phase/precursor state counts disagree")
    for liquid, vapor, precursor in zip(liquids, vapors, precursors):
        mix = liquid.properties["mix"]
        if vapor.properties["mix"] is not mix or mix.properties["liquid"] is not liquid or mix.properties["vapor"] is not vapor:
            raise ValueError("Incorrect phase/mixture handle links")
        if mix.properties["mixture"] is not precursor:
            raise ValueError("Two-fluid group refers to incorrect mixture precursor")
    init_links = []
    for phase in ("liquid", "vapor"):
        for state in object_list(p[phase + "Init"]):
            same = state.properties["mix"] is liquids[0].properties["mix"]
            init_links.append(same)
            if not same:
                raise ValueError("Initialization does not preserve upstream shallow-copy group")
    return {"physical_phase_parent_links": True, "precursor_links": True,
            "initial_phase_shared_group_links": len(init_links),
            "all_initial_groups_reference_physical_time_zero": all(init_links)}


def convergence(initial, options):
    point, temporal = {}, {}
    for phase in ("liquid", "vapor"):
        for key, opt in (("DW", "ERRORW"), ("DU", "ERRORU"), ("DH", "ERRORH")):
            value = float(np.max(initial[phase + ".ITR." + key][-1]))
            limit = float(options[opt].item())
            point[phase + "." + key] = {"max": value, "threshold": limit, "passed": bool(np.isfinite(value) and 0 <= value < limit)}
        for key, opt in (("W", "SSCONVW"), ("U", "SSCONVU"), ("H", "SSCONVH")):
            value = float(np.max(np.abs(initial[phase + "." + key][-1] - initial[phase + "." + key][-2])))
            limit = float(options[opt].item())
            temporal[phase + "." + key] = {"max": value, "threshold": limit, "passed": bool(np.isfinite(value) and value < limit)}
    return {"source_formula": "strict max < original option threshold", "final_point": point,
            "final_temporal": temporal, "point_passed": all(v["passed"] for v in point.values()),
            "temporal_passed": all(v["passed"] for v in temporal.values()),
            "max_point_iterations_by_state": {p: [int(np.max(row)) for row in initial[p + ".ITR.N"]] for p in ("liquid", "vapor")}}


def physical_checks(solver, arrays):
    """Independent dimensional diagnostics from archived phase W/U/H."""
    p = solver.properties
    cfg = p["inputSet"].properties
    fluid = p["fluid"].properties
    if _enum(fluid["PROPERTIES"]) != "SATURATED":
        raise ValueError("Physical audit currently requires archived SATURATED densities")
    area = float(cfg["geometry"].properties["AREA"].item())
    rf, rg = float(fluid["RHOF"].item()), float(fluid["RHOG"].item())
    wl, wv, ul, uv, hl, hv = [arrays[k][0] for k in ("liquid.W", "vapor.W", "liquid.U", "vapor.U", "liquid.H", "vapor.H")]
    occupied = wl / (rf * ul) + wv / (rg * uv)
    error = occupied / area - 1
    worst = int(np.argmax(np.abs(error)))
    power = float(cfg["bc"].properties["POWER"].item())
    total_w = wl + wv
    energy = wl * hl + wv * hv
    return {"units": {"occupied_area": "m^2", "mass_flow": "kg/s", "energy_flux": "W"},
            "prescribed_area_m2": area, "max_occupied_area_relative_error": float(np.max(np.abs(error))),
            "worst_node_index_zero_based": worst, "worst_z_m": float(arrays["Z"][worst]),
            "worst_occupied_area_m2": float(occupied[worst]), "outlet_area_relative_error": float(error[-1]),
            "outlet_mass_defect_kg_s": float(total_w[-1] - total_w[0]),
            "outlet_energy_defect_W": float(energy[-1] - energy[0] - power),
            "minimum_phase_velocity_m_s": float(min(ul.min(), uv.min())),
            "minimum_phase_flow_kg_s": float(min(wl.min(), wv.min())),
            "interpretation": "Area inconsistency is present in original stored MATLAB baseline, not introduced by the Python translation. No experimental validation."}


def export_reference(archive, output):
    archive, output = Path(archive).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        solver = load_archive(archive)["solver"]
    if caught:
        raise ValueError("Archive decoding emitted warnings: " + "; ".join(str(w.message) for w in caught))
    if solver.classname != "Solvers.TwoFluid.TwoFluidSolver":
        raise ValueError("Expected the two-fluid solver archive")
    links = validate_object_graph(solver)
    physical, initial = phase_arrays(solver), phase_arrays(solver, "Init")
    if not np.array_equal(physical["TIME"], _column(solver.properties["TIME"].T, "solver.TIME")):
        raise ValueError("Solver and physical phase time coordinates differ")
    raw, graph = graph_arrays(solver)
    inputs = effective_inputs(solver)
    options = solver.properties["inputSet"].properties["options"].properties
    units = {"Z": "m", "TIME": "s"}
    for phase in ("liquid", "vapor"):
        for key, unit in (("W", "kg/s"), ("U", "m/s"), ("H", "J/kg"), ("ITR.N", "1"),
                          ("ITR.DW", "kg/s"), ("ITR.DU", "m/s"), ("ITR.DH", "J/kg")):
            units[phase + "." + key] = unit
    output.mkdir(parents=True)
    np.savez_compressed(output / "results.npz", **physical)
    np.savez_compressed(output / "initialization.npz", **initial)
    np.savez_compressed(output / "raw_arrays.npz", **raw)
    (output / "object_graph.json").write_text(json.dumps(graph, indent=2, allow_nan=False), encoding="utf-8")
    precursor = solver.properties["mixSolver"]
    mix_physical = mixture_arrays(object_list(precursor.properties["mixture"]))
    mix_initial = mixture_arrays(precursor.properties["mixtureInit"])
    (output / "mixture").mkdir()
    np.savez_compressed(output / "mixture/results.npz", **mix_physical)
    np.savez_compressed(output / "mixture/initialization.npz", **mix_initial)
    mix_manifest = {"schema": "openstream-recovered-embedded-mixture-v1", "complete": True,
                    "parent_archive_sha256": digest, "object_path": "solver.mixSolver", "framework": "Mixture",
                    "state": _enum(precursor.properties["STATE"]), "effective_inputs": effective_inputs(precursor),
                    "units": quantity_units(), "physical_states": len(mix_physical["TIME"]),
                    "initialization_states": len(mix_initial["TIME"]),
                    "convergence": mixture_convergence(mix_initial, precursor.properties["inputSet"].properties["options"].properties),
                    "reconstructed_methods": ["U", "liquid.W", "liquid.U", "liquid.H", "vapor.W", "vapor.U", "vapor.H"],
                    "note": "Extracted embedded precursor, not a separate standalone mixture reference archive."}
    (output / "mixture/manifest.json").write_text(json.dumps(mix_manifest, indent=2, allow_nan=False), encoding="utf-8")
    manifest = {"schema": "openstream-recovered-twofluid-v1", "complete": True, "framework": "TwoFluid",
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "source_kind": "original_approved_archive_decoded_without_matlab",
                "archive": {"file": str(archive), "sha256": digest, "bytes": archive.stat().st_size,
                            "header": archive.read_bytes()[:116].rstrip(b" \x00").decode("ascii")},
                "decoder": {"package": "mat-io", "version": importlib.metadata.version("mat-io"),
                            "release_commit": "f9be7123707c134292fbfb67fcacac14516f5f83", "license": "BSD-3-Clause",
                            "python": platform.python_version(), "warnings": [],
                            "enum_workaround": "See tools/REFERENCE_READER.md; restored after read",
                            "dependencies": {n: importlib.metadata.version(n) for n in ("numpy", "scipy", "pandas", "h5py")}},
                "state": _enum(solver.properties["STATE"]), "effective_inputs": inputs,
                "fluid_constants": {k: plain_input(v) for k, v in solver.properties["fluid"].properties.items() if k != "coolpropH"},
                "physical_states": len(physical["TIME"]), "initialization_states": len(initial["TIME"]),
                "convergence": convergence(initial, options), "object_link_checks": links,
                "physical_checks": physical_checks(solver, physical), "units": units,
                "array_layout": "Named arrays: (time,node); raw arrays retain MATLAB dimensions.",
                "stored_quantity_mapping": {k: "solver." + k for k in CORE}, "reconstructed_methods": {},
                "producer_metadata": {"matlab_version": None, "coolprop_version": None, "source_commit": None},
                "limitations": ["No fresh MATLAB run", "Unknown original producing runtime/source version", "No experimental validation", "Original physical area inconsistency retained"]}
    manifest["files"] = {str(path.relative_to(output)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in sorted(output.rglob("*")) if path.is_file()}
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise ValueError("Archive changed during read")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = export_reference(args.archive, args.output)
    print(json.dumps({"output": str(args.output), "state": result["state"], "convergence": result["convergence"],
                      "physical_checks": result["physical_checks"]}, indent=2))
