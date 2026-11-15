# Full parity and experimental validation: acceptance plan

The [Sawai numerical-control study](SAWAI_CONTROL_STUDY.md) completed eight
separate RELAXWW/MAXITER cases with unchanged equations, closures, tolerances
and defaults. Six meet native convergence; none meets the fixed-scale
common-state wave mass screen. Higher iteration caps have negligible effect.
Next, trace sequential proposals and subsequent coupled changes in the 0.25
native pass before preregistering tighter-stop/control checks. Preserve all
original failures and experimental metrics; no acceptance status is promoted.

Snapshot: 2026-11-15. Numerical target: OpenSTREAM `a614c7173822a93c1e64ac28d1541cbac028cbd8` and CoolPropWrapper `a7c40902ff66faf6ed668986398bb1b9faa16e13`. Database target: `b48541e6438a92b4c0ddc83cf0ceda3f71a59b22`. Python implementation: 0.2.1, with source-hash-tracked corrections. The supplied 2025 papers are additional model and benchmark evidence, not replacements for the pinned implementation.

Current execution update: the [matched diagnostic replay](MATCHED_DIAGNOSTIC_REPLAY.md)
corrected a confirmed FourField precursor-selection translation error and
rechecked all four archived baselines successfully. Sawai point oscillation
persists. A separate longer TwoFluid initialization budget converges without
changing tolerances; its original failed case and area diagnostic remain.
The [Sawai constituent trace](SAWAI_OSCILLATION_DIAGNOSTIC.md) now identifies
signed deposition as the dominant varying term in its retained point cycle;
no additional active translation error was confirmed. Next: preregister a
separate study of source-exposed numerical controls with unchanged tolerances,
obtain a matched runtime comparison when available, scope the
analogous ThreeField precursor selection, and replay affected cohorts before
replacing their pre-correction comparisons. Fresh MATLAB references remain
unavailable. The 81-row matrix retains all original acceptance criteria.

## Deliverables and interpretation

- [Acceptance matrix](ACCEPTANCE_MATRIX.md), with detailed scope, existing evidence, gaps, closure criteria and next actions for each requirement.
- [CSV](ACCEPTANCE_MATRIX.csv) and [JSON](ACCEPTANCE_MATRIX.json) for filtering and continued tracking.
- [Option annex](ACCEPTANCE_OPTIONS.csv): every declared InputEnums choice plus axial/time interpolation selections.
- [Public-method annex](ACCEPTANCE_METHODS.csv): all non-constructor entries in the existing 25-class inventory, including inherited repetitions.
- [Literature review](LITERATURE_ACCEPTANCE_REVIEW.md): paper-specific equations, assumptions, case distinctions, measured quantities and unresolved reproduction inputs.
- [Source fingerprints](../provenance/acceptance_sources.json): exact repository revisions and hashes of the three supplied PDFs. Original PDFs and raw extracted text are not redistributed.

These are separate inventories, not additive completion denominators. Method presence does not prove numerical correctness; a smoke test does not establish a closure's operating range. The matrix is a reviewed requirements baseline, not a claim that every legal combination, limiting state or experimental condition has already been enumerated or tested. Each option must be expanded into applicable framework/regime/wall/time/interaction cases before branch-complete acceptance can close. Add newly discovered requirements with stable IDs; retain old evidence and failed attempts.

The five evidence axes are independent: **implementation**, **native tests**, **MATLAB comparison**, **physical consistency**, and **experimental comparison**. `passed_scoped` applies only to the stated check and case. `partial` means incomplete evidence; `failed` means an executed criterion failed; `not_run` means a qualifying check has not been executed; `not_applicable` means that axis is outside the row's subject. `unsupported_source_defect` and `unsupported_port_gap` must remain distinguishable. Mixed groups are `partial` and identify their unsupported members in the gap text.

## Existing evidence that remains valid

The four TUTORIAL1 archived steady primary-profile comparisons, initialization histories and precursor checks passed at their recorded scope. The unchanged original core tolerance is `rtol=1e-8`, `atol=0`; exact reference zeros remain exact. Supplementary diagnostic failures are retained. Archive-producing source/property/runtime metadata remain incomplete; no fresh MATLAB runtime export has been executed.

The GUI Windows CI checkpoint passed 213 Python and nine JavaScript tests, with two retained four-field warnings. This is functional-test evidence, not closure-domain coverage or experimental accuracy. The subsequent [Bartolomey pilot](BARTOLOMEY_PILOT.md) adds 85 adapter/comparator/policy tests and 40 experimental-condition runs: all converge and pass scoped physical gates, while three of 32 sensitivity criteria fail. The original steady occupied-area discrepancies are reproduced in the MATLAB archives. Native transient area/balance failures and incomplete or failed refinement studies also remain recorded. Intentional one-way pressure coupling is a model approximation; neither agreement with it nor a physical-check failure by itself identifies a translation error.

## Ordered work

The historical Bartolomey Windows checkpoint `dfbcaa1` passed 298 Python and nine
JavaScript tests, with two retained FourField warnings, and builds both
distributions. The separate wheel-install smoke also passes. These are
functional/reproducibility checks; the pilot still fails three frozen mesh
criteria. Evidence: [CI receipt](../outputs/verification/bartolomey-windows-ci.json).

### 1. Establish trustworthy case and data contracts (P0)

Create a case registry with exact source/data revision, dataset/record ID, geometry, heating profile, input variables and units, closure coefficients, property backend/version, mesh/time controls, output definitions, comparison coordinates and calibration membership. Preserve raw source values beside normalized values and record every transformation. Missing coordinates, uncertainty or onset data must not become zeros.

Resolve the paper/companion differences before labeling a run as a reproduction:

- The ICMF demonstrations use a 5 m channel; the longer paper and current TUTORIAL1 use 5.5 m. Chan's droplet no-slip choice differs from the longer paper's full momentum choice. The current baseline is not a substitute for either paper case.
- The longer paper's Sawai wave-relaxation time is 0.2 s; the pinned NURETH21 companion uses 0.1 s. R. W. Morse confirmed 0.2 s as intended, so the main figure and matched replay use 0.2 s. Preserve the separately labeled 0.1 s comparison and unresolved historical plot-producing provenance. A sensitivity run is not permission to choose the best-fitting value and call it independent validation.
- The companion uses `VAPORFRIC='CONST'`, but the pinned solver declares `CONSTANT`. Establish a source-version or explicit input-migration record before executing the intended model; do not silently replace an invalid selection.
- The Wurtz coefficient reduction and Sawai relaxation choice are associated with fitting those measurements. Preserve these settings for reproduction and keep them separate from independent evaluation cases.
- Sawai period data require milliseconds-to-seconds conversion. Some stored measurement coordinates exceed the stored length; resolve the coordinate convention from source evidence or explicitly exclude those points. Do not clamp or extrapolate silently.

These issues block the affected reproduction claims, not all independent work. Recovering original uncertainty information can proceed while exploratory comparisons are developed.

### 2. Implement the native database adapter and first mixture campaign (P0/P1)

Implement an XML reader and dataset-specific input/measurement adapters, starting with the 34 Bartolomey records. Verify quantities, units, geometry, axial origin, heating and boundary-condition conversions against the source adapter. Use immutable dataset hashes and explicit exclusion reasons. First select a small set with complete inputs and usable coordinates; freeze the selection and acceptance policy before viewing prediction errors.

Current scope completed: all 34 Bartolomey records map to native inputs, and
the four-record pilot was frozen in commit `4e76cc1` before prediction errors.
Its 40 runs and descriptive measurement comparisons are saved. Numerical
acceptance remains open because three mesh criteria failed; quantified combined
uncertainty and independent validation also remain open. Other dataset families
and database transient input semantics still need adapters.

Run those mixture cases with selected supported closures, compare at the measured coordinates, and publish raw and normalized inputs, solver outputs, convergence/balance checks, mesh/time sensitivity where relevant, signed errors and unit-labelled plots. Separate elevation-based measurements from quality-based measurements; document interpolation and coordinate uncertainty. Missing uncertainty permits a descriptive error comparison but blocks an uncertainty-qualified validation pass.

### 3. Expand MATLAB equivalence in parallel (P0/P1)

Recover existing independent arrays or execute the prepared exporter in a compatible MATLAB environment if one becomes available. Normal Python operation remains MATLAB-free. Prioritize the four original transients, both MRM integrators, closures used by database cases, onset/boiling/dryout transitions and supported multiwall paths. Preserve effective inputs, array dimensions, units, coordinates, physical and pseudo-time axes, convergence and source/CoolProp metadata.

Retain original core tolerances. For newly assessed diagnostics or quantities near zero, establish dimensional absolute and relative criteria from numerical/error analysis before comparison; do not reclassify existing failures by widening tolerances. Separate final-state agreement from iteration-history agreement. Unknown runtime metadata and reference availability remain explicit gates, not values inferred from a plot.

### 4. Investigate physical failures and numerical uncertainty (P0/P1)

Compare identical-domain balances and occupied-area definitions in Python, stored MATLAB state and source equations. Distinguish implementation mistakes, iteration error, discretization error, clipping and intentional model approximations. Track local/global mass and enthalpy balances, applicable momentum terms, phase/area bounds and inlet/outlet conditions with units and justified domain masks. For annular fields, do not treat pre-onset initialization quantities as physical predictions.

Preserve the original model for compatibility. Any proposed model correction needs a documented scientific rationale, separate version/configuration and new validation evidence; it must not be concealed in the translation. Measurement comparisons may proceed with flags, but apparent agreement must not erase failed physical criteria or justify claims beyond their assessed domain. Every accepted refinement run must satisfy the applicable iterative convergence criteria. An observed order or Richardson-based uncertainty estimate additionally requires demonstrated asymptotic mesh/time-step behavior. Otherwise report sensitivity or a justified uncertainty bound with its limited basis, without claiming an asymptotic order.

### 5. Reproduce published comparisons, then evaluate independent measurements (P1)

Reproduce the specified Wurtz TS20 and Sawai records 1, 2, 5 and 6 from NURETH21 after their configuration/coordinate issues are resolved. Compare base thickness, wave velocity, number density and period using their actual definitions: `N=f/U_wave` is in m^-1, `f` in Hz, and `1/f` in seconds. Preserve milliseconds in the raw Sawai record. The companion MLX contains source and illustrations, with no numerical output-array entries; its TRACE section explicitly lacks reference results. Do not digitize a displayed curve and label it a raw MATLAB reference.

Extend to Adamsson film flow, suitable Wurtz/Sawai conditions outside calibration selections, and Bennett/Groeneveld thermal/dryout targets. Establish a target-by-target validation domain and account for original-publication, transcription/digitization and numerical uncertainty, propagated input/boundary-condition/property/coefficient uncertainty, and known correlations among them. Keep model discrepancy separate; do not enlarge the uncertainty budget merely to absorb disagreement. Report signed bias, MAE/RMSE and uncertainty-aware errors with units; relative errors need a defined treatment near zero. Keep measured, inferred and correlation-derived targets separate. An imposed measured dryout location cannot independently validate dryout prediction.

### 6. Close full interface and workflow parity (P1/P2)

Complete public input writers/default reporting, live-field extraction, interpolation conveniences, supported multiwall behavior, remaining diagnostics and post-processing. Translate and verify all nine tutorial workflows. Define explicit functional replacements for MATLAB-specific object serialization and graphical formats, rather than claiming binary MATLAB interoperability. Unsupported source expressions remain documented explicit errors unless an approved compatibility resolution exists.

Run the acceptance campaign from a clean Windows checkout with immutable references, pinned dependencies, scripts and saved reports. Close a requirement only when its stated criteria and evidence agree. Publish separate summaries for feature parity, MATLAB agreement, numerical consistency and experimental accuracy; do not combine them into one percentage.

## Rebuild and integrity check

```powershell
.\.venv\Scripts\python.exe tools\audit_method_coverage.py
.\.venv\Scripts\python.exe tools\build_acceptance_matrix.py
.\.venv\Scripts\python.exe tools\build_acceptance_matrix.py --check
```

The generator verifies required fields/statuses, unique IDs, local evidence paths, acyclic dependency links, every enum type/choice against its preserved source, declaration fingerprints and complete inventory links. Source/ledger text hashes normalize CRLF to LF for reproducibility across Git checkouts; PDF fingerprints remain exact binary hashes. It writes the human and machine-readable matrix and the two annexes. It does not execute MATLAB, new numerical cases or experimental validation, and it cannot certify the scientific truth of a prose acceptance claim.

Next: resolve Bartolomey's failed mesh/interpolation screens with a separately frozen refinement study, quantify measurement/digitization/input uncertainty, and establish source MRM reproduction and independent MATLAB references. Preserve the first pilot and its failed criteria. Paper-specific source discrepancies, other dataset adapters and the transient-reference campaign remain parallel work.
