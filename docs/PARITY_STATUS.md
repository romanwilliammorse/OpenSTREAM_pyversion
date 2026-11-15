# Capability and parity status

Snapshot: 2026-11-14. Target source: OpenSTREAM
`a614c7173822a93c1e64ac28d1541cbac028cbd8`, CoolPropWrapper
`a7c40902ff66faf6ed668986398bb1b9faa16e13`.

The local native Python application is operational, including a browser GUI and
command-window launcher. The four archived steady core baselines agree; full
feature parity, broader MATLAB numerical equivalence and experimental validation
remain separate, unfinished requirements.

## Progress measures

| Measure | Numerator / denominator | Interpretation |
|---|---:|---|
| Runnable solver-family breadth | 4 / 4 = 100% | Mixture, TwoFluid, ThreeField and FourField each have selected steady and original transient runs with numerical convergence |
| Selected steady example execution | 4 / 4 | Fresh original-input samples in outputs/release-02 |
| Selected transient example execution | 4 / 4 | Each framework has a completed 51-state, 101-node original-input transient |
| Passing archived MATLAB core baselines | 4 / 4 = 100% | All original TUTORIAL1 W/U/H profiles, initializations and precursors pass; this is not full-software parity |
| Existing native automated tests | 129 / 129 passed | Includes two new MRM branch tests; this is neither branch coverage nor full parity |
| Fresh-export comparator machinery tests | 34 / 34 passed | Historical synthetic fixtures |
| Baseline-audit native/recovery/comparison suite | 212 / 212 passed | Earlier executed checkpoint: 129 native + 83 recovery/comparison tests; one optional-reader deprecation and two retained four-field warnings |
| GUI 0.2.0 native/GUI suite | 213 / 213 passed | 129 native + 84 GUI tests, plus 5 passing JavaScript tests; recovery-tool internals were not rerun in this checkpoint |
| Bartolomey native data adapter | 34 / 34 records | 85 adapter/comparator/pilot-policy tests passed; source mapping checked, MATLAB execution not run |
| Bartolomey pilot execution / physical gates | 40 / 40 passed | Four records, two fixed closures, meshes and tighter controls; scoped steady checks only |
| Bartolomey numerical sensitivity | 29 / 32 passed | Three frozen mesh criteria failed and remain open |
| Experimental comparison against OpenSTREAM-database | Descriptive pilot executed | 59 unique measurements; uncertainty-qualified validation and independent holdout status not established; see BARTOLOMEY_PILOT.md |
| Acceptance requirements ledger | 81 reviewed rows | Separate implementation/test/MATLAB/physical/experimental statuses; not a completion percentage |
| Full feature/option/API parity | Not yet quantified | The ledger links 127 enum choices, 16 interpolation entries and 585 public method entries; combinations and operating-domain coverage remain incomplete |

The primary scientific parity metric is **framework baselines with a passing
executed comparison against MATLAB-produced core profiles / four framework
baselines**. It is currently 4/4. All archives were recovered without MATLAB.
Mixture method quantities and four-field dependent film properties were
evaluated from stored state using upstream formulas; all other core fields
are directly stored. All initialization core comparisons pass. Actual base-film
profiles and wave frequency also pass supplementary checks. Diagnostic
differences remain recorded; full-output equivalence is not claimed.
Passing all four establishes only the selected baseline agreement; complete
parity additionally requires branch/operating-domain, transient and API coverage.
Runnable solver-family breadth tracks implementation progress separately.
Neither fraction estimates remaining engineering effort or physical accuracy.

The declaration audit contains 585 non-constructor interface entries across 25
mapped classes: 447 native name candidates, 54 partial/internal alternatives,
77 infrastructure/presentation gaps, 5 explicitly unsupported method entries,
and 2 setter-contract review entries. Inherited methods repeat across classes.
These classifications are not acceptance results. In particular, 447/585 must
not be presented as an implementation or parity percentage. See
METHOD_COVERAGE.md/json for the scope and limitations.

## Operational capabilities

- Local Windows operation with an isolated Python environment, native CoolProp,
  NumPy/SciPy, installable package, browser GUI and command-window launcher.
- Four steady GUI starting cases, 163 input fields with units and reference/default
  values, JSON import/export, local runs, saved results and plots. The GUI does
  not yet expose physical-time schedules; native transient solvers are available.
- Original INP/JSON inputs, initialization, pseudo-time convergence and physical
  time stepping. Both MRM integrators and numerous original closure selections
  are translated; option-by-option evidence is in FEATURE_MAP.md.
- Native mixture, two-fluid, three-field and four-field calculations, including
  phase/film/drop/base/wave variables where applicable. Four-field currently
  supports one wall.
- Portable NPZ/CSV/JSON outputs with units, inputs, provenance and convergence;
  axial profiles, time histories, space-time maps and GIF animations.
- Portable MATLAB exporter and all-framework reference comparator. The exporter
  has not yet been executed in MATLAB.
- Native structural recovery of the mixture MCOS archive, preserved raw shapes,
  object graph, units, inputs and convergence; passing archived core comparison.

## Scientific limitations measured in native runs

| Framework | Actual finding |
|---|---|
| Mixture | Steady sample balances pass the recorded checks; transient conservative-enthalpy defects and mesh/time-step sensitivity remain documented |
| TwoFluid | Original transient occupied-area discrepancy reaches 43.3609% |
| ThreeField | Fully annular transient area discrepancy reaches 11.2004%; fixed-annular-domain mass residual reaches 0.00746082 kg/s |
| FourField | Fully annular transient area discrepancy reaches 15.5181%; fixed-annular-domain mass residual reaches 0.00642295 kg/s |

The latter two mass residuals are 10.6583% and 9.17564% of the 0.07 kg/s inlet.
Numerical convergence does not erase these failures. Annular acceptance excludes
upstream initialization fields. These findings do not yet establish Python–MATLAB
disagreement: the original implementation may exhibit the same behavior.
Experimental validation is also not established. Separately, the archived
steady MATLAB states reproduce occupied-area discrepancies of 41.056107%
(TwoFluid), 7.485259% (ThreeField) and 11.241052% (FourField), with the latter
two evaluated only in the fully annular region. Those checked steady failures
are shared with the source; this finding does not settle the transient cases.

## Next acceptance steps

The [acceptance matrix](ACCEPTANCE_MATRIX.md) and [ordered plan](ACCEPTANCE_PLAN.md)
are the current requirement-level tracker. The [literature review](LITERATURE_ACCEPTANCE_REVIEW.md)
distinguishes the supplied 2025 demonstration and experimental cases from the
pinned 2026 implementation, and records paper/companion parameter conflicts and
calibration-associated measurements. No new experimental run is claimed.

1. Implement a native adapter for the external
   [OpenSTREAM-database](https://github.com/OpenSTREAM-solvers/openstream-database/tree/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22),
   pinned to commit `b48541e6438a92b4c0ddc83cf0ceda3f71a59b22`. Start with selected
   Bartolomey void-fraction cases, matching geometry, boundary conditions, heating
   and measured quantity definitions. Report dimensional errors, convergence,
   balances and experimental/digitization uncertainty separately. No dataset
   run or physical-validation pass is claimed by the repository inspection.
2. Extend MATLAB comparison beyond the four steady baselines to transient and
   closure cases using independent outputs, recovered archives or the existing
   portable exporter in any available compatible MATLAB environment. Normal
   Python operation remains independent of MATLAB. The pinned core regression
   archive supplies four steady cases, not a transient acceptance suite.
3. Resolve each outstanding physical failure against source/reference evidence;
   distinguish translation differences from shared model defects before altering
   any underlying model. Preserve the recorded failed diagnostic comparisons.
4. Close the source/option/API acceptance ledger across all nine tutorial
   workflows, branch and legal multiwall behavior, numerical sensitivity, input
   writers and post-processing. Source-defective options remain explicit errors.

[PARITY_COMPLETION.md](PARITY_COMPLETION.md) gives the ordered acceptance plan,
six-family experimental-data audit, unit/domain issues requiring resolution,
and evidence needed to close each workstream. Method counts and GUI completion
are not proxies for scientific parity or physical accuracy.

## Evidence

- docs/FEATURE_MAP.md, METHOD_COVERAGE.json, VERIFICATION.md, PROGRESS.md.
- docs/MIXTURE_BASELINE_VERIFICATION.md; reference_exports/recovered-mixture-02;
  outputs/mixture-baseline-recovery/comparison-03 and verification-tests.log.
- docs/ALL_BASELINES_VERIFICATION.md; outputs/baseline-parity-02/summary.json
  and per-framework recovery/native/comparison directories; version 0.1.1.
- outputs/release-02/manifest.json.
- outputs/verification/native-sensitivity-01/transient-0.1/metadata.json.
- outputs/twofluid-transient-02/verification.json.
- outputs/threefield_transient_audited/verification.json.
- outputs/fourfield-transient-audited/verification.json.
- outputs/verification/final-tests-02.log and comparator-tests-02.log.
- [GUI verification](GUI_VERIFICATION.md), including the separate 0.2.0 test
  checkpoint and executed browser baseline runs.
- [Remaining completion and external-validation plan](PARITY_COMPLETION.md).

The baseline evidence includes fresh runs of all four baselines under version
0.1.1, 212 combined native/recovery/comparison tests and 34 synthetic
exporter-comparator tests. The later GUI 0.2.0 checkpoint passed its own 213
native/GUI and 5 JavaScript tests, plus four app baseline runs. These overlapping
suites must not be added together as a unique test count. The earlier
mixture-only checkpoint remains available. No weighted overall score is used.
