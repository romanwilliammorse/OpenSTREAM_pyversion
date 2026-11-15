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

## Completed observer and classification review

Both initial observer-integrity requests were resolved before the reviewed baseline execution. The stored-state fingerprint now records ndarray identity as well as shape, dtype and bytes, so changing equal-content array alias topology is detectable. Each case binds the shared executed runner by SHA-256 and records its imported helper hashes. The helpers must match the registration commit after line-ending normalization. The analyzer independently verifies these bindings and requires the frozen manifest to match the recorded registration commit byte-for-byte. These changes affect observation and provenance only.

The analyzer requires every registered qualification condition: the retained native converged flag; onset and nested checks; exact precursor arrays; finite primary states; a nonempty, unchanged reference mask whose candidate base/wave flows and velocities are positive and finite; and both reference-scaled common-state mass-defect maxima strictly below one on that mask. Nonfinite or empty selected sets cannot pass. All interior residuals, actual-case masks and signed bounds remain reported separately. No annular phase-volume constraint is added. The common-state diagnostic is not identical to the sequential point-iteration proposal, and the report must not describe it as the source stopping predicate.

An additional evidence-integrity check preserves the native flag before and after output evaluation and rejects a qualification claim if those flags differ. At a source temporal stop, the final point arrays must agree with the retained point flag. A claimed native pass also requires passing final point arrays. At temporal-budget exhaustion, the source can leave its point flag false even if the final point arrays pass; that legitimate failed attempt is retained without inventing an integrity failure. These checks do not rewrite native statuses or create a governing equation.

The unchanged control reproduced all 215 reference arrays exactly, including both precursor files. Its native converged flags were false both before and after output generation. Only this completed baseline was inspected during the present review; the other seven results and aggregate outcomes are outside this report's completed evidence.

The final independently invoked targeted tests were:

```powershell
.venv/Scripts/python.exe -m pytest tests/test_sawai_control_analysis.py tests/test_sawai_control_study.py -q
```

Result: 22 passed. In addition to the driver checks, these cover an independent source-proposal fixture, false acceptance from smaller relaxation, strict threshold comparisons, nonfinite and empty masks, fixed-mask applicability, exact saved-state binding, artifact tampering, and output/status consistency.

## Independent baseline arithmetic audit

`tools/audit_sawai_control_baseline.py` reads saved arrays without importing or executing an OpenSTREAM solver. It verifies the baseline artifact hashes and evaluates each of the 100 interior base equations and 100 interior wave equations with `Decimal.from_float` at 60-digit precision. The direct unrelaxed source proposal minus the saved flow is independently compared with the residual rearrangement. The 200 algebra/arithmetic checks passed.

| Field | Maximum residual discrepancy [kg/s] | Maximum direct-proposal defect discrepancy [kg/s] | Arithmetic roundoff allowance range [kg/s] |
|---|---:|---:|---:|
| Base | 1.8661194619196304e-21 | 1.8032537353656003e-21 | 2.1141e-18 to 3.8163e-18 |
| Wave | 2.0954139277193297e-20 | 2.005085804828539e-20 | 2.4813e-17 to 4.9830e-17 |

The allowance is 32 times binary64 epsilon times the L1 magnitude of the residual terms. It is solely a floating-point arithmetic check; it does not alter any scientific acceptance tolerance. Exact inputs, per-node discrepancies and allowances, source hashes and limitations are preserved in `outputs/verification/sawai-control-study-01/baseline_arithmetic_review.json`. The receipt identifies the analyzer hash at review, rather than assuming later edits have the same hash.

This audit establishes consistency of the saved baseline residual arithmetic with its frozen source returns. It does not independently validate the closure returns, prove suppression of an inner-iteration cycle, establish nonlinear stability or mesh independence, or supply missing MATLAB or experimental validation. No governing equation, closure, registered design or production setting was changed, and no solver case was executed by the reviewer.
