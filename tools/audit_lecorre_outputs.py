"""Independently audit saved Le Corre campaign arithmetic; never execute a solver.

No runner, adapter, comparison, or solver routines are imported. Audit tolerances
cover float arithmetic and decimal serialization, not model accuracy or validation.
The physical/convergence findings in the original report are preserved unchanged.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
import csv
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {"BaseThickness": ("base.THICK", "m"),
           "WaveVelocity": ("wave.U", "m/s"),
           "WaveNumberDensity": ("wave.N", "m^-1"),
           "WaveTimePeriod": ("wave.PERIOD", "s")}


def close(left, right, *, rtol=2e-12, atol=1e-12):
    if left is None or right is None:
        return left is right
    return math.isfinite(float(left)) and math.isfinite(float(right)) and math.isclose(
        float(left), float(right), rel_tol=rtol, abs_tol=atol)


def source_values(record, key):
    return [None if element.text is None or not element.text.strip()
            else float(element.text) for element in record.findall(key)]


def rounded_mass_flux_check(record):
    """Use independent half-last-place bounds of the actual XML decimal strings."""
    values = [Decimal(record.findtext(key)) for key in ("MassFlux", "Area", "MassFlow")]
    g, area, flow = values
    dg, da, dw = [Decimal(5).scaleb(v.as_tuple().exponent - 1) for v in values]
    residual = g * area - flow
    bound = abs(g) * da + abs(area) * dg + dg * da + dw
    return {"mass_flux_times_area_kg_s": float(g * area), "stored_mass_flow_kg_s": float(flow),
            "signed_difference_kg_s": float(residual), "decimal_rounding_bound_kg_s": float(bound),
            "within_source_decimal_resolution": abs(residual) <= bound,
            "interpretation": "Descriptive consistency of rounded source inputs; no replacement of explicit stored mass flow or area."}


def match_point(z, y, affnc, position, measured):
    """Piecewise linear interpolation, requiring both bracketing nodes eligible."""
    if position is None or measured is None:
        return None, "missing_coordinate_or_measurement"
    if not math.isfinite(position) or not math.isfinite(measured):
        return None, "nonfinite_observation"
    if position < z[0] or position > z[-1]:
        return None, "outside_stored_channel"
    upper = bisect_left(z, position)
    lower = upper if z[upper] == position else upper - 1
    if any(affnc[index] < 1 - 1e-12 for index in (lower, upper)):
        return None, "outside_fully_annular_domain"
    if any(not math.isfinite(y[index]) for index in (lower, upper)):
        return None, "nonfinite_prediction"
    if lower == upper:
        return float(y[upper]), None
    weight = (position - z[lower]) / (z[upper] - z[lower])
    return float((1 - weight) * y[lower] + weight * y[upper]), None


def expected_runs(manifest):
    base = [case["case_id"] for case in manifest["demo"]["frameworks"]]
    base += [f"wurtz-{entry:02d}" for entry in manifest["wurtz"]["entry_ids"]]
    base += [f"sawai-{entry:02d}-{variant['variant_id']}"
             for entry in manifest["sawai"]["entry_ids"] for variant in manifest["sawai"]["variants"]]
    result = {f"{case}-n{manifest['base']['nnodes']}-base" for case in base}
    for sentinel in manifest["study"]["sentinels"]:
        result.update(f"{sentinel['case_id']}-n{cells}-mesh" for cells in manifest["study"]["meshes"])
        result.add(f"{sentinel['case_id']}-n{manifest['study']['tightening']['nnodes']}-tight")
    return result


def fourfield_point_evidence(run_dir, options, curves):
    """Read the final saved point changes using the unchanged source thresholds."""
    criteria = {
        "film.base.ITR.DWL": ("ERRORWF", "kg/(s m)"),
        "film.base.ITR.DU": ("ERRORUF", "m/s"),
        "film.wave.ITR.DWL": ("ERRORWF", "kg/(s m)"),
        "film.wave.ITR.DU": ("ERRORUF", "m/s"),
        "film.wave.ITR.DF": ("ERRORFW", "Hz"),
        "drop.ITR.DU": ("ERRORUD", "m/s"),
    }
    with np.load(run_dir / "numerical/initialization.npz", allow_pickle=False) as arrays:
        results = {}
        for key, (control, unit) in criteria.items():
            changes = arrays[key][-1].reshape(-1)
            node = int(np.argmax(changes))
            failed = np.flatnonzero(~np.isfinite(changes) | (changes >= options[control]))
            phase = key.split(".ITR.")[0]
            iterations = arrays[phase + ".ITR.N"][-1].reshape(-1)
            results[key] = {
                "unit": unit, "maximum_absolute_iteration_change": float(changes[node]),
                "threshold_name": control, "strict_threshold": options[control],
                "maximum_node_zero_based": node, "maximum_elevation_m": float(arrays["Z"][node]),
                "failed_nodes": [{"node_zero_based": int(j), "elevation_m": float(arrays["Z"][j]),
                                  "iteration_change": float(changes[j]), "iterations": int(iterations[j]),
                                  "AFFNC": float(curves["AFFNC"][j])} for j in failed],
                "passed": len(failed) == 0}
        pseudo_time = float(arrays["TIME"][-1])
    with (run_dir / "numerical/convergence.csv").open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    last = [row for row in rows if row["phase"] == "initialization"][-1]
    return {"final_initialization_pseudo_time_s": pseudo_time,
            "point_converged_from_saved_changes": all(v["passed"] for v in results.values()),
            "logged_point_converged": last["point_converged"] == "True",
            "criteria": results,
            "interpretation": "DWL is the iteration change in mass flow per wetted perimeter, kg/(s m), not a governing-equation residual. The source stop checks temporal changes; it can stop with point criteria still failed. Thresholds and stopping algorithm are unchanged."}


def convergence_diagnosis(run_dir, assessment, inputs, fourfield_points):
    """Resolve failed gates from saved final initialization states, without rerun."""
    framework, options = assessment["framework"], inputs["options"]
    if framework == "Mixture":
        return {"source_state": assessment["source_state"], "native_converged": assessment["native_converged"],
                "rejection_reasons": [] if assessment["native_converged"] else ["mixture_gate_requires_separate_diagnosis"]}
    with np.load(run_dir / "numerical/initialization.npz", allow_pickle=False) as arrays:
        temporal = {}
        if framework == "TwoFluid":
            definitions = {f"{phase}.{field}": (control, unit) for phase in ("liquid", "vapor")
                           for field, control, unit in (("W", "SSCONVW", "kg/s"), ("U", "SSCONVU", "m/s"), ("H", "SSCONVH", "J/kg"))}
        elif framework == "ThreeField":
            definitions = {"film.W": ("SSCONVWF", "kg/(s m)"), "film.U": ("SSCONVUF", "m/s"), "drop.U": ("SSCONVUD", "m/s")}
        else:
            definitions = {f"film.{phase}.{field}": (control, unit) for phase in ("base", "wave")
                           for field, control, unit in (("W", "SSCONVWF", "kg/(s m)"), ("U", "SSCONVUF", "m/s"))}
            definitions.update({"drop.U": ("SSCONVUD", "m/s"), "film.wave.FREQUENCY": ("SSCONVFW", "Hz")})
        for key, (control, unit) in definitions.items():
            changes = np.abs(arrays[key][-1] - arrays[key][-2]).reshape(-1)
            if unit == "kg/(s m)":
                changes = changes / float(inputs["geometry"]["PERIM"][0])
            node = int(np.argmax(changes))
            temporal[key] = {"maximum_absolute_temporal_change": float(changes[node]), "unit": unit,
                             "threshold_name": control, "strict_threshold": options[control],
                             "maximum_node_zero_based": node, "maximum_elevation_m": float(arrays["Z"][node]),
                             "passed": bool(np.all(np.isfinite(changes) & (changes < options[control]))),
                             "included_in_source_temporal_stop": key != "film.wave.FREQUENCY"}
        if framework == "FourField":
            point = fourfield_points["criteria"]
        else:
            definitions = ({f"{phase}.ITR.{field}": (control, unit) for phase in ("liquid", "vapor")
                            for field, control, unit in (("DW", "ERRORW", "kg/s"), ("DU", "ERRORU", "m/s"), ("DH", "ERRORH", "J/kg"))}
                           if framework == "TwoFluid" else {"film.ITR.DWL": ("ERRORWF", "kg/(s m)"), "film.ITR.DU": ("ERRORUF", "m/s"), "drop.ITR.DU": ("ERRORUD", "m/s")})
            point = {}
            for key, (control, unit) in definitions.items():
                changes = arrays[key][-1].reshape(-1)
                node = int(np.argmax(changes))
                failed = np.flatnonzero(~np.isfinite(changes) | (changes >= options[control]))
                phase = key.split(".ITR.")[0]
                iterations = arrays[phase + ".ITR.N"][-1].reshape(-1)
                point[key] = {"maximum_absolute_iteration_change": float(changes[node]), "unit": unit,
                              "threshold_name": control, "strict_threshold": options[control],
                              "maximum_node_zero_based": node, "maximum_elevation_m": float(arrays["Z"][node]),
                              "passed": len(failed) == 0,
                              "failed_nodes": [{"node_zero_based": int(j), "elevation_m": float(arrays["Z"][j]), "iteration_change": float(changes[j]), "iterations": int(iterations[j])} for j in failed]}
        pseudo_time = float(arrays["TIME"][-1])
    reasons = []
    if assessment["source_state"] not in ("INITIALSTEPCONVERGED", "SOLVEDCONVERGED"):
        reasons.append("source_temporal_stop_not_reached")
    if not all(value["passed"] for value in point.values()):
        reasons.append("final_point_iterations_failed")
    if framework == "FourField" and not temporal["film.wave.FREQUENCY"]["passed"]:
        reasons.append("wave_frequency_temporal_criterion_failed")
    diagnostics = assessment["physical"]["source_field_diagnostics"]
    if diagnostics.get("onset_equilibrium_converged") is False:
        reasons.append("onset_equilibrium_failed")
    if diagnostics.get("nested_closure_failures"):
        reasons.append("nested_closure_failed")
    if framework == "TwoFluid":
        with np.load(run_dir / "numerical/results.npz", allow_pickle=False) as arrays:
            finite_positive = all(np.all(np.isfinite(arrays[f"{phase}.{field}"]))
                                  and (field == "H" or bool(np.all(arrays[f"{phase}.{field}"] >= 0 if field == "W" else arrays[f"{phase}.{field}"] > 0)))
                                  for phase in ("liquid", "vapor") for field in ("W", "U", "H"))
        if not finite_positive:
            reasons.append("phase_finite_positive_bounds_failed")
    if not assessment["native_converged"] and not reasons:
        reasons.append("native_rejection_requires_further_diagnosis")
    return {"source_state": assessment["source_state"], "native_converged": assessment["native_converged"],
            "precursor_converged": assessment["precursor_converged"], "final_initialization_pseudo_time_s": pseudo_time,
            "temporal_criteria": temporal, "point_criteria": point, "rejection_reasons": reasons,
            "interpretation": "Saved successive-iteration/pseudo-time changes, not governing-equation residuals. Source algorithm and numerical tolerances unchanged; physical-consistency rejection remains separate."}


def audit_campaign(directory, allow_partial=False):
    report_bytes = (directory / "report.json").read_bytes()
    report = json.loads(report_bytes)
    manifest_bytes = (directory / "frozen_manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    checks = []

    def check(name, condition, detail=None):
        checks.append({"check": name, "passed": bool(condition), **({"detail": detail} if detail is not None else {})})

    canonical_hash = hashlib.sha256(manifest_bytes.replace(b"\r\n", b"\n")).hexdigest()
    check("frozen_manifest_hash", canonical_hash == report["manifest_sha256_lf"])
    expected = expected_runs(manifest)
    actual = set(report["runs"])
    check("run_population_no_unplanned_cases", actual <= expected)
    check("all_planned_runs_accounted", actual == expected if not allow_partial else actual <= expected,
          {"planned": len(expected), "reported": len(actual), "missing": sorted(expected - actual)})
    records = {}
    source_checks = {}
    for family in ("wurtz", "sawai"):
        source = manifest["sources"]["xml"][family]
        path = ROOT / source["path"]
        raw = path.read_bytes()
        check(f"{family}.xml_hash", hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == source["sha256_lf"])
        records[family] = ET.fromstring(raw).findall("dataset")

    observations = {"compared": 0, "excluded": 0, "excluded_reasons": {}}
    base_populations = {}
    unique_source_targets = {}
    run_facts = {}
    for run_id, assessment in report["runs"].items():
        run_checks_start = len(checks)
        run_dir = directory / run_id
        saved = json.loads((run_dir / "assessment.json").read_text(encoding="utf-8"))
        check(f"{run_id}.assessment_identity", saved == assessment)
        if assessment["execution"] != "completed":
            run_facts[run_id] = {"execution": assessment["execution"], "arithmetic_audit": "not_applicable_execution_failed"}
            continue
        inputs = json.loads((run_dir / "effective_inputs.json").read_text(encoding="utf-8"))
        units = json.loads((run_dir / "comparison_units.json").read_text(encoding="utf-8"))
        metadata = json.loads((run_dir / "numerical/metadata.json").read_text(encoding="utf-8"))
        check(f"{run_id}.native_source_fingerprints", metadata["native_source_sha256"] == report["source_fingerprints"])
        curves = dict(np.load(run_dir / "comparison_profiles.npz", allow_pickle=False))
        z = curves["Z"]
        bc = inputs["bc"][0]
        geometry = inputs["geometry"]
        check(f"{run_id}.profile_dimensions", all(v.ndim == 1 and v.size == z.size for v in curves.values())
              and z.size == assessment["cells"] + 1 and bool(np.all(np.diff(z) > 0)))
        check(f"{run_id}.spatial_domain", close(z[0], 0) and close(z[-1], geometry["LENGTH"]))
        expected_units = {"Z": "m", "HFLUX": "W/m^2", "AFFNC": "1", "mixture.VF": "1", "mixture.X": "1", "mixture.XEQ": "1"}
        for key in curves:
            suffix = key.split(".")[-1]
            if suffix in ("VF", "X", "XEQ"):
                expected_units[key] = "1"
            if suffix in ("W", "U", "THICK", "AMPLITUDE", "FREQUENCY", "EQFREQUENCY", "PERIOD", "N"):
                expected_units[key] = {"W": "kg/s", "U": "m/s", "THICK": "m", "AMPLITUDE": "m", "FREQUENCY": "Hz", "EQFREQUENCY": "Hz", "PERIOD": "s", "N": "m^-1"}[suffix]
        check(f"{run_id}.units", units == expected_units)
        perimeters = np.asarray(geometry["PERIM"], dtype=float)
        check(f"{run_id}.single_wall_scope", perimeters.size == 1)
        power = math.fsum(float(q * dz * perimeters[0]) for q, dz in zip(curves["HFLUX"][1:], np.diff(z)))
        balances = assessment["physical"]["precursor_balances"]
        check(f"{run_id}.wall_power_integral", close(power, bc["POWER"], atol=1e-7)
              and close(power, balances["discrete_wall_power_W"], atol=1e-7))
        mixture_path = run_dir / "numerical" / ("results.npz" if assessment["framework"] == "Mixture" else "mixture/results.npz")
        with np.load(mixture_path, allow_pickle=False) as mixture:
            flow, enthalpy = mixture["W"][-1].reshape(-1), mixture["H"][-1].reshape(-1)
            transported = float(flow[0] * (enthalpy[-1] - enthalpy[0]))
            check(f"{run_id}.reported_steady_enthalpy", close(transported, balances["steady_enthalpy_gain_W"], atol=1e-7))
            check(f"{run_id}.reported_mass_deviation", close(float(np.max(abs(flow - flow[0]))), balances["steady_mass_max_deviation_kg_s"]))
        if "wave.FREQUENCY" in curves:
            frequency, speed = curves["wave.FREQUENCY"], curves["wave.U"]
            eligible = (frequency > 0) & (speed > 0) & np.isfinite(frequency) & np.isfinite(speed)
            check(f"{run_id}.wave_period_reciprocal", bool(np.allclose(curves["wave.PERIOD"][eligible], 1 / frequency[eligible], rtol=2e-12, atol=1e-12)))
            check(f"{run_id}.wave_number_density", bool(np.allclose(curves["wave.N"][eligible], frequency[eligible] / speed[eligible], rtol=2e-12, atol=1e-12)))
        physical = assessment["physical"]
        diag = physical["source_field_diagnostics"]
        point_evidence = None
        if assessment["framework"] == "FourField":
            point_evidence = fourfield_point_evidence(run_dir, inputs["options"], curves)
            check(f"{run_id}.point_convergence_log", point_evidence["point_converged_from_saved_changes"] == point_evidence["logged_point_converged"])
            check(f"{run_id}.native_flag_retains_point_failure", not assessment["native_converged"] or point_evidence["point_converged_from_saved_changes"])
            check(f"{run_id}.failed_point_iteration_limits", all(node["iterations"] == inputs["options"]["MAXITER"]
                  for criterion in point_evidence["criteria"].values() for node in criterion["failed_nodes"]))
        if diag.get("physical_consistency") is False:
            check(f"{run_id}.physical_failure_retained", physical["status"] == "failed")
        convergence = convergence_diagnosis(run_dir, assessment, inputs, point_evidence)
        check(f"{run_id}.native_convergence_diagnosed", not assessment["native_converged"] or not convergence["rejection_reasons"])
        family = assessment["family"]
        comparisons = json.loads((run_dir / "comparisons.json").read_text(encoding="utf-8"))
        check(f"{run_id}.comparison_report_identity", comparisons == assessment["comparisons"])
        with (run_dir / "paired_measurements.csv").open(newline="", encoding="utf-8") as stream:
            csv_points = list(csv.DictReader(stream))
        check(f"{run_id}.csv_population", len(csv_points) == sum(len(c["points"]) for c in comparisons.values()))
        csv_lookup = {(p["quantity"], int(p["index"])): p for p in csv_points}
        check(f"{run_id}.csv_unique_keys", len(csv_lookup) == len(csv_points))
        if family != "demo":
            record = records[family][assessment["entry_id"] - 1]
            source_key = f"{family}-{assessment['entry_id']:02d}"
            source_checks[source_key] = rounded_mass_flux_check(record)
            check(f"{run_id}.source_mass_flux_area_resolution", source_checks[source_key]["within_source_decimal_resolution"])
            for source_key, effective in (("MassFlow", bc["MFLOW"]), ("Power", bc["POWER"]), ("Pressure", bc["PRESSURE"]), ("InletEnthalpy", bc["HIN"]), ("Length", geometry["LENGTH"]), ("Area", geometry["AREA"])):
                check(f"{run_id}.source_input.{source_key}", close(float(record.findtext(source_key)), effective, rtol=0, atol=5.1e-12))
            check(f"{run_id}.all_target_quantities", set(comparisons) == set(manifest[family]["targets"]))
            for quantity, comparison in comparisons.items():
                key, unit = TARGETS[quantity]
                raw_values = source_values(record, quantity) or [None]
                values = [None if value is None else value * (0.001 if quantity == "WaveTimePeriod" else 1) for value in raw_values]
                positions = source_values(record, "Elevation") if family == "sawai" else [float(record.findtext("Length"))]
                check(f"{run_id}.{quantity}.raw_population", len(comparison["points"]) == len(values) == len(positions))
                check(f"{run_id}.{quantity}.units", comparison["unit"] == unit and comparison["observations"]["quantity_unit"] == unit and comparison["observations"]["coordinate_unit"] == "m")
                observation = comparison["observations"]
                check(f"{run_id}.{quantity}.raw_values_retained", observation["raw_values"] == raw_values and observation["raw_quantity_unit"] == ("ms" if quantity == "WaveTimePeriod" else unit))
                check(f"{run_id}.{quantity}.converted_values", len(observation["values"]) == len(values) and all(close(a, b) for a, b in zip(observation["values"], values)))
                errors = []
                for index, (position, measured) in enumerate(zip(positions, values)):
                    point = comparison["points"][index]
                    predicted, reason = match_point(z, curves[key], curves["AFFNC"], position, measured)
                    error = None if predicted is None else predicted - measured
                    csv_point = csv_lookup.get((quantity, index), {})
                    name = f"{run_id}.{quantity}[{index}]"
                    check(name + ".source_observation", close(point["elevation_m"], position) and close(point["measured"], measured))
                    check(name + ".domain_and_interpolation", point["reason"] == reason and close(point["predicted"], predicted) and close(point["error"], error))
                    status = "excluded" if reason is not None else "compared"
                    check(name + ".status", point["status"] == status and csv_point.get("status") == status and csv_point.get("reason") == (reason or "") and csv_point.get("unit") == unit)
                    for field, expected_value in (("elevation_m", position), ("measured", measured), ("predicted", predicted), ("error", error)):
                        value = csv_point.get(field)
                        check(name + ".csv." + field, close(None if value in (None, "") else float(value), expected_value))
                    observations[status] += 1
                    if assessment["numerics"] == "base":
                        group = family + ("-" + assessment["variant_id"] if "variant_id" in assessment else "")
                        population = base_populations.setdefault(group, {"compared": 0, "excluded": 0, "reasons": {}})
                        population[status] += 1
                        if reason:
                            population["reasons"][reason] = population["reasons"].get(reason, 0) + 1
                        unique_source_targets[(family, assessment["entry_id"], quantity, index)] = measured
                    if reason:
                        observations["excluded_reasons"][reason] = observations["excluded_reasons"].get(reason, 0) + 1
                    else:
                        errors.append(error)
                summary = comparison["summary"]
                check(f"{run_id}.{quantity}.counts", summary["n_total"] == len(values) and summary["n_compared"] == len(errors) and summary["n_excluded"] == len(values) - len(errors))
                for statistic, value in (("bias", math.fsum(errors) / len(errors) if errors else None),
                                         ("mae", math.fsum(map(abs, errors)) / len(errors) if errors else None),
                                         ("rmse", math.sqrt(math.fsum(e * e for e in errors) / len(errors)) if errors else None)):
                    check(f"{run_id}.{quantity}.{statistic}", close(summary[statistic], value))
        run_facts[run_id] = {"execution": assessment["execution"], "native_converged": assessment["native_converged"],
                             "physical_status_unchanged": physical["status"], "power_integral_W": power,
                             "fourfield_point_iteration_evidence": point_evidence,
                             "convergence_diagnosis": convergence,
                             "audit_checks": len(checks) - run_checks_start,
                             "audit_passed": all(c["passed"] for c in checks[run_checks_start:])}
    return {"schema": "openstream-lecorre-independent-output-audit-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(), "manifest_sha256_lf": canonical_hash,
            "audit_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": "Independent saved-array, raw-XML, unit, population, CSV and arithmetic audit. No solver execution or MATLAB equivalence; no new physical or uncertainty-qualified experimental acceptance.",
            "float_arithmetic_policy": {"rtol": 2e-12, "atol": 1e-12, "power_W_atol": 1e-7,
                                        "input_decimal_serialization_atol": 5.1e-12,
                                        "physical_criteria_changed": False},
            "complete_campaign": actual == expected, "source_input_resolution": source_checks,
            "observation_counts_all_runs": observations, "runs": run_facts,
            "base_comparison_populations": base_populations,
            "unique_source_observations_in_completed_base_runs": {
                "targets_including_missing": len(unique_source_targets),
                "present": sum(value is not None for value in unique_source_targets.values()),
                "missing": sum(value is None for value in unique_source_targets.values()),
                "interpretation": "Repeated relaxation, mesh, or iterative predictions do not create independent measurements."},
            "summary": {"checks": len(checks), "passed": sum(c["passed"] for c in checks),
                        "failed": sum(not c["passed"] for c in checks), "runs_audited": len(run_facts)},
            "failures": [c for c in checks if not c["passed"]], "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--output", type=Path, required=True, help="New audit receipt; existing files are never overwritten.")
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    result = audit_campaign(args.campaign, args.allow_partial)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result["summary"]))
    return 0 if result["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
