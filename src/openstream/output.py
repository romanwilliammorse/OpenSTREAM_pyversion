"""Portable numerical output and plotting, separate from the numerical core."""
from __future__ import annotations

import csv
import hashlib
from importlib.metadata import version
from importlib.resources import files
import json
from pathlib import Path
import platform
import shutil
import numpy as np


def portable_json(value):
    """Encode upstream NaN sentinels explicitly, without nonstandard JSON."""
    if isinstance(value, dict):
        return {k: portable_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [portable_json(v) for v in value]
    if isinstance(value, float) and not np.isfinite(value):
        return "NaN" if np.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    return value


def source_hashes():
    """Identify the exact Python implementation even before a Git commit."""
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(Path(__file__).parent.glob("*.py"))}

UNITS = {"Z": "m", "TIME": "s", "W": "kg/s", "P": "Pa", "H": "J/kg", "U": "m/s", "UP": "m/s",
         "RHO": "kg/m^3", "X": "1", "XEQ": "1", "VF": "1", "T": "K", "HFLUX": "W/m^2",
         "LHGR": "W/m", "TWALL": "K", "MCT": "kg/s", "ECT": "J/m"}
for phase in ("liquid", "vapor"):
    for key in ("W", "H", "U", "T", "X", "VF"):
        UNITS[f"{phase}.{key}"] = UNITS[key]
for prefix in ("DP", "DPSUM"):
    for key in ("Grav", "Wall", "Acc_z", "Acc_t", "Acc_s", "K", "Tot"):
        UNITS[f"{prefix}.{key}"] = "Pa"
for key, unit in {"U_z": "m/s^2", "U_t": "m/s^2", "U": "m/s^2", "H_z": "J/kg/s", "H_t": "J/kg/s", "H": "J/kg/s"}.items():
    UNITS[f"MDER.{key}"] = unit
for key, unit in {"WV": "kg/s", "X": "1", "HV": "J/kg", "TV": "K", "TCOND": "s", "TEVAP": "s"}.items():
    UNITS[f"MRM.{key}"] = unit
for key, unit in {"W": "kg/s", "H": "J/kg", "HFLUX": "W/m^2", "XEQ": "1", "WBULK": "kg/s", "HBULK": "J/kg", "XBULK": "1", "TRELAX": "s"}.items():
    UNITS[f"NEARWALL.{key}"] = unit
for key, unit in {"N": "1", "DW": "kg/s", "DP": "Pa", "DPSUM": "Pa", "DH": "J/kg", "DWV": "kg/s", "DHV": "J/kg"}.items():
    UNITS[f"ITR.{key}"] = unit


def state_arrays(states):
    arrays = {}
    for name in ("W", "P", "H", "U", "UP", "RHO", "X", "XEQ", "VF", "T", "HFLUX", "LHGR", "TWALL", "MCT", "ECT"):
        vals = [getattr(m, name) for m in states]
        arrays[name] = np.stack([v() if callable(v) else v for v in vals])
    for phase in ("liquid", "vapor"):
        for name in ("W", "H", "U", "T", "X", "VF"):
            arrays[f"{phase}.{name}"] = np.stack([getattr(getattr(m, phase), name)() for m in states])
    for prefix in ("DP", "DPSUM", "MDER", "MRM", "NEARWALL", "ITR"):
        for name in getattr(states[0], prefix):
            arrays[f"{prefix}.{name}"] = np.stack([getattr(m, prefix)[name] for m in states])
    return arrays


def balances(solver):
    """Independent integrated steady checks and discrete transient residuals.

    Units: mass residual kg/s; energy residual W; momentum residual Pa.
    These check the implemented upstream equations (enthalpy transport omits
    kinetic/potential energy), not a more general total-energy model.
    """
    states = solver.mixtureInit
    m, old = states[-1], states[-2] if len(states) > 1 else states[-1]
    dz, dt = solver.DZ, m.DT
    w, u, h = m.W, m.U(), m.H
    mass = w[1:]-w[:-1]+dz/dt*(w[1:]/u[1:]-old.W[1:]/old.U()[1:])
    energy = w[1:]*(h[1:]-h[:-1])/dz+(m.ECT()[1:]-old.ECT()[1:])/dt+w[1:]/u[1:]*(h[1:]-old.H[1:])/dt-m.LHGR()[1:].sum(axis=1)
    momentum = np.array([m.P[j]-m.P[j-1]-m.DPTOT(old.UP(j), old.MCT(j), j) for j in range(1, m.NZ)])
    q = float(np.sum(m.LHGR()[1:])*dz)
    transported = float(w[0]*(h[-1]-h[0]))
    return {"prescribed_power_W": float(solver.boundaryConditions["POWER"][0]),
            "discrete_wall_power_W": q, "steady_enthalpy_gain_W": transported,
            "steady_energy_relative_error": abs(transported-q)/max(abs(q), 1),
            "steady_mass_max_deviation_kg_s": float(np.max(abs(w-w[0]))),
            "discrete_mass_max_residual_kg_s": float(np.max(abs(mass))),
            "discrete_energy_max_residual_W_per_m": float(np.max(abs(energy))),
            "discrete_momentum_max_residual_Pa": float(np.max(abs(momentum))),
            "pressure_drop_Pa": float(m.P[0]-m.P[-1]), "outlet_enthalpy_J_kg": float(h[-1]),
            "outlet_void_fraction": float(m.VF(-1)), "outlet_vapor_quality": float(m.X(-1)),
            "minimum_pressure_Pa": float(np.min(m.P)), "minimum_density_kg_m3": float(np.min(m.RHO()))}


def plot_axial(solver, filename=None, time_index=-1):
    import matplotlib
    if filename is not None:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    m = solver.mixture[time_index]
    z = m.Z
    with plt.rc_context({"font.size": 10, "axes.grid": True, "grid.alpha": .25, "lines.linewidth": 1.5}):
        fig, axes = plt.subplots(2, 3, figsize=(13, 7.4), layout="constrained")
        colors = {"Mixture": "#c52347", "Liquid": "#e35b27", "Vapor": "#147bbd"}
        axes[0, 0].plot(z, m.HFLUX/1e6)
        axes[0, 0].set(title="Wall heat flux", ylabel="Heat flux [MW/m²]")
        for obj, label in ((m, "Mixture"), (m.liquid, "Liquid"), (m.vapor, "Vapor")):
            for ax, key, scale in ((axes[0, 1], "W", 1), (axes[1, 0], "U", 1), (axes[1, 1], "H", 1e-6)):
                value = getattr(obj, key)
                ax.plot(z, (value() if callable(value) else value)*scale, label=label, color=colors[label])
        axes[0, 1].set(title="Mass flow rates", ylabel="Mass flow rate [kg/s]")
        for key, label in (("Grav", "Gravity"), ("Wall", "Wall friction"), ("Acc_z", "Axial acceleration"),
                           ("Acc_t", "Temporal acceleration"), ("Acc_s", "Slip temporal"), ("K", "Local losses"), ("Tot", "Total")):
            axes[0, 2].plot(z, m.DPSUM[key]/1e3, label=label)
        axes[0, 2].set(title="Cumulative pressure drops", ylabel="Pressure drop [kPa]")
        axes[1, 0].set(title="Velocities", ylabel="Velocity [m/s]")
        axes[1, 1].axhline(m.fluid.HF/1e6, ls="--", color=colors["Liquid"], label="Saturated liquid")
        axes[1, 1].axhline(m.fluid.HG/1e6, ls="--", color=colors["Vapor"], label="Saturated vapor")
        axes[1, 1].set(title="Specific enthalpies", ylabel="Specific enthalpy [MJ/kg]")
        for key, label in (("XEQ", "Equilibrium quality"), ("X", "Vapor mass quality"), ("VF", "Void fraction")):
            axes[1, 2].plot(z, getattr(m, key)(), label=label)
        axes[1, 2].set(title="Void fraction and qualities", ylabel="Quality / void fraction [1]")
        for ax in axes.flat:
            ax.set(xlabel="Axial position [m]", xlim=(z[0], z[-1]))
            if ax.get_legend_handles_labels()[0]:
                ax.legend(fontsize=8)
        fig.suptitle(f"OpenSTREAM Python — {solver.inputSet.model.ID} — t = {m.TIME:g} s\nNative calculation; verification scope is recorded separately", fontsize=13)
        if filename:
            fig.savefig(filename, dpi=170)
        return fig


def save_result(solver, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    arrays = {"Z": solver.Z, "TIME": solver.TIME, **state_arrays(solver.mixture)}
    np.savez_compressed(directory/"results.npz", **arrays)
    init = {"Z": solver.Z, "TIME": np.array([m.TIME for m in solver.mixtureInit]), **state_arrays(solver.mixtureInit)}
    np.savez_compressed(directory/"initialization.npz", **init)
    metadata = {"schema": "openstream-python-v1", "framework": "Mixture", "upstream_commit": "a614c7173822a93c1e64ac28d1541cbac028cbd8",
                "wrapper_commit": "a7c40902ff66faf6ed668986398bb1b9faa16e13",
                "state": solver.STATE.name, "converged": bool(solver.converged), "elapsed_seconds": solver.elapsed_seconds,
                "units": UNITS, "array_layout": "(time,node) or (time,node,wall); coordinates 1D",
                "versions": {k: version(k) for k in ("openstream-python", "numpy", "scipy", "CoolProp", "matplotlib")},
                "python": platform.python_version(), "platform": platform.platform(), "inputs": solver.inputSet.to_dict(),
                "native_source_sha256": source_hashes(),
                "constants": {"model.G": solver.inputSet.model.G},
                "function_samples": {"model.CBTMULT": np.broadcast_to(solver.inputSet.model.CBTMULT(solver.Z), solver.Z.shape).tolist()},
                "nonfinite_input_convention": "NaN and +/-Infinity input sentinels are strings; numerical arrays retain IEEE values",
                "verification": {"MATLAB_equivalence": "unverified: portable reference not yet executed", "experimental_validation": "not performed"},
                "balances": balances(solver)}
    metadata["source_files"] = []
    sources = getattr(solver.inputSet, "source_files", [])
    if sources:
        (directory/"inputs").mkdir()
        for i, source in enumerate(sources):
            source = Path(source)
            target = directory/"inputs"/f"{i:02d}-{source.name}"
            shutil.copyfile(source, target)
            metadata["source_files"].append({"source": str(source), "copy": str(target.relative_to(directory)),
                                             "sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
    (directory/"metadata.json").write_text(json.dumps(portable_json(metadata), indent=2, allow_nan=False)+"\n", encoding="utf-8")
    with (directory/"convergence.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=list(solver.history[0]) if solver.history else ["phase"])
        writer.writeheader()
        writer.writerows(solver.history)
    keys = [k for k, v in arrays.items() if v.ndim == 2]
    with (directory/"profiles.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out)
        writer.writerow(["time [s]", "z [m]"]+[f"{k} [{UNITS[k]}]" for k in keys])
        for t in range(len(solver.TIME)):
            for z in range(len(solver.Z)):
                writer.writerow([solver.TIME[t], solver.Z[z]]+[arrays[k][t,z] for k in keys])
    with (directory/"wall_profiles.csv").open("w", newline="", encoding="utf-8") as out:
        keys = [k for k, v in arrays.items() if v.ndim == 3]
        writer = csv.writer(out)
        writer.writerow(["time [s]", "z [m]", "wall index (zero based)"]+[f"{k} [{UNITS[k]}]" for k in keys])
        for t in range(len(solver.TIME)):
            for z in range(len(solver.Z)):
                for w in range(solver.inputSet.geometry.NWALL()):
                    writer.writerow([solver.TIME[t], solver.Z[z], w]+[arrays[k][t,z,w] for k in keys])
    fig = plot_axial(solver, directory/"axial.png")
    import matplotlib.pyplot as plt
    plt.close(fig)
    return directory
