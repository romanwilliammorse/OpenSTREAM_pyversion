"""Audit diagnostic cancellation using saved states, without changing a solver.

Reconstructs the exact source diagnostic expressions from archived and native
initialization arrays. It reports residual differences and never changes the
strict reference acceptance result or applies a new tolerance.
"""
import argparse
import json
from pathlib import Path

import numpy as np


def reconstruct(a, area):
    w, u, up, h, rho = [a[k] for k in ("W", "U", "UP", "H", "RHO")]
    dz = a["Z"][1] - a["Z"][0]
    dt = np.diff(a["TIME"])[:, None]
    mct = (u - up) * w / u
    out = {}
    # Index zero is the prescribed inlet, where the source diagnostics retain
    # their initialized zero values. The first pseudo state has no advance.
    out["DP.Acc_z"] = w[1:, 1:] / area * np.diff(up[1:], axis=1)
    out["DP.Acc_t"] = rho[1:, 1:] * np.diff(up, axis=0)[:, 1:] * dz / dt
    out["DP.Acc_s"] = 1 / area * np.diff(mct, axis=0)[:, 1:] * dz / dt
    out["MDER.U_z"] = u[1:, 1:] * np.diff(up[1:], axis=1) / dz
    out["MDER.U_t"] = np.diff(up, axis=0)[:, 1:] / dt
    out["MDER.U"] = out["MDER.U_z"] + out["MDER.U_t"]
    out["MDER.H_z"] = u[1:, 1:] * np.diff(h[1:], axis=1) / dz
    out["MDER.H_t"] = np.diff(h, axis=0)[:, 1:] / dt
    out["MDER.H"] = out["MDER.H_z"] + out["MDER.H_t"]
    for key in ("Acc_s", "Acc_t"):
        out["DPSUM." + key] = np.cumsum(out["DP." + key], axis=1)
    return out


def audit(reference, native):
    manifest = json.loads((reference / "manifest.json").read_text())
    metadata = json.loads((native / "metadata.json").read_text())
    area = metadata["inputs"]["geometry"]["AREA"]
    if area != manifest["effective_inputs"]["geometry"]["AREA"]:
        raise ValueError("Mismatched reference/native channel area")
    with np.load(reference / "initialization.npz") as archive, np.load(native / "initialization.npz") as calculated:
        reference_values, native_values = reconstruct(archive, area), reconstruct(calculated, area)
        rows = {}
        for key in reference_values:
            stored_ref, stored_native = archive[key][1:, 1:], calculated[key][1:, 1:]
            recomputed_ref, recomputed_native = reference_values[key], native_values[key]
            rows[key] = {
                "unit": manifest["units"][key],
                "max_stored_difference": float(np.max(abs(stored_native - stored_ref))),
                "max_reference_reconstruction_residual": float(np.max(abs(recomputed_ref - stored_ref))),
                "max_native_reconstruction_residual": float(np.max(abs(recomputed_native - stored_native))),
                "max_difference_unexplained_by_saved_state_reconstruction": float(np.max(abs(
                    (stored_native - stored_ref) - (recomputed_native - recomputed_ref)))),
                "nonmatching_reference_zeros": int(np.count_nonzero((stored_ref == 0) & (stored_native != 0))),
            }
        iteration_rows = {}
        for key, state in (("ITR.DW", "W"), ("ITR.DP", "P"), ("ITR.DH", "H")):
            delta = abs(calculated[key][1:, 1:] - archive[key][1:, 1:])
            spacing = np.spacing(np.abs(archive[state][1:, 1:]))
            iteration_rows[key] = {
                "unit": manifest["units"][key],
                "max_absolute_difference": float(np.max(delta)),
                "max_difference_in_ulps_of_stored_state": float(np.max(delta / spacing)),
                "note": "Iteration-old state is not archived; this quantifies scale, not exact causal reconstruction.",
            }
    return {
        "scope": "All nine pseudo-time advances, 100 non-inlet nodes; preserved original reference",
        "source_expressions": "Mixture/solve.m MDER, Mixture.m DPACCZ/DPACCT/DPACCS and cumsum",
        "diagnostic_reconstructions": rows,
        "iteration_increment_scale": iteration_rows,
        "acceptance": "No acceptance tolerances changed. The 14 strict supplementary failures remain failures.",
        "limits": "The archived producing CoolProp version and operation-level execution trace are unknown. This does not prove bitwise equivalence.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("native", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = audit(args.reference, args.native)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result, indent=2))
