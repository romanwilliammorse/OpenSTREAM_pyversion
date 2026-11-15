"""Windows-friendly native command line entry point."""
import argparse
from pathlib import Path
import json

from .inputs import InputSet
from .solver import MixtureSolver
from .output import balances


def main(argv=None):
    parser = argparse.ArgumentParser(description="Native OpenSTREAM solvers (partial port; see feature map)")
    parser.add_argument("command", choices=["sample", "run"])
    parser.add_argument("--inputs", type=Path, help="Directory containing original .inp files")
    parser.add_argument("--model", default="TUTORIAL1")
    parser.add_argument("--options", default="DEFAULT")
    parser.add_argument("--geometry", default="TUTORIAL1")
    parser.add_argument("--boundary", default="tutorial1.inp")
    parser.add_argument("--output", type=Path, required=True, help="New output directory (never overwritten)")
    parser.add_argument("--nodes", type=int)
    parser.add_argument("--framework", choices=["mixture", "twofluid", "threefield", "fourfield"], default="mixture")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output directory exists; choose a new directory")
    if args.inputs is None:
        from importlib.resources import files
        args.inputs = Path(str(files("openstream")/"data"))
    inputs = InputSet.from_files(args.inputs/"models.inp", args.model, args.inputs/"options.inp", args.options,
                                args.inputs/"geom.inp", args.geometry, args.inputs/args.boundary)
    if args.nodes is not None:
        inputs.model.NNODES = args.nodes
    def progress(r):
        if not args.quiet:
            print(f"{r['phase']}: t={r['time_s']:g} s, iterations={r['max_iterations']}, "
                  f"point_converged={r['point_converged']}", flush=True)
    from . import TwoFluidSolver, ThreeFieldSolver, FourFieldSolver
    constructor = {"mixture": MixtureSolver, "twofluid": TwoFluidSolver, "threefield": ThreeFieldSolver, "fourfield": FourFieldSolver}[args.framework]
    solver = constructor(inputs).solve(progress)
    solver.save(args.output)
    print(json.dumps({"state": solver.STATE.name, "converged": bool(solver.converged),
                      "output": str(args.output.resolve()), "precursor_or_mixture_balances": balances(solver if args.framework == "mixture" else solver.mixSolver)}, indent=2))
    if hasattr(solver, "diagnostics"):
        diagnostics = solver.diagnostics()
        print(json.dumps({"physical_diagnostics": diagnostics}, indent=2))
        if diagnostics.get("physical_consistency") is False:
            return 3
    return 0 if solver.converged else 2
