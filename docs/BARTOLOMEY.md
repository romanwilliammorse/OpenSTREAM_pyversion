# Bartolomey database adapter and pilot

The native adapter reads all 34 records of OpenSTREAM-database at commit
`b48541e6438a92b4c0ddc83cf0ceda3f71a59b22`. It translates the source input
mapping and compares void fraction in the actual measured coordinate. MATLAB,
MATLAB Engine and Octave are not required. Other experimental families and
transient database records remain explicitly unsupported by this adapter.

The preserved source is the `database` Git submodule. Update an existing checkout
with `git submodule update --init --recursive`; new checkouts should use
`git clone --recurse-submodules`. The database remains separate from the package:
pass the checkout or an XML path to the installed API. Its MIT notice is also
retained in `licenses/OpenSTREAM_database_LICENSE` and included in distributions.

## Python API

```python
from openstream.database import load_bartolomey
from openstream import MixtureSolver
from openstream.experimental_comparison import compare_void_profile

database = load_bartolomey("database")  # Or the full Bartolomey.xml path.
record = database.select(1)  # MATLAB-style one-based XML row, not TestID.
inputs = record.to_input_set(
    model={"ID": "Bartolomey entry 1", "NNODES": 200,
           "VOID": "BESTION", "THERMALNONEQ": "SAHAZUBER"},
    options={"SSMAXITER": 100},
)
solver = MixtureSolver(inputs).solve()
observations = record.observations()
field = solver.mixture[-1]
coordinate = field.XEQ() if observations.coordinate == "Quality" else solver.Z
comparison = compare_void_profile(observations, coordinate, field.VF())
print(solver.converged, comparison["summary"])
```

This short API example is not the frozen numerical acceptance campaign. Check
convergence, physical balances and sensitivity before interpreting its errors.

- `database.records` preserves source order. `select(16)` selects TestID 17.
  `matching_test_id(28)` returns records 24–26; `by_test_id(28)` raises an
  ambiguity error. `filter_runs(Pressure=(6e6, 7e6))` returns inclusive row IDs.
- `record.raw_fields` retains repeated tags and original text, including empty
  coordinates. `record.values` exposes immutable interpreted SI values.
  `record.to_dict()` produces raw/normalized values, units and provenance.
- `to_input_set(model=..., options=..., geometry=..., boundary_conditions=...)`
  accepts explicit overrides and independent copies. Empty mandatory defaults
  follow the source's fallback rules. Source `MassFlow`, `Power`, and
  `InletEnthalpy` are authoritative; descriptive mass flux, heat flux and
  temperature do not replace them. Numeric generated inputs preserve the
  source writer's `%.11f` round-trip, including column-major array meaning.
- `input_consistency()` independently compares redundant arithmetic and stored
  decimal rounding intervals. Those intervals are not uncertainty estimates.
- `observations()` distinguishes equilibrium quality [1] from elevation [m].
  Negative digitized void values are retained and flagged. They are not physical
  predictions and are not silently clipped to zero.
- `compare_void_profile()` returns every measurement, a signed error
  (prediction minus measurement) in void fraction [1], and explicit exclusions.
  Interpolation is linear and within domain. Nonmonotonic or repeated model
  coordinates fail explicitly; no quality plateau is inverted into an elevation.
  Bias, MAE and RMSE are descriptive, with no experimental acceptance flag.

## Frozen pilot and reproduction

The manifest `examples/bartolomey_pilot.json` was committed as `4e76cc1` before
predictions were run. It selects the first row of each experimental group:
1, 22, 29 and 31 (TestIDs 1, 26, 31 and 33). Two fixed closures use upstream
defaults and the upstream TUTORIAL2D Saha–Zuber/Bestion selection. No coefficients
are fitted. Three meshes, a tighter iteration run and a changed pseudo-time
step give 40 attempted runs. There is no physical transient in this campaign.

Run from the repository root in PowerShell:

```powershell
.\.venv\Scripts\python.exe tools/run_bartolomey_pilot.py `
  --database database --output outputs/validation/bartolomey-pilot-02
```

Choose a new output directory for each execution. The runner rejects altered
XML or manifest fingerprints before creating output. A scientifically revised
campaign requires separate preregistration; do not edit the frozen tolerances
to obtain a pass. Exit code 3 means a retained execution, physical or numerical
sensitivity failure; inspect `report.json` rather than treating it as a crash.

Outputs include the full 34-record case registry, frozen manifest, every
attempted run, input files, convergence history, native arrays, units, paired
measurement CSV/JSON, balance checks, mesh/iteration/pseudo-time sensitivity,
and summary plots. Each run also exports `gui_inputs.json`; use **Import** in
the local app to inspect its settings or rerun it. Imported pilot cases remain
custom cases without archived MATLAB-equivalence claims.

See [the pilot results](BARTOLOMEY_PILOT.md),
[source review](BARTOLOMEY_SOURCE_REVIEW.md), and
[acceptance matrix](ACCEPTANCE_MATRIX.md). The source report's absolute void
error bound of 0.04 is recorded with its stated scope. Digitization, coordinate,
input propagation and correlation information remain incomplete, and historical
calibration overlap is unknown. These comparisons cannot yet establish
uncertainty-qualified or independent experimental validation.
