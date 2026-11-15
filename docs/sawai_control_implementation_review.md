# Sawai numerical-control study: implementation review

Date: 2026-11-15. Preregistration commit: `a43298385963a248fc9dac2ffef517122724fb77`. This report is separate from the registered design review and does not rewrite that design. Governing equations and closure models remain unchanged throughout the project.

## Driver review before case execution

The reviewed driver is `tools/run_sawai_control_study.py`. It constructs the existing database case through the established Le Corre input path and requires exact equality with the corrected reference effective inputs before applying the registered numerical overrides. It constructs a new Options object and requires exact equality with the original complete input structure plus those overrides afterward. It also explicitly checks 100 cells and RELAXTW=0.2 s.

The manifest must already exist in the current Git commit byte-for-byte. All 25 native module hashes must match its frozen source map; corrected reference hashes and both historical matched-case evidence sets are checked before execution and afterward. Case identifiers are restricted to safe directory names, new case directories cannot overwrite existing attempts, and failed attempts retain their error records and any available partial primary state. The full grid contains only source-valid MAXITER values 100 and 250; the existing input validator already rejects values above the source uint8 limit rather than silently saturating them.

No solver method is replaced or monkeypatched. Each case calls the existing FourField constructor and solve method. Saving records the original source STATE, native convergence status, point increments, temporal/frequency flags and onset evidence. The driver also records native convergence after output evaluation; any difference must remain explicit in analysis.

All five numerical output files are compared with the corrected reference. The two mixture result/initialization files are separately required to agree exactly for a pure FourField-control interpretation. The unchanged 0.5/100 control must reproduce all 215 compared arrays. These are runtime checks that must pass on actual execution; this static review does not presume their outcome.

## Supplementary state and equation diagnostics

After normal output is saved, the driver deep-copies the entire solver so the copied object graph preserves shared references. It explicitly checks that copied base/wave fields retain the copied physical precursor, that each belongs to the copied current film, and that aggregate film and droplets share their copied aggregate precursor. New MTOT/FTOT and related evaluations occur on that detached graph, not as additional calls during the actual iteration.

Before and after copying/evaluating, a stored-state fingerprint checks numeric arrays, cache dictionaries, scalar values and object alias topology. Detached primary W/U/H/frequency arrays are also compared exactly. The immutable FluidProperties wrapper intentionally shares its locked backend through the existing deepcopy contract; opaque backend and lock internals are excluded and that exclusion is stated in the receipt. A whole-graph copy is preferable to independently copying fields, which could break the source's deliberate handle relationships.

The supplementary snapshots retain current and previous initialization state arrays, per-node source returns and SI units. They are explicitly labelled re-evaluations at a common final state, not recorded point-iteration proposals. Their primary arrays can therefore be checked against the saved initialization NPZ before residual analysis. Boundary node zero remains an inlet rather than an interior balance equation.

The independent analyzer's mass residual, unrelaxed defect and reference-scaled ratio follow the preregistered equations:

`R = W_j-W_(j-1) + dz/dt*(W_j/U_j-W_old/U_old) - P*MTOT*dz` [kg/s]

`D = -U_j/(U_j+dz/dt)*R` [kg/s]

`q = 0.5*abs(D)/(P*ERRORWF)` [dimensionless].

All terms are dimensionally consistent. Inlet diagnostics are NaN rather than falsely reported as zero. Nonfinite interior values remain flagged. The screen uses strict q<1 and is supplementary to the unchanged native stop. A frozen reference mask, its applicability checks and all-node residuals prevent candidate-dependent exclusions from hiding a failure. Qualification is a bounded numerical-control result, never a physical-validation or MATLAB-equivalence pass.

## Verification and review follow-up

The ten initial driver tests passed independently. They cover input isolation, prohibited changes, source iteration limits, immutable shared provenance, stored cache/object-alias mutation detection, strict point comparisons and preservation of failed attempts. These tests supplement, rather than replace, the fresh baseline and exact precursor comparisons.

Two provenance improvements were requested before the first run: bind the shared executed runner and its imported helper files to each case record, and either track ndarray alias topology or explicitly limit the fingerprint's topology claim to non-array objects. The initially reviewed fingerprint checked array content before recording identity, so equal-content array alias changes were not detected. This is an observer-integrity limitation, not a numerical equation change. Subsequent implementation and runtime results must be recorded below or in the final study report.

No numerical source file or registered design was edited by this review. No case was executed by the reviewer. The final aggregate classification and actual baseline/control results require their own completed audit.
