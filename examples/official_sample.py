"""Run with: .\.venv\Scripts\python.exe examples\official_sample.py"""
from pathlib import Path
from openstream import InputSet, MixtureSolver

root = Path(__file__).resolve().parents[1]
inputs = InputSet.official_sample(root/"upstream"/"inputs")
solver = MixtureSolver(inputs).solve(progress=print)
solver.save(root/"outputs"/"example-api")
print(solver.STATE.name, "converged:", solver.converged)
if not solver.converged:
    raise SystemExit(2)
