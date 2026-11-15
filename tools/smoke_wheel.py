"""Verify an installed wheel, prioritizing its directory over the editable checkout."""
import json
from pathlib import Path
import sys

target = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(target))
import openstream
assert Path(openstream.__file__).resolve().is_relative_to(target), openstream.__file__
inputs = openstream.InputSet.official_sample()
assert all(Path(p).is_relative_to(target) for p in inputs.source_files)
solver = openstream.MixtureSolver(inputs).solve()
assert solver.converged
assert not any(name == "matlab" or name.startswith("matlab.") or name.startswith("oct2py") for name in sys.modules)
print(json.dumps({"imported_from": openstream.__file__, "state": solver.STATE.name,
                  "converged": bool(solver.converged), "outlet_enthalpy_J_kg": float(solver.mixture[0].H[-1]),
                  "bundled_input_paths": inputs.source_files}, indent=2))
