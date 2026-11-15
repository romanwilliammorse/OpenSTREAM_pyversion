# Progress and resume record

The user's requested full native port is **not yet complete**. Continue implementation and verification without replacing the preserved source or changing equations to obtain passing tests.

## Current presentation and diagnostic policy revision

The project owner confirmed tau=0.2 s as the intended paper setting, requested
all figure/subplot titles removed, and directed that ThreeField/FourField
phase-volume closure be informational rather than a convergence or acceptance
criterion. The original MATLAB OpenSTREAM solver convergence checks contain
no such gate. No governing equations, closure models or numerical stopping
criteria are changed; Mixture/TwoFluid checks are retained.

`figures-clean-02/` within the Le Corre campaign contains the current six clean
plots: five primary figures and a separate two-relaxation comparison. Main
Figure 7 uses only the already-computed 0.2 s branch. `PRESENTATION.json`
records hashes and unchanged original evidence. The numerical analysis and
all 69 original run records remain immutable. The former clean-01 presentation
is retained as a draft with subplot headings, superseded by clean-02.

`outputs/verification/annular-policy-01/reassessment.json` binds the revised
criterion scope to the original campaign: 61 annular area flags become
informational, four TwoFluid area rejections remain, and four Mixture assessments
are unchanged. Native convergence remains 63/69. This is not 61 new physical
validation passes. Other recorded bounds and source-equation residuals remain
separate evidence. Current GUI display applies this policy to historical
area-only badges while retaining the original assessment in details/downloads.

Final revision checks passed: 490 Python tests (two existing FourField warnings),
11 JavaScript tests and 13 archive-reader tests (one existing reader warning).
The 25-module AST audit confirms unchanged numerical equations, closure code,
stopping predicates and diagnostic arithmetic. A real Windows progress-file
PermissionError exposed during testing was fixed with a bounded permission-only
retry; the original trace and successful checks remain in annular-policy-01.
The method fingerprints and 81-row matrix have been regenerated and checked.
Live GUI inspection confirmed neutral annular information and retained TwoFluid
rejection without editing saved results.

Clean Windows CI passed for implementation commit
`056acf29110a59986bb7bbb082feda472b761f38` (run `43682832263`):
490 Python tests, 11 JavaScript tests, dependency consistency and distribution
build. The 13 archive-reader tests were local; CI did not rerun the campaign.

Three revised PDFs are prepared for publication under
`output/pdf/LeCorre_2025_Reports_03/`; the original report snapshot remains
intact. The local `_02` draft passed content/plate checks but left a one-sentence
orphan page; final prose tightening removes that pagination defect without
changing numerical evidence. Remaining delivery steps: export and visually
check the final PDFs, then publish. Do not rerun the 69-case campaign or modify
calculations to improve a comparison.

## Completed Le Corre campaign — 2026-11-14

Native Wurtz/Sawai adapters, frozen case execution, paper digitization and
independent comparison/audit tools are implemented. The preregistration is
`03fb5eaebc7b020f441c1b47544cd836978f8469`; implementation checkpoint
`4cda1a4d5c34dba397bc408ec27c93e69fe52aee` is public. No core solver equation
was changed. The exact publication-producing runtime remains unresolved:
historical MATLAB inputs differ from the current companion and include a
scalar relaxation-time incompatibility. See LECORRE_REPRODUCTION.md and
references/paper/lecorre2025/source_history.json.

All 69 frozen attempts completed in `outputs/validation/lecorre-2025-01/`:
33 source-default cases and 36 mesh/control studies. There are 63 native
convergence passes, 65 multifield physical-consistency rejections, and four
partially assessed mixture runs. The runner exited with the expected status 3;
no campaign process remains active. Preserve this directory and all failures.
Final `analysis/` contains numerical comparisons and five rendered plots for
Figures 3, 4, 6 and 7. Figure 5 remains incomplete because the exact TRACE
reference arrays and producing configurations are unavailable.

The independent output audit passed 4,708 arithmetic/provenance/accounting
checks, including all seven measurement-error groups. These are audit checks,
not physical-validation passes. The 31/36 eligible pairwise sensitivity
comparisons are retained. A separate posthoc common-coordinate diagnostic
admits 9/12 sentinels; it does not replace the original metrics. The upstream
OAFTRANSITION formula changes the physical blending length with mesh, so these
studies do not establish mesh independence. All 81 acceptance requirement IDs
and criteria remain unchanged; original Bartolomey failures remain open.

Local verification: 476 Python tests passed with two retained FourField
warnings; see `outputs/verification/lecorre-native-tests-final.log`.
Clean Windows CI for final scientific/code commit
`ac2f419ebfe58de705398c0be5c3840f037ea546` passed 476 Python and nine JavaScript
tests, dependency checks and wheel/sdist builds. See
`outputs/verification/lecorre-windows-ci-ac2f419.json` and its complete log.
The scientific outputs and matrix are public at that commit. Three updated
PDFs in `output/pdf/LeCorre_2025_Reports/` preserve the same source snapshot;
the reproduction report includes five enlarged figure plates. Their source,
text/numerical retention, PDF hashes and rendered layout review are recorded
alongside them. The earlier full documentation library remains unchanged.
No numerical rerun is required to resume from this checkpoint.

The user requested to see the original Figures 3/4 before identifying their
producer files; both original page-9 images were shown. No further production
metadata has been supplied. Continue the traced companion reconstruction while
keeping exact publication equivalence unverified.

Scientific next steps: recover or identify the original figure-producing inputs
and versions; resolve the historical relaxation-vector incompatibility and
paper/code 0.2 s versus 0.1 s discrepancy; recover Figure 5 TRACE evidence;
investigate source-matched volume closure and mesh-dependent blending in a
separately frozen study; establish measurement uncertainty and an independent
experimental holdout. Do not alter equations, inputs or thresholds to obtain
agreement. The four archived TUTORIAL1 agreements remain a separate result.

User clarification: geometric area is correctly specified. The multifield
rejection tests phase-volume closure, sum(W/(rho U))/A - 1. Recounting all 65
multifield results at relative tolerance 1e-4 instead of 1e-6 still gives zero
area-check passes; the smallest residual is 0.00162442438. No acceptance
criterion was changed. The user's requested native-calculation figures are
the final Figure 3, 4, 6 and 7 plots linked from README and the reproduction
report, with exact-source limitations and the unresolved Figure 5 stated.

## Earlier Bartolomey checkpoint — 0.2.1, 2026-11-14

Bartolomey adapter and frozen pilot implemented and executed. The database is
now a pinned submodule. Native loading/input mapping covers all 34 records;
85 new adapter/comparator/pilot-policy tests pass. Pilot entries 1/22/29/31,
HEM and Saha–Zuber/Bestion, 100/200/400 cells and two control sensitivities
produced 40 completed, converged runs passing the stated physical gates.
All 59 unique measurements were paired in both models; 29/32 sensitivity
checks passed, with three mesh failures retained. See BARTOLOMEY_PILOT.md and
outputs/validation/bartolomey-pilot-01. No fitting, MATLAB execution or
uncertainty-qualified experimental pass is claimed. The acceptance matrix
now includes this later evidence; the initial audit paragraph below is historical.

Published numerical/code checkpoint: `dfbcaa1d4cbb9c84c69e4fe3f56618150829e06c`.
Fresh Windows CI: 298 Python tests, 9 JavaScript tests, successful wheel/sdist
build, with two retained existing FourField warnings. Separate installed-wheel
smoke passed. Receipts are in outputs/verification/bartolomey-*.
Next: freeze a separate study addressing the zero-quality interpolation and
heated-end mesh effects, retain the three original failures, quantify the
measurement/input/digitization uncertainty, then reproduce calibrated MRM
settings separately from independent validation. New MATLAB references and
other dataset/framework acceptance requirements remain open.


After completing and publishing the acceptance audit, implemented the requested
GUI usability changes: original name-tag spelling in run titles/history/footer,
an initial four-model chooser, prominent workspace model selection, and a
collapsible sidebar with browser persistence. Saved history restores its actual
submitted model and inputs. Protected asynchronous selection/submission against
stale responses and a changed editor. See `GUI_USABILITY_VERIFICATION.md`.
The running editable installation serves these static changes immediately;
refresh the browser to load them. Numerical parity work resumes below.

Acceptance audit completed using the preserved implementation, evidence and the
three user-supplied 2025 papers (the user identifies as R.W. Morse). See
`ACCEPTANCE_MATRIX.md/json/csv`, `ACCEPTANCE_PLAN.md`, and
`LITERATURE_ACCEPTANCE_REVIEW.md`. There are 81 reviewed requirements, with
separate evidence axes and linked declaration annexes for 127 enum choices,
16 interpolation entries and 585 inherited/public method entries. These counts
are not additive and are not a full-parity percentage. The regenerated method
inventory now fingerprints the current 0.2.1 source. No solver equations,
reference arrays, numerical tolerances or new experimental results changed
in that initial audit.

Next: resolve the retained Bartolomey mesh/interpolation failures in a separately
frozen follow-up, quantify digitization/input uncertainty, and reproduce the
calibration-associated MRM settings separately. Broader database families remain
unported. Parallel gates: new transient MATLAB references; the
NURETH companion's rejected `CONST` value and 0.1 s relaxation setting versus
the paper's 0.2 s; Sawai coordinates/units; uncertainty and calibration partition.
The inspected companion MLX contains no numerical output-array entries.
At that earlier checkpoint, Wurtz/Sawai comparisons were literature evidence;
the completed Le Corre campaign above now adds executed Python comparisons.
Preserve their distinct settings and identify independent cases.
Rebuild/check with `tools/build_acceptance_matrix.py` and `--check`; source
ledgers are under `docs/acceptance/` and PDF hashes under `provenance/`.

The local GUI now follows the OpenSTREAM documentation's logo, fonts and colors,
with shorter visible labels and expandable help. Actions are **Check**, **Run**,
**Cancel**, **Import**, **Export** and **Save PNG**. All 163 inputs and separate
convergence, MATLAB-archive and physical-consistency results remain available.
No numerical equations or comparison tolerances changed. The focused restyle
suite passed 76 schema/reference/lock tests plus eight real-job GUI tests and
five JavaScript tests. Logs are `outputs/verification/gui-restyle-tests.log` and
`gui-restyle-backend-tests.log`; build and
installed-wheel mixture checks are recorded in `gui-0.2.1-build.log` and
`gui-0.2.1-wheel-smoke.log` under the same directory.

The project is published publicly at
[romanwilliammorse/OpenSTREAM_pyversion](https://github.com/romanwilliammorse/OpenSTREAM_pyversion);
the first complete source/evidence commit is
`9b3d67e8e56f30381a7ae127792de42079148546`. Its remote hash was checked against
the local commit. The upstream submodule remains pinned. Environments, caches,
scratch checkouts and live process locks are excluded; scientific outputs,
references, failures and license notices are retained. A Windows GitHub Actions
workflow passed clean installation, all Python and JavaScript tests, and
distribution builds. Its first run is linked in
[PUBLICATION.md](PUBLICATION.md).

Physical validation uses the external OpenSTREAM-database, pinned to
`b48541e6438a92b4c0ddc83cf0ceda3f71a59b22`. The Bartolomey and Le Corre
checkpoints above supersede the initial dataset inspection. Broader family
coverage, new MATLAB references and source/API gaps remain open. See
[PARITY_COMPLETION.md](PARITY_COMPLETION.md) for the acceptance plan, unit/domain
issues and separation of equivalence from validation.

## Earlier baseline checkpoint — 0.1.1

Roman approved continuation with "ok continue" after reviewing the mixture checkpoint and next steps. Proceed through TwoFluid, ThreeField and FourField in dependency order, preserving equations and original tolerances. The earlier visualization pause has ended. Existing implementations are retained and corrections must be justified against source/reference evidence.

Baseline result: **all four original TUTORIAL1 core baselines pass** with original 1e-8 relative/zero absolute tolerance. All initialization states and embedded mixture precursors also pass. Four-field actual base W/U/H and wave frequency pass additional checks. Reproducible complete run: `outputs/baseline-parity-02`, generated by `tools/verify_all_baselines.py`; report `docs/ALL_BASELINES_VERIFICATION.md`. Native package at this checkpoint: 0.1.1. One source-faithful correction was made to MRM Vapor.H infinity handling, with two branch tests and original MRM transient checks; steady mixture arrays remain bitwise unchanged. No governing equations or source tolerances changed.

Archived steady occupied-area errors are confirmed: TwoFluid 41.0561%, ThreeField 7.48526%, FourField 11.24105% (annular domain restricted). These specific defects exist in the original MATLAB states. Earlier transient area/mass findings are still unverified against transient MATLAB data. Original producer source/CoolProp metadata remain unknown; no fresh MATLAB execution or experimental validation. Diagnostic strict-relative failures remain visible. Primary baseline metric now 4/4; full-software completeness remains unquantified.

Completed 2026-11-14: structurally decoded the original mixture MCOS archive using isolated mat-io 1.0.2 plus a documented enumeration-reader correction. All nine original W/U/H profiles pass unchanged `rtol=1e-8`, `atol=0`; max physical relative error 6.22214e-13. All ten initialization states also pass core comparisons (max 7.18944e-13). Reference convergence and effective inputs checked, harmless historical zero-default differences disclosed. No solver/core code change was necessary. Fourteen supplementary diagnostic profiles fail the same strict relative-only policy at small absolute differences; recorded, not waived. 81 focused tests passed with one optional-reader pandas deprecation warning.

Earlier mixture-only checkpoint (superseded by the all-four result): `docs/MIXTURE_BASELINE_VERIFICATION.md`; `reference_exports/recovered-mixture-02/`; `outputs/mixture-baseline-recovery/native-before/`, `comparison-03/`, `independent-audit-02.json`, `verification-tests.log/xml`. Its original visualization is preserved. Baseline metric was 1/4 at that checkpoint; current metric is 4/4. Original producer source/CoolProp metadata remain unknown.

The approved continuation completed the other three archive recoveries and the MRM fallback correction. Continue with remaining feature/option/API acceptance gaps and additional transient/closure references; do not infer full parity from four passing baselines. The earlier requirement to obtain MATLAB before any reference comparison is superseded: archive recovery works locally. A known-runtime fresh MATLAB run remains useful additional evidence.

Baseline-checkpoint tests: **212 passed, 3 documented warnings**, 88.84 s, in `outputs/baseline-parity-01/complete-tests.log/xml` (129 native + 83 recovery/comparison). The separate fresh-export comparator's 34 synthetic tests also pass. Source mutations at that checkpoint were limited to the MRM fallback, version 0.1.1, and clearer diagnostic descriptions; all original archives and upstream/submodule source remain unchanged. The older 127/81-test checkpoint descriptions are historical.

## Anchors and environment

- Paths in this record are relative to the repository root.
- Local development branch: `codex/native-python`.
- Original OpenSTREAM source: `upstream/`, commit `a614c7173822a93c1e64ac28d1541cbac028cbd8`.
- Original nested property wrapper: `upstream/+CoolPropWrapper`, commit `a7c40902ff66faf6ed668986398bb1b9faa16e13`.
- Native interpreter: `.venv/Scripts/python.exe`, CPython3.12.14. Exact package versions: requirements.lock and provenance/environment.json.
- All normal-operation physics code is native Python under `src/openstream`; no MATLAB/Engine/Octave runtime calls.

## Implemented work

Original input parsing/defaults/validation, native properties, mixture field closures and time integration, native result tables/plots, portable MATLAB reference-export/comparison tooling, and independent unit/integration/sensitivity checks are in place. Additional framework implementations reside in their named modules; `FEATURE_MAP.md` and `VERIFICATION.md` are the status authority. An available class or translated enum is not evidence of full branch coverage.

The documented original mixture sample selects TUTORIAL1, not the sandbox's TUTORIAL2A. Original MAT references contain MATLAB MCOS objects. The mixture archive is now recovered and numerically compared as described above. The optional MATLAB exporter has only been source-reviewed. Do not substitute generated Python results for upstream references.

## Required next work

Historical pre-baseline release checkpoint: **127 pytest tests passed** with two retained four-field zero-slip warnings; **34 synthetic comparator tests passed**. Wheel/sdist built under dist/release-final and standalone installed-wheel sample smoke check passed. The 17 shipped Python modules matched src byte-for-byte and original license notices were bundled. Release examples and actual failure diagnostics are in outputs/release-02; logs are outputs/verification/final-tests-02.log and comparator-tests-02.log. All four frameworks have native implementations, numerically converged original samples and executed original transient workflows, but this does not remove the outstanding coverage/physical/reference failures below. METHOD_COVERAGE.json is an inventory, not a completeness score.

1. All four steady archive comparisons are complete. Expand reference coverage to transients/alternative closures and preserve all inputs, hashes, convergence records and unchanged tolerances. If an independent MATLAB environment later becomes available, run the exporter for known-runtime evidence; do not assume account/license access. No user pause is currently active.
2. Complete every unsupported option and resolve documented ambiguous upstream branches only with an explicit, documented compatibility policy. Review shared mutable-state semantics, vector-vs-scalar closure iterations, clipping and transition caching against actual MATLAB behavior.
3. Prioritize actual physical failures: TwoFluid transient area discrepancy 43.3609%; ThreeField fully annular transient area discrepancy 11.2004% and fixed-domain mass residual 0.00746082 kg/s; FourField fully annular transient area discrepancy 15.5181% and fixed-domain mass residual 0.00642295 kg/s. Extend successful sensitivity/closure coverage. Two tightened 25-cell ThreeField runs failed point convergence; do not use their differences as time convergence. Resolve these against MATLAB/source theory before modifying physics. The original cases' state arrays were preserved after adding diagnostics.
4. Complete remaining tutorial workflows and full post-processing options. Native SavedResults now supplies time histories, space–time maps, GIF animations, slicing and explicit pseudo-time labels. Missing grouped live diagnostics, custom MATLAB styling, 3D/video export, live transient/struct helpers and input writers are recorded in METHOD_COVERAGE.md/json.
5. Maintain source-to-Python feature map, tests and verification report after every change. Re-run only affected checks, then the complete suite for a release artifact. Capture provenance again and rebuild wheel after final modifications.
6. Experimental validation is separate: implement the inspected OpenSTREAM-database adapter, check original measurement conditions and uncertainty, and execute the scoped comparisons in PARITY_COMPLETION.md. Repository inspection is complete; experimental validation is not.

## Important retained observations

- Properties use prescribed system pressure, not solved axial pressure.
- Upstream copying of wall arrays preserves only the first column-major scalar; additional wall inlet entries can be overwritten.
- Annular onset/sigmoid caches can freeze on first invocation.
- Point and pseudo-time convergence are separate. Upstream can report temporal convergence despite point failure.
- Original transient mixture enthalpy equations exhibit a discrete product-rule energy defect; see saved sensitivity evidence.
- Three-field POSFILM clipping can leave an unconstrained film mass-equation residual at dryout; do not loosen residual tests to conceal it.
- Two-fluid phase-specific enthalpy transport also has a nonzero conservative energy defect; inspect documented source/copy semantics.
- Three-/four-field area/inventory acceptance is restricted to the fully annular region. Pre-onset fields are initialization quantities, not physical predictions. Fixed-domain transient mass checks require both faces and every cell to remain annular across all times.
- Four-field wave-frequency steady stopping and original base-field regression coverage require special attention; see framework notes.

## Resume from these artifacts

- `outputs/release-02`: fresh original steady cases, numerical arrays, units, inputs/hashes, convergence, diagnosed physical failures and plots.
- `outputs/twofluid-transient-02`, `outputs/threefield_transient_audited`: original transient cases and per-time independent checks; status 3 means a physical-consistency failure, not a tool crash.
- `outputs/fourfield-transient-audited/TUTORIAL5F`: final original four-field transient with domain-specific physical diagnostics. The earlier outputs/fourfield_tutorial5f numerical arrays remain bitwise identical and preserved.
- `outputs/saved-result-plots-02`, `outputs/final-diagnostic-plots`: inspected static plots and GIFs; the latter visibly label physical-check failures.
- `tools/export_matlab_reference.m`, `tools/compare_matlab_reference.py`, `docs/REFERENCE_COMPARISON.md`: all-framework portable export/comparison procedure; MATLAB still unavailable/unexecuted.
- `tools/audit_method_coverage.py`: regenerate the scoped method map after any source/API change.

No test result establishes experimental validation. Source-dependent unsupported physics remains explicit; do not substitute a different closure to remove an error. Normal calculations require only the local native Python environment.

Failed-development output `outputs/sample-01` is an incomplete serialization attempt (NaN input sentinel initially rejected by strict JSON). It is not a reference or verified result. It is retained for honesty and must not be used as a baseline.

## Local interactive installation

The user subsequently requested installation and opening for use. The package was reinstalled editable into the existing isolated environment; pip check passed. `OpenSTREAM.cmd` and Desktop `OpenSTREAM Python.lnk` launch the environment's IDLE shell with `tools/interactive_console.py`. No numerical implementation changed. Command help is in GETTING_STARTED.md.

Actual launcher checks: 46 quick pytest tests passed; sample(), transient(), history/map plotting and GIF export executed successfully. The new transient has 51 states and numerically converged. Logs are outputs/verification/interactive-launcher-check.log and interactive-transient-check.log; generated files are under outputs/interactive. The visible IDLE and Photos processes and the console-ready marker confirmed launch. Computer-use screenshot verification failed with the helper's window-owner mismatch; no claim of screenshot inspection of the launched IDLE window is made. This does not affect the separate executed solver/plot checks.

# GUI milestone — 0.2.0, 2026-11-14

User selected a local browser app with desktop shortcut, every supported input
in one comprehensive editor, and only the four verified steady baseline presets.
Implemented in gui.py/gui_worker.py/gui_schema.py/gui_reference.py/gui_lock.py,
gui_launcher.py and gui_static/. All 163 fields carry units/reference/default
metadata, unchanged presets are compared against immutable bundled archives,
and custom configurations are explicitly identified. Normal operation remains
native Python, using optional Flask/Waitress/Plotly locally.

Actual verification: 213 pytest tests plus 5 JavaScript logic tests passed;
all four local GUI baseline runs agree with the archives at the existing
tolerances. Mixture consistency passes; the other three retain physical area
failures. Browser editing, plots, cancel, history, JSON import/export and PNG
export were exercised. Standalone wheel smoke and pip checks passed. See
GUI_VERIFICATION.md and outputs/verification/gui-* for exact evidence and limits.
The GUI is at http://127.0.0.1:8765, output root outputs/gui, Desktop shortcut
OpenSTREAM GUI.lnk. GUI.md supplies launch/installation/usage commands.

Resume numerical parity work from the earlier ALL_BASELINES_VERIFICATION.md
and PARITY_STATUS.md; this GUI did not expand the verified physics scope.
Next GUI scope would require an explicit request for transient schedules or
nonconstant function editing. Keep all earlier physical-defect observations
and archive provenance; do not treat green reference agreement as validation.

