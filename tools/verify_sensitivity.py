r"""Reproducible native verification; does not assert MATLAB equivalence.

Run from the repository root with the installed project environment::

    .\.venv\Scripts\python.exe tools/verify_sensitivity.py --output outputs/verification/native-sensitivity-01

The output directory must not exist. Every completed case is saved separately;
exceptions and nonconvergence are retained in the aggregate report.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import traceback
import warnings

import numpy as np

from openstream import BoundaryConditions, InputSet, MixtureSolver
from openstream.output import balances, portable_json

ROOT = Path(__file__).resolve().parents[1]


def physical_bounds(solver):
    """Bounds over every physical time and node; no experimental validation."""
    states = solver.mixture
    values = {name: np.concatenate([np.asarray(getattr(m, name)() if callable(getattr(m, name)) else getattr(m, name)).ravel()
                                   for m in states]) for name in ("P", "W", "H", "RHO", "X", "VF")}
    return {"all_finite": bool(all(np.all(np.isfinite(a)) for a in values.values())),
            "min_pressure_Pa": float(values["P"].min()), "min_mass_flow_kg_s": float(values["W"].min()),
            "min_density_kg_m3": float(values["RHO"].min()),
            "min_quality": float(values["X"].min()), "max_quality": float(values["X"].max()),
            "min_void": float(values["VF"].min()), "max_void": float(values["VF"].max()),
            "max_phase_mass_split_error_kg_s": max(float(np.max(np.abs(m.liquid.W()+m.vapor.W()-m.W))) for m in states)}


def transient_balances(solver):
    """Evaluate source discrete equations and an independent integral balance.

    m'=rho*A has units kg/m. The upstream energy equation transports enthalpy
    in advective form. Its finite differences do not satisfy an exact discrete
    product rule. Therefore the conservative stored-enthalpy balance below can
    be nonzero even when the implemented source equation has converged.

    For homogeneous equilibrium (MCT=ECT=0), the conservative energy defect is
    exactly the source-energy residual plus two explicitly reported terms:

        sum(r_mass*H_upstream) + sum(dm'/dt*(H_old-H_upstream))*dz.

    No total-energy (kinetic/potential energy) or compressible pressure-work
    validation is implied; those terms are absent from this source equation.
    """
    rows = []
    g = solver.inputSet.geometry
    for old, current in zip(solver.mixture, solver.mixture[1:]):
        dz, dt = solver.DZ, current.DT
        w, h, old_w, old_h = current.W, current.H, old.W, old.H
        mass_per_length = g.AREA * current.RHO()
        old_mass_per_length = g.AREA * old.RHO()
        dmass_dt = (mass_per_length[1:] - old_mass_per_length[1:]) / dt
        source = current.HFLUX[1:] @ g.PERIM
        mass_residual = np.diff(w) + dmass_dt * dz  # kg/s
        ect_change = (current.ECT()[1:] - old.ECT()[1:]) / dt  # W/m
        energy_residual = (w[1:] * np.diff(h) / dz + mass_per_length[1:] * (h[1:] - old_h[1:]) / dt
                           + ect_change - source)  # W/m
        # Independent HEM momentum reconstruction, avoiding DPTOT/DPPARTS.
        if solver.inputSet.model.VOID == "HOMOGENEOUS" and solver.inputSet.model.TPFM == "HOMOGENEOUS":
            rho = current.RHO()[1:]
            velocity = w / (g.AREA * current.RHO())
            old_velocity = old_w / (g.AREA * old.RHO())
            quality = current.X()[1:]
            viscosity = quality*current.fluid.MUG+(1-quality)*current.fluid.MUF
            reynolds = 4*w[1:]/(viscosity*g.PERIM.sum())
            a, b, c = solver.inputSet.model.FRICTION
            darcy = a*reynolds**b+c
            pressure_gradient_drop = (solver.inputSet.model.G*np.cos(np.deg2rad(g.ANGLE))*rho*dz
                + darcy/g.HDIAM()*(w[1:]/g.AREA)**2/(2*rho)*dz
                + w[1:]/g.AREA*np.diff(velocity)
                + rho*(velocity[1:]-old_velocity[1:])*dz/dt)
            if np.any(solver.inputSet.model.KLOSS != 0):
                raise NotImplementedError("Independent HEM momentum audit requires zero local-loss coefficients")
            momentum_residual = np.diff(current.P)+pressure_gradient_drop  # Pa
        else:
            raise NotImplementedError("Independent momentum audit currently covers homogeneous equilibrium only")
        wall_power = float(source.sum()*dz)
        boundary_enthalpy_flow = float(w[-1]*h[-1]-w[0]*h[0])
        storage_rate = float(np.sum(mass_per_length[1:]*h[1:] - old_mass_per_length[1:]*old_h[1:])*dz/dt)
        correction_rate = float(ect_change.sum()*dz)
        conservative_defect = boundary_enthalpy_flow+storage_rate+correction_rate-wall_power
        product_term = float(np.sum(dmass_dt*(old_h[1:]-h[:-1]))*dz)
        mass_term = float(np.sum(mass_residual*h[:-1]))
        equation_term = float(np.sum(energy_residual)*dz)
        rows.append({"time_s": current.TIME, "dt_s": dt,
                     "mass_max_residual_kg_s": float(np.max(np.abs(mass_residual))),
                     "energy_equation_max_residual_W_per_m": float(np.max(np.abs(energy_residual))),
                     "momentum_max_residual_Pa": float(np.max(np.abs(momentum_residual))),
                     "wall_power_W": wall_power, "boundary_enthalpy_flow_W": boundary_enthalpy_flow,
                     "stored_enthalpy_rate_W": storage_rate, "slip_energy_correction_rate_W": correction_rate,
                     "conservative_enthalpy_defect_W": conservative_defect,
                     "conservative_enthalpy_defect_relative_to_power": abs(conservative_defect)/max(abs(wall_power), 1),
                     "finite_difference_product_term_W": product_term,
                     "mass_residual_energy_term_W": mass_term,
                     "integrated_energy_equation_residual_W": equation_term,
                     "product_identity_residual_W": conservative_defect-product_term-mass_term-equation_term})
    return rows


def make_transient(nodes=100, timestep=.1):
    """Full original 0–5 s TUTORIAL2A HEM transient; file contents unchanged."""
    inputs = InputSet.from_files(ROOT/"upstream/inputs/models.inp", "TUTORIAL2A",
        ROOT/"upstream/inputs/options.inp", "DEFAULT", ROOT/"upstream/inputs/geom.inp", "TUTORIAL1",
        ROOT/"upstream/inputs/tutorial2_transient.inp")
    inputs.model.NNODES = nodes
    inputs.options.TSTEP = timestep
    return inputs


def make_multiwall(nodes=50):
    """Same total perimeter, area, power; two heated wall segments in ratio 1:2."""
    inputs = InputSet.official_sample()
    inputs.model.NNODES = nodes
    inputs.geometry.PERIM = np.array([.0276/3, 2*.0276/3])
    original = inputs.bc[0].to_dict()
    original["WPOWER"] = [[1, 2], [0, 0]]
    inputs.bc = [BoundaryConditions(original, inputs.geometry)]
    return inputs


def make_adiabatic(nodes=50):
    inputs = InputSet.official_sample()
    inputs.model.NNODES = nodes
    inputs.bc[0].POWER = 0.0
    return inputs


def metrics(solver):
    m = solver.mixture[-1]
    return {"outlet_enthalpy_J_kg": float(m.H[-1]),
            "pressure_drop_Pa": float(m.P[0]-m.P[-1]),
            "outlet_void_fraction": float(m.VF(-1)),
            "outlet_mass_flow_kg_s": float(m.W[-1])}


def _write_json(path, data):
    path.write_text(json.dumps(portable_json(data), indent=2, allow_nan=False)+"\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "scope": "Native convergence, bounds and sensitivity evidence; MATLAB equivalence and experimental validation remain unverified",
              "python": platform.python_version(), "versions": {name: version(name) for name in ("numpy", "scipy", "CoolProp", "matplotlib")},
              "source_commit": "a614c7173822a93c1e64ac28d1541cbac028cbd8", "cases": {}, "comparisons": {}}
    cases = []
    for nodes in (50, 100, 200):
        inputs = InputSet.official_sample()
        inputs.model.NNODES = nodes
        cases.append((f"mesh-{nodes}", inputs))
    for dt in (.5, 1., 2.):
        inputs = InputSet.official_sample()
        inputs.options.SSTSTEP = dt
        # Preserve actual pseudo-time duration when reducing step size.
        inputs.options.SSMAXITER = 60 if dt == .5 else 30
        cases.append((f"pseudo-{dt:g}", inputs))
    for dt in (.2, .1, .05):
        cases.append((f"transient-{dt:g}", make_transient(timestep=dt)))
    cases.extend((("multiwall", make_multiwall()), ("adiabatic", make_adiabatic())))
    solved = {}
    for label, inputs in cases:
        print(f"Running {label}", flush=True)
        try:
            with warnings.catch_warnings(record=True) as observed_warnings:
                warnings.simplefilter("always", RuntimeWarning)
                solver = MixtureSolver(inputs).solve()
                solved[label] = solver
                solver.save(args.output/label)
            transient = transient_balances(solver)
            case = {"converged": bool(solver.converged), "state": solver.STATE.name,
                    "elapsed_seconds": solver.elapsed_seconds, "nodes": solver.NZ-1,
                    "physical_time_steps": solver.NTIME, "pseudo_time_step_s": solver.inputSet.options.SSTSTEP,
                    "initialization_steps": len(solver.mixtureInit)-1,
                    "metrics": metrics(solver), "steady_initialization_balances": balances(solver),
                    "physical_bounds": physical_bounds(solver), "transient_balances": transient,
                    "runtime_warnings": sorted(set(str(item.message) for item in observed_warnings))}
            if transient:
                case["max_transient_residuals"] = {key: max(abs(row[key]) for row in transient) for key in
                    ("mass_max_residual_kg_s", "energy_equation_max_residual_W_per_m", "momentum_max_residual_Pa",
                     "conservative_enthalpy_defect_W", "conservative_enthalpy_defect_relative_to_power", "product_identity_residual_W")}
            report["cases"][label] = case
            print(label, case["converged"], case["metrics"], flush=True)
        except Exception as error:
            report["cases"][label] = {"failed": True, "error": repr(error), "traceback": traceback.format_exc()}
            print(f"FAILED {label}: {error}", flush=True)
        _write_json(args.output/"verification.json", report)

    def compare(label, coarse, fine):
        a, b = solved[coarse], solved[fine]
        comparison = {key: {"absolute_difference": abs(value-metrics(b)[key]),
                            "relative_difference": abs(value-metrics(b)[key])/max(abs(metrics(b)[key]), 1e-30)}
                      for key, value in metrics(a).items()}
        comparison["enthalpy_profile_rms_difference_J_kg"] = float(np.sqrt(np.mean((np.interp(b.Z, a.Z, a.mixture[-1].H)-b.mixture[-1].H)**2)))
        report["comparisons"][label] = comparison

    for label, coarse, fine in (("mesh_50_to_100", "mesh-50", "mesh-100"), ("mesh_100_to_200", "mesh-100", "mesh-200"),
                               ("pseudo_0.5_to_1", "pseudo-0.5", "pseudo-1"), ("pseudo_1_to_2", "pseudo-1", "pseudo-2"),
                               ("transient_0.2_to_0.1", "transient-0.2", "transient-0.1"),
                               ("transient_0.1_to_0.05", "transient-0.1", "transient-0.05"), ("multiwall_to_singlewall", "multiwall", "mesh-50")):
        if coarse in solved and fine in solved:
            compare(label, coarse, fine)
    report["transient_energy_interpretation"] = ("The source uses an advective enthalpy equation. Its converged discrete equation does not imply exact conservative stored-enthalpy balance. The reported finite_difference_product_term_W explains the product-rule truncation defect; no model correction has been applied.")
    _write_json(args.output/"verification.json", report)
    plot_sensitivity(solved, args.output)
    summarize_saved_profiles(args.output)
    failures = [label for label, case in report["cases"].items() if case.get("failed") or not case.get("converged")]
    print(f"Saved evidence to {args.output}; failed/nonconverged cases: {failures}", flush=True)
    return 1 if failures else 0


def summarize_saved_profiles(output):
    """Add heater-grid alignment and whole-transient errors from saved arrays.

    This postprocessing can be rerun without solving or overwriting numerical
    case outputs. It updates only the derived aggregate verification report.
    """
    output = Path(output)
    report = json.loads((output/"verification.json").read_text(encoding="utf-8"))
    for label, case in report["cases"].items():
        path = output/label/"results.npz"
        if not path.exists():
            continue
        with np.load(path, allow_pickle=False) as arrays:
            z, flux = arrays["Z"], arrays["HFLUX"]
            heated = np.any(flux[0, 1:, :] > 0, axis=1)
            case["heater_grid"] = {"source_heater_length_m": 3.5,
                "discrete_heated_length_m": float(heated.sum()*(z[1]-z[0])),
                "last_heated_node_m": float(z[1:][heated][-1]) if np.any(heated) else None,
                "maximum_heat_flux_W_m2": float(np.max(flux)),
                "interpretation": "Source next interpolation and discrete power normalization retained; the 3.5 m heater boundary is not aligned with every requested uniform mesh."}
    for label, coarse, fine in (("transient_0.2_to_0.1", "transient-0.2", "transient-0.1"),
                               ("transient_0.1_to_0.05", "transient-0.1", "transient-0.05")):
        if label not in report["comparisons"]:
            continue
        with np.load(output/coarse/"results.npz", allow_pickle=False) as a, np.load(output/fine/"results.npz", allow_pickle=False) as b:
            compare = report["comparisons"][label]
            for name, unit in (("H", "J_kg"), ("VF", "dimensionless"), ("W", "kg_s")):
                difference = np.interp(b["TIME"], a["TIME"], a[name][:, -1])-b[name][:, -1]
                compare[f"outlet_{name}_history_max_difference_{unit}"] = float(np.max(np.abs(difference)))
                compare[f"outlet_{name}_history_rms_difference_{unit}"] = float(np.sqrt(np.mean(difference**2)))
            compare["temporal_comparison_method"] = "Coarser outlet history linearly interpolated to finer physical time nodes over the full original 0–5 s interval."
    _write_json(output/"verification.json", report)
    return report


def plot_sensitivity(solved, output):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    with plt.rc_context({"font.size": 10, "axes.grid": True, "grid.alpha": .25}):
        fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout="constrained")
        for label, s in solved.items():
            if label.startswith("mesh-"):
                m = s.mixture[-1]
                axes[0, 0].plot(s.Z, (m.P[0]-m.P)/1000, label=f"{s.NZ-1} cells")
                axes[0, 1].plot(s.Z, m.H/1e6, label=f"{s.NZ-1} cells")
            if label.startswith("transient-"):
                axes[1, 0].plot(s.TIME, [m.H[-1]/1e6 for m in s.mixture], label=f"dt={s.DT:g} s")
                rows = transient_balances(s)
                axes[1, 1].plot([r["time_s"] for r in rows], [r["conservative_enthalpy_defect_W"]/1000 for r in rows], label=f"dt={s.DT:g} s")
        axes[0, 0].set(xlabel="Axial position [m]", ylabel="Cumulative pressure drop [kPa]", title="Mesh sensitivity: official sample")
        axes[0, 1].set(xlabel="Axial position [m]", ylabel="Enthalpy [MJ/kg]", title="Mesh sensitivity: official sample")
        axes[1, 0].set(xlabel="Time [s]", ylabel="Outlet enthalpy [MJ/kg]", title="Full official transient: 100 cells")
        axes[1, 1].set(xlabel="Time [s]", ylabel="Conservative enthalpy defect [kW]", title="Finite-difference product-rule defect")
        for ax in axes.flat:
            ax.legend()
        fig.suptitle("Native OpenSTREAM verification — MATLAB agreement pending")
        fig.savefig(output/"sensitivity.png", dpi=170)
        plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
