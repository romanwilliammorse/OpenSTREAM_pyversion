"""Convenience commands for the local OpenSTREAM Python window.

This launcher does not change solver equations, inputs or reference data.
Each new calculation or plot goes into a distinct output directory.
"""
from datetime import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from uuid import uuid4

import matplotlib
matplotlib.use("Agg")
from openstream import InputSet, MixtureSolver, SavedResults
from openstream.output import balances

ROOT = Path(__file__).resolve().parents[1]
latest_result = ROOT/"outputs/release-02/MixtureSolver"
latest_transient = ROOT/"outputs/verification/native-sensitivity-01/transient-0.1"
solver = None


def _new_directory(label):
    parent = ROOT/"outputs/interactive"
    parent.mkdir(parents=True, exist_ok=True)
    return parent/f"{datetime.now():%Y%m%d-%H%M%S}-{label}-{uuid4().hex[:6]}"


def _open(path, enabled=True):
    print(f"Saved: {path}", flush=True)
    if enabled:
        os.startfile(str(path))


def _run(inputs, label, open_plot):
    global solver, latest_result, latest_transient
    print("Running native mixture solver...", flush=True)
    result = MixtureSolver(inputs).solve()
    destination = result.save(_new_directory(label))
    solver, latest_result = result, destination
    if result.NTIME > 1:
        latest_transient = destination
    print(f"Numerically converged: {result.converged}; stored physical states: {result.NTIME}")
    print(f"Final outlet enthalpy: {result.mixture[-1].H[-1]:.6f} J/kg")
    if result.NTIME == 1:
        report = balances(result)
        print(f"Pressure drop: {report['pressure_drop_Pa']:.6f} Pa")
        print(f"Steady energy relative error: {report['steady_energy_relative_error']:.6g}")
    print("This console run has not been compared with the archived MATLAB baseline.")
    print("Experimental validation has not been performed.")
    _open(destination/"axial.png", open_plot)
    if not result.converged:
        print("NUMERICAL CONVERGENCE FAILED. Inspect convergence.csv before interpreting results.")
    return str(destination)


def sample(power_W=87500., cells=100, open_plot=True):
    """Run the official steady mixture case; optionally change power or cells."""
    inputs = InputSet.official_sample()
    inputs.bc[0].POWER = power_W
    inputs.model.NNODES = cells
    return _run(inputs, "sample", open_plot)


def transient(cells=100, dt=.1, open_plot=True):
    """Run original TUTORIAL2A inputs with the original 0–5 s power schedule."""
    source = ROOT/"upstream/inputs"
    inputs = InputSet.from_files(source/"models.inp", "TUTORIAL2A", source/"options.inp", "DEFAULT",
                                source/"geom.inp", "TUTORIAL1", source/"tutorial2_transient.inp")
    inputs.model.NNODES = cells
    inputs.options.TSTEP = dt
    return _run(inputs, "transient", open_plot)


def checks(full=False):
    """Run automated tests; passing tests do not establish physical validation."""
    executable = Path(sys.executable).with_name("python.exe")
    command = [str(executable), "-m", "pytest", "-q"]
    if not full:
        command += ["tests/test_inputs.py", "tests/test_properties.py", "tests/test_solver.py", "tests/test_plotting.py"]
    print("Running tests. Please wait for the >>> prompt to return...", flush=True)
    run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    destination = _new_directory("tests")
    destination.mkdir()
    (destination/"tests.log").write_text(run.stdout+run.stderr, encoding="utf-8")
    print(run.stdout+run.stderr)
    print(f"Test exit code: {run.returncode}; log: {destination/'tests.log'}")
    return run.returncode


def _saved(source=None, need_time=False, phase="physical"):
    if source is None:
        path = latest_transient if need_time and phase == "physical" else latest_result
    else:
        path = Path(source)
        if not path.is_absolute(): path = ROOT/path
    print(f"Using saved {phase} data: {path}")
    return SavedResults(path, phase=phase)


def plot(quantity="H", kind="axial", wall=None, source=None, phase="physical", open_plot=True):
    """Open an axial plot, outlet history or space–time map from saved data."""
    if kind not in ("axial", "history", "map"):
        raise ValueError("kind must be 'axial', 'history' or 'map'")
    data = _saved(source, need_time=kind != "axial", phase=phase)
    if kind == "axial": figure = data.axial(quantity, walls=wall)
    elif kind == "history": figure = data.history(quantity, nodes=-1, walls=wall)
    else: figure = data.space_time(quantity, wall=wall)
    destination = _new_directory("plot")
    destination.mkdir()
    path = destination/(re.sub(r"[^A-Za-z0-9_.-]", "_", quantity)+f"-{kind}.png")
    figure.savefig(path, dpi=160)
    from matplotlib import pyplot as plt
    plt.close(figure)
    _open(path, open_plot)
    return str(path)


def animate(quantity="H", wall=None, source=None, phase="physical", open_plot=True):
    """Open a GIF of every second stored state; playback is not physical time."""
    data = _saved(source, need_time=True, phase=phase)
    destination = _new_directory("animation")
    destination.mkdir()
    path = destination/(re.sub(r"[^A-Za-z0-9_.-]", "_", quantity)+".gif")
    data.save_animation(quantity, path, times=slice(None, None, 2), walls=wall, fps=8)
    _open(path, open_plot)
    return str(path)


def results():
    """Open the latest calculation's folder."""
    os.startfile(str(latest_result))


def quantities(source=None):
    """List exact saved field names and SI units."""
    data = _saved(source)
    for key in data.quantities: print(f"{key:25s} {data.units[key]}")


def guide():
    print("""
OpenSTREAM — native Python command window
Type a command at >>> and press Enter. Do not type the >>> itself.

sample()                         Run the official steady case and open its plot
checks()                         Run quick automated checks
checks(full=True)                Run the complete test suite
transient()                      Run the 0–5 s power-reduction calculation
plot("H", kind="history")         Plot outlet enthalpy versus time
plot("H", kind="map")             Plot enthalpy versus position and time
animate("H")                     Open an animated enthalpy profile
plot("VF")                       Plot axial void fraction
sample(power_W=70000, cells=100)  Try a different power [W]
quantities()                     List available field names and units
results()                        Open the latest calculation folder
guide()                          Show this help again

History/maps/animation initially use the existing original mixture transient.
After transient(), they use your new run. Outputs are never overwritten.
Natural-language requests go in Codex; this window accepts Python commands.
Four steady TUTORIAL1 baselines agree with archived MATLAB profiles.
Custom/transient cases remain unverified; no experimental validation.
This console does not automatically compare new runs with the archives.
Detailed-framework physical checks currently fail; see docs/VERIFICATION.md.
""")


if __name__ == "__main__":
    os.chdir(ROOT)
    guide()
    # Readiness evidence for the launcher; no credentials or external traffic.
    (ROOT/"outputs/interactive").mkdir(parents=True, exist_ok=True)
    (ROOT/"outputs/interactive/console-ready.json").write_text(json.dumps(
        {"pid": os.getpid(), "python": sys.executable, "started": datetime.now().isoformat(), "root": str(ROOT)}, indent=2))
