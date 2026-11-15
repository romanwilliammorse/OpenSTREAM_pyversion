"""Recover approved three-/four-field MATLAB state without executing a solver.

Stored properties are copied by MCOS property name. Only FourField.Film W/U/H
are dependent properties and are evaluated using the original source formulas.
The original archive is never modified. Producer runtime metadata is unknown.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import warnings

from recover_mcos_reference import (ROOT, MatlabOpaque, _enum, _column, load_archive,
                                   mixture_arrays, plain_input, quantity_units,
                                   convergence as mixture_convergence)
import numpy as np
from matio.utils.matclass import EmptyMatStruct

ARCHIVES = {
    "ThreeField": "eabaef27d5b94dce4506783675d90563def40db1a491b8a16b982b9de070e884",
    "FourField": "fd28edab74cad654721572c4644461dc20fef27ed4a3d617458b9717e13eacf1",
}


def objects(value):
    return list(np.asarray(value, dtype=object).ravel(order="F"))


def film_values(film):
    """Source FourField/Film.m:90-128 dependent getters; all other WUH stored."""
    p = film.properties
    if film.classname == "Solvers.ThreeField.Film":
        return {key: np.asarray(p[key]).copy() for key in ("W", "U", "H")}
    if film.classname != "Solvers.FourField.Film":
        raise ValueError("Unknown film class")
    base, wave = p["base"].properties, p["wave"].properties
    if base["film"] is not film or wave["film"] is not film:
        raise ValueError("Base/wave handle points to the wrong aggregate film")
    w = base["W"] + wave["W"]
    with np.errstate(divide="ignore", invalid="ignore"):
        u = w / (base["W"] / base["U"] + wave["W"] / wave["U"])
    u[w == 0] = base["U"][w == 0]
    return {"W": w.copy(), "U": u.copy(), "H": base["H"].copy()}


def _iteration_dict(obj):
    raw = obj.properties["ITR"]
    if raw.size == 0 or isinstance(raw, EmptyMatStruct):
        return {}
    if raw.shape != (1, 1) or not raw.dtype.names:
        raise ValueError("Expected scalar iteration struct")
    return {key: np.asarray(raw[0, 0][key]).copy() for key in raw.dtype.names}


def annular_arrays(solver, suffix=""):
    """Explicit native axes: time,node,wall for film; time,node for droplets."""
    p = solver.properties
    films, drops = objects(p["film" + suffix]), objects(p["drop" + suffix])
    if len(films) != len(drops):
        raise ValueError("Film/drop time counts differ")
    z = _column(p["Z"], "solver.Z")
    nw = int(np.asarray(p["inputSet"].properties["geometry"].properties["PERIM"]).size)
    rows, presence = [], {}
    for film, drop in zip(films, drops):
        fp, dp = film.properties, drop.properties
        if not np.array_equal(_column(fp["Z"], "film.Z"), z) or not np.array_equal(_column(dp["Z"], "drop.Z"), z):
            raise ValueError("State meshes differ")
        if float(fp["TIME"].item()) != float(dp["TIME"].item()):
            raise ValueError("Film/drop times differ")
        row = {"TIME": float(fp["TIME"].item())}
        fields = {"film": film, "drop": drop}
        if "base" in fp:
            fields.update({"film.base": fp["base"], "film.wave": fp["wave"]})
        for prefix, obj in fields.items():
            wall = prefix != "drop"
            vals = film_values(obj) if prefix == "film" else {key: obj.properties[key] for key in ("W", "U", "H")}
            for key, value in vals.items():
                value = np.asarray(value)
                expected = (len(z), nw if wall else 1)
                if value.shape != expected or not np.all(np.isfinite(value)):
                    raise ValueError(f"Invalid {prefix}.{key} {value.shape}; expected {expected}")
                row[prefix + "." + key] = value.copy() if wall else value[:, 0].copy()
            if "FREQUENCY" in obj.properties:
                value = np.asarray(obj.properties["FREQUENCY"])
                if value.shape != (len(z), nw) or not np.all(np.isfinite(value)):
                    raise ValueError("Invalid wave frequency")
                row[prefix + ".FREQUENCY"] = value.copy()
            for key, value in _iteration_dict(obj).items():
                if value.shape != (len(z), nw if wall and key != "N" else 1):
                    raise ValueError(f"Unexpected iteration dimensions {prefix}.{key}: {value.shape}")
                row[prefix + ".ITR." + key] = value if wall and key != "N" else value[:, 0]
        rows.append(row)
    result = {"Z": z, "TIME": np.array([row["TIME"] for row in rows])}
    for key in sorted(set().union(*(row.keys() for row in rows)) - {"TIME"}):
        template = next(row[key] for row in rows if key in row)
        present = [key in row for row in rows]
        result[key] = np.stack([row[key] if key in row else np.full(template.shape, np.nan) for row in rows])
        if not all(present):
            presence[key] = present
    return result, presence


def graph_arrays(solver):
    arrays, graph, seen = {}, [], {}
    def walk(value, path):
        if isinstance(value, MatlabOpaque):
            if id(value) in seen:
                graph.append({"path": path, "kind": "object_reference", "target": seen[id(value)]})
                return
            seen[id(value)] = path
            graph.append({"path": path, "kind": "object", "class": value.classname})
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
                key = f"array_{len(arrays):05d}"
                arrays[key] = np.asarray(value).copy()
                graph.append({"path": path, "kind": "numeric_array", "key": key, "shape": list(value.shape), "dtype": str(value.dtype)})
            elif value.dtype.kind in "UST":
                graph.append({"path": path, "kind": "text_array", "shape": list(value.shape), "values": value.tolist()})
            else:
                raise ValueError(f"Unknown array dtype at {path}: {value.dtype}")
        elif value is None or isinstance(value, (str, int, float, bool)):
            graph.append({"path": path, "kind": "scalar", "value": plain_input(value)})
        else:
            raise ValueError(f"Unknown value at {path}: {type(value)}")
    walk(solver, "solver")
    return arrays, graph


def effective_inputs(solver):
    cfg = solver.properties["inputSet"].properties
    return {group: {key: plain_input(value) for key, value in cfg[group].properties.items()
                    if key not in ("warnings", "extra", "geometryObj")}
            for group in ("model", "options", "geometry", "bc")}


def annular_convergence(initial, solver, framework):
    opts = solver.properties["inputSet"].properties["options"].properties
    perim = np.asarray(solver.properties["inputSet"].properties["geometry"].properties["PERIM"]).ravel()
    fields = ["film"] if framework == "ThreeField" else ["film.base", "film.wave"]
    point, temporal = {}, {}
    def record(value, opt, unit):
        value = float(np.max(np.abs(value)))
        threshold = float(opts[opt].item())
        return {"max": value, "threshold": threshold, "unit": unit,
                "passed": bool(np.isfinite(value) and value < threshold)}
    for field in fields:
        point[field + ".ITR.DWL"] = record(initial[field + ".ITR.DWL"][-1], "ERRORWF", "kg/s/m")
        point[field + ".ITR.DU"] = record(initial[field + ".ITR.DU"][-1], "ERRORUF", "m/s")
        # Source compares WL=W/PERIM; division precedes subtraction.
        temporal[field + ".WL"] = record(initial[field + ".W"][-1] / perim - initial[field + ".W"][-2] / perim, "SSCONVWF", "kg/s/m")
        temporal[field + ".U"] = record(initial[field + ".U"][-1] - initial[field + ".U"][-2], "SSCONVUF", "m/s")
    point["drop.ITR.DU"] = record(initial["drop.ITR.DU"][-1], "ERRORUD", "m/s")
    temporal["drop.U"] = record(initial["drop.U"][-1] - initial["drop.U"][-2], "SSCONVUD", "m/s")
    additional = None
    if framework == "FourField":
        point["film.wave.ITR.DF"] = record(initial["film.wave.ITR.DF"][-1], "ERRORFW", "Hz")
        additional = record(initial["film.wave.FREQUENCY"][-1] - initial["film.wave.FREQUENCY"][-2], "SSCONVFW", "Hz")
        additional["source_stopping_predicate_includes_this"] = False
    return {"source_formula": "Strict maximum < original threshold; final pseudo state, not copied physical ITR",
            "final_point": point, "final_temporal": temporal,
            "point_passed": all(v["passed"] for v in point.values()),
            "temporal_passed": all(v["passed"] for v in temporal.values()),
            "additional_wave_frequency_temporal": additional,
            "max_point_iterations_by_state": {field: [int(np.max(v)) for v in initial[field + ".ITR.N"]] for field in fields + ["drop"]}}


def physical_checks(solver, arrays):
    """Independent occupied area/mass accounting from original saved values."""
    p = solver.properties
    geom = p["inputSet"].properties["geometry"].properties
    area, dz = float(geom["AREA"].item()), float(p["DZ"].item())
    fields, records = objects(p["film"]), []
    for i, film in enumerate(fields):
        m = film.properties["mix"]
        if _enum(m.properties["fluid"].properties["PROPERTIES"]) != "SATURATED":
            raise ValueError("Archive physical check requires saturated density properties")
        mix = mixture_arrays([m])
        rho_f = float(m.properties["fluid"].properties["RHOF"].item())
        rho_g = float(m.properties["fluid"].properties["RHOG"].item())
        affnc = _column(m.properties["sigm_const"], "mix.sigm_const")
        if len(affnc) != len(arrays["Z"]):
            raise ValueError("Annular transition cache is missing or malformed")
        annular = affnc >= 1 - 1e-12
        with np.errstate(divide="ignore", invalid="ignore"):
            film_inventory = np.sum(arrays["film.W"][i] / arrays["film.U"][i], axis=1)
            drop_inventory = arrays["drop.W"][i] / arrays["drop.U"][i]
            vapor_inventory = mix["vapor.W"][0] / mix["vapor.U"][0]
            occupied = (film_inventory + drop_inventory) / rho_f + vapor_inventory / rho_g
        relative = occupied / area - 1
        finite = np.isfinite(relative)
        flux = np.sum(arrays["film.W"][i], axis=1) + arrays["drop.W"][i] + mix["vapor.W"][0]
        outside = np.flatnonzero(~annular)
        first = int(outside[-1] + 1) if outside.size else 0
        residual = np.diff(flux)
        valid = annular & finite
        max_error = float(np.max(abs(relative[valid]))) if np.any(valid) and np.all(finite[annular]) else None
        records.append({"time_s": float(arrays["TIME"][i]), "annular_node_count": int(np.count_nonzero(annular)),
                        "onset_index_matlab": int(m.properties["oafidx_const"].item()),
                        "first_fully_annular_z_m": float(arrays["Z"][first]) if first < len(annular) else None,
                        "max_unblended_annular_area_closure_relative": max_error,
                        "outlet_area_closure_relative": float(relative[-1]),
                        "nonfinite_annular_nodes": int(np.count_nonzero(annular & ~finite)),
                        "common_annular_mass_residual_kg_s": float(np.sum(residual[first:])),
                        "common_annular_cell_count": len(residual[first:]),
                        "common_annular_inventory_kg": float(np.sum((film_inventory + drop_inventory + vapor_inventory)[first+1:]) * dz),
                        "phase_partition_max_error_kg_s": float(np.max(abs(flux - mix["W"][0])))})
    errors = [r["max_unblended_annular_area_closure_relative"] for r in records]
    return {"area_closure_relative_tolerance": None,
            "phase_volume_closure_role": "informational",
            "phase_volume_closure_status": "indeterminate" if any(r["nonfinite_annular_nodes"] for r in records) else "reported" if any(r["annular_node_count"] for r in records) else "no_applicable_region",
            "max_unblended_annular_area_closure_relative": max(errors) if all(v is not None for v in errors) else None,
            "physical_consistency": None, "records": records,
            "interpretation": "Independent saved-state occupied area sum(W/U/rho); reporting domain is stored sigmoid >=1-1e-12. Phase-volume closure is informational: the original MATLAB ThreeField/FourField frameworks do not impose an acceptance or convergence gate on this diagnostic. No residual threshold is applied; indeterminate NaN/Inf values are retained without adding a failure criterion. Steady mass flux differences only, no transient storage evaluated. This report does not establish physical or experimental validation."}


def export_reference(archive, output):
    archive, output = Path(archive).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    before = hashlib.sha256(archive.read_bytes()).hexdigest()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        solver = load_archive(archive)["solver"]
    if caught:
        raise ValueError("Archive decoding emitted warnings: " + "; ".join(str(v.message) for v in caught))
    framework = solver.classname.split(".")[-1].removesuffix("Solver")
    if framework not in ARCHIVES or before != ARCHIVES[framework]:
        raise ValueError("Only the preserved approved annular baselines are supported")
    physical, physical_presence = annular_arrays(solver)
    initial, initial_presence = annular_arrays(solver, "Init")
    raw, graph = graph_arrays(solver)
    p = solver.properties
    precursor = p["mixSolver"]
    mixphysical = mixture_arrays(objects(precursor.properties["mixture"]))
    mixinitial = mixture_arrays(precursor.properties["mixtureInit"])
    for film in objects(p["film"]):
        if film.properties["mix"] is not precursor.properties["mixture"]:
            raise ValueError("Physical film does not refer to physical precursor")
    units = {"Z": "m", "TIME": "s"}
    for key in set(physical) | set(initial):
        quantity = key.rsplit(".", 1)[-1]
        if key in units:
            continue
        units[key] = {"W": "kg/s", "U": "m/s", "H": "J/kg", "FREQUENCY": "Hz", "N": "1", "DWL": "kg/s/m", "DU": "m/s", "DF": "Hz", "DFW": "Hz"}[quantity]
    manifest = {"schema": "openstream-recovered-mcos-annular-v1", "complete": True,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "source_kind": "original_approved_archive_decoded_without_matlab", "framework": framework,
                "state": _enum(p["STATE"]),
                "archive": {"file": str(archive), "sha256": before, "bytes": archive.stat().st_size,
                            "header": archive.read_bytes()[:116].rstrip(b" \x00").decode("ascii")},
                "decoder": {"package": "mat-io", "version": importlib.metadata.version("mat-io"), "warnings": []},
                "producer_metadata": {"matlab_version": None, "coolprop_version": None, "source_commit": None},
                "effective_inputs": effective_inputs(solver),
                "fluid_constants": {k: plain_input(v) for k, v in p["fluid"].properties.items() if k != "coolpropH"},
                "convergence": annular_convergence(initial, solver, framework),
                "physical_checks": physical_checks(solver, physical),
                "array_layout": "time,node,wall for films including single wall; time,node for droplets and ITR.N; raw MATLAB dimensions retained separately",
                "physical_states": len(physical["TIME"]), "initialization_states": len(initial["TIME"]), "units": units,
                "missing_iteration_fields": {"physical": physical_presence, "initialization": initial_presence},
                "iteration_note": "Absent actual DF is NaN, never substituted by initialized DFW. Final pseudo DF is authoritative for convergence.",
                "reconstructed_methods": {key: "FourField.Film dependent getter evaluated using archived base/wave values, no native field method or solver execution" for key in ("film.W", "film.U", "film.H")} if framework == "FourField" else {},
                "original_regression_fields": ["film", "drop", "film.wave"] if framework == "FourField" else ["film", "drop"],
                "supplementary_regression_fields": ["film.base", "film.wave.FREQUENCY"] if framework == "FourField" else [],
                "regression_note": "Upstream misspelled film.basefilm path skips actual base field; actual base and frequency are required supplementary checks here.",
                "limitations": ["No fresh MATLAB execution", "Unknown producer source/CoolProp version", "No experimental validation", "Recovery does not itself compare native results"]}
    output.mkdir(parents=True)
    for name, arrays in (("results.npz", physical), ("initialization.npz", initial), ("raw_arrays.npz", raw)):
        np.savez_compressed(output / name, **arrays)
    (output / "object_graph.json").write_text(json.dumps(graph, indent=2, allow_nan=False), encoding="utf-8")
    (output / "mixture").mkdir()
    np.savez_compressed(output / "mixture/results.npz", **mixphysical)
    np.savez_compressed(output / "mixture/initialization.npz", **mixinitial)
    mixmeta = {"framework": "Mixture", "state": _enum(precursor.properties["STATE"]),
               "effective_inputs": effective_inputs(precursor), "units": quantity_units(),
               "convergence": mixture_convergence(mixinitial, precursor.properties["inputSet"].properties["options"].properties),
               "source": "Embedded precursor in original annular archive", "array_layout": "time,node[,wall]"}
    (output / "mixture/manifest.json").write_text(json.dumps(mixmeta, indent=2, allow_nan=False), encoding="utf-8")
    manifest["files"] = {str(path.relative_to(output)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(output.rglob("*")) if path.is_file()}
    if hashlib.sha256(archive.read_bytes()).hexdigest() != before:
        raise ValueError("Original archive changed during export")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--framework", choices=list(ARCHIVES), required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    archive = args.archive or ROOT / f"upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/tutorial1_{args.framework}Solver.mat"
    report = export_reference(archive, args.output)
    print(json.dumps({"framework": report["framework"], "output": str(args.output), "state": report["state"],
                      "point_converged": report["convergence"]["point_passed"],
                      "temporal_converged": report["convergence"]["temporal_passed"],
                      "physical_checks": report["physical_checks"]}, indent=2))
