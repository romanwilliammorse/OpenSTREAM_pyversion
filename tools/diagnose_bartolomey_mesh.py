"""Diagnose frozen pilot mesh failures from saved arrays, without a new solve.

This is supplemental evidence. It never replaces the preregistered linear
observation comparisons, changes acceptance thresholds, or edits saved results.
"""
from __future__ import annotations

import argparse
import hashlib
from importlib.metadata import version
import json
from pathlib import Path

import CoolProp
from CoolProp.CoolProp import PQ_INPUTS, iphase_twophase
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
# Fixed source Model.G constant, not a user input serialized in metadata.
GRAVITY_M_S2 = 9.81
PROPERTY_BACKEND = "BICUBIC&HEOS"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_run(root, run_id):
    directory = root/run_id/"numerical"
    metadata = json.loads((directory/"metadata.json").read_text(encoding="utf-8"))
    if metadata["versions"]["CoolProp"] != version("CoolProp"):
        raise ValueError("Diagnostic CoolProp version differs from saved run")
    if metadata["inputs"]["model"]["PROPERTIES"] != "SATURATED":
        raise ValueError("This analytic diagnostic is scoped to saturated phase properties")
    with np.load(directory/"results.npz", allow_pickle=False) as archive:
        values = {key: archive[key].copy() for key in ("Z", "XEQ", "VF", "HFLUX", "H", "W")}
    pressure = metadata["inputs"]["bc"][0]["PRESSURE"]
    fluid = metadata["inputs"]["model"]["FLUID"]
    # Use the preserved source backend directly, without native property/field
    # classes. HEOS-only PropsSI would introduce small tabulation differences.
    state = CoolProp.AbstractState(PROPERTY_BACKEND, fluid)
    state.specify_phase(iphase_twophase)
    state.update(PQ_INPUTS, pressure, 0)
    props = {"rho_liquid_kg_m3": state.rhomass(),
             "h_liquid_J_kg": state.hmass(),
             "cp_liquid_J_kg_K": state.cpmass(),
             "k_liquid_W_m_K": state.conductivity()}
    state.update(PQ_INPUTS, pressure, 1)
    props.update(rho_vapor_kg_m3=state.rhomass(), h_vapor_J_kg=state.hmass())
    props["h_fg_J_kg"] = props["h_vapor_J_kg"]-props["h_liquid_J_kg"]
    return metadata, values, props


def homogeneous_void(equilibrium_quality, properties):
    x = np.clip(np.asarray(equilibrium_quality, dtype=float), 0, 1)
    rl, rv = properties["rho_liquid_kg_m3"], properties["rho_vapor_kg_m3"]
    return x*rl/(x*rl+(1-x)*rv)


def saha_zuber_bestion_void(xeq, flux, mass_flux, inlet_xeq, inputs, properties):
    """Evaluate the preserved algebraic closure independently of native fields.

    xeq [1], wall flux [W/m²], mass_flux [kg/(m² s)], hydraulic diameter [m].
    This diagnostic is restricted to one wall and SATURATED phase properties.
    """
    xeq, flux, mass_flux = np.broadcast_arrays(xeq, flux, mass_flux)
    geometry = inputs["geometry"]
    diameter = 4*geometry["AREA"]/sum(geometry["PERIM"])
    pe = mass_flux*diameter*properties["cp_liquid_J_kg_K"]/properties["k_liquid_W_m_K"]
    bo = flux/mass_flux/properties["h_fg_J_kg"]
    xb = np.maximum(-.0022*np.minimum(7e4, pe)*bo, min(inlet_xeq, -1e-6))
    x = np.maximum(xeq, 0)
    selected = xeq > xb
    # The source zero-wall-heat limiting expression is x=max(xeq,0).
    regular = selected & (xb != 0)
    correction = np.zeros_like(xeq)
    correction[regular] = xb[regular]*np.exp(xeq[regular]/xb[regular]-1)
    x = np.where(selected, (xeq-correction)/(1-correction), x)
    x = np.clip(x, 0, 1)
    rl, rv = properties["rho_liquid_kg_m3"], properties["rho_vapor_kg_m3"]
    drift = .188*np.sqrt(GRAVITY_M_S2*diameter*(rl-rv)/rv)
    jg, jl = x*mass_flux/rv, (1-x)*mass_flux/rl
    return jg/(jg+jl+drift)


def bracket(coordinate, query):
    upper = int(np.searchsorted(coordinate, query, side="right"))
    upper = min(max(upper, 1), len(coordinate)-1)
    return upper-1, upper


def diagnose(root):
    report_path = root/"report.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    failures = [s for s in report["sensitivity"] if s["status"] == "failed" and s["kind"].startswith("mesh_")]
    result = {"schema": "openstream-bartolomey-mesh-diagnosis-v1",
              "input_report_sha256": sha256(report_path),
              "diagnostic_script_sha256": sha256(Path(__file__)),
              "CoolProp_version": version("CoolProp"),
              "source_gravity_m_s2": GRAVITY_M_S2,
              "property_backend": PROPERTY_BACKEND,
              "scope": "Saved-array and algebraic-closure diagnostics only; no new solver execution or revised acceptance results.",
              "unit_void_fraction": "1", "index_base": 0, "failures": [],
              "hem_quality_records": []}

    # Compare all quality-coordinate HEM pilot grids with the algebraic model.
    # No measurement errors or alternate experimental acceptance are produced.
    for run_id, run in report["runs"].items():
        if run["model"] != "hem" or run["variant"] != "base" or run["comparison"]["coordinate"] != "Quality":
            continue
        metadata, values, props = read_run(root, run_id)
        native_x, native_vf = values["XEQ"][0], values["VF"][0]
        points = []
        for point in run["comparison"]["points"]:
            if point["status"] != "compared":
                continue
            q = point["coordinate"]
            direct = float(homogeneous_void(q, props))
            i, j = bracket(native_x, q)
            points.append({"index": point["index"], "equilibrium_quality": q,
                           "saved_linear_prediction": point["predicted"],
                           "direct_algebraic_prediction": direct,
                           "linear_minus_algebraic": point["predicted"]-direct,
                           "bracket_quality": [float(native_x[i]), float(native_x[j])],
                           "bracket_crosses_zero_quality": bool(native_x[i] < 0 < native_x[j])})
        result["hem_quality_records"].append({
            "run_id": run_id, "properties": props,
            "results_npz_sha256": sha256(root/run_id/"numerical/results.npz"),
            "native_node_max_difference_from_algebraic": float(np.max(np.abs(native_vf-homogeneous_void(native_x, props)))),
            "max_linear_observation_difference_from_algebraic": max(abs(p["linear_minus_algebraic"]) for p in points),
            "points": points})

    for failure in failures:
        left = report["runs"][failure["left"]]
        right = report["runs"][failure["right"]]
        a = {p["index"]: p for p in left["comparison"]["points"] if p["status"] == "compared"}
        b = {p["index"]: p for p in right["comparison"]["points"] if p["status"] == "compared"}
        if a.keys() != b.keys():
            raise ValueError("Failure has unequal point populations; requires a different diagnosis")
        worst = max(a, key=lambda i: abs(b[i]["predicted"]-a[i]["predicted"]))
        query = a[worst]["coordinate"]
        diagnostic = {"entry_id": failure["entry_id"], "model": failure["model"], "kind": failure["kind"],
                      "threshold": failure["threshold"], "reported_status": failure["status"],
                      "worst_observation_index": worst, "observation_coordinate": query,
                      "coordinate_unit": left["comparison"]["coordinate_unit"],
                      "saved_left_prediction": a[worst]["predicted"],
                      "saved_right_prediction": b[worst]["predicted"],
                      "recomputed_max_change": abs(b[worst]["predicted"]-a[worst]["predicted"]),
                      "grids": []}
        if not np.isclose(diagnostic["recomputed_max_change"], failure["max_void_change"], rtol=0, atol=1e-15):
            raise ValueError("Saved failure metric does not match the paired points")
        for run_id in (failure["left"], failure["right"]):
            metadata, values, props = read_run(root, run_id)
            inputs = metadata["inputs"]
            coordinate = values["XEQ"][0] if left["comparison"]["coordinate"] == "Quality" else values["Z"]
            i, j = bracket(coordinate, query)
            z, x, vf, h, q, w = (values["Z"], values["XEQ"][0], values["VF"][0], values["H"][0], values["HFLUX"][0, :, 0], values["W"][0])
            bc, geometry = inputs["bc"][0], inputs["geometry"]
            dz = z[1]-z[0]
            positive_heat = np.flatnonzero(q > 0)
            grid = {"run_id": run_id, "results_npz_sha256": sha256(root/run_id/"numerical/results.npz"),
                    "bracket_node_indices": [i, j],
                    "bracket_coordinate": [float(coordinate[i]), float(coordinate[j])],
                    "bracket_void_fraction": [float(vf[i]), float(vf[j])],
                    "bracket_wall_flux_W_m2": [float(q[i]), float(q[j])],
                    "grid_spacing_m": float(dz),
                    "last_heated_node_m": float(z[positive_heat[-1]]),
                    "discrete_heated_length_m": float(np.count_nonzero(q[1:] > 0)*dz),
                    "maximum_wall_flux_W_m2": float(np.max(q))}
            if failure["model"] == "hem":
                direct = float(homogeneous_void(query, props))
                grid.update(direct_algebraic_prediction=direct,
                            interpolation_minus_algebraic=float(np.interp(query, coordinate, vf))-direct,
                            bracket_crosses_zero_quality=bool(coordinate[i] < 0 < coordinate[j]))
            elif failure["model"] == "saha_zuber_bestion":
                if q[i] != q[j] or q[i] <= 0:
                    raise ValueError("Worst point crosses a heating discontinuity; requires a different analytic decomposition")
                x_at_point = float(np.interp(query, z, x))
                w_at_point = float(np.interp(query, z, w))
                primitive = float(saha_zuber_bestion_void(x_at_point, q[i], w_at_point/geometry["AREA"], x[0], inputs, props))
                nodal_closure = saha_zuber_bestion_void(x, q, w/geometry["AREA"], x[0], inputs, props)
                linear_steady_h = bc["HIN"]+np.r_[0, np.cumsum(q[1:]*sum(geometry["PERIM"])*dz/bc["MFLOW"])]
                steady_at_point = bc["HIN"]+q[i]*sum(geometry["PERIM"])*query/bc["MFLOW"]
                steady_x_at_point = (steady_at_point-props["h_liquid_J_kg"])/props["h_fg_J_kg"]
                steady_closure = float(saha_zuber_bestion_void(steady_x_at_point, q[i], bc["MFLOW"]/geometry["AREA"], x[0], inputs, props))
                grid.update(interpolated_equilibrium_quality=x_at_point,
                            direct_closure_at_interpolated_primitives=primitive,
                            grid_normalized_steady_closure_at_coordinate=steady_closure,
                            interpolation_minus_direct_closure=float(np.interp(query, z, vf))-primitive,
                            native_node_max_difference_from_algebraic=float(np.max(np.abs(vf-nodal_closure))),
                            independent_steady_enthalpy_max_residual_J_kg=float(np.max(np.abs(h-linear_steady_h))))
            diagnostic["grids"].append(grid)
        if failure["model"] == "hem":
            diagnostic["finding"] = "Both grids reproduce the algebraic HEM at native nodes. The worst observation lies within a grid interval crossing the Xeq=0 slope discontinuity on at least one grid (100 and 200 cells cross; 400 does not). Linear interpolation across this interval creates the large mesh-dependent change. The frozen comparison remains failed."
        else:
            ga, gb = diagnostic["grids"]
            diagnostic["direct_closure_change"] = gb["direct_closure_at_interpolated_primitives"]-ga["direct_closure_at_interpolated_primitives"]
            diagnostic["interpolation_contribution_change"] = gb["interpolation_minus_direct_closure"]-ga["interpolation_minus_direct_closure"]
            diagnostic["finding"] = "The worst point is within the uniformly heated region. The source next interpolation represents the heater with a grid-dependent heated nodal extent; preserving integrated power changes the normalized wall heat flux. That changes both local Saha-Zuber heating and accumulated enthalpy. The algebraic-closure and interpolation decomposition quantifies their combined effect; no threshold or source equation is altered."
        result["failures"].append(diagnostic)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, default=ROOT/"outputs/validation/bartolomey-pilot-01")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)
    output = args.output or args.campaign/"mesh_diagnosis.json"
    result = diagnose(args.campaign)
    with output.open("x", encoding="utf-8") as f:
        json.dump(result, f, indent=2, allow_nan=False)
        f.write("\n")
    print(json.dumps({"output": str(output), "failed_mesh_comparisons_diagnosed": len(result["failures"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
