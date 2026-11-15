"""Diagnose the retained Sawai two-cycle from saved observations only.

No OpenSTREAM or property-backend import and no solver execution. This audit
does not classify MATLAB equivalence or introduce a convergence tolerance.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASE = ROOT / "outputs/verification/matched-replay-01/native-after/sawai-01-paper-tw020-n100-base"
DEFAULT_OUTPUT = ROOT / "outputs/verification/sawai-oscillation-01/saved_cycle_analysis.json"
STATE_UNITS = {"base_W": "kg/s", "base_U": "m/s", "wave_W": "kg/s",
               "wave_U": "m/s", "wave_F": "Hz", "drop_W": "kg/s", "drop_U": "m/s"}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(value):
    if isinstance(value, list):
        if len(value) != 1:
            raise ValueError(f"Expected a single-wall scalar: {value!r}")
        return scalar(value[0])
    return float(value)


def unique(rows, stage=None, method=None):
    selected = [r for r in rows if (stage is None or r["stage"] == stage)
                and (method is None or r.get("method") == method)]
    if len(selected) != 1:
        raise ValueError(f"Expected one {stage=} {method=}; found {len(selected)}")
    return selected[0]


def proposal_terms(record, source, perimeter, prefix):
    """Units: advective/transient + source contributions each kg/s."""
    loc = record["locals"]
    u = scalar(loc["ub" if prefix == "wb" else "uw"])
    u_old = scalar(loc["ub_old" if prefix == "wb" else "uw_old"])
    w_up, w_old = scalar(loc[prefix + "_up"]), scalar(loc[prefix + "_old"])
    dz, dt = loc["dz"], loc["dt"]
    transient = w_old / u_old * dz / dt
    mass_source = perimeter * source * dz
    denominator = u + dz / dt
    reconstructed = u * (w_up + transient + mass_source) / denominator
    recorded = scalar(loc[prefix + "_new"])
    return {
        "recorded_kg_s": recorded,
        "reconstructed_kg_s": reconstructed,
        "reconstruction_difference_kg_s": reconstructed - recorded,
        "exact_reconstruction": reconstructed == recorded,
        "transport_and_old_state_kg_s": u * (w_up + transient) / denominator,
        "source_kg_s": u * mass_source / denominator,
        "source_to_proposal_factor_m2": u * perimeter * dz / denominator,
    }


def analyze(case):
    required = [case / "effective_inputs.json", case / "point_trace.csv",
                case / "update_trace.jsonl", case / "temporal_trace.json"]
    hashes_before = {str(p.relative_to(ROOT)): sha256(p) for p in required}
    inputs = json.loads(required[0].read_text())
    model, options = inputs["model"], inputs["options"]
    if model["NNODES"] != 100 or model["RELAXTW"] != .2:
        raise ValueError("This analysis is registered for Sawai tau=0.2 s, 100 cells")
    perimeter = scalar(inputs["geometry"]["PERIM"])
    with required[1].open(newline="") as handle:
        points = list(csv.DictReader(handle))
    final_time = max(float(p["time_s"]) for p in points)
    final_points = [p for p in points if float(p["time_s"]) == final_time]
    point_keys = {(int(p["node_zero_based"]), int(p["iteration"])): p for p in final_points}
    if len(point_keys) != len(final_points):
        raise ValueError("Duplicate final-time point records")
    late = defaultdict(list)
    with required[2].open() as handle:
        for line in handle:
            record = json.loads(line)
            if record["time_s"] == final_time and record["node_zero_based"] in (24, 25, 26) and record["iteration"] >= 91:
                late[(record["node_zero_based"], record["iteration"])].append(record)
    nodes = []
    for node in (24, 25, 26):
        iterations = []
        for iteration in range(91, 101):
            rows = late[(node, iteration)]
            bp = unique(rows, "base_mass_proposal")
            wp = unique(rows, "wave_mass_proposal")
            pre = unique(rows, "before_clipping")
            post = unique(rows, "after_clipping")
            base_after = unique(rows, "after_base_momentum")
            end = unique(rows, "point")
            secant = unique(rows, method="AnnularField._secant")
            b_source = scalar(unique(rows, method="Base.MTOT")["return_value"])
            w_source = scalar(unique(rows, method="Wave.MTOT")["return_value"])
            point = point_keys[(node, iteration)]
            thickness = scalar(base_after["locals"]["thick"])
            # Compute thickness independently at the actual pre-momentum state.
            frequency_after = unique(rows, "after_frequency")
            thickness_from_state = frequency_after["base_W"] / perimeter / frequency_after["base_U"] / bp["locals"]["rho"]
            item = {
                "iteration": iteration,
                "state": {k: end[k] for k in STATE_UNITS},
                "base_MTOT_kg_m2_s": b_source,
                "wave_MTOT_kg_m2_s": w_source,
                "base_proposal": proposal_terms(bp, b_source, perimeter, "wb"),
                "wave_proposal": proposal_terms(wp, w_source, perimeter, "ww"),
                "wave_FTOT_Pa": scalar(unique(rows, method="Wave.FTOT")["return_value"]),
                "wave_deltafreq_Hz_m": scalar(unique(rows, method="Wave.DELTAFREQ")["return_value"]),
                "clipping_change_base_kg_s": post["base_W"] - pre["base_W"],
                "clipping_change_wave_kg_s": post["wave_W"] - pre["wave_W"],
                "thin_base_momentum": {
                    "thickness_m": thickness,
                    "thickness_reconstructed_m": thickness_from_state,
                    "threshold_m": model["THINFILMTHICK"],
                    "thin_branch": thickness <= model["THINFILMTHICK"],
                    "secant_final_force_abs_Pa": secant["locals"]["error"],
                    "secant_tolerance_Pa": secant["locals"]["tolerance"],
                    "secant_reported_loop_index": secant["locals"]["_"],
                    "secant_trial_U_m_s": scalar(secant["locals"]["u2"]),
                    "returned_blended_U_m_s": scalar(secant["return_value"]),
                },
                "point_increments": {k: float(point[k]) for k in ("dWLb", "dUb", "dWLw", "dUw", "dFw", "dUd")},
                "failed_point_criteria": [k for k in ("dWLb", "dUb", "dWLw", "dUw", "dFw", "dUd")
                                          if float(point[k]) >= float(point["threshold_" + k])],
            }
            # Relaxation is inspected separately from source decomposition.
            item["wave_relaxation_exact"] = (.5 * wp["wave_W"] + .5 * item["wave_proposal"]["recorded_kg_s"] == pre["wave_W"])
            if options["RELAXWW"] != .5:
                raise ValueError("Recorded relaxation differs from registered case")
            iterations.append(item)
        odd, even = iterations[-2:]
        p2diff = {k: max(abs(iterations[j]["state"][k] - iterations[j-2]["state"][k])
                        for j in range(2, len(iterations))) for k in STATE_UNITS}
        contrasts = {}
        for field in ("base", "wave"):
            p_odd, p_even = odd[field + "_proposal"], even[field + "_proposal"]
            s_odd, s_even = odd[field + "_MTOT_kg_m2_s"], even[field + "_MTOT_kg_m2_s"]
            k_odd, k_even = p_odd["source_to_proposal_factor_m2"], p_even["source_to_proposal_factor_m2"]
            relaxation = options["RELAXWB" if field == "base" else "RELAXWW"]
            contrasts[field + "_proposal_delta_100_minus_99"] = {
                **{key: p_even[key] - p_odd[key]
                   for key in ("recorded_kg_s", "transport_and_old_state_kg_s", "source_kg_s")},
                "MTOT_change_at_iteration99_coefficient_kg_s": k_odd * (s_even - s_odd),
                "coefficient_and_transport_change_kg_s": (k_even - k_odd) * s_even + p_even["transport_and_old_state_kg_s"] - p_odd["transport_and_old_state_kg_s"],
                "iteration99_relaxed_source_coefficient_m2": relaxation * k_odd,
                "relaxed_MTOT_change_at_iteration99_coefficient_kg_s": relaxation * k_odd * (s_even - s_odd),
                "interpretation": "An exact algebraic decomposition up to floating-point rounding, holding the iteration-99 source coefficient for the first term; not a perturbation experiment or a full-map Jacobian.",
            }
        nodes.append({
            "node_zero_based": node, "node_one_based": node + 1,
            "z_m": float(point_keys[(node, 100)]["z_m"]),
            "late_iteration_window": [91, 100],
            "period_two_max_return_difference": p2diff,
            "last_pair_absolute_state_difference": {k: abs(even["state"][k] - odd["state"][k]) for k in STATE_UNITS},
            "wave_flow_increment_over_threshold": even["point_increments"]["dWLw"] / options["ERRORWF"],
            "drop_flow_crosses_zero_in_last_pair": odd["state"]["drop_W"] * even["state"]["drop_W"] < 0,
            "all_late_thin_base": all(x["thin_base_momentum"]["thin_branch"] for x in iterations),
            "all_late_secant_within_source_tolerance": all(x["thin_base_momentum"]["secant_final_force_abs_Pa"] < x["thin_base_momentum"]["secant_tolerance_Pa"] for x in iterations),
            "max_late_clipping_change_base_kg_s": max(abs(x["clipping_change_base_kg_s"]) for x in iterations),
            "max_late_clipping_change_wave_kg_s": max(abs(x["clipping_change_wave_kg_s"]) for x in iterations),
            "proposal_contrast": contrasts,
            "iterations": iterations,
        })
    hashes_after = {str(p.relative_to(ROOT)): sha256(p) for p in required}
    if hashes_before != hashes_after:
        raise ValueError("Input evidence changed while reading")
    latest = {}
    for point in final_points:
        node = int(point["node_zero_based"])
        if node not in latest or int(point["iteration"]) > int(latest[node]["iteration"]):
            latest[node] = point
    return {
        "schema": "openstream-sawai-saved-cycle-analysis-v1",
        "evidence_type": "read-only saved native observations and independently reconstructed update arithmetic",
        "solver_executed": False, "governing_equations_changed": False,
        "input_sha256": hashes_before,
        "analysis_tool_sha256": sha256(Path(__file__).resolve()),
        "source_for_formula_sha256": {str(p.relative_to(ROOT)): sha256(p) for p in [ROOT / "src/openstream/fourfield.py", ROOT / "src/openstream/annular.py", ROOT / "src/openstream/ff_fields.py"]},
        "final_time_s": final_time, "wetted_perimeter_m": perimeter,
        "point_thresholds": {k: options[k] for k in ("ERRORWF", "ERRORUF", "ERRORUD", "ERRORFW")},
        "state_units": STATE_UNITS,
        "point_increment_units": {"dWLb": "kg/(s m)", "dUb": "m/s", "dWLw": "kg/(s m)", "dUw": "m/s", "dFw": "Hz", "dUd": "m/s"},
        "selected_trace_nodes_at_final_time": sorted(latest),
        "selected_nodes_failing_final_point_predicate": sorted(n for n, p in latest.items() if p["all_point_criteria_pass"] != "True"),
        "all_60_mass_proposals_exactly_reconstructed": all(it[f + "_proposal"]["exact_reconstruction"] for n in nodes for it in n["iterations"] for f in ("base", "wave")),
        "nodes": nodes,
        "interpretation": [
            "All three failed nodes exhibit a persistent late period-two waveform; reported differences are descriptive, not a new convergence criterion.",
            "The wave mass proposal alternates chiefly through its total source contribution; positive-film clipping leaves wave flow unchanged in these late iterations.",
            "Signed droplet flow alternates across zero at every failed node, while both iterations use a successful thin-base secant solve.",
            "Individual evaporation, entrainment, deposition and internal exchange terms were not present in this saved trace. Their responsibility cannot be uniquely assigned from these totals.",
        ],
        "next_trace_requirements": [
            "Capture actual Drop.CONC and Drop.MDEP returns, film MENT/MEVAP, and Base/Wave MDEP, MWAVE, MBASE returns at each wave-mass proposal.",
            "Capture actual branch/cap operands and nested force constituents without calling extra lazy property getters.",
            "Confirm observer invariance by comparing every saved numerical array with this retained native replay.",
        ],
        "limits": [
            "No matched MATLAB Sawai execution is available; this receipt establishes neither MATLAB equivalence nor that MATLAB exhibits the same cycle.",
            "Same-state cancellation of internal exchange does not imply exact cancellation across the sequential base and wave proposals.",
            "Point increments and their tolerances are the source iteration controls, not physical balance residuals or experimental validation.",
        ],
    }


def plot_cycle(case, result, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    iterations = result["nodes"][0]["iterations"]
    x = [p["iteration"] for p in iterations]
    fig, axes = plt.subplots(2, 2, figsize=(10.2, 7.0), constrained_layout=True)
    blue, orange = "#0072B2", "#D55E00"
    axes[0, 0].plot(x, [p["state"]["wave_W"] for p in iterations], "o-", color=blue, label="Node 24; z = 0.39552 m")
    axes[0, 0].set_ylabel("Wave mass flow [kg/s]")
    axes[0, 0].legend(frameon=False, loc="upper center", bbox_to_anchor=(.5, 1.14), fontsize=9)
    axes[0, 1].plot(x, [p["state"]["drop_W"] for p in iterations], "o-", color=orange)
    axes[0, 1].axhline(0, color="0.4", lw=1, linestyle="--")
    axes[0, 1].set_ylabel("Droplet mass flow [kg/s]")
    axes[1, 0].plot(x, [p["wave_MTOT_kg_m2_s"] for p in iterations], "o-", color=blue)
    axes[1, 0].set_ylabel("Wave total mass source [kg/(m² s)]")
    for axis in (axes[0, 0], axes[0, 1], axes[1, 0]):
        axis.set_xlabel("Point iteration")
        axis.set_xticks([91, 93, 95, 97, 99, 100])
    with (case / "point_trace.csv").open(newline="") as handle:
        points = [p for p in csv.DictReader(handle) if float(p["time_s"]) == result["final_time_s"]]
    latest = {}
    for point in points:
        latest[int(point["node_zero_based"])] = point
    ordered = [latest[node] for node in sorted(latest)]
    axes[1, 1].semilogy([float(p["z_m"]) for p in ordered], [float(p["dWLw"]) for p in ordered], "o-", color=blue, label="Final point increment")
    axes[1, 1].axhline(result["point_thresholds"]["ERRORWF"], color=orange, linestyle="--", label="Source tolerance")
    axes[1, 1].set_xlabel("Axial position [m]")
    axes[1, 1].set_ylabel("Wave flow increment / perimeter [kg/(s m)]")
    axes[1, 1].legend(frameon=False, fontsize=9)
    for axis in axes.flat:
        axis.grid(alpha=.2)
    axes[0, 0].ticklabel_format(axis="y", style="sci", scilimits=(0, 0), useOffset=False)
    axes[0, 1].ticklabel_format(axis="y", style="sci", scilimits=(0, 0), useOffset=False)
    fig.savefig(output, dpi=180)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, default=DEFAULT_CASE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--plot", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"Refusing to overwrite evidence: {args.output}")
    if args.plot and args.plot.exists():
        raise FileExistsError(f"Refusing to overwrite evidence: {args.plot}")
    result = analyze(args.case.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.plot:
        args.plot.parent.mkdir(parents=True, exist_ok=True)
        plot_cycle(args.case.resolve(), result, args.plot)
        result["plot"] = {"path": str(args.plot), "sha256": sha256(args.plot)}
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "mass_proposals_exact": result["all_60_mass_proposals_exactly_reconstructed"],
                      "nodes": [{k: node[k] for k in ("node_zero_based", "z_m", "wave_flow_increment_over_threshold", "drop_flow_crosses_zero_in_last_pair")} for node in result["nodes"]]}, indent=2))


if __name__ == "__main__":
    main()
