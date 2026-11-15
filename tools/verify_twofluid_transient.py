"""Execute Tutorial 3's original 0–5 s two-fluid transient and report defects.

Numerical convergence, discrete balances and physical consistency are
different checks. This script retains actual failures without changing the
upstream equations or controls. MATLAB agreement is unverified.
"""
import argparse
import json
from pathlib import Path
import warnings
import numpy as np
from openstream import InputSet, TwoFluidSolver
from openstream.output import portable_json, source_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): raise FileExistsError(args.output)
    root = Path(__file__).resolve().parents[1]/"upstream"/"inputs"
    inputs = InputSet.from_files(root/"models.inp", "TUTORIAL3B", root/"options.inp", "DEFAULT",
                                root/"geom.inp", "TUTORIAL1", root/"tutorial2_transient.inp")
    def progress(record):
        if record["phase"] == "initialization" or np.isclose(record["time_s"] % 1, 0):
            print(json.dumps(record), flush=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        solver = TwoFluidSolver(inputs).solve(progress)
        solver.save(args.output)
        residuals = []
        for k in range(1, solver.NTIME):
            l, v = solver.liquid[k], solver.vapor[k]
            row = dict(time_s=float(solver.TIME[k]))
            for label, phase, other, old, pre in (
                ("liquid", l, v, solver.liquid[k-1], solver.mixSolver.mixture[k].liquid),
                ("vapor", v, l, solver.vapor[k-1], solver.mixSolver.mixture[k].vapor)):
                inventory = phase.W[1:]/phase.U[1:]
                old_inventory = old.W[1:]/old.U[1:]
                source_mass = np.sum(phase.MTOT(other), axis=-1)[1:]
                source_heat = np.sum(phase.HTOT(other), axis=-1)[1:]
                source_force = np.sum(phase.FTOT(other), axis=-1)[1:]
                mass = np.diff(phase.W)/solver.DZ+(inventory-old_inventory)/solver.DT-source_mass
                heat = inventory*(phase.H[1:]-old.H[1:])/solver.DT+phase.W[1:]*np.diff(phase.H)/solver.DZ-source_heat
                momentum = inventory*(phase.U[1:]-old.U[1:])/solver.DT+phase.W[1:]*np.diff(phase.U)/solver.DZ-source_force
                # The upstream 0.001 kg/s source suppression and velocity
                # bounds invalidate unrestricted momentum/enthalpy equations.
                active = phase.W[1:] > 1e-3
                # Reconstruct the unconstrained update at the final state.
                # Being below the upper bound alone is insufficient: under-
                # relaxation can stop just short of a repeatedly clipped bound.
                trial = (phase.U[1:]*phase.U[:-1]+old.U[1:]*solver.DZ/solver.DT
                         +source_force/inventory*solver.DZ)/(phase.U[1:]+solver.DZ/solver.DT)
                unbounded = (phase.W[1:] > 1e-3+solver.inputSet.options.ERRORW) & (trial > 0) & (trial < 1.5*pre.U()[1:])
                row[label] = dict(max_mass_residual_kg_s_m=float(np.max(abs(mass))),
                                  max_heat_residual_W_m=float(np.max(abs(heat))),
                                  max_active_heat_residual_W_m=float(np.max(abs(heat[active]))) if np.any(active) else None,
                                  max_momentum_residual_N_m=float(np.max(abs(momentum))),
                                  max_unbounded_momentum_residual_N_m=float(np.max(abs(momentum[unbounded]))) if np.any(unbounded) else None,
                                  heat_cutoff_cells=int(np.count_nonzero(~active)),
                                  bounded_or_cutoff_momentum_cells=int(np.count_nonzero(~unbounded)))
            residuals.append(row)
    states = solver.liquid+solver.vapor
    report = dict(case="Tutorial 3 transient: TUTORIAL3B + tutorial2_transient.inp", reference_comparison="unverified",
                  experimental_validation="not performed", native_source_sha256=source_hashes(),
                  state=solver.STATE.name, converged=bool(solver.converged), stored_times=solver.NTIME, stored_nodes=solver.NZ,
                  all_physical_steps_point_converged=all(r["point_converged"] for r in solver.history if r["phase"]=="transient"),
                  nonfinite_primary_count=sum(int(np.count_nonzero(~np.isfinite(getattr(p,key)))) for p in states for key in ("W","U","H")),
                  min_mass_kg_s=float(min(np.min(p.W) for p in states)), min_velocity_m_s=float(min(np.min(p.U) for p in states)),
                  diagnostics=solver.diagnostics(), per_time_discrete_residuals=residuals,
                  residual_note="Post-step source evaluation. Unrestricted values retain source-cutoff and velocity-bound defects. Unbounded momentum mask requires a final-state reconstructed trial inside the source velocity bounds and phase flow above cutoff+ERRORW; it is not a log of every inner iteration. No residual acceptance is inferred from point-change convergence.",
                  warnings=sorted(set(str(w.message) for w in caught)))
    (args.output/"verification.json").write_text(json.dumps(portable_json(report), indent=2, allow_nan=False)+"\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("state", "converged", "stored_times", "stored_nodes", "all_physical_steps_point_converged", "nonfinite_primary_count", "min_mass_kg_s", "min_velocity_m_s", "warnings")}), flush=True)
    if not solver.converged: return 2
    if solver.diagnostics()["physical_consistency"] is False: return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
