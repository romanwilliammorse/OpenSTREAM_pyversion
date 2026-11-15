"""Portable output for phase/annular frameworks; solver-independent plotting."""
import csv
import json
from pathlib import Path
import numpy as np
from .output import save_result, portable_json, source_hashes


def save_multifield(solver, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    save_result(solver.mixSolver, directory/"mixture")
    names = [k for k in ("liquid", "vapor", "film", "drop") if hasattr(solver, k)]
    arrays = {"Z": solver.Z, "TIME": solver.TIME}
    units = {"Z": "m", "TIME": "s"}
    def collect(prefix, states):
        for key, unit in (("W", "kg/s"), ("U", "m/s"), ("H", "J/kg")):
            arrays[prefix+"."+key] = np.stack([getattr(s, key) for s in states])
            units[prefix+"."+key] = unit
        for key in ("base", "wave"):
            if hasattr(states[0], key): collect(prefix+"."+key, [getattr(s, key) for s in states])
        if hasattr(states[0], "FREQUENCY"):
            arrays[prefix+".FREQUENCY"] = np.stack([s.FREQUENCY for s in states])
            units[prefix+".FREQUENCY"] = "Hz"
        for key in sorted(set().union(*(s.ITR.keys() for s in states))):
            template = next(s.ITR[key] for s in states if key in s.ITR)
            arrays[prefix+".ITR."+key] = np.stack([s.ITR.get(key, np.full_like(template, np.nan)) for s in states])
            units[prefix+".ITR."+key] = {"N": "1", "DU": "m/s", "DWL": "kg/s/m", "DW": "kg/s", "DH": "J/kg", "DF": "Hz", "DFW": "Hz"}.get(key, "UNRESOLVED")
    for name in names: collect(name, getattr(solver, name))
    np.savez_compressed(directory/"results.npz", **arrays)
    physical_arrays = arrays
    arrays = {"Z": solver.Z, "TIME": np.array([s.TIME for s in getattr(solver, names[0]+"Init")])}
    for name in names: collect(name, getattr(solver, name+"Init"))
    np.savez_compressed(directory/"initialization.npz", **arrays)
    arrays = physical_arrays
    metadata = {"schema": "openstream-python-v1", "framework": getattr(solver, "framework", type(solver).__name__), "state": solver.STATE.name,
                "converged": bool(solver.converged), "elapsed_seconds": solver.elapsed_seconds, "units": units,
                "native_source_sha256": source_hashes(),
                "iteration_note": "Absent iteration fields are NaN; FourField DF is actual frequency residual, DFW is an unused upstream initialized field. Physical-time iteration arrays can remain zero because source copies omit them; inspect initialization.npz.",
                "initialization_onset": getattr(solver, "onset_diagnostics", []),
                "inputs": solver.inputSet.to_dict(), "verification": "MATLAB agreement and experimental validation unverified"}
    if hasattr(solver, "diagnostics"):
        metadata["physical_diagnostics"] = solver.diagnostics()
    if hasattr(solver, "wave_frequency_converged"):
        metadata["wave_frequency_converged"] = bool(solver.wave_frequency_converged)
    precursor_metadata = json.loads((directory/"mixture"/"metadata.json").read_text(encoding="utf-8"))
    for key in ("upstream_commit", "wrapper_commit", "versions", "python", "platform", "constants", "function_samples"):
        metadata[key] = precursor_metadata[key]
    metadata["source_files"] = [{**item, "copy": "mixture/"+item["copy"]} for item in precursor_metadata["source_files"]]
    (directory/"metadata.json").write_text(json.dumps(portable_json(metadata), indent=2, allow_nan=False)+"\n", encoding="utf-8")
    with (directory/"convergence.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.DictWriter(out, fieldnames=list(solver.history[0]))
        writer.writeheader(); writer.writerows(solver.history)
    # Long-format portable table, one quantity/field/wall per row.
    with (directory/"profiles.csv").open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out); writer.writerow(["time_s", "z_m", "quantity", "wall", "value", "unit"])
        for key, values in arrays.items():
            if key in ("Z", "TIME"): continue
            values = values[:, :, None] if values.ndim == 2 else values
            for t in range(len(solver.TIME)):
                for j, z in enumerate(solver.Z):
                    for wall in range(values.shape[2]):
                        writer.writerow([solver.TIME[t], z, key, wall, values[t,j,wall], units[key]])
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.5), layout="constrained")
    for ax, key, label in zip(axes, ("W", "U", "H"), ("Mass flow [kg/s]", "Velocity [m/s]", "Enthalpy [J/kg]")):
        plot_fields = names + (["film.base", "film.wave"] if "film.base.W" in arrays else [])
        for field in plot_fields:
            ax.plot(solver.Z, arrays[field+"."+key][-1], label=field)
        ax.set(xlabel="Axial position [m]", ylabel=label)
        ax.grid(alpha=.25); ax.legend()
    fig.suptitle(f"OpenSTREAM Python {metadata['framework']} — native calculation")
    fig.savefig(directory/"axial.png", dpi=170); plt.close(fig)
    if "film.wave.FREQUENCY" in arrays:
        fig, ax = plt.subplots(figsize=(8, 4.5), layout="constrained")
        ax.plot(solver.Z, arrays["film.wave.FREQUENCY"][-1])
        ax.set(xlabel="Axial position [m]", ylabel="Disturbance-wave frequency [Hz]",
               title="Four-field wave frequency — native calculation")
        ax.grid(alpha=.25)
        fig.savefig(directory/"wave_frequency.png", dpi=170); plt.close(fig)
    return directory
