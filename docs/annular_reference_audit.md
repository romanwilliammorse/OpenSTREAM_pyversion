# Annular archived-baseline recovery and independent audit

Date: 2026-11-14. The existing three-field and four-field MATLAB archives were
decoded without MATLAB. Their direct stored profiles and source-dependent
getters were compared with fresh native calculations. All primary profiles
pass the unchanged `rtol=1e-8`, `atol=0` policy in physical and initialization
states. No annular numerical implementation or governing equation was changed.

## Preserved evidence

| Framework | Original archive SHA256 | Initialization states |
|---|---|---:|
| ThreeField | eabaef27d5b94dce4506783675d90563def40db1a491b8a16b982b9de070e884 | 6 |
| FourField | fd28edab74cad654721572c4644461dc20fef27ed4a3d617458b9717e13eacf1 | 9 |

Original files remain under
`upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/`.
Portable exports are `reference_exports/recovered-threefield-01/` and
`reference_exports/recovered-fourfield-01/`. Each contains native-shaped
`results.npz`, `initialization.npz`, original-shape `raw_arrays.npz`, the full
named `object_graph.json`, and an embedded mixture precursor under `mixture/`.
The manifest records archive/file hashes, original effective inputs, units,
fluid constants, convergence, method reconstruction and unknown producer
metadata. No MATLAB callbacks, native solver or CoolProp calls generate these
references. Original archive hashes were checked before and after export.

Source interpretation uses preserved OpenSTREAM commit
`a614c7173822a93c1e64ac28d1541cbac028cbd8`. The exact producer commit and original
CoolProp runtime are not established by the archive. This is agreement with
existing approved stored results, not a fresh known-runtime MATLAB execution.
The optional reader is mat-io 1.0.2 with the previously documented MCOS enum
workaround; its licensing and dependencies are in tools/REFERENCE_READER.md.

## Source mapping and dimensional checks

ThreeField film and droplet W [kg/s], U [m/s], and H [J/kg] are directly stored
properties. FourField base, wave and droplet W/U/H and wave FREQUENCY [Hz] are
also directly stored. The aggregate FourField film is a dependent property;
`+Solvers/+FourField/Film.m` defines:

- `W = base.W + wave.W`.
- `H = base.H`.
- `U = W / (base.W/base.U + wave.W/wave.U)`, elementwise. Where W is exactly
  zero, use base.U, including the source zero-flow fallback.

Both phase mass flow divided by velocity and the denominator have units kg/m,
so aggregate U has units m/s. The getters are evaluated from archived values;
they are distinguished from directly saved arrays in the manifest. Parent
references `base.film` and `wave.film` identify the exact containing film for
physical and all initialization states. Each physical film references its
saved mixture precursor. Initialization mixtures are distinct copied objects;
the complete raw graph preserves these relationships rather than flattening
them into a guessed alias structure.

MATLAB film matrices `(node,wall)` become `(time,node,wall)` even for one wall.
Droplet columns become `(time,node)`. Film ITR.N is a scalar per node, while
film residual arrays retain wall dimensions. No implicit squeeze/broadcast is
used for core comparisons. All reference coordinates and primary values are
finite and checked before export.

## Convergence and upstream coverage gaps

Both archive STATE enums are INITIALSTEPCONVERGED. Final pseudo-time point
and temporal increments satisfy the original strict thresholds. The three-field
last pseudo-time is 5 s; four-field last pseudo-time is 8 s. These are
initialization times, not physical elapsed transient duration.

The original annular solver compares film mass flow per perimeter `WL=W/PERIM`
in kg/(s m). The reference checker divides each state's W by perimeter before
subtracting, preserving source operation order.

The four-field wave's actual point frequency residual is `ITR.DF`. `ITR.DFW`
is an initialized, unused array and must not substitute for it. DF is absent
from the unsolved initial state; the export records that absence explicitly
and represents it as NaN in the aligned history. It is also absent in copied
physical state zero, because original copy behavior does not copy the actual
iteration struct. Final-pseudo DF is 0.0603654303546 Hz, below ERRORFW=0.1 Hz.
The original steady stopping predicate omits the frequency temporal increment.
The added supplementary check also passes: 0.0603654303546 Hz < SSCONVFW=0.1 Hz.

The first advanced four-field pseudo-time state uses the maximum 100 point
iterations. This intermediate state is retained, not discarded. Final point
and temporal checks pass, and its primary history profiles also agree with the
native result within the original relative tolerance.

`SolverIntegrationTest.m` names `film.basefilm`, while the source field is
`film.base`. The original test consequently skips the base-film profiles.
The audit compares original four-field film/drop/wave profiles (nine W/U/H
profiles) and additionally requires actual base-film W/U/H and wave frequency.
These four extra checks are explicitly supplementary; they are not falsely
attributed to the original test.

## Independent native comparisons

`tools/audit_recovered_annular.py` reads original MCOS objects directly and
independently reconstructs only the aggregate film getters. It does not read
the exported reference NPZ files or call native field methods. Fresh native
directories are `outputs/baseline-parity-01/ThreeFieldSolver/` and
`outputs/baseline-parity-01/FourFieldSolver/`. Reports are
`threefield-independent-audit.json` and `fourfield-independent-audit.json` in
their parent directory.

| Comparison | Physical profiles | Initialization profiles | Largest relative error |
|---|---:|---:|---:|
| ThreeField film/drop W/U/H | 6 pass | All 6 states pass | Physical 1.22500e-13; initialization 5.29623e-13 |
| FourField film/drop/wave W/U/H | 9 pass | All 9 states pass | 2.53961e-9, wave U |
| FourField actual base W/U/H and frequency | 4 pass | All 9 states pass | Physical 4.10782e-11; initialization 8.07245e-11 |

The four-field velocity difference is larger than mixture/three-field
roundoff-scale differences, but is still below the unchanged 1e-8 acceptance
criterion. This audit does not infer a cause or change a closure to reduce it.
Broader diagnostics are reported separately by the parent comparison tool.

## Physical inconsistency exists in the MATLAB archives

Using recovered absolute W/U values and saved saturated densities, occupied
area is independently evaluated as

`Aoccupied = sum(Wfilm/Ufilm)/rhoF + Wdrop/(Udrop*rhoF) + Wvapor/(Uvapor*rhoG)`.

Each term has units m2. The physically applicable comparison domain uses the
original stored annular transition cache `sigm_const >= 1-1e-12`, following the
source AFFNC accessor. Both cases have 72 such nodes, beginning at z=1.595 m.
No transition is recalculated using potentially changed parameters.

| Archived case | Maximum fully annular area discrepancy | Outlet discrepancy |
|---|---:|---:|
| ThreeField | 7.48525943686% | 1.60664429926% |
| FourField | 11.2410517421% | 1.07370486821% |

Both exceed the independently selected 1e-6 relative algebraic area-identity
tolerance. Their phase flow partition nevertheless closes to 1.39e-17 kg/s,
and the steady downstream annular mass-flux difference is 7.24089e-10 kg/s.
Partition or mass-flux agreement does not establish occupied-area consistency.
These specific steady inconsistencies are demonstrably present in the
original MATLAB-produced states. This result does not establish that every
previously observed transient problem is upstream; those require their own
reference evidence. No experimental validation is implied.

## Executed checks and reproduction

Eleven focused recovery tests passed, with one import-time pandas deprecation
warning from mat-io and no archive-decoding warning. They check archive hashes,
direct stored values, dimensions, named raw-array mapping, handle links,
dependent getters/zero-flow fallback, final actual DF, physical failures,
complete file hashes and refusal to overwrite. Logs and JUnit output:
`outputs/baseline-parity-01/annular-recovery-tests.log` and `.xml`.

```powershell
.\.venv\Scripts\python.exe tools\recover_annular_reference.py --framework ThreeField --output reference_exports\threefield-repeat
.\.venv\Scripts\python.exe tools\recover_annular_reference.py --framework FourField --output reference_exports\fourfield-repeat
.\.venv\Scripts\python.exe tools\audit_recovered_annular.py --framework ThreeField --native outputs\baseline-parity-01\ThreeFieldSolver --output outputs\threefield-audit-repeat.json
.\.venv\Scripts\python.exe tools\audit_recovered_annular.py --framework FourField --native outputs\baseline-parity-01\FourFieldSolver --output outputs\fourfield-audit-repeat.json
.\.venv\Scripts\python.exe -m pytest tools\test_recover_annular_reference.py -q
```

Use new output names. All original references and tolerances remain unchanged.
