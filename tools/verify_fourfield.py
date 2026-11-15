r"""Run unmodified upstream Tutorial 5 inputs and retain actual outcomes.

From the project root: .venv\Scripts\python.exe tools/verify_fourfield.py
No MATLAB-equivalence or experimental validation is implied by these checks.
"""
from pathlib import Path
import argparse
import csv
import json
import traceback
import warnings
import numpy as np
from openstream import InputSet
from openstream.fourfield import FourFieldSolver


def check_saved_arrays(directory):
    """Check every saved physical state independently of solver diagnostics."""
    with np.load(directory/"results.npz") as arrays,np.load(directory/"mixture/results.npz") as mix:
        total=arrays["film.base.W"].sum(axis=2)+arrays["film.wave.W"].sum(axis=2)+arrays["drop.W"]+mix["vapor.W"]
        masses=["film.base.W","film.wave.W","drop.W"]
        speeds=["film.base.U","film.wave.U","drop.U"]
        primary=masses+speeds+["film.base.H","film.wave.H","drop.H","film.wave.FREQUENCY"]
        checks={"stored_times":len(arrays["TIME"]),"stored_nodes":len(arrays["Z"]),
                "all_time_max_mass_partition_error_kg_s":float(np.max(abs(total-mix["W"]))),
                "all_time_min_mass_kg_s":min(float(np.min(arrays[key])) for key in masses),
                "all_time_min_velocity_m_s":min(float(np.min(arrays[key])) for key in speeds),
                "all_time_min_frequency_Hz":float(np.min(arrays["film.wave.FREQUENCY"])),
                "all_time_nonfinite_primary_count":sum(int(np.sum(~np.isfinite(arrays[key]))) for key in primary)}
        if len(arrays["TIME"])>1:
            checks.update(minimum_time_step_s=float(np.min(np.diff(arrays["TIME"]))),
                          maximum_time_step_s=float(np.max(np.diff(arrays["TIME"]))))
    with (directory/"convergence.csv").open(newline="") as stream:
        transient=[row for row in csv.DictReader(stream) if row["phase"]=="transient"]
    if transient:
        checks.update(all_physical_steps_point_converged=all(row["point_converged"]=="True" for row in transient),
                      physical_point_max_iterations=max(int(row["max_iterations"]) for row in transient))
    return checks


def run(output=Path("outputs/fourfield_tutorials"),cases="ABCDE"):
    if not cases or any(letter not in "ABCDEF" for letter in cases):
        raise ValueError("cases must contain Tutorial 5 letters A through F")
    output.mkdir(parents=True,exist_ok=False)
    source=Path(__file__).resolve().parents[1]/"upstream"/"inputs"
    results=[]
    for letter in cases:
        case="TUTORIAL5"+letter
        print(case,"starting",flush=True)
        # Tutorial F is a workflow label, not a model ID: the original MLX
        # selects TUTORIAL5E with the existing power-transient BC file.
        model="TUTORIAL5E" if letter=="F" else case
        bc="tutorial2_transient.inp" if letter=="F" else "tutorial1.inp"
        inputs=InputSet.from_files(source/"models.inp",model,source/"options.inp","DEFAULT",
                                   source/"geom.inp","TUTORIAL1",source/bc)
        result={"case":case,"reference_comparison":"unverified","experimental_validation":"not performed"}
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                solver=FourFieldSolver(inputs).solve()
                solver.save(output/case)
                result.update(converged=bool(solver.converged),state=solver.STATE.name,
                              pseudo_steps=len(solver.filmInit)-1,physical_steps=solver.NTIME-1,
                              diagnostics=solver.diagnostics(),
                              independent_saved_array_checks=check_saved_arrays(output/case),
                              final_convergence=solver.history[-1])
            except Exception as exc:
                result.update(converged=False,error=f"{type(exc).__name__}: {exc}",traceback=traceback.format_exc())
            result["warnings"]=sorted(set(str(w.message) for w in caught))
        results.append(result)
        (output/"verification.json").write_text(json.dumps(results,indent=2,allow_nan=False)+"\n",encoding="utf-8")
        print(case,result.get("state",result.get("error")),result["converged"],flush=True)
    return results


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("outputs/fourfield_tutorials"))
    parser.add_argument("--cases",default="ABCDE",help="Tutorial letters A--F; F selects5E with transient BC")
    args=parser.parse_args()
    results = run(args.output,args.cases)
    if any(not result.get("converged", False) for result in results): raise SystemExit(2)
    if any(result.get("diagnostics", {}).get("physical_consistency") is False for result in results): raise SystemExit(3)
