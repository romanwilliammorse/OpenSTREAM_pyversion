"""Independently account for the retained Sawai closure-return observations.

Uses recorded function returns, never imports or executes the OpenSTREAM solver.
The frozen-variable deposition derivative is not a full iteration Jacobian.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT / "outputs/verification/sawai-oscillation-01"
UNITS = "kg/(m^2 s)"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(value):
    if isinstance(value, list):
        if len(value) != 1:
            raise ValueError("Expected a recorded one-wall scalar")
        return scalar(value[0])
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("Nonfinite observation cannot support this finite-cycle audit")
    return value


def select(rows, method, caller_prefix, *, receiver=None, stage="closure_return"):
    """Require an unambiguous recorded call path; nested repeated calls differ."""
    matches = [r for r in rows if r["stage"] == stage and r["method"] == method
               and (receiver is None or r["receiver_class"] == receiver)
               and tuple(c["method"] for c in r["callers"][:len(caller_prefix)]) == tuple(caller_prefix)]
    if len(matches) != 1:
        raise ValueError(f"Expected one {method} via {caller_prefix}; found {len(matches)}")
    return matches[0]


def value(rows, method, callers, **kwargs):
    return scalar(select(rows, method, callers, **kwargs)["return_value"])


def verify_hashes(directory, expected):
    for name, sha in expected.items():
        path = directory / name
        if not path.is_file() or digest(path) != sha:
            raise ValueError(f"Recorded artifact hash differs: {path}")


def group_records(records):
    grouped = defaultdict(list)
    for index, row in enumerate(records):
        if row["event_index"] != index:
            raise ValueError("Missing, duplicated or reordered deep-trace event")
        key = (float(row["time_s"]), int(row["node_zero_based"]), int(row["iteration"]))
        grouped[key].append(row)
    expected = {(8., n, it) for n in (24, 25, 26) for it in range(90, 101)}
    if set(grouped) != expected:
        raise ValueError(f"Expected complete 33-group frozen window; missing={expected - set(grouped)}, extra={set(grouped) - expected}")
    return grouped


def source_terms(rows, field):
    caller = field + ".MTOT"
    parent = select(rows, caller, ("FourFieldSolver._advance",))
    names = ((field + ".MEVAP", "evaporation"), (field + ".MENT", "entrainment"),
             (field + ".MDEP", "deposition"),
             ("Base.MWAVE" if field == "Base" else "Wave.MBASE", "internal_in"),
             ("Wave.MBASE" if field == "Base" else "Base.MWAVE", "internal_out"))
    children = [select(rows, method, (caller,)) for method, _ in names]
    state_keys = ("base_W", "base_U", "wave_W", "wave_U", "wave_F", "drop_W", "drop_U")
    for child in children:
        if child["event_index"] >= parent["event_index"]:
            raise ValueError("Child return appears after the parent return")
        if any(child[k] != parent[k] for k in state_keys):
            raise ValueError("Closure constituents were not evaluated at one primary state")
    terms = {name: scalar(row["return_value"]) for (_, name), row in zip(names, children)}
    reconstructed = terms["evaporation"] + terms["entrainment"] + terms["deposition"] + terms["internal_in"] - terms["internal_out"]
    observed = scalar(parent["return_value"])
    if reconstructed != observed:
        raise ValueError(f"{caller} constituent reconstruction is not exact: {reconstructed} != {observed}")
    terms.update({"total": observed, "reconstructed": reconstructed,
                  "exact_reconstruction": True, "event_index": parent["event_index"],
                  "state": {k: parent[k] for k in state_keys}})
    return terms


def signed_okawa_slope(mdep, concentration, drop_flow, rho_f):
    """d(Mdep)/d(Wd) [1/m²] for nonzero Wd with all other inputs fixed.

    C=Wd/(abs(Wd)/rhoF+B); Mdep=sign(Wd)*K*sqrt(abs(C)+1e-6).
    K includes the actual constant geometry/property/blending multiplier.
    """
    c, w = abs(concentration), abs(drop_flow)
    if not (w > 0 and 0 < c < rho_f and rho_f > 0):
        raise ValueError("Slope requires nonzero finite flow and 0<|C|<rhoF")
    return abs(mdep) / (2 * (c + 1e-6)) * c / w * (1 - c / rho_f)


def analyze(directory, saved_cycle):
    assessment_path = directory / "assessment.json"
    assessment = json.loads(assessment_path.read_text())
    if not assessment["observer_exact_numeric_equality"]:
        raise ValueError("Observer invariance was not established")
    verify_hashes(directory, assessment["artifact_sha256"])
    schema = json.loads((directory / "deep_trace_schema.json").read_text())
    with gzip.open(directory / "closure_trace.jsonl.gz", "rt", encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle]
    if len(records) != schema["records"]:
        raise ValueError("Deep-trace schema record count mismatch")
    groups = group_records(records)
    coarse = {}
    with (directory / "update_trace.jsonl").open() as handle:
        for line in handle:
            row = json.loads(line)
            key = (row["time_s"], row["node_zero_based"], row["iteration"])
            if key in groups and row["stage"] in ("base_mass_proposal", "wave_mass_proposal"):
                duplicate = (*key, row["stage"])
                if duplicate in coarse:
                    raise ValueError("Duplicate coarse proposal record")
                coarse[duplicate] = row
    if len(coarse) != 66:
        raise ValueError("Missing coarse mass proposals")
    inputs = json.loads((directory / "effective_inputs.json").read_text())
    if inputs["model"]["DEPOSITION"] != "OKAWA" or inputs["model"]["DEPENHANCEMENT"] != "NONE":
        raise ValueError("Frozen derivative is specific to the recorded unenhanced OKAWA branch")
    cycle = json.loads(saved_cycle.read_text())
    verify_hashes(ROOT, cycle["input_sha256"])
    for recorded_name, sha in cycle["input_sha256"].items():
        counterpart = directory / Path(recorded_name).name
        if counterpart.name in ("update_trace.jsonl", "point_trace.csv", "temporal_trace.json", "effective_inputs.json"):
            if digest(counterpart) != sha:
                raise ValueError(f"Saved-cycle observations differ from new deep replay: {counterpart.name}")
    cycle_by_node = {n["node_zero_based"]: n for n in cycle["nodes"]}
    all_phases = []
    for (time, node, iteration), rows in sorted(groups.items()):
        base = source_terms(rows, "Base")
        wave = source_terms(rows, "Wave")
        wave_mdep_path = ("Wave.MDEP", "Wave.MTOT")
        drop_dep = select(rows, "Drop.MDEP", wave_mdep_path)
        concentration = value(rows, "Drop.CONC", ("Drop.MDEP", *wave_mdep_path))
        dep = scalar(drop_dep["return_value"])
        eta = value(rows, "Wave.ETA", wave_mdep_path)
        base_eta = value(rows, "Base.ETA", ("Wave.ETA", *wave_mdep_path))
        if scalar(drop_dep["locals"]["conc"]) != abs(concentration) + 1e-6:
            raise ValueError("Recorded deposition concentration floor does not reconstruct")
        if eta * dep != wave["deposition"]:
            raise ValueError("Wave deposition allocation does not reconstruct exactly")
        delta = select(rows, "Wave.DELTAFREQ", ("FourFieldSolver._advance",))
        # Obtain the actual physical-precursor blend from an observed linear
        # blend with zero first endpoint; no extra getter is evaluated.
        r = scalar(delta["return_value"]) / scalar(delta["locals"]["value"])
        rho_f = coarse[(time, node, iteration, "base_mass_proposal")]["locals"]["rho"]
        slope = signed_okawa_slope(dep, concentration, wave["state"]["drop_W"], rho_f)
        wave_proposal = coarse[(time, node, iteration, "wave_mass_proposal")]
        loc = wave_proposal["locals"]
        uw, dz, dt = scalar(loc["uw"]), loc["dz"], loc["dt"]
        perimeter = scalar(inputs["geometry"]["PERIM"])
        relaxed_coefficient = inputs["options"]["RELAXWW"] * uw * perimeter * dz / (uw + dz / dt)
        wave_dep_coefficient = eta + r * base_eta
        # Trace the unblended exchange net at the wave-source state. The
        # direct Base.MWAVE call and the copy evaluated inside Wave.MBASE
        # must agree because no primary state is mutated within this source.
        mwave = select(rows, "Base.MWAVE", ("Wave.MTOT",))
        mwave_nested = select(rows, "Base.MWAVE", ("Wave.MBASE", "Wave.MTOT"))
        net = scalar(mwave["locals"]["net"])
        net_nested = scalar(mwave_nested["locals"]["net"])
        if net != net_nested:
            raise ValueError("Repeated exchange net differs at an unchanged primary state")
        internal_net = wave["internal_in"] - wave["internal_out"]
        algebraic_internal_net = -r * net
        same_state_base_q = value(rows, "Base.MEVAP", ("Base.MWAVE", "Wave.MTOT")) + value(rows, "Base.MENT", ("Base.MWAVE", "Wave.MTOT")) + value(rows, "Base.MDEP", ("Base.MWAVE", "Wave.MTOT"))
        same_state_base_source = same_state_base_q + r * net
        all_phases.append({
            "time_s": time, "node_zero_based": node, "iteration": iteration,
            "base_source": base, "wave_source": wave,
            "drop_CONC_kg_m3": concentration, "drop_MDEP_kg_m2_s": dep,
            "wave_deposition_fraction": eta, "base_deposition_fraction": base_eta,
            "blend_from_observed_deltafreq": r,
            "exchange_net_at_wave_state_kg_m2_s": net,
            "internal_net_kg_m2_s": internal_net,
            "internal_net_from_minus_blend_times_net_kg_m2_s": algebraic_internal_net,
            "internal_exchange_algebra_difference_kg_m2_s": internal_net - algebraic_internal_net,
            "same_state_base_source_kg_m2_s": same_state_base_source,
            "base_source_at_wave_state_minus_actual_earlier_base_source_kg_m2_s": same_state_base_source - base["total"],
            "wave_source_deposition_coefficient_with_internal_exchange": wave_dep_coefficient,
            "drop_MDEP_partial_derivative_per_m2": slope,
            "relaxed_wave_source_coefficient_m2": relaxed_coefficient,
            "frozen_direct_deposition_feedback_only": -relaxed_coefficient * wave_dep_coefficient * slope,
            "frozen_feedback_plus_old_wave_relaxation_only": 1 - inputs["options"]["RELAXWW"] - relaxed_coefficient * wave_dep_coefficient * slope,
            "rhoF_from_recorded_outer_local_kg_m3": rho_f,
        })
    contrasts = []
    for node in (24, 25, 26):
        a, b = [next(p for p in all_phases if p["node_zero_based"] == node and p["iteration"] == it) for it in (99, 100)]
        terms = {name: b["wave_source"][name] - a["wave_source"][name]
                 for name in ("evaporation", "entrainment", "deposition", "internal_in", "internal_out", "total")}
        # This attribution includes the actual small internal source changes;
        # it is not a re-evaluation with one term disabled.
        total = terms["total"]
        contrasts.append({
            "node_zero_based": node,
            "wave_constituent_delta_100_minus_99_kg_m2_s": terms,
            "direct_deposition_fraction_of_total_source_contrast": terms["deposition"] / total,
            "internal_net_contrast_kg_m2_s": terms["internal_in"] - terms["internal_out"],
            "drop_MDEP_delta_100_minus_99_kg_m2_s": b["drop_MDEP_kg_m2_s"] - a["drop_MDEP_kg_m2_s"],
            "drop_deposition_delta_at_iteration99_allocation_with_internal_exchange_kg_m2_s": a["wave_source_deposition_coefficient_with_internal_exchange"] * (b["drop_MDEP_kg_m2_s"] - a["drop_MDEP_kg_m2_s"]),
            "all_other_source_contrast_after_fixed_allocation_deposition_delta_kg_m2_s": total - a["wave_source_deposition_coefficient_with_internal_exchange"] * (b["drop_MDEP_kg_m2_s"] - a["drop_MDEP_kg_m2_s"]),
            "frozen_feedback_plus_old_wave_relaxation_only_at_99_and_100": [a["frozen_feedback_plus_old_wave_relaxation_only"], b["frozen_feedback_plus_old_wave_relaxation_only"]],
            "wave_proposal_decomposition_from_saved_cycle": cycle_by_node[node]["proposal_contrast"]["wave_proposal_delta_100_minus_99"],
        })
    bindings = [directory / name for name in ("assessment.json", "closure_trace.jsonl.gz", "update_trace.jsonl", "effective_inputs.json", "frozen_manifest.json", "deep_trace_schema.json")] + [saved_cycle]
    return {
        "schema": "openstream-sawai-deposition-cycle-analysis-v1",
        "input_sha256": {str(p.relative_to(ROOT)).replace("\\", "/"): digest(p) for p in bindings},
        "analysis_tool_sha256": digest(Path(__file__).resolve()),
        "solver_executed": False, "observed_records": len(records), "groups": len(groups),
        "observer_exact_numeric_equality": True,
        "all_66_source_sums_exact": True,
        "source_term_units": UNITS,
        "max_internal_exchange_algebra_difference_kg_m2_s": max(abs(p["internal_exchange_algebra_difference_kg_m2_s"]) for p in all_phases),
        "phases": all_phases, "contrasts": contrasts,
        "interpretation_limits": [
            "Actual constituent returns identify the source swing; attribution fractions compare two coupled states and are not a perturbation experiment.",
            "The signed Okawa partial slope freezes vapor mass, fluid properties, geometry, annular blending, base/wave allocation and all other source/momentum feedback. The resulting scalar gain is not an eigenvalue of the full sequential iteration.",
            "The fixed physical-precursor blending factor is inferred as recorded DELTAFREQ return divided by its unblended local value. This floating-point ratio is approximate and is not a new convergence criterion.",
            "Wave-source states precede the algebraic droplet-mass update in each point iteration; final plotted droplet states are later in the same iteration.",
            "The source retains negative droplet flow and its signed deposition. No clamp, extra closure, relaxed tolerance, or equation change is introduced by this audit.",
            "No matched MATLAB Sawai run exists; the behavior of that runtime remains unverified.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=STUDY / "deep-trace")
    parser.add_argument("--saved-cycle", type=Path, default=STUDY / "saved_cycle_analysis.json")
    parser.add_argument("--output", type=Path, default=STUDY / "deposition_cycle_analysis.json")
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite evidence: {args.output}")
    result = analyze(args.directory.resolve(), args.saved_cycle.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "groups": result["groups"], "all_66_source_sums_exact": True, "contrasts": result["contrasts"]}, indent=2))


if __name__ == "__main__":
    main()
