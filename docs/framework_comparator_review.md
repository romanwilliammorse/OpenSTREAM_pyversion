# Independent review of recovered-framework comparisons

2026-11-14. Reviewed `tools/verify_recovered_framework.py` against the preserved
source regression tests, saved input/convergence records, and recovered
TwoFluid, ThreeField and FourField archives. The review did not modify numerical
solver equations or source references.

## Correct acceptance scope

The upstream `SolverIntegrationTest.compareFieldProperty` checks the first
physical state at relative tolerance 1e-8 with zero absolute tolerance:

| Framework | Original compared fields | Number of W/U/H profiles |
|---|---|---:|
| TwoFluid | liquid, vapor | 6 |
| ThreeField | film, drop | 6 |
| FourField | film, drop, film.wave | 9 |

The original test spells the base field `film.basefilm`, which is absent and
skipped. The new comparator correctly treats actual `film.base.W/U/H` and
wave frequency as four additional comparisons, rather than claiming the
upstream test originally covered them. Their failures remain distinct from
the original field-comparison result. Initialization and precursor comparisons
are also additional verification. The CLI requires original, expanded and
initialization checks to pass before returning success.

Film/base/wave arrays retain `(time,node,wall)` even for the one-wall baseline;
phase/drop arrays retain `(time,node)`. There is no shape squeezing or mesh
interpolation. Exact reference zeros must remain exact zeros. All core
comparisons require finite values.

## Convergence and units

The source `AbstractFilm.WL` and `FourField.Wave.WL` calculate W divided by
PERIM. Therefore both point DWL and temporal WL increments are kg/(s m), not
kg/s. The comparator converts stored W back to WL before using SSCONVWF. A
test deliberately gives a total mass increment below the numerical threshold
but a perimeter-normalized increment above it, so omitting the division would
be detected.

FourField's actual frequency residual is `film.wave.ITR.DF`. The initialized
`DFW` zeros cannot satisfy that check. Final DF must be finite and below
ERRORFW; missing or NaN DF is rejected. Source temporal stopping omits
SSCONVFW, so the comparator reports that additional frequency stopping check
separately rather than altering the original convergence predicate.

The first FourField initialization state does not contain DF. The extractor
records its absence explicitly and fills that missing row with NaN. Matching
NaN is accepted only for the exact iteration rows identified as absent in the
reference presence map. Undeclared NaNs, partial-row NaNs, a wrong absence mask,
and infinities are rejected. These absent values are not numerical agreement
observations. Final convergence still requires actual finite DF.

## Issues identified and corrected during review

The root implementation was hardened in response to this review:

1. Require integrity records for precursor results, initialization and
   manifest files, in addition to checking the main reference files.
2. Check pinned native wrapper commit and gravity as well as upstream commit.
3. Check compared coordinate, core, diagnostic and convergence units, rejecting
   missing or unresolved units.
4. Verify copied native input files against their recorded hashes and reject
   paths escaping the native result directory.
5. Restrict undefined diagnostic acceptance to declared absent iteration rows;
   reject matching infinities and arbitrary matching NaNs.
6. Check precursor effective inputs, solver state and actual final point/time
   convergence separately from the parent solver.

Archive hashes and recovered file hashes are verified before comparing values.
The approved archive producer's exact source/runtime versions remain unknown;
the tool reports that limitation rather than fabricating full provenance.
Historical zero-valued input defaults are disclosed and narrowly checked, and
source-equivalent interpolation capitalization is explicitly recognized.

## Executed tests

`tools/test_recovered_framework.py` contains **43 passing tests**. They cover
the three real recovered baselines and adversarial cases for:

- Exact zeros, required original and expanded fields, and separate scope flags.
- Node/wall axes, transposition, spatial/time grids, and nonfinite core data.
- Archive/extraction hashes, required precursor hashes, wrapper, gravity,
  units, missing units and tampered copied inputs.
- Parent-independent precursor state, inputs and actual point residuals.
- Actual DF versus unused DFW, strict threshold equality, explicit missing-row
  masks, malformed masks and infinite diagnostics.
- Correct perimeter normalization and film convergence units.

Synthetic test files are temporary acceptance fixtures and are never used as
OpenSTREAM reference data. The actual-baseline tests use the preserved
`reference_exports/recovered-{twofluid,threefield,fourfield}-01` directories and
fresh `outputs/baseline-parity-01/{TwoFluid,ThreeField,FourField}Solver` runs.
They also require physical-diagnostic records to remain present. Array agreement
does not erase the reported area-closure failures or establish experimental
validation.

Reproduce from the project directory:

```powershell
.\.venv\Scripts\python.exe -m pytest tools\test_recovered_framework.py -q
```

The tests require this workspace's recovered archives and saved native runs.
They do not execute MATLAB or rerun the numerical solvers.
