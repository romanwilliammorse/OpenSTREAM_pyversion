"""Posthoc fixed-coordinate diagnostic for the frozen Le Corre campaign.

This reads saved arrays only. It was introduced after observing that the source
AFFNC transition changes physical width with mesh size. No original run, pairwise
metric, governing equation, input, numerical tolerance or acceptance rule changes.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sample(z, values, annular_fraction, position, require_annular):
    """Interpolate only through finite, eligible brackets inside the domain."""
    if position < z[0] or position > z[-1]:
        return None
    right = bisect_left(z, position)
    left = right if z[right] == position else right - 1
    if any(not math.isfinite(values[index]) for index in (left, right)):
        return None
    if require_annular and any(not math.isfinite(annular_fraction[index]) or annular_fraction[index] < 1 - 1e-12 for index in (left, right)):
        return None
    if left == right:
        return float(values[right])
    weight = (position - z[left]) / (z[right] - z[left])
    return float(values[left] * (1 - weight) + values[right] * weight)


def stats(values):
    if not values:
        return {"n": 0, "bias": None, "mae": None, "rmse": None, "max_absolute_difference": None}
    return {"n": len(values), "bias": math.fsum(values) / len(values),
            "mae": math.fsum(abs(value) for value in values) / len(values),
            "rmse": math.sqrt(math.fsum(value * value for value in values) / len(values)),
            "max_absolute_difference": max(abs(value) for value in values)}


def diagnose(directory):
    report_bytes = (directory / "report.json").read_bytes()
    report = json.loads(report_bytes)
    manifest_bytes = (directory / "frozen_manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    if report["counts"]["attempted"] != manifest["expected_attempts"]["total"]:
        raise ValueError("The final diagnostic requires all frozen attempts to be accounted for")
    output = []
    for sentinel in manifest["study"]["sentinels"]:
        case_id = sentinel["case_id"]
        ids = {"100": case_id + "-n100-base", "200": case_id + "-n200-mesh",
               "400": case_id + "-n400-mesh", "100_tight": case_id + "-n100-tight"}
        states = {label: report["runs"][identity] for label, identity in ids.items()}
        entry = {"case_id": case_id, "runs": ids,
                 "source_states": {label: state.get("source_state") for label, state in states.items()},
                 "native_converged": {label: state["native_converged"] for label, state in states.items()},
                 "physical_status_unchanged": {label: state.get("physical", {}).get("status") for label, state in states.items()}}
        unavailable = [ids[label] for label, state in states.items()
                       if state["execution"] != "completed" or not state["native_converged"]]
        if unavailable:
            entry.update(status="unavailable", reason="All four configurations must have completed and converged natively",
                         disqualifying_runs=unavailable, quantities={})
            output.append(entry)
            continue
        profiles, units = {}, {}
        source_domains = {}
        for label, identity in ids.items():
            with np.load(directory / identity / "comparison_profiles.npz", allow_pickle=False) as archive:
                profiles[label] = {key: archive[key].copy() for key in archive.files}
            units[label] = json.loads((directory / identity / "comparison_units.json").read_text(encoding="utf-8"))
            inputs = json.loads((directory / identity / "effective_inputs.json").read_text(encoding="utf-8"))
            z, fraction = profiles[label]["Z"], profiles[label]["AFFNC"]
            if z.ndim != 1 or not np.all(np.isfinite(z)) or not np.all(np.diff(z) > 0):
                raise ValueError(f"Invalid spatial coordinates: {identity}")
            eligible = np.flatnonzero(fraction >= 1 - 1e-12)
            dz = inputs["geometry"]["LENGTH"] / inputs["model"]["NNODES"]
            width_parameter = inputs["model"]["OAFTRANSITION"][0]
            source_domains[label] = {
                "channel_lower_m": float(z[0]), "channel_upper_m": float(z[-1]),
                "first_fully_annular_node_m": float(z[eligible[0]]) if eligible.size else None,
                "last_fully_annular_node_m": float(z[eligible[-1]]) if eligible.size else None,
                "fully_annular_node_count": int(eligible.size), "uniform_cell_length_m": dz,
                "stored_OAFTRANSITION": inputs["model"]["OAFTRANSITION"],
                "source_logistic_characteristic_length_m": dz * dz / width_parameter if width_parameter > 0 else None}
        entry["source_domains"] = source_domains
        basis = profiles["100"]["Z"]
        if any(set(profiles[label]) != set(profiles["100"]) for label in profiles):
            raise ValueError(f"Mismatched saved quantities: {case_id}")
        quantities = {}
        for key in profiles["100"]:
            if key in ("Z", "AFFNC"):
                continue
            if len({units[label][key] for label in units}) != 1:
                raise ValueError(f"Mismatched units: {case_id}, {key}")
            annular = key.startswith(("film.", "base.", "wave.", "drop."))
            paired, coordinates = {label: [] for label in ids}, []
            excluded_indices = []
            for index, position in enumerate(basis):
                values = {label: sample(profile["Z"], profile[key], profile["AFFNC"], position, annular)
                          for label, profile in profiles.items()}
                if any(value is None for value in values.values()):
                    excluded_indices.append(index)
                    continue
                coordinates.append(float(position))
                for label, value in values.items():
                    paired[label].append(value)
            differences = {}
            for left, right, name in (("100", "200", "100_to_200"), ("200", "400", "200_to_400"),
                                      ("100", "100_tight", "100_to_100_tight")):
                differences[name] = stats([b - a for a, b in zip(paired[left], paired[right])])
            quantities[key] = {"unit": units["100"][key], "annular_bracket_gate_applied": annular,
                               "status": "descriptive_diagnostic" if coordinates else "no_common_eligible_coordinates",
                               "coarse_coordinates_total": len(basis), "n_eligible": len(coordinates),
                               "n_excluded": len(excluded_indices), "excluded_coarse_indices_zero_based": excluded_indices,
                               "eligible_coordinates_m": coordinates,
                               "lower_eligible_m": min(coordinates) if coordinates else None,
                               "upper_eligible_m": max(coordinates) if coordinates else None,
                               "differences_right_minus_left": differences}
        entry.update(status="descriptive_diagnostic", quantities=quantities)
        output.append(entry)
    sources = {}
    for path in (ROOT / "upstream/+Solvers/+Mixture/Mixture.m", ROOT / "upstream/+Inputs/Model.m", ROOT / "src/openstream/fields.py"):
        sources[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    return {"schema": "openstream-lecorre-common-domain-diagnostic-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
            "timing": "Posthoc read-only diagnostic prompted by observed changes in pairwise annular eligibility domains.",
            "report_sha256": hashlib.sha256(report_bytes).hexdigest(),
            "manifest_sha256_lf": hashlib.sha256(manifest_bytes.replace(b"\r\n", b"\n")).hexdigest(),
            "diagnostic_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "policy": {"coordinate_basis": "Original 100-cell axial coordinates for every difference in a sentinel",
                       "required_configurations": ["100", "200", "400", "100_tight"],
                       "required_native_convergence": "All four configurations, with no original failure relabeled",
                       "eligibility": "Intersection of finite interpolation brackets in all four profiles; annular fields also require both bracket nodes AFFNC >= 1-1e-12",
                       "extrapolation": False, "original_pairwise_metrics_modified": False,
                       "acceptance_threshold_added": False, "convergence_order_claimed": False,
                       "scope": "Descriptive finite-grid differences only. No MATLAB, physical, experimental or mesh-independence pass."},
            "source_transition_scaling": {
                "references": {"upstream_AFFNC": "upstream/+Solvers/+Mixture/Mixture.m:2153",
                               "upstream_logistic": "upstream/+Solvers/+Mixture/Mixture.m:2206",
                               "upstream_parameter_units": "upstream/+Inputs/Model.m:24",
                               "python_AFFNC": "src/openstream/fields.py:530"},
                "source_sha256_lf": sources,
                "derivation": "Let dz=L/N, w=OAFTRANSITION[0], offset=OAFTRANSITION[1]. Source p=(w,offset)/dz and logistic argument p0*(node-onset-p1) imply logit a=w*(z-z_onset-offset)/dz^2, with AFFNC=1/(1+exp(-a)). For positive w, characteristic physical transition length is dz^2/w; doubling N divides it by four.",
                "interpretation": "Source-matched mesh-dependent blending; the input comment calls w a width in metres. This is a documented parameter-semantics concern, not a repaired translation or proof of new-case MATLAB equivalence. Refinement changes the transition profile as well as discretization; fixed-coordinate diagnostics do not remove that confounding."},
            "summary": {"sentinels": len(output), "eligible_sentinels": sum(e["status"] == "descriptive_diagnostic" for e in output),
                        "unavailable_sentinels": sum(e["status"] == "unavailable" for e in output)},
            "sentinels": output}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    result = diagnose(args.campaign)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(result["summary"]))


if __name__ == "__main__":
    main()
