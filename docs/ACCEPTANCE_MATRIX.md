# Acceptance matrix

Generated from the reviewed ledgers in `docs/acceptance/`. This is a requirement/evidence inventory, not a percentage of full parity.

[Prioritized work and acceptance rules](ACCEPTANCE_PLAN.md) | [Complete CSV](ACCEPTANCE_MATRIX.csv) | [Machine-readable JSON](ACCEPTANCE_MATRIX.json) | [Literature review](LITERATURE_ACCEPTANCE_REVIEW.md)

Scope: **81 requirements**, **41 enum types / 127 choices**, 16 interpolation entries, and **585 public method entries including inheritance**. These inventories overlap and are not additive. Combinations and operating-domain cases must be expanded before branch-complete acceptance can be claimed.

`passed_scoped` means the cited evidence passed only its stated scope. `partial` means incomplete evidence or implementation; `failed` records an executed failed criterion; `not_run` means no qualifying executed check. `not_applicable` is only for an axis that does not apply. No status is inferred from a matching method name.

P0: establish trustworthy inputs/references and investigate blocking inconsistencies. P1: execute the first reference/measurement acceptance campaigns. P2: complete remaining interfaces, domains, and release coverage; these remain required.

## Experimental Validation

| ID / priority | Requirement | Implementation | Native checks | MATLAB | Physical | Experimental |
|---|---|---|---|---|---|---|
| EXP-005 / P0 | Implement native reading, selection and case input generation | partial | partial | not_run | not_applicable | partial |
| EXP-006 / P0 | Match the actual measured quantity and coordinate system | partial | partial | not_run | not_applicable | partial |
| EXP-007 / P0 | Establish evidence-based validation criteria | partial | partial | not_applicable | not_run | partial |
| EXP-008 / P1 | Produce reproducible per-case and aggregate validation evidence | partial | partial | not_applicable | failed | partial |
| EXP-009 / P1 | Execute the first measured-versus-calculated mixture cases | implemented | failed | not_run | passed_scoped | partial |
| EXP-010 / P1 | Reproduce the selected NURETH Figure 6 comparisons | implemented | passed_scoped | not_run | partial | partial |
| EXP-011 / P1 | Reproduce the selected NURETH Figure 7 comparisons | implemented | failed | not_run | partial | partial |
| EXP-012 / P0 | Resolve unit exceptions and out-of-domain measurement coordinates | partial | passed_scoped | not_applicable | partial | partial |
| EXP-014 / P1 | Separate model development, calibration-associated reproduction and independent evaluation | partial | partial | not_applicable | not_run | partial |
| EXP-015 / P2 | Compare predicted liquid-film flow against measured heated-tube film flow | missing | not_run | not_run | not_run | not_run |
| EXP-016 / P2 | Validate thermal predictions and onset/dryout observables separately | missing | not_run | not_run | not_run | not_run |
| EXP-017 / P2 | Validate critical-power search and CHF comparisons as distinct algorithms and observables | missing | not_run | not_run | not_run | not_run |

## Interface Parity

| ID / priority | Requirement | Implementation | Native checks | MATLAB | Physical | Experimental |
|---|---|---|---|---|---|---|
| API-001 / P1 | Read original INP and JSON records with auditable effective inputs. | implemented | passed_scoped | not_run | not_applicable | not_applicable |
| API-002 / P1 | Cover every declared default and enum, including solver-dependent defaults. | implemented | passed_scoped | not_run | not_applicable | not_applicable |
| API-003 / P1 | Provide equivalents for INP writing, INP-to-JSON conversion and used-default reports. | partial | partial | not_run | not_applicable | not_applicable |
| API-004 / P1 | Define a reproducible native contract for source function-valued input. | partial | partial | not_run | not_applicable | not_applicable |
| API-005 / P0 | Preserve geometry, wall orientation, units and time-dependent boundary meaning. | implemented | passed_scoped | not_run | not_applicable | not_applicable |
| API-006 / P1 | Verify every supported interpolation method and public coordinate convention. | partial | passed_scoped | not_run | not_applicable | not_applicable |
| API-007 / P0 | Preserve source update order, indexing and shared-state relationships. | implemented | passed_scoped | partial | not_applicable | not_applicable |
| API-010 / P1 | Audit public numerical method contracts beyond matching names. | partial | partial | partial | not_applicable | not_applicable |
| API-011 / P1 | Complete generic transient/struct extraction and interpolation convenience methods. | partial | partial | not_run | not_applicable | not_applicable |
| API-012 / P2 | Document and test native equivalents of Session, logging, solver state and output-directory rules. | partial | passed_scoped | not_run | not_applicable | not_applicable |
| API-013 / P1 | Complete the numerical data contract for all solver outputs. | implemented | passed_scoped | passed_scoped | not_applicable | not_applicable |
| API-014 / P2 | Verify implemented plots as faithful displays of saved arrays. | implemented | passed_scoped | not_run | not_applicable | not_applicable |
| API-015 / P2 | Close source plot options and live-calculation display gaps. | partial | partial | not_run | not_applicable | not_applicable |
| API-016 / P1 | Reproduce the complete quick-start workflow for all four frameworks. | partial | passed_scoped | passed_scoped | not_applicable | not_applicable |
| API-017 / P1 | Cover every original model tutorial operation and case selection. | partial | partial | partial | not_applicable | not_applicable |
| API-018 / P1 | Reproduce input inspection, equivalent INP/JSON loading and conversion workflows. | partial | partial | not_run | not_applicable | not_applicable |
| API-019 / P1 | Reproduce diagnostic and discretization-study workflows. | partial | partial | not_run | not_applicable | not_applicable |
| API-020 / P2 | Reproduce the complete advanced post-processing workflow with explicit format replacements. | partial | passed_scoped | not_run | not_applicable | not_applicable |
| API-024 / P2 | Preserve a usable local front end without overstating scientific coverage. | implemented | passed_scoped | passed_scoped | not_applicable | not_applicable |

## Literature Scope

| ID / priority | Requirement | Implementation | Native checks | MATLAB | Physical | Experimental |
|---|---|---|---|---|---|---|
| EXP-001 / P0 | Define distinct publication, companion and pinned-code targets | partial | partial | not_run | not_applicable | not_applicable |
| EXP-002 / P1 | Reproduce NURETH Figures 3-4 with their selected physics | implemented | failed | not_run | failed | not_applicable |
| EXP-003 / P1 | Reproduce the Chan demonstration as a separately identified transient | partial | not_run | not_run | not_run | not_applicable |
| EXP-004 / P2 | Reproduce the two-fluid code-to-code comparison without calling it experimental validation | partial | not_run | not_run | not_run | not_applicable |
| EXP-013 / P0 | Resolve paper-to-companion and companion-to-solver inconsistencies | partial | passed_scoped | not_run | not_applicable | not_applicable |
| EXP-018 / P0 | Enforce the supplied papers' domain limits without expanding parity into future model development | partial | partial | not_run | not_run | not_applicable |

## Matlab Equivalence

| ID / priority | Requirement | Implementation | Native checks | MATLAB | Physical | Experimental |
|---|---|---|---|---|---|---|
| CORE-001 / P1 | Preserve original TUTORIAL1 steady primary-profile agreement | implemented | passed_scoped | passed_scoped | passed_scoped | not_run |
| CORE-002 / P1 | Preserve original TUTORIAL1 steady primary-profile agreement | implemented | passed_scoped | passed_scoped | failed | not_run |
| CORE-003 / P1 | Preserve original TUTORIAL1 steady primary-profile agreement | implemented | passed_scoped | passed_scoped | failed | not_run |
| CORE-004 / P1 | Preserve original TUTORIAL1 steady primary-profile agreement | implemented | passed_scoped | passed_scoped | failed | not_run |
| CORE-005 / P1 | Preserve pseudo-time initialization and precursor semantics | implemented | passed_scoped | passed_scoped | not_applicable | not_applicable |
| CORE-006 / P0 | Resolve supplementary diagnostic comparison failures | implemented | partial | failed | not_applicable | not_applicable |
| CORE-007 / P0 | Verify original physical transient against MATLAB | implemented | passed_scoped | not_run | failed | not_run |
| CORE-008 / P0 | Verify original physical transient against MATLAB | implemented | passed_scoped | not_run | failed | not_run |
| CORE-009 / P0 | Verify original physical transient against MATLAB | implemented | passed_scoped | not_run | failed | not_run |
| CORE-010 / P0 | Verify original physical transient against MATLAB | implemented | passed_scoped | not_run | failed | not_run |
| CORE-011 / P1 | Cover void and slip closures | implemented | partial | not_run | partial | not_run |
| CORE-012 / P1 | Cover thermal nonequilibrium closures | implemented | partial | not_run | partial | not_run |
| CORE-013 / P0 | Verify both MRM integrators and exception semantics | implemented | passed_scoped | not_run | partial | not_run |
| CORE-014 / P1 | Cover relaxation and near-wall alternatives | implemented | partial | not_run | partial | not_run |
| CORE-015 / P1 | Cover friction, local losses and momentum components | implemented | partial | not_run | partial | not_run |
| CORE-016 / P1 | Cover supported wall heat-transfer closures | implemented | partial | not_run | partial | not_run |
| CORE-017 / P1 | Verify boiling-crisis, rewet and associated momentum switches | implemented | partial | not_run | partial | not_run |
| CORE-018 / P0 | Verify onset criteria, cached sigmoid and initialization split | implemented | partial | not_run | partial | not_run |
| CORE-019 / P1 | Cover phase momentum and local relative-velocity alternatives | implemented | partial | not_run | partial | not_run |
| CORE-020 / P1 | Cover interfacial area, drag and heat/mass exchange | implemented | partial | not_run | partial | not_run |
| CORE-021 / P1 | Cover entrainment, deposition and obstruction enhancement | implemented | partial | not_run | partial | not_run |
| CORE-022 / P0 | Cover film/drop momentum alternatives and nested secant behavior | implemented | partial | not_run | partial | not_run |
| CORE-023 / P1 | Cover base/wave split, geometry and frequency closures | implemented | partial | not_run | partial | not_run |
| CORE-024 / P1 | Cover base/wave momentum and shear coupling | implemented | partial | not_run | partial | not_run |
| CORE-034 / P1 | Verify supported multiwall calculations and isolate dimension ambiguities | partial | partial | not_run | partial | not_run |
| CORE-035 / P1 | Resolve unsupported model selections without substituting physics | unsupported_source_defect | passed_scoped | not_run | not_applicable | not_applicable |
| CORE-036 / P1 | Complete MATLAB-to-Python edge-case equivalence | implemented | partial | not_run | partial | not_run |

## Numerical Verification

| ID / priority | Requirement | Implementation | Native checks | MATLAB | Physical | Experimental |
|---|---|---|---|---|---|---|
| CORE-025 / P1 | Retain independent steady mass, energy and momentum checks | implemented | passed_scoped | not_applicable | passed_scoped | not_run |
| CORE-026 / P0 | Resolve occupied-area and conservative-balance failure | implemented | passed_scoped | passed_scoped | failed | not_run |
| CORE-027 / P0 | Assess source-equation dryout mass residuals; report annular volume diagnostics | implemented | passed_scoped | passed_scoped | failed | not_run |
| CORE-028 / P0 | Assess source-equation compensating-clip residuals; report annular volume diagnostics | implemented | passed_scoped | passed_scoped | failed | not_run |
| CORE-029 / P0 | Separate increment stopping, nested solves and physical residuals | implemented | passed_scoped | not_run | partial | not_run |
| CORE-030 / P0 | Establish mesh and time-step numerical uncertainty | partial | passed_scoped | not_applicable | partial | not_run |
| CORE-031 / P0 | Complete successful mesh/time-step study | partial | failed | not_applicable | failed | not_run |
| CORE-032 / P0 | Complete annular mesh/time-step study with point convergence | partial | failed | not_applicable | failed | not_run |
| CORE-033 / P0 | Establish wave/base/drop mesh and time-step uncertainty | partial | not_run | not_applicable | not_run | not_run |
| CORE-037 / P0 | Enforce documented physical scope and closure-specific limits | partial | partial | not_applicable | partial | not_run |

## Reference Infrastructure

| ID / priority | Requirement | Implementation | Native checks | MATLAB | Physical | Experimental |
|---|---|---|---|---|---|---|
| API-008 / P0 | Preserve the native CoolProp backend, clamping and pressure contract. | implemented | passed_scoped | partial | passed_scoped | not_applicable |
| API-009 / P1 | Resolve QKMAX optimization equivalence and external wrapper API boundaries. | partial | partial | not_run | not_applicable | not_applicable |
| API-021 / P0 | Execute and verify the portable exporter against a known MATLAB environment. | implemented | partial | not_run | not_applicable | not_applicable |
| API-022 / P0 | Keep structural MAT5/MCOS recovery auditable and correctly scoped. | implemented | passed_scoped | passed_scoped | not_applicable | not_applicable |
| API-023 / P0 | Maintain trustworthy comparisons for fresh exports and recovered archives. | implemented | passed_scoped | passed_scoped | not_applicable | not_applicable |

## Release

| ID / priority | Requirement | Implementation | Native checks | MATLAB | Physical | Experimental |
|---|---|---|---|---|---|---|
| API-025 / P1 | Retain clean Windows installation, package contents and no-MATLAB runtime independence. | implemented | passed_scoped | not_applicable | not_applicable | not_applicable |
| API-026 / P0 | Keep the acceptance ledger and historical evidence internally consistent. | partial | partial | not_applicable | not_applicable | not_applicable |

## Requirement details

### CORE-001: Mixture

**Scope:** TUTORIAL1/DEFAULT/TUTORIAL1/tutorial1.inp; 100 cells and 101 nodes; 9 original W/U/H profiles. The common case is 6 MPa, 0.07 kg/s, 87.5 kW and 5.5 m.

**Missing or unverified:** Selected-case agreement only. Archive producer source, MATLAB and CoolProp versions remain unknown; the result does not cover other closures or establish physical accuracy.

**Acceptance evidence required:**

- Compare every original core value at all matching nodes using unchanged rtol=1e-8, atol=0 and exact reference zeros.
- Preserve original input/hash/unit/axis/convergence checks and separate the physical-consistency outcome from the archive comparison.

**Next action:** Retain this immutable regression gate while extending reference cases.

**Evidence:** `docs/ALL_BASELINES_VERIFICATION.md`; `outputs/baseline-parity-02/Mixture/comparison/comparison.json`; `outputs/baseline-parity-02/summary.json`; `tests/test_solver.py`; `outputs/verification/native-sensitivity-01/verification.json`

**Dependencies:** API-022, API-023

### CORE-002: TwoFluid

**Scope:** TUTORIAL1/DEFAULT/TUTORIAL1/tutorial1.inp; 100 cells and 101 nodes; 6 original W/U/H profiles. The common case is 6 MPa, 0.07 kg/s, 87.5 kW and 5.5 m.

**Missing or unverified:** Selected-case agreement only. Archive producer source, MATLAB and CoolProp versions remain unknown; the result does not cover other closures or establish physical accuracy.

**Acceptance evidence required:**

- Compare every original core value at all matching nodes using unchanged rtol=1e-8, atol=0 and exact reference zeros.
- Preserve original input/hash/unit/axis/convergence checks and separate the physical-consistency outcome from the archive comparison.

**Next action:** Retain this immutable regression gate while extending reference cases.

**Evidence:** `docs/ALL_BASELINES_VERIFICATION.md`; `outputs/baseline-parity-02/TwoFluid/comparison/comparison.json`; `outputs/baseline-parity-02/summary.json`

**Dependencies:** API-022, API-023

### CORE-003: ThreeField

**Scope:** TUTORIAL1/DEFAULT/TUTORIAL1/tutorial1.inp; 100 cells and 101 nodes; 6 original W/U/H profiles. The common case is 6 MPa, 0.07 kg/s, 87.5 kW and 5.5 m.

**Missing or unverified:** Selected-case agreement only. Archive producer source, MATLAB and CoolProp versions remain unknown; the result does not cover other closures or establish physical accuracy. Current policy, explicitly directed by R. W. Morse on 2026-11-14: ThreeField/FourField phase-volume closure is supplemental only, with no pass/fail role; original receipts remain immutable. Mixture/TwoFluid policy and other source-equation/numerical criteria are unchanged. Its retained physical failure concerns separately recorded clipped-cell mass residuals (CORE-027), not area alone.

**Acceptance evidence required:**

- Compare every original core value at all matching nodes using unchanged rtol=1e-8, atol=0 and exact reference zeros.
- Preserve original input/hash/unit/axis/convergence checks and separate the physical-consistency outcome from the archive comparison.

**Next action:** Retain this immutable regression gate while extending reference cases.

**Evidence:** `docs/ALL_BASELINES_VERIFICATION.md`; `outputs/baseline-parity-02/ThreeField/comparison/comparison.json`; `outputs/baseline-parity-02/summary.json`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `outputs/verification/annular-policy-01/reassessment.json`

**Dependencies:** API-022, API-023

### CORE-004: FourField

**Scope:** TUTORIAL1/DEFAULT/TUTORIAL1/tutorial1.inp; 100 cells and 101 nodes; 9 original W/U/H profiles. The common case is 6 MPa, 0.07 kg/s, 87.5 kW and 5.5 m.

**Missing or unverified:** Selected-case agreement only. Archive producer source, MATLAB and CoolProp versions remain unknown; the result does not cover other closures or establish physical accuracy. Current policy, explicitly directed by R. W. Morse on 2026-11-14: ThreeField/FourField phase-volume closure is supplemental only, with no pass/fail role; original receipts remain immutable. Mixture/TwoFluid policy and other source-equation/numerical criteria are unchanged. Its retained physical failure concerns separately recorded base/wave mass residuals (CORE-028), not area alone.

**Acceptance evidence required:**

- Compare every original core value at all matching nodes using unchanged rtol=1e-8, atol=0 and exact reference zeros.
- Preserve original input/hash/unit/axis/convergence checks and separate the physical-consistency outcome from the archive comparison.

**Next action:** Retain this immutable regression gate while extending reference cases.

**Evidence:** `docs/ALL_BASELINES_VERIFICATION.md`; `outputs/baseline-parity-02/FourField/comparison/comparison.json`; `outputs/baseline-parity-02/summary.json`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `outputs/verification/annular-policy-01/reassessment.json`

**Dependencies:** API-022, API-023

### CORE-005: All frameworks

**Scope:** All 10/15/6/9 archived initialization states for Mixture/TwoFluid/ThreeField/FourField, including embedded mixture precursors; physical time is separate.

**Missing or unverified:** Agreement is limited to stored TUTORIAL1 histories; the archive does not preserve every point iteration.

**Acceptance evidence required:**

- Continue exact matching of archived state counts, axes and core profiles at rtol=1e-8, atol=0.
- Verify boundary-node exclusion, shallow aggregate handles and final initialization-to-physical transfer on additional cases.

**Next action:** Extend reference export to retain point iterates where needed and branch-specific initialization cases.

**Evidence:** `docs/ALL_BASELINES_VERIFICATION.md`; `outputs/baseline-parity-02/summary.json`; `docs/annular_reference_audit.md`

**Dependencies:** API-022, API-023, API-007

### CORE-006: All frameworks

**Scope:** Strict relative-only physical-state failures: 14 Mixture, 6 TwoFluid, 2 ThreeField and 1 FourField; additional annular initialization iteration differences remain.

**Missing or unverified:** Eleven mixture failures are accounted for by stored-state differences; three point-increment differences lack archived intermediate iterates. Other failures must retain their recorded status.

**Acceptance evidence required:**

- Keep all existing strict comparisons and failures unchanged.
- Reconstruct diagnostics independently with their units and expression order; identify translation errors separately from roundoff amplification and unknown producer metadata.
- Any additional diagnostic tolerance requires a recorded numerical/physical justification fixed before rerunning; it must not replace the original failed metric.

**Next action:** Capture missing point iterates/property versions and perform quantity-by-quantity attribution before deciding any separately justified diagnostic acceptance policy.

**Evidence:** `docs/ALL_BASELINES_VERIFICATION.md`; `docs/mixture_followup.md`; `outputs/mixture-followup/diagnostic-audit.json`; `outputs/baseline-parity-02`

**Dependencies:** API-023, API-010

### CORE-007: Mixture

**Scope:** TUTORIAL2A original 0-5 s power-reduction schedule, 100 cells, 0.1 s nominal step; initialization is a separate dataset.

**Missing or unverified:** No MATLAB transient arrays. The material-enthalpy discretization has a measured conservative-energy product-rule defect; steady agreement does not resolve transient equivalence.

**Acceptance evidence required:**

- Match every stored physical time and space coordinate, W/P/H and derived phase states under predeclared dimensional tolerances.
- Check each boundary schedule change, storage term and source-ordered update; report conservative and material-equation residuals separately.

**Next action:** Recover or export a time-resolved MATLAB case with all boundary records, property versions and equation residuals.

**Evidence:** `tests/test_transient.py`; `outputs/verification/native-sensitivity-01/verification.json`; `docs/VERIFICATION.md`

**Dependencies:** API-021, API-008, CORE-036

### CORE-008: TwoFluid

**Scope:** TUTORIAL3B with tutorial2_transient.inp; 51 states, 101 nodes.

**Missing or unverified:** No MATLAB transient reference. Native run converges but maximum occupied-area discrepancy is 43.3609%; this transient defect's source attribution is unresolved.

**Acceptance evidence required:**

- Compare phase W/U/H and mixture-precursor fields at every physical state with the same boundary schedule.
- Preserve measured mass/enthalpy/momentum residuals and clamp applicability; matching MATLAB cannot waive physical failures.

**Next action:** Obtain matching MATLAB transient arrays and independently compare inventories, sources and constrained momentum updates.

**Evidence:** `tools/verify_twofluid_transient.py`; `outputs/twofluid-transient-02/verification.json`; `docs/twofluid_notes.md`

**Dependencies:** API-021, API-008, CORE-036

### CORE-009: ThreeField

**Scope:** TUTORIAL4D original 51-state, 101-node transient; annular acceptance only where applicable.

**Missing or unverified:** No MATLAB transient reference. Fully annular area discrepancy 11.2004% is now supplemental only; the separate fixed-annular-domain mass residual 0.00746082 kg/s remains the physical failure evidence. Current policy, explicitly directed by R. W. Morse on 2026-11-14: ThreeField/FourField phase-volume closure is supplemental only, with no pass/fail role; original receipts remain immutable. Mixture/TwoFluid policy and other source-equation/numerical criteria are unchanged.

**Acceptance evidence required:**

- Compare film/drop W/U/H, mixture precursor and source terms over every state.
- Use a control volume annular at all included times for storage checks; do not mix pre-annular initialization fields into physical acceptance.

**Next action:** Obtain matching MATLAB transient arrays and source-order traces at onset, momentum bounds and dryout.

**Evidence:** `tools/verify_threefield_transient.py`; `outputs/threefield_transient_audited/verification.json`; `docs/threefield_transient.md`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `outputs/verification/annular-policy-01/reassessment.json`

**Dependencies:** API-021, API-008, CORE-018, CORE-036

### CORE-010: FourField

**Scope:** TUTORIAL5E plus tutorial2_transient.inp (workflow named TUTORIAL5F); 51 states, 101 nodes, one wall.

**Missing or unverified:** No MATLAB transient reference. Fully annular area discrepancy 15.5181% is now supplemental only; the separate fixed-annular mass residual 0.00642295 kg/s remains the physical failure evidence. Current policy, explicitly directed by R. W. Morse on 2026-11-14: ThreeField/FourField phase-volume closure is supplemental only, with no pass/fail role; original receipts remain immutable. Mixture/TwoFluid policy and other source-equation/numerical criteria are unchanged.

**Acceptance evidence required:**

- Compare actual film.base, film.wave and drop W/U/H plus frequency, not the erroneous upstream basefilm traversal alone.
- Preserve all physical failures, including storage residuals in the common annular domain.

**Next action:** Export native and MATLAB base/wave/drop/frequency histories with source-order and constraint diagnostics.

**Evidence:** `tools/verify_fourfield.py`; `outputs/fourfield-transient-audited/verification.json`; `docs/fourfield_notes.md`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `outputs/verification/annular-policy-01/reassessment.json`

**Dependencies:** API-021, API-008, CORE-018, CORE-036

### CORE-011: Mixture closures

**Scope:** VOID=HOMOGENEOUS/SLIP/BESTION/EPRI; slip corrections and phase reconstruction, with subcooled/two-phase/pure-phase boundaries.

**Missing or unverified:** Selected identities and tutorial executions exist; no independent MATLAB arrays across all alternatives and operating regimes.

**Acceptance evidence required:**

- Match independently exported void, phase velocity and energy/momentum correction fields for each legal closure.
- Verify phase mass/energy partition and appropriate bounds without treating boundedness as correlation validation.

**Next action:** Select minimal branch-isolating cases and compatible parameter sweeps before database comparisons.

**Evidence:** `tests/test_fields.py`; `outputs/mixture_variant_checks.json`; `docs/field_notes.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-012: Mixture closures

**Scope:** THERMALNONEQ=EQUILIBRIUM/SAHAZUBER/EPRI/MRM, including boiling onset and zero-heat limits.

**Missing or unverified:** EPRI has scoped smoke/bound checks; other tutorial executions do not establish reference equivalence. None is experimentally validated in this port.

**Acceptance evidence required:**

- Check every legal thermal model against independent MATLAB states and valid limiting conditions.
- Retain explicit applicability domains and avoid substituting saturation equilibrium for unevaluated nonequilibrium physics.

**Next action:** Compare thermal branch cases with exact wall-power partitions, void/quality definitions and enthalpy states.

**Evidence:** `tests/test_fields.py`; `outputs/mixture_variant_checks.json`; `outputs/mixture-followup/mrm-transient-after.json`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-013: Mixture MRM

**Scope:** MRMTIMEINT=EULER/EXPONENTIAL; NaN-only MRM Vapor.H fallback versus NaN-or-infinity non-MRM behavior; finite valid calculations and synthetic invalid-state tests distinguished.

**Missing or unverified:** Both original transients executed, but no MATLAB reference. Loose point-increment criteria leave material residuals; tightened native checks cover only selected conditions.

**Acceptance evidence required:**

- Exercise both integrators at schedule transitions and verify residuals with units kg/(s m), W/m and Pa.
- Preserve NaN/Inf branch semantics without interpreting deliberately invalid synthetic states as physical predictions.

**Next action:** Generate MRM transient MATLAB references and repeat converged refinement with source integrators unchanged.

**Evidence:** `tests/test_mixture_mrm_semantics.py`; `docs/mixture_followup.md`; `outputs/mrm_transient_checks.json`; `outputs/mrm_transient_tight_checks.json`; `outputs/mixture-followup/mrm-transient-after.json`

**Dependencies:** API-008, CORE-012, CORE-036

### CORE-014: Mixture relaxation

**Scope:** THERMALRELAX=FOURIERX/TIMEX/VOID/HOMOGENEOUS/FOURIER; NEARWALLH and NEARWALLRELAX selections; obstruction overrides and coefficient units.

**Missing or unverified:** All relaxation branches have selected finite/positive tests; near-wall alternatives are largely source-inspected. No branch-wide numerical reference or uncertainty evidence.

**Acceptance evidence required:**

- Check relaxation times in seconds and each mixed-unit coefficient explicitly.
- Verify source NaN omission and near-wall source cancellation at boundaries; compare corresponding MATLAB outputs.

**Next action:** Construct branch-specific fixtures including obstruction interpolation, condensation/evaporation, and pure-phase limits.

**Evidence:** `tests/test_fields.py`; `docs/field_notes.md`; `docs/FEATURE_MAP.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-015: Mixture momentum

**Scope:** SPMTM=BLASIUS; TPFM=HOMOGENEOUS/SLIP/EPRI; TPKM=HOMOGENEOUS/SLIP/ROMIE; BTMTM choices; gravity, spatial/temporal acceleration and slip corrections.

**Missing or unverified:** Analytic homogeneous pressure-drop and selected local-loss cases exist; several alternatives only have source inspection.

**Acceptance evidence required:**

- Check sign, units and sum of pressure components in Pa at obstruction nodes, inclinations and time-dependent states.
- Verify nearest-node ties, repeated obstructions and slip correction behavior without changing cached source order.

**Next action:** Build independent component-by-component pressure and force fixtures and MATLAB comparison cases.

**Evidence:** `tests/test_fields.py`; `tests/test_transient.py`; `outputs/mixture_variant_checks.json`; `docs/VERIFICATION.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-016: Mixture heat transfer

**Scope:** SPHTM=DITTUSBOELTER/SIEDERTATE/GNIELINSKI; TPHTM=THOM; BTHTM=VAPOR/DOUGALL/BISHOP/MOECK/DELORME/CONDIEIV (DELORME one wall).

**Missing or unverified:** Selected finite/positive coefficient and wall-energy identities are not full model-domain tests or validation. No alternative-closure MATLAB references.

**Acceptance evidence required:**

- Verify W/(m2 K) coefficients, K temperatures and W/m2 flux with phase-specific property choices.
- Test relevant regime boundaries and thermal partitions; compare field outputs before experimental fitting.

**Next action:** Map each closure's published domain, create independently calculated fixture values and obtain MATLAB wall-temperature/flux arrays.

**Evidence:** `tests/test_fields.py`; `docs/field_notes.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-017: Mixture transitions

**Scope:** CBT, MFBT and BTMTM legal selections, including BIASI/BEZRUKOV/ELEVATION, NONE/CONSTANT rewet behavior and crossing histories.

**Missing or unverified:** NONE and prescribed ELEVATION are exercised; remaining transition branches are largely source-inspected. Transient transition timing and hysteresis/reset behavior are unverified.

**Acceptance evidence required:**

- Record the criterion, first crossed cell/time and resulting model selection for each legal option.
- Distinguish prescribed measured onset from a predicted onset when later validating against data.

**Next action:** Create cases crossing each applicable transition and retrieve MATLAB event/field histories.

**Evidence:** `tests/test_fields.py`; `docs/FEATURE_MAP.md`; `docs/field_notes.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-018: Annular onset

**Scope:** OAF=WALLIS/WALLIS_SIMP/LEVITAN; OAFENTRAINED=RATIO/EQUILIBRIUM; transition width and node-dependent caching.

**Missing or unverified:** WALLIS/cached sigmoid and selected split cases tested; alternative onset and wall-enhancement interactions lack references. Mesh changes alter the source sigmoid's physical width.

**Acceptance evidence required:**

- Compare onset indices/elevations and cached transition arrays exactly under documented indexing semantics.
- Separate pre-annular initialization from physical annular acceptance; do not interpret mesh-dependent smoothing as pure discretization error.

**Next action:** Export onset location, cached transition function, split equations and closure convergence for alternative branches and meshes.

**Evidence:** `tests/test_fields.py`; `outputs/threefield_variant_checks.json`; `docs/threefield_transient.md`; `docs/fourfield_notes.md`

**Dependencies:** API-006, API-007, CORE-037

### CORE-019: TwoFluid momentum

**Scope:** MOMENTLIQUID/GAS=MIXTURE/SLIP/FULL; LOCRELVEL=AREAMEAN/SCALED/DRIFT in implemented legal paths; one-wall FULL momentum.

**Missing or unverified:** Selected original momentum tutorials and slip identities tested. Other option combinations, regime transitions and dimensional balance at clipped bounds lack MATLAB references. Current policy, explicitly directed by R. W. Morse on 2026-11-14: ThreeField/FourField phase-volume closure is supplemental only, with no pass/fail role; original receipts remain immutable. Mixture/TwoFluid policy and other source-equation/numerical criteria are unchanged.

**Acceptance evidence required:**

- Verify phase velocities, material acceleration and conservative force sums in their proper units.
- Report reconstruction masks and clamp effects. Occupied-area acceptance for Mixture/TwoFluid is unchanged; for ThreeField/FourField the phase-volume residual is supplemental information only, not a required closure or acceptance criterion.

**Next action:** Construct legal pairwise momentum/relative-velocity cases with unclipped and constrained states.

**Evidence:** `tests/test_twofluid.py`; `outputs/twofluid_variant_checks.json`; `docs/twofluid_baseline_audit.md`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `outputs/verification/annular-policy-01/reassessment.json`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-020: TwoFluid exchanges

**Scope:** INTLENGTH=CONSTANT; INTAREA=DISPGAS2DISPLIQ; BUBBLEDRAG/DROPDRAG legal alternatives; INTNU=CONSTANT/RANZMARSHALL/RELAXATION; INTTRANSH=BULK/SATURATED.

**Missing or unverified:** Scoped cancellation tests cover six INTNU/INTTRANSH combinations. Drag/flow-regime domains and combinations lack comprehensive branch evidence and numerical references.

**Acceptance evidence required:**

- Verify pairwise mass cancellation and conservative energy/momentum identities, including H*dW and U*dW terms.
- Test interfacial-area transition continuity, selected Reynolds regimes and signs using documented applicability.

**Next action:** Add independent closure values and boundary/regime fixtures with matched MATLAB phase-source outputs.

**Evidence:** `tests/test_twofluid.py`; `docs/twofluid_notes.md`; `docs/FEATURE_MAP.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-021: ThreeField exchange

**Scope:** ENTRAINMENT=NONE/GOVAN/OKAWA2003/OKAWA2004/OKAWA2004MOD/OKAWAGEN; DEPOSITION=NONE/GOVAN/OKAWA; DEPENHANCEMENT=NONE/WINDECKER; THINFILMFRIC/VAPORFRIC choices.

**Missing or unverified:** Tutorials exercise defaults, Govan and disabled exchange. Other branches/combinations are source-inspected or scoped unit checks. Okawa vector and pointwise iteration stopping differ upstream.

**Acceptance evidence required:**

- Check mass-source units and sign, evaporation latent-heat balance, wall/perimeter scaling and obstruction coordinates.
- Use the solver's pointwise closure path for equation residuals; do not silently substitute the vector diagnostic path.

**Next action:** Compare pointwise solver closure outputs, nested iteration status and separate vector diagnostics for every legal branch.

**Evidence:** `tests/test_threefield.py`; `outputs/threefield_variant_checks.json`; `docs/threefield_review.md`; `docs/FEATURE_MAP.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-022: ThreeField momentum

**Scope:** MOMENTFILM=ALGEBRAIC/EQUILIBRIUM/EQUILIBRIUMS/FULL; MOMENTDROP=ALGEBRAIC/SLIP/EQUILIBRIUM/EQUILIBRIUMS/FULL; thin-film branch and dryout clipping.

**Missing or unverified:** Selected full/equilibrium tutorials executed, but no alternative-closure MATLAB references. Sequential sources and clipping leave nonzero raw residuals.

**Acceptance evidence required:**

- Check film force in N/m2 and drop force in N/m3 and resulting acceleration in m/s2.
- Retain raw, applicable unclamped and reconstructed update residuals separately; verify inner and outer convergence independently.

**Next action:** Export nested solve traces and compare each momentum branch on wet, thin-film, dryout and constrained-velocity states.

**Evidence:** `tests/test_threefield.py`; `tests/test_threefield_transient_audit.py`; `outputs/threefield_variant_checks.json`; `docs/threefield_review.md`; `docs/threefield_transient.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-023: FourField structure

**Scope:** OAFFILMSPLIT=RATIO/EQUILIBRIUM; BASEEQTHICK=RISO/COEFS/YPLUS/MFVAL; WAVEFREQUENCY=EQUILIBRIUM/RELAXATION; EQSTROUHAL=RISO/SAWAI/MFVAL/CUSTOM/CSTFREQ.

**Missing or unverified:** Actual base/frequency pass TUTORIAL1 additional comparisons; alternative cases run natively but branch-wide MATLAB equivalence is not established.

**Acceptance evidence required:**

- Check W=base.W+wave.W, source residence-inventory weighted film U, dimensions of thickness/width/spacing and frequency in Hz.
- Compare actual base fields and frequency for every selected closure; preserve the source dry-film NaN fallback.

**Next action:** Create branch-isolating base thickness, wave geometry/frequency and zero-film references.

**Evidence:** `tests/test_fourfield.py`; `outputs/fourfield_tutorials/verification.json`; `docs/fourfield_notes.md`; `docs/annular_reference_audit.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-024: FourField momentum

**Scope:** MOMENTBASE=ALGEBRAIC/EQUILIBRIUM/EQUILIBRIUMS/FULL/FULLNOP; MOMENTWAVE=ALGEBRAIC/EQUILIBRIUM/FULL; WAVEBASEINT=VAPORSHEAR/VAPORSHEARDROPMASS.

**Missing or unverified:** Selected tutorials and cancellation tests exist; all branch combinations and source-order momentum residuals lack independent reference coverage. Exact zero-slip evaluates infinity times zero upstream.

**Acceptance evidence required:**

- Verify internal shear and mass exchange cancellation with N/m2 and kg/(s m2) conventions preserved.
- Document zero-slip NaN behavior separately from any future analytic-limit correction; never silently replace the source operation order.

**Next action:** Add source-equivalent boundary fixtures and reference traces for base/wave/drop source-order and constrained momentum branches.

**Evidence:** `tests/test_fourfield.py`; `outputs/fourfield_tutorials/verification.json`; `docs/fourfield_notes.md`; `docs/fourfield_review.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-025: Mixture physical checks

**Scope:** Original TUTORIAL1 at 6 MPa; independent analytic adiabatic subcooled case; no claim of all closures or all fluids.

**Missing or unverified:** Selected steady checks pass; this is neither experimental validation nor a universal balance guarantee.

**Acceptance evidence required:**

- Verify imposed discrete power 87500 W and steady enthalpy target 1139400+87500/0.07=2389400 J/kg for this case.
- Check local and global mass/enthalpy/momentum residuals with correct units and boundary contributions, not just solver increments.

**Next action:** Retain independent balance gates while adding closure- and condition-specific cases.

**Evidence:** `tests/test_solver.py`; `tests/test_transient.py`; `outputs/verification/native-sensitivity-01/verification.json`; `docs/VERIFICATION.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-026: TwoFluid physical checks

**Scope:** Original TUTORIAL1 steady archive and native solution; physical domain is the full channel.

**Missing or unverified:** Archived occupied-area discrepancy is 41.056107%, also reproduced natively. The archive also has nonzero mass/enthalpy-flux defects. This specific steady defect is shared with upstream. The one-way pressure treatment is an intentional formulation choice; this physical-identity failure alone does not prove a translation error or accidental source-code defect.

**Acceptance evidence required:**

- Maintain the compatibility result and its failed physical flag.
- Demonstrate physically consistent occupied area, inventories and balances for accepted engineering-use configurations; document exclusions when a shared source defect remains.

**Next action:** Trace absolute area from W/(rho U), pressure coupling and source discretization; propose any governing-model correction as a separately reviewed variant.

**Evidence:** `docs/ALL_BASELINES_VERIFICATION.md`; `docs/twofluid_baseline_audit.md`; `outputs/verification/twofluid-area-01`; `tests/test_twofluid.py`

**Dependencies:** CORE-029, CORE-037

### CORE-027: ThreeField physical checks

**Scope:** Original steady sample, fully annular nodes only; separately inspect wet, clipped and dry-film cells.

**Missing or unverified:** Archived fully annular phase-volume discrepancy is 7.485259%, also reproduced natively, and is now supplemental information. The retained physical failure is the separately documented POSFILM-clipped raw mass residual; bookkeeping partitions do not prove equation balance. Current policy, explicitly directed by R. W. Morse on 2026-11-14: ThreeField/FourField phase-volume closure is supplemental only, with no pass/fail role; original receipts remain immutable. Mixture/TwoFluid policy and other source-equation/numerical criteria are unchanged.

**Acceptance evidence required:**

- Report phase-volume residuals without an annular acceptance threshold; retain raw clipped/unclipped source mass residuals as separate evidence.
- Do not alter velocity/area algebra or select an additional closure to enforce volume equality; preserve the requested governing equations and model settings.

**Next action:** Trace clipped-cell mass residuals against the source update and independent reference arrays; keep phase-volume diagnostics informational and preserve source equations.

**Evidence:** `docs/ALL_BASELINES_VERIFICATION.md`; `docs/annular_reference_audit.md`; `docs/threefield_review.md`; `tests/test_threefield.py`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `outputs/verification/annular-policy-01/reassessment.json`

**Dependencies:** CORE-018, CORE-029, CORE-037

### CORE-028: FourField physical checks

**Scope:** Original steady sample, fully annular nodes; base/wave/drop inventories with source film aggregation.

**Missing or unverified:** Archived fully annular phase-volume discrepancy is 11.241052%, reproduced natively, and is now supplemental information. The retained physical failure is the separately documented base/wave raw pseudo-time mass residuals of about 4.31e-4 and 4.24e-4 kg/s near clipping. Current policy, explicitly directed by R. W. Morse on 2026-11-14: ThreeField/FourField phase-volume closure is supplemental only, with no pass/fail role; original receipts remain immutable. Mixture/TwoFluid policy and other source-equation/numerical criteria are unchanged.

**Acceptance evidence required:**

- Report phase-volume residuals as supplemental information, without an annular acceptance threshold or additional model constraint.
- Report both-fields-positive annular source-equation residuals separately from wet-but-compensated and dryout cells; preserve separate numerical and MATLAB compatibility outcomes.

**Next action:** Trace base-compensation mass residuals against the source update and independent arrays; retain reported inventories without imposing another closure model.

**Evidence:** `docs/ALL_BASELINES_VERIFICATION.md`; `docs/annular_reference_audit.md`; `docs/fourfield_notes.md`; `tests/test_fourfield.py`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `outputs/verification/annular-policy-01/reassessment.json`

**Dependencies:** CORE-018, CORE-029, CORE-037

### CORE-029: Convergence contracts

**Scope:** All frameworks; point, pseudo-time and physical-time semantics; FourField frequency criterion and source STATE versus enhanced native .converged.

**Missing or unverified:** Some temporally steady iterates fail point convergence. Source FourField stopping omits SSCONVFW; native STATE preserves it while .converged additionally checks frequency/nested failures. Source initializes DFW but writes DF.

**Acceptance evidence required:**

- Preserve source iteration counts/stopping when testing equivalence; label enhanced acceptance separately.
- Require all applicable nested and point criteria plus independently calculated residuals for a numerically accepted solution.
- Never use unused DFW zeros as frequency evidence or convert failure to pass by loosening controls.

**Next action:** Create acceptance tests for exhaustion, false temporal convergence, inner failure, actual DF and each source stop branch with MATLAB traces.

**Evidence:** `tests/test_solver.py`; `tests/test_fourfield.py`; `docs/fourfield_notes.md`; `docs/threefield_transient.md`; `outputs/twofluid_mesh_checks.json`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-030: Mixture discretization

**Scope:** Existing 50/100/200-cell steady; 0.5/1/2 s pseudo-time; physical dt=0.2/0.1/0.05 s sensitivity.

**Missing or unverified:** Existing studies show sensitivity, not a proven continuum result. Heated-length discretization changes with the mesh; transient conservative-energy defects decrease but remain nonzero.

**Acceptance evidence required:**

- Fix physically identical geometry, heating integrals and schedules across refinements; disclose mesh-dependent transition definitions.
- Use at least three successful refinements where an observed-order/uncertainty claim is intended; report non-asymptotic behavior rather than fitting an unjustified order.
- Make numerical uncertainty small enough to distinguish the intended experimental comparison.

**Next action:** Run converged, consistent-geometry refinement and bound iterative versus spatial/temporal error at measurement coordinates.

**Evidence:** `outputs/verification/native-sensitivity-01/verification.json`; `docs/VERIFICATION.md`

**Dependencies:** CORE-029

### CORE-031: TwoFluid discretization

**Scope:** Existing tightened 50/100/200-cell steady study and original transient; one wall.

**Missing or unverified:** The 50-cell tightened run failed point convergence; 100/200-cell energy defects decrease but two successful grids do not establish an order. Transient time-step sensitivity is missing.

**Acceptance evidence required:**

- Exclude failed iterates from convergence-order estimates while retaining them in evidence.
- Separate conservative product-rule error, iterative residuals, pressure/area coupling and physical-time error.

**Next action:** Diagnose the coarse-grid failure and obtain a successful sequence before estimating discretization uncertainty.

**Evidence:** `outputs/twofluid_mesh_checks.json`; `outputs/twofluid-transient-02/verification.json`; `docs/twofluid_notes.md`

**Dependencies:** CORE-026, CORE-029

### CORE-032: ThreeField discretization

**Scope:** Existing 25-cell dt=0.25/0.125 s tightened attempts versus original 100-cell transient.

**Missing or unverified:** Both tightened runs failed point convergence; at 25 cells no node meets the strict unblended-annular mask. Differences between these failed iterates are not convergence evidence.

**Acceptance evidence required:**

- Retain failure records and do not claim asymptotic behavior from them.
- Ensure an applicable common-annular region exists or report acceptance as not assessed; quantify transition-width changes with mesh.

**Next action:** Isolate the reported node-9 film-velocity failure and choose a physically comparable annular refinement sequence.

**Evidence:** `outputs/threefield_transient_tight_dt025/verification.json`; `outputs/threefield_transient_tight_dt0125/verification.json`; `outputs/threefield_transient_study/failed_time_step_comparison.json`; `docs/threefield_transient.md`

**Dependencies:** CORE-027, CORE-029

### CORE-033: FourField discretization

**Scope:** Physical transient and pseudo-time frequency relaxation, within one-wall fully annular applicability.

**Missing or unverified:** No successful FourField mesh/time-step sensitivity sequence is recorded. Saturated enthalpy, wave bounds and frequency changes require separate checks.

**Acceptance evidence required:**

- Require point/nested convergence and common physical domains before comparing grids/times.
- Report uncertainty in film/base flow, wave velocity/thickness/frequency and event timing, not only final-state mixture quantities.

**Next action:** Run predeclared refinements after diagnosing the applicable balance and nested-convergence failures.

**Evidence:** `outputs/fourfield-transient-audited/verification.json`; `docs/fourfield_notes.md`

**Dependencies:** CORE-028, CORE-029

### CORE-034: Multiwall numerical behavior

**Scope:** Native two-wall HEM mixture exists; general mixture/annular combinations unverified; DELORME, FourField and TwoFluid FULL momentum multiwall explicitly rejected.

**Missing or unverified:** Two-wall HEM total balance does not establish per-wall nonequilibrium, source indexing, or transient equivalence. Several upstream force/index expressions are incompatible or ambiguous for multiple walls.

**Acceptance evidence required:**

- Check node-by-wall versus node-only shapes, wall-wise source sums, heating partition and column-major linear indexing.
- Retain explicit errors for unresolved cases; document any proposed corrected source contract independently from compatibility implementation.

**Next action:** Separate supported combinations from unresolved source expressions, then obtain wall-indexed independent references for valid cases.

**Evidence:** `tests/test_fields.py`; `tests/test_transient.py`; `tests/test_twofluid.py`; `docs/FEATURE_MAP.md`; `docs/fourfield_notes.md`

**Dependencies:** API-005, CORE-035

### CORE-035: Source-defective scientific options

**Scope:** SPHTM=DITTUSBOELTERGEN; annular DROPDRAG=DISTORDED; TwoFluid LOCRELVEL=SIMPLE; NEARWALLRATIO=0/1 singular diagnostics.

**Missing or unverified:** These paths are rejected rather than silently repaired: incompatible matrix multiplication, undefined source objects, an enum lacking a source equation, or singular endpoint diagnostics.

**Acceptance evidence required:**

- Explicitly identify the rejected field/value and source defect.
- Only implement a corrected path after its equations, dimensions, numerical consequences and independent reference expectations are recorded.

**Next action:** Document a source-backed intended contract or retain a named unsupported exception; review any correction as a separate model/API change.

**Evidence:** `tests/test_fields.py`; `tests/test_threefield.py`; `tests/test_twofluid.py`; `docs/FEATURE_MAP.md`; `docs/field_notes.md`

**Dependencies:** No additional matrix-row prerequisite.

### CORE-036: Numerical language semantics

**Scope:** Node/wall indices and slices, column-major copy, cache update order, shared handles, NaN min/max and fallback order, colon endpoints and interpolation tie/extrapolation rules.

**Missing or unverified:** Selected tests and archived cases support specific semantics, but no complete cross-language boundary fixture set exists. Ambiguous interpolation cubic is explicitly unsupported.

**Acceptance evidence required:**

- Assert shapes and mutability/alias relationships as well as numerical values.
- Distinguish elementwise and matrix operations and preserve source NaN policy; flag invalid physical states rather than coercing them to plausible results.

**Next action:** Generate independent MATLAB fixtures for singleton/multiwall arrays, subsets/duplicates, exact ties, NaNs and boundaries without changing expression order.

**Evidence:** `tests/test_solver.py`; `tests/test_fields.py`; `tests/test_mixture_mrm_semantics.py`; `tests/test_twofluid.py`; `tests/test_fourfield.py`; `docs/mixture_translation_audit.md`

**Dependencies:** API-006, API-007

### CORE-037: Operating domain

**Scope:** One-dimensional straight constant-area channels; principally single-component co-current boiling; annular frameworks apply only within their appropriate regime and generally assume saturated liquid fields.

**Missing or unverified:** Parser validity and available CoolProp properties do not establish model applicability. A complete closure-by-closure fluid/pressure/Reynolds/regime domain ledger and boundary acceptance suite is missing.

**Acceptance evidence required:**

- Check fluid, geometry, pressure, mass flux, heating and regime compatibility before a physical-validation claim.
- Reject invalid numeric inputs and distinguish unsupported conditions, indeterminate applicability and failed physical checks; do not present no-annular-domain results as an annular pass.

**Next action:** Attach source/literature domains to each legal option and selected validation case; classify unknown domains explicitly.

**Evidence:** `docs/FEATURE_MAP.md`; `docs/threefield_transient.md`; `docs/fourfield_notes.md`; `tests/test_inputs.py`; `tests/test_threefield.py`

**Dependencies:** No additional matrix-row prerequisite.

### API-001: Input readers

**Scope:** Named Model/Options/Geometry records and steady/transient boundary files; original legal inputs, not execution of arbitrary MATLAB text.

**Missing or unverified:** Original records and selected malformed inputs are tested, but a MATLAB-exported input corpus is absent. Unknown keys and numeric suffixes are stricter errors than upstream warnings/prefix parsing. Bartolomey source-record/default/override generation now has native fixtures and a complete 34-record registry; this does not supply an independent MATLAB-exported input corpus.

**Acceptance evidence required:**

- Export effective input records for every preserved input set and compare values, types, dimensions, selected identifiers and solver-dependent resolution.
- Record each intentional parser-contract difference; do not label stricter native errors as exact MATLAB behavior.
- Reject malformed or unsupported data without silently selecting another model.

**Next action:** Create immutable effective-input fixtures and a documented compatibility-difference list.

**Evidence:** `tests/test_inputs.py`; `outputs/verification/github-windows-ci.json`; `docs/input_properties_notes.md`; `tests/test_bartolomey_adapter.py`; `outputs/validation/bartolomey-pilot-01/case_registry.json`; `docs/BARTOLOMEY_SOURCE_REVIEW.md`; `docs/BARTOLOMEY_PILOT.md`

**Dependencies:** No additional matrix-row prerequisite.

### API-002: Defaults and enums

**Scope:** 102 model fields, 49 option fields, five geometry fields, seven boundary fields; the 41 source enum definitions are inventory, not demonstrated branch coverage.

**Missing or unverified:** Selected default values, complete GUI field enumeration and original input records are checked; no per-field independent MATLAB default/value golden export covers all declarations.

**Acceptance evidence required:**

- Each declared field and enum has a native mapping, applicability rule, test case and explicit unsupported reason where needed.
- Verify raw SOLVER_DEPENDENT tokens separately from their resolved values for all four frameworks.
- Input objects and defaults remain isolated under construction, copying and solver resolution.
- Verify MRMTIMEINT EULER and EXPONENTIAL tokens, defaults and serialization; their numerical integration acceptance belongs to the solver/core rows.

**Next action:** Generate a field-by-field exported-default fixture and join enum choices to closure acceptance rows.

**Evidence:** `docs/upstream_inventory.json`; `tests/test_inputs.py`; `tests/test_gui_schema.py`; `outputs/verification/github-windows-ci.json`

**Dependencies:** No additional matrix-row prerequisite.

### API-003: Input writers and default reporting

**Scope:** Upstream Input.writeInputFile, convert2JSON, defaultValueString/defaultValueUsedReport and field descriptions.

**Missing or unverified:** Native to_dict and GUI configuration export exist, but they are not the upstream generic INP writer or default-usage reporting API.

**Acceptance evidence required:**

- Implement documented native writer/converter/report functions or identify an explicitly approved native replacement for each upstream operation.
- Round-trip scalar, vector, multiwall matrix, enum, boolean, sentinel and multiple-record inputs without dimensional/value loss.
- Retain field descriptions, identifiers and default-versus-user-supplied provenance.

**Next action:** Implement the generic input export/report layer and round-trip acceptance fixtures.

**Evidence:** `docs/METHOD_COVERAGE.json`; `docs/input_properties_notes.md`; `tests/test_gui_schema.py`

**Dependencies:** No additional matrix-row prerequisite.

### API-004: Function-valued inputs

**Scope:** CBTMULT and any original function expressions; preserve the function's evaluated values without treating serialized MATLAB text as trusted instructions.

**Missing or unverified:** Python API callables and constant GUI multipliers work; arbitrary MATLAB expressions are rejected and callable behavior is not fully serializable. There is no cross-runtime function-evaluation reference corpus.

**Acceptance evidence required:**

- List each supported original expression and define its native callable or safe structured-function representation.
- Compare evaluated values at mesh, transition and boundary points against independent source values.
- Store a reproducible function specification and evaluated mesh values; unsupported expressions must fail explicitly.

**Next action:** Inventory actual function expressions in source inputs and database adapters before extending the parser.

**Evidence:** `docs/API.md`; `docs/input_properties_notes.md`; `tests/test_gui_schema.py`

**Dependencies:** No additional matrix-row prerequisite.

### API-005: Geometry and boundary dimensions

**Scope:** ANGLE uses degrees from vertical in Geometry.m despite a radians comment in geom.inp; WPOWER rows are segments and columns are walls; NNODES means cells.

**Missing or unverified:** Column-major wall reshaping and selected boundary/geometry rules are checked, but nonzero-angle and broad multiwall source-export comparisons are absent. Bartolomey tests and 40 pilot runs add straight-tube SI dimension, distributed heating and boundary checks; redundant rounded source values are audited without replacing stored mandatory inputs. General asymmetric/multiwall and nonzero-angle MATLAB comparisons remain open.

**Acceptance evidence required:**

- Check hydraulic diameter, wall fractions, axial length and segment power integration with explicit units.
- Compare asymmetric two-wall inputs and nonzero-angle cases to source values without transposing walls or converting degrees as radians.
- Reject unordered times, incompatible segment/wall shapes and invalid boundary values before solving.

**Next action:** Create asymmetric geometry/power and nonzero-angle reference cases before importing experimental configurations.

**Evidence:** `tests/test_inputs.py`; `tests/test_gui_schema.py`; `docs/input_properties_notes.md`; `docs/API.md`; `tests/test_bartolomey_adapter.py`; `outputs/validation/bartolomey-pilot-01/case_registry.json`; `outputs/validation/bartolomey-pilot-01/report.json`; `docs/BARTOLOMEY_SOURCE_REVIEW.md`; `docs/BARTOLOMEY_PILOT.md`

**Dependencies:** No additional matrix-row prerequisite.

### API-006: Colon and interpolation semantics

**Scope:** Positive-step MATLAB colon; LINEAR, NEAREST, NEXT, PREVIOUS, PCHIP, SPLINE and MAKIMA; singleton, endpoint, midpoint, extrapolation and multidimensional ordinate cases.

**Missing or unverified:** Selected colon/nearest/next semantics are tested. Higher-order method equivalence and public interpolation convenience wrappers are not established. Ambiguous CUBIC is explicitly unsupported.

**Acceptance evidence required:**

- Freeze independent MATLAB vectors for each supported method, node count, tie and extrapolation case with dimensions retained.
- Verify axis-zero interpolation and MATLAB half-way tie behavior without accidental broadcasting.
- Resolve CUBIC against the pinned MATLAB release or retain its explicit unsupported status; do not silently alias it.

**Next action:** Add method-by-method reference fixtures and public-wrapper acceptance cases.

**Evidence:** `tests/test_solver.py`; `docs/API.md`; `docs/METHOD_COVERAGE.json`

**Dependencies:** No additional matrix-row prerequisite.

### API-007: Copy, caches and array indexing

**Scope:** MATLAB one-based/linear indexing versus zero-based NumPy; column-major multiwall copies; state caches and handle references in all four frameworks.

**Missing or unverified:** Four selected trajectories provide indirect coverage; explicit copy/setter/alias contracts and arbitrary subsets are not independently compared across the full API. Method audit retains two setter-contract review entries.

**Acceptance evidence required:**

- For each source copy/update operation, specify which arrays are copied, shared, preserved or recomputed and in what order.
- Use asymmetric multiwall and duplicate/subset fixtures to expose column/row and linear-index errors.
- Compare actual object-graph relationships and before/after cache values for transient and initialization paths.

**Next action:** Close the two setter-contract review entries and add targeted source-export state-transition fixtures.

**Evidence:** `tests/test_fields.py`; `tests/test_diagnostic_api.py`; `tests/test_twofluid.py`; `docs/mixture_translation_audit.md`; `docs/twofluid_notes.md`; `outputs/baseline-parity-02/summary.json`

**Dependencies:** No additional matrix-row prerequisite.

### API-008: Thermophysical properties

**Scope:** BICUBIC&HEOS property calls with HEOS surface tension, SATURATED/PSYSTEM branches, pressure bounds, scalar/array shapes and boundary-pressure diagnostics.

**Missing or unverified:** Native HEOS consistency and selected archived solver states are checked; property-by-property MATLAB equivalence across fluids, pressures, enthalpy bounds and CoolProp versions is unverified. The low-table-bound inversion discrepancy is retained.

**Acceptance evidence required:**

- Compare exported property tables at interior and limiting states for every supported property mode with pinned CoolProp version/backend.
- Keep dimensional identities, pressure range, saturation ordering, clamping and scalar/array return contracts explicit.
- Document the 6 MPa lower-table inversion discrepancy and do not replace source enthalpy clamping with a temperature correction.

**Next action:** Create a property reference grid and boundary-condition pressure mismatch cases before broad experimental runs.

**Evidence:** `tests/test_properties.py`; `docs/input_properties_notes.md`; `outputs/baseline-parity-02/summary.json`

**Dependencies:** No additional matrix-row prerequisite.

### API-009: Property optimization and helper scope

**Scope:** SciPy bounded optimization of the source Kutateladze expression versus MATLAB fminbnd; optional property plot and general wrapper helpers.

**Missing or unverified:** QKMAX exists and has native bounds/scale checks but its optimizer result is not MATLAB-verified. Property plotting, humid-air and general wrapper unit-conversion utilities are not fully ported; these external utilities are outside the 585-method inventory.

**Acceptance evidence required:**

- Compare maximizing pressure and heat-flux value with explicit Pa and W/m^2 tolerances justified against the source optimization settings.
- State whether each general external-wrapper utility is part of the port acceptance scope; runtime independence does not require reimplementing unused MATLAB wrappers.
- Provide direct native replacements for required property plotting/conversion operations and test unit conversions independently.

**Next action:** Export QKMAX reference values and inventory required versus unused external-wrapper operations.

**Evidence:** `tests/test_properties.py`; `docs/input_properties_notes.md`; `docs/METHOD_COVERAGE.md`

**Dependencies:** No additional matrix-row prerequisite.

### API-010: Public diagnostics and subsets

**Scope:** All 585 non-constructor entries in the existing 25-class inventory; inherited repetitions are not unique implemented capabilities.

**Missing or unverified:** 447 name candidates, 54 partial/internal alternatives, 77 infrastructure/presentation gaps, five explicit unsupported entries and two setter reviews are declaration classifications, not acceptance outcomes. Only selected diagnostics have behavior tests or archive comparisons.

**Acceptance evidence required:**

- Attach every inventory entry to a requirement and fixture, including arguments, index selections, dimensions, units and failure semantics.
- Compare stored, derived and computed-on-demand quantities separately; preserve errors for source-defective diagnostics.
- Do not use a same-name method or a declaration count as proof of equation or operating-domain parity.

**Next action:** Join the method inventory to this acceptance ledger and prioritize public diagnostics needed by dataset adapters.

**Evidence:** `docs/METHOD_COVERAGE.json`; `docs/METHOD_COVERAGE.md`; `tests/test_diagnostic_api.py`; `outputs/baseline-parity-02/summary.json`

**Dependencies:** No additional matrix-row prerequisite.

### API-011: Live-field extraction and public interpolation API

**Scope:** Arbitrary public live-field quantities, nested subobjects and physical/pseudo-time state selection.

**Missing or unverified:** SavedResults handles only saved numeric quantities; it cannot reproduce arbitrary source method evaluation. Public interpolation wrappers and generic live-field struct/transient behavior remain missing or internal.

**Acceptance evidence required:**

- Extract selected quantities from live fields with explicit time/node/wall shapes and preserve nested path identity.
- Match source values for methods as well as stored properties without confusing pseudo-time and physical time.
- Unsupported unsaved closures must raise an explicit error rather than inventing or silently omitting a result.

**Next action:** Implement a public quantity-query contract and verify it on saved and unsaved source methods.

**Evidence:** `docs/METHOD_COVERAGE.json`; `docs/API.md`; `docs/PLOTTING.md`; `tests/test_plotting.py`

**Dependencies:** No additional matrix-row prerequisite.

### API-012: Session and runtime behavior

**Scope:** Named sessions, directory creation, logging modes, warnings, no-overwrite behavior, cancellation and restart semantics.

**Missing or unverified:** Native progress, metadata, locks and worker logs exist; MATLAB diary/class/session option parity is not complete. Stronger native convergence/physical rejection signals need an explicit mapping to upstream STATE rather than being called identical.

**Acceptance evidence required:**

- Map every public session/logging option and solver state to the native behavior or documented replacement.
- Verify failed, cancelled and resumed runs cannot masquerade as completed results or overwrite previous evidence.
- Retain distinct numerical, reference and physical statuses in all interfaces.

**Next action:** Write the session/state compatibility table and add remaining restart/logging acceptance cases.

**Evidence:** `tests/test_cli.py`; `tests/test_gui.py`; `tests/test_gui_lock.py`; `docs/GUI_VERIFICATION.md`; `outputs/verification/github-windows-ci.json`

**Dependencies:** No additional matrix-row prerequisite.

### API-013: Portable results and serialization

**Scope:** NPZ/CSV/JSON, coordinates, units, metadata, effective inputs, initialization histories and mixture precursors; MATLAB class-object serialization is a separate unsupported format.

**Missing or unverified:** Core selected archived outputs are compared, but full derived-output completeness, arbitrary callables and MATLAB object reload compatibility are not established. Exact .mat class serialization is not implemented.

**Acceptance evidence required:**

- Every exported quantity has audited units, dimensions, coordinates and source provenance; retain nonfinite values and flag their validity.
- Round-trip all four native schemas with allow_pickle=False and verify values without implicit squeezing or interpolation.
- List every source output unavailable from the portable native format; do not describe NPZ loading as MATLAB object reconstruction.

**Next action:** Add an output-field completeness ledger and full-schema round-trip fixtures for supported transient and multiwall cases.

**Evidence:** `tests/test_solver.py`; `tests/test_plotting.py`; `tests/test_gui.py`; `outputs/baseline-parity-02/summary.json`; `docs/ALL_BASELINES_VERIFICATION.md`

**Dependencies:** No additional matrix-row prerequisite.

### API-014: Saved-array post-processing

**Scope:** Axial profiles, histories, time-elevation maps, GIF animations, units and physical/pseudo-time selections for all four schemas.

**Missing or unverified:** Seventeen plotting checks and rendered examples establish exact selected values/layout semantics, not visual identity with MATLAB or correctness of the underlying physics.

**Acceptance evidence required:**

- Confirm every plotted line/frame/cell corresponds to the selected saved values and actual time/node/wall coordinates.
- Retain units, failed-physical-status warnings and nonfinite gaps; reject incompatible selections.
- Keep playback speed distinct from physical time and retain frame-count/timing evidence.

**Next action:** Retain these tests and add any missing quantity/schema cases exposed by experimental comparison plots.

**Evidence:** `tests/test_plotting.py`; `docs/PLOTTING.md`; `outputs/saved-result-plots-02/provenance.json`; `outputs/saved-result-plots-02/render_verification.json`

**Dependencies:** No additional matrix-row prerequisite.

### API-015: Complete plotting API

**Scope:** Annular masks, obstruction/onset overlays, grouped presets, dual axes, 3D/shading, video export and interactive playback options.

**Missing or unverified:** Unsupported source plotting keywords are rejected; saved-array plots and GUI charts provide only a subset of upstream presentation/workflow behavior.

**Acceptance evidence required:**

- Inventory each public plot keyword and grouped quantity selection with an equivalent native operation or approved format replacement.
- Verify masks and overlays against the numerical onset/obstruction coordinates rather than visual resemblance alone.
- Test exported frame/data values, labels and orientation; do not let presentation defaults alter the numerical data.

**Next action:** Prioritize masks/overlays and quantities needed by validation, then remaining presentation/export options.

**Evidence:** `docs/PLOTTING.md`; `docs/METHOD_COVERAGE.md`; `tests/test_plotting.py`; `tests/gui_frontend_logic.test.cjs`

**Dependencies:** No additional matrix-row prerequisite.

### API-016: Tutorial 01: quick start

**Scope:** Original input selection, solve, selected inspection, plotting and save/reload through native formats.

**Missing or unverified:** All four selected steady solves/core comparisons exist, but a complete cell-by-cell native tutorial and every inspection/object-reload operation are not accepted. Known multifield physical failures remain separate.

**Acceptance evidence required:**

- Map each executable tutorial operation to a runnable native command/example.
- Retain all four original input selections and their separate convergence, archived agreement and physical statuses.
- Explain native serialization/plotting replacements without claiming MATLAB class-object parity.

**Next action:** Create a runnable tutorial01 acceptance script with explicit per-operation expected outcomes.

**Evidence:** `outputs/release-02/manifest.json`; `outputs/baseline-parity-02/summary.json`; `docs/ALL_BASELINES_VERIFICATION.md`; `docs/GUI_VERIFICATION.md`

**Dependencies:** CORE-001, CORE-002, CORE-003, CORE-004

### API-017: Tutorials 02-05: model capabilities

**Scope:** Mixture, TwoFluid, ThreeField and FourField tutorial cases, diagnostics, pseudo-time and physical transients; model physics gates belong to CORE rows.

**Missing or unverified:** Selected native tutorial inputs run, but complete cell/operation ledgers and independent comparisons for each tutorial variant/transient are absent. Four TUTORIAL1 agreements do not accept tutorials02-05.

**Acceptance evidence required:**

- Enumerate every tutorial case and public operation, including conditional branches and expected errors.
- Provide native runnable equivalents and link each numerical claim to a CORE acceptance row and independent reference.
- Report unsupported operations and source-defective options rather than silently changing tutorial physics.

**Next action:** Extract the four Live Script workflows into a case/operation manifest and native acceptance examples.

**Evidence:** `docs/FEATURE_MAP.md`; `docs/threefield_review.md`; `docs/fourfield_notes.md`; `docs/twofluid_notes.md`; `outputs/verification/github-windows-ci.json`

**Dependencies:** CORE-007, CORE-008, CORE-009, CORE-010

### API-018: Tutorial 06: input workflows

**Scope:** All tutorial06 operations, not just the ability to read an INP file.

**Missing or unverified:** Parsing and GUI export are tested, but generic writer/default-report/INP-to-JSON tutorial operation parity remains incomplete.

**Acceptance evidence required:**

- Match effective values and wall dimensions between original INP and equivalent JSON cases.
- Execute every tutorial inspection/conversion operation and verify round-trip output.
- Make default usage and unsupported expression differences visible.

**Next action:** Implement API-003 and add the native tutorial06 end-to-end acceptance script.

**Evidence:** `tests/test_inputs.py`; `tests/test_gui_schema.py`; `docs/input_properties_notes.md`; `docs/METHOD_COVERAGE.json`

**Dependencies:** API-001, API-002, API-003

### API-019: Tutorials 07-08: convergence and sensitivity

**Scope:** Point, pseudo-time and physical-time distinctions; mesh/time-step comparisons; thresholds and failure reporting without asserting unsupported convergence order.

**Missing or unverified:** Existing sensitivity studies and diagnostics are narrower than complete tutorial operations or all-framework asymptotic convergence evidence; some tightened cases fail.

**Acceptance evidence required:**

- Provide reproducible studies that preserve all input differences and distinguish iterative, temporal and spatial error.
- Link every reported convergence claim to an executed sequence with raw values, units and failures retained.
- Verify tutorial diagnostic extraction against source arrays; do not interpret smooth plots as validation.

**Next action:** Build tutorial07/08 scripts around the existing sensitivity tools and close missing diagnostic APIs.

**Evidence:** `outputs/verification/native-sensitivity-01/verification.json`; `docs/VERIFICATION.md`; `docs/PARITY_STATUS.md`; `tests/test_solver.py`

**Dependencies:** CORE-029, CORE-030, CORE-031, CORE-032, CORE-033

### API-020: Tutorial 09: advanced visualization

**Scope:** Animation, point histories, time-elevation surfaces, extracted tables/CSV and save/reload operations.

**Missing or unverified:** History, maps, GIF and portable reload exist, but a complete tutorial09 operation manifest and full surface/video/grouped plotting behavior are missing.

**Acceptance evidence required:**

- Execute a native equivalent for each tutorial operation on the same saved transient data.
- Compare extracted numerical tables, selection axes and frame values independently of chart styling.
- Identify approved native output-format substitutions explicitly and keep unsupported options visible.

**Next action:** Create the tutorial09 workflow ledger and implement remaining scientific display operations before cosmetic parity.

**Evidence:** `docs/PLOTTING.md`; `tests/test_plotting.py`; `outputs/saved-result-plots-02/render_verification.json`

**Dependencies:** API-011, API-014, API-015

### API-021: MATLAB reference export

**Scope:** Fresh and approved-object source modes for all four frameworks, arbitrary selected model/boundary cases, initialization and precursor arrays.

**Missing or unverified:** Exporter source was reviewed but never executed in MATLAB. Synthetic comparator fixtures do not verify successful class construction, CoolProp compatibility, export dimensions or version capture.

**Acceptance evidence required:**

- Run a fresh reference export in an available compatible MATLAB installation and retain its execution log, exact source/submodule/CoolProp/MATLAB versions and input hashes.
- Require complete primary arrays, audited units/shapes, coordinates and convergence histories; optional method errors remain explicit.
- Do not overwrite original archives; compare an independently produced export without interpolation or tolerance changes.

**Next action:** Obtain known-runtime exports for the first transient/alternative-closure acceptance cases; MATLAB remains unnecessary for normal Python execution.

**Evidence:** `docs/REFERENCE_COMPARISON.md`; `tools/export_matlab_reference.m`; `tools/test_reference_comparator.py`

**Dependencies:** API-026

### API-022: Archive recovery

**Scope:** Four original TUTORIAL1 regression archives, named properties/object links/enums, raw shapes and formula-derived baseline quantities.

**Missing or unverified:** Recovery works for the four actual archives; original producing MATLAB/CoolProp/source versions remain unknown. Reconstructed baseline methods are not independent fresh MATLAB executions or a generic decoder for all future cases.

**Acceptance evidence required:**

- Preserve before/after archive hashes, object identity and original dimensions; record every stored versus reconstructed quantity.
- Fail on unsupported models, decoder warnings and missing required data rather than guessing arrays.
- Retain unknown producer metadata and prohibit extending baseline reconstruction formulas to other physics without audit.

**Next action:** Use the existing immutable archives as scoped anchors; add independent known-runtime references rather than claiming recovery supplies all needed cases.

**Evidence:** `tools/REFERENCE_READER.md`; `tools/test_recover_mcos_reference.py`; `tools/test_recovered_twofluid.py`; `tools/test_recover_annular_reference.py`; `outputs/baseline-parity-02/summary.json`

**Dependencies:** API-026

### API-023: Comparison acceptance machinery

**Scope:** Core W/U/H and required FourField base/frequency, histories/precursors, inputs, units, shapes and convergence; supplementary diagnostics separately identified.

**Missing or unverified:** Four original core baselines pass; supplementary diagnostic differences remain. GUI comparisons have a narrower scope than the full archived audit. Original 1e-8/0 criteria must not be mistaken for a universal experimental or all-quantity accuracy tolerance.

**Acceptance evidence required:**

- Preserve original core rtol=1e-8 and atol=0, exact zeros and exact shape/unit checks; no interpolation, broadcasting or missing-field skips.
- Audit new quantity-specific absolute/relative criteria before comparisons, with dimensional justification and provenance; never change criteria merely to obtain a pass.
- Keep synthetic tooling-test passes, actual reference agreement and physical consistency as separate results.

**Next action:** Extend immutable adversarial fixtures and explicit comparison scopes for each new reference case.

**Evidence:** `tools/test_reference_comparator.py`; `tools/test_recovered_framework.py`; `tests/test_gui_reference.py`; `docs/REFERENCE_COMPARISON.md`; `docs/ALL_BASELINES_VERIFICATION.md`; `outputs/baseline-parity-02/summary.json`

**Dependencies:** API-026

### API-024: GUI and command interfaces

**Scope:** Four steady presets, 163 inputs, units/reference/defaults, validated edits, saved results and plots; native solvers also have transient schedules.

**Missing or unverified:** GUI coverage is intentionally steady-only; arbitrary functions and transient scheduling are absent. Four preset comparisons do not establish every edited combination, keyboard/screen-reader accessibility or full solver API parity.

**Acceptance evidence required:**

- Ensure supported inputs retain units, references/defaults and explicit unsupported/inactive explanations.
- Keep errors, cancellation, custom-case identity and numerical/reference/physical statuses accurate across GUI and CLI.
- If transient GUI support becomes a requirement, add schedule editing and physical/pseudo-time safeguards without changing solver equations.

**Next action:** Keep native parity independent of UI completion; extend GUI scheduling only after transient numerical acceptance.

**Evidence:** `docs/GUI.md`; `docs/GUI_STYLE.md`; `docs/GUI_VERIFICATION.md`; `outputs/verification/github-windows-ci.json`; `tests/test_gui.py`; `tests/gui_frontend_logic.test.cjs`

**Dependencies:** No additional matrix-row prerequisite.

### API-025: Reproducible installation and release

**Scope:** Pinned Python 3.12 dependencies, source/wheel installation, CLI/GUI launches, bundled inputs/reference/assets/licenses and runtime import boundaries.

**Missing or unverified:** The clean Windows workflow passed213 Python tests and5 JavaScript tests with2 recorded FourField warnings. This confirms the tested installation/runtime scope, not all operating conditions or scientific parity. Test/evidence versions must remain traceable after changes.

**Acceptance evidence required:**

- Reproduce installation and actual solver execution from a clean recursive checkout and installed wheel without MATLAB, Engine or Octave.
- Verify bundled arrays/assets/licenses, dependency consistency and source/reference fingerprints.
- Require all applicable tests and disclosed warnings/physical failures in release evidence; do not sum overlapping historical test suites.

**Next action:** Keep CI and installed-wheel smoke checks as release gates for every future numerical change.

**Evidence:** `outputs/verification/github-windows-ci.json`; `outputs/verification/gui-0.2.1-package.json`; `outputs/verification/gui-0.2.1-wheel-smoke.log`; `docs/PUBLICATION.md`

**Dependencies:** No additional matrix-row prerequisite.

### API-026: Evidence provenance and status consistency

**Scope:** Source/submodule/data commits, artifact hashes, units, input identity, independent test scopes and stale documentation wording.

**Missing or unverified:** Historical checkpoints and independent evidence scopes need continuing reconciliation as the acceptance ledger expands; method counts and test counts are not a complete acceptance denominator. Source/archive producer metadata remain unknown where explicitly recorded.

**Acceptance evidence required:**

- Each requirement row has stable ID, pinned source anchor, executable case, units/domain, independent evidence and separate implementation/equivalence/physical/experimental status.
- Mark earlier checkpoints as historical and distinguish unexecuted fresh exports from completed archive recovery/comparisons.
- Verify source/evidence paths and hashes; missing evidence cannot become a pass because an implementation is present.

**Next action:** Maintain the machine-readable ledger, pinned provenance and accurate historical/current status wording together as each new case is accepted.

**Evidence:** `provenance`; `docs/FEATURE_MAP.md`; `docs/PARITY_STATUS.md`; `docs/METHOD_COVERAGE.json`; `docs/REFERENCE_COMPARISON.md`; `docs/PROGRESS.md`

**Dependencies:** No additional matrix-row prerequisite.

### EXP-001: Publication/version provenance

**Scope:** 2025 ICMF abstracts, 2025 NURETH paper, 2026 pinned solver and database revisions

**Missing or unverified:** The 33 source-default and 36 diagnostic cases were frozen before predictions in commit 03fb5eaebc7b020f441c1b47544cd836978f8469, with paper/MLX/XML hashes and exact effective inputs. Historical March-2025 NURETH21.m is recovered, but it differs from the September-2026 companion and contains literal CONST and scalar RELAXTCOND incompatibilities. The selected historical solver revision is a date-based audit target, not established publication-producing provenance. Current-companion reconstruction is distinct from exact historical replay. R. W. Morse subsequently confirms 0.2 s as the intended Sawai setting; the actual historical plot-producing runtime is still unverified.

**Acceptance evidence required:**

- Every reproduction case has immutable paper/figure identifiers, exact source revisions and effective inputs.
- Keep 5 m ICMF and 5.5 m NURETH cases distinct; preserve explicit perimeter/area and inlet enthalpy rather than replacing them with rounded paper values.
- Document which current-code changes differ from the publication-time implementation.

**Next action:** Obtain the actual plot-producing generated inputs, solver/property versions and numerical reference arrays; reconcile the recovered script inconsistencies without inferring a constant-relaxation repair.

**Evidence:** `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `local-paper:Chan2025.pdf#page=1`; `local-paper:LeCorre2025ICMF.pdf#page=2`; `local-paper:LeCorre2025OpenSTREAM.pdf#page=8`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `references/paper/lecorre2025/source_history.json`; `references/paper/lecorre2025/NURETH21_2025_original.m`

**Dependencies:** No additional matrix-row prerequisite.

### EXP-002: NURETH demonstration

**Scope:** Water; 6 MPa; 0.07 kg/s; 87.5 kW; 3.5 m heated plus 2 m adiabatic; explicit companion closure selections

**Missing or unverified:** All four frozen companion demonstration frameworks executed and converged at 100 cells. Sampled readings from 21 of 22 Figure 3/4 series intersect graphical reading envelopes; three of five sampled FourField wave-velocity points do not (RMSE 0.499978 m/s). The 100-cell onset 0.715 m agrees graphically with the marker but differs from the paper-text 0.77 m. Across all 16 demonstration variants 15 converge natively and 12 were physically rejected under the original policy; annular area-only rejections are now superseded, while TwoFluid area policy is unchanged; the 400-cell TwoFluid run fails temporal liquid enthalpy (2.07523442 J/kg versus SSCONVH=1 at 29 s). Original numerical arrays and exact publication runtime remain absent; graphical agreement is not MATLAB equivalence. Current policy, explicitly directed by R. W. Morse on 2026-11-14: ThreeField/FourField phase-volume closure is supplemental only, with no pass/fail role; original receipts remain immutable. Mixture/TwoFluid policy and other source-equation/numerical criteria are unchanged.

**Acceptance evidence required:**

- Archive exact generated inputs, closure selections and any sequential inheritance of options.
- Obtain independent numerical reference arrays for all plotted quantities and compare on matched coordinates with predeclared justified criteria.
- Check convergence and applicable balances; retain source-shared physical failures separately from equivalence results.

**Next action:** Recover independent demonstration arrays and original inputs; investigate the TwoFluid 400-cell temporal limit and its retained physical criteria. Preserve annular area diagnostics as information and all original attempts.

**Evidence:** `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `local-paper:LeCorre2025OpenSTREAM.pdf#page=8`; `local-paper:LeCorre2025OpenSTREAM.pdf#page=9`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `references/paper/lecorre2025/source_history.json`; `references/paper/lecorre2025/NURETH21_2025_original.m`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `references/paper/lecorre2025/physical_scope_review.json`; `outputs/validation/lecorre-2025-01/physical_scope_audit.json`; `references/paper/lecorre2025/metadata.json`; `references/paper/lecorre2025/digitized_curves.csv`; `tests/test_lecorre_database.py`; `tests/test_lecorre_runner.py`; `tests/test_lecorre_comparison.py`; `tests/test_lecorre_output_audit.py`; `tests/test_lecorre_common_domain.py`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `outputs/verification/annular-policy-01/reassessment.json`

**Dependencies:** EXP-001, EXP-013, API-023

### EXP-003: ICMF annular transient

**Scope:** 5 m channel; 1 Hz power between 0 and 87.5 kW; three/four-field drop no-slip selection stated in Chan paper

**Missing or unverified:** Exact waveform phase/sampling, original numerical settings and plotted numerical arrays are not supplied by the two-page abstract.

**Acceptance evidence required:**

- Recover the original boundary schedule and numerical/model settings rather than inventing a sine-wave phase or substituting a current tutorial.
- Separate physical time from initialization pseudo-time and retain moving annular-domain eligibility.
- Compare transient wave flow, velocity and frequency against independent arrays; quantify timestep/mesh sensitivity.

**Next action:** Locate the publication calculation files and reference data; retain the case as unverified until its inputs and outputs are traceable.

**Evidence:** `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `local-paper:Chan2025.pdf#page=2`

**Dependencies:** EXP-001, API-021, CORE-009, CORE-010

### EXP-004: TRACE benchmark

**Scope:** NURETH Figure 5: 0.6 MJ/kg inlet enthalpy, 150 kW, prescribed subcooled-boiling settings and mixture slip ratio 2

**Missing or unverified:** Figure 5 remains not reproduced: both companion review and source audit lack the TRACE deck, version, closure selections and output arrays. The paper's rounded HIN=0.6 MJ/kg and POWER=150 kW do not establish an exact paired input configuration. No substitute TRACE result or invented reference was created.

**Acceptance evidence required:**

- Identify TRACE version, complete input deck, numerical settings, selected closures and output units.
- Compare matched phase quantities and domains without treating another code as experimental truth.
- Record whether data were rerun, recovered or digitized; plot digitization cannot establish full-precision equivalence.

**Next action:** Recover the TRACE reference case and arrays if available; keep the benchmark outside experimental-validation counts.

**Evidence:** `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `local-paper:LeCorre2025OpenSTREAM.pdf#page=10`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `references/paper/lecorre2025/source_history.json`; `references/paper/lecorre2025/NURETH21_2025_original.m`

**Dependencies:** EXP-001, API-023, CORE-026

### EXP-005: Native database adapter

**Scope:** All six inspected experimental families; inherited Dataset behavior, explicit overrides and transient schedule semantics

**Missing or unverified:** Native steady adapters now cover Bartolomey (34 records), Wurtz1978 (50) and Sawai1989 (8), with raw repeated/missing fields, one-based identities, source hashes and generated-input precision retained. The paper campaign executes the exact 21 TS 20 Wurtz records and Sawai rows 1,2,5,6 under both named relaxation settings. The remaining three dataset families, inherited general Dataset API and transient partial-record inheritance remain incomplete. Source inspection/native fixtures are not an executed MATLAB generated-input comparison.

**Acceptance evidence required:**

- Retain raw XML values, missing entries, repeated fields, record identifiers, source hashes and citations.
- Match geometry, pressure, inlet enthalpy, mass flow, power, axial heating and default/override precedence.
- Verify mass flux times area equals mass flow and integrated prescribed heating equals power within documented input precision.
- For transient partial records, match initial-state inheritance rather than silently inheriting a previous transient record.

**Next action:** Extend the checked adapter contract to Moeck, Bennett and Groeneveld plus transient inheritance; obtain independent MATLAB effective-input exports before claiming cross-runtime generation equivalence.

**Evidence:** `docs/PARITY_COMPLETION.md`; `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `tests/test_bartolomey_adapter.py`; `outputs/validation/bartolomey-pilot-01/case_registry.json`; `docs/BARTOLOMEY_SOURCE_REVIEW.md`; `docs/BARTOLOMEY_PILOT.md`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `tests/test_lecorre_database.py`; `tests/test_lecorre_runner.py`; `tests/test_lecorre_comparison.py`; `tests/test_lecorre_output_audit.py`; `tests/test_lecorre_common_domain.py`

**Dependencies:** API-001, API-005, EXP-006, EXP-018

### EXP-006: Units and observable definitions

**Scope:** Film/base/wave quantities, void fraction, quality, heat transfer and dryout measurements

**Missing or unverified:** Bartolomey definitions remain preserved. Wurtz outlet base thickness [m], wave velocity [m/s] and stored wave number density [m^-1] now compare directly; the Figure 6 measured-film-flow correlation remains distinct from native base.THICK. Sawai raw periods [ms] convert once to seconds, with strict within-channel/unblended-annular interpolation. All selected raw targets are accounted: Wurtz 52 present and 11 missing; Sawai 32 raw targets per relaxation variant with 24 within-channel and eight out-of-domain. Unknown measurement/digitization uncertainty and thermal/dryout definitions remain unresolved.

**Acceptance evidence required:**

- Carry SI dimensions while preserving raw units; explicitly distinguish wave number density (m^-1), frequency (Hz), period (s), and velocity (m/s).
- Use period=1/f and frequency=U_wave*N only with verified source definitions; track derived quantities and correlated uncertainties.
- Record axial origin and use within-domain interpolation with stated numerical error; no silent clamping or extrapolation.
- Missing measurements remain missing and relative errors are not computed with physically meaningless near-zero denominators.

**Next action:** Reconcile Sawai source coordinates and quantify measurement/digitization uncertainty; extend observable definitions to the remaining thermal/dryout families without extrapolating missing data.

**Evidence:** `docs/PARITY_COMPLETION.md`; `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `tests/test_bartolomey_adapter.py`; `tests/test_experimental_comparison.py`; `outputs/validation/bartolomey-pilot-01/report.json`; `outputs/validation/bartolomey-pilot-01/summary/summary.json`; `docs/BARTOLOMEY_SOURCE_REVIEW.md`; `docs/BARTOLOMEY_PILOT.md`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `tests/test_lecorre_database.py`; `tests/test_lecorre_runner.py`; `tests/test_lecorre_comparison.py`; `tests/test_lecorre_output_audit.py`; `tests/test_lecorre_common_domain.py`; `references/paper/lecorre2025/figures6_7/metadata.json`

**Dependencies:** No additional matrix-row prerequisite.

### EXP-007: Uncertainty and acceptance

**Scope:** Measurement, digitization/transcription, input and numerical uncertainty for each compared quantity

**Missing or unverified:** NUREG/IA-0025 section 3.1, printed p.9 reports an absolute void-fraction error below 0.04 for its tests, without a stated confidence level or distribution; example input-error bounds apply to its 1982 reference. The pilot freezes descriptive-only comparisons and numerical sensitivity screens before predictions. Digitization/coordinate uncertainty, group-specific input propagation, correlations and a combined uncertainty budget remain unresolved. The 0.04 bound is not a total experimental acceptance tolerance; three mesh screens failed and no asymptotic numerical uncertainty was estimated. The Le Corre campaign adds descriptive measurement errors, pixel-bounded paper comparisons and 31/36 available convergence-qualified numerical sensitivity pairs. Pixel reading envelopes are not confidence intervals or experimental acceptance bands. No experimental threshold was fitted or adopted from plot guides, and no asymptotic numerical uncertainty is established. Source AFFNC scaling makes physical transition length proportional to dz^2/w, so refinement also changes blending and eligible domains. A labeled posthoc common-coordinate diagnostic covers 9/12 fully natively converged four-configuration sentinels; original pairwise metrics are retained and no convergence order or pure discretization uncertainty is claimed.

**Acceptance evidence required:**

- Recover original experimental uncertainty and distinguish it from digitization/transcription and numerical uncertainty.
- Document uncertainty propagation and correlations; label unavailable uncertainty as unknown.
- Allow descriptive comparisons with unknown uncertainty but prohibit an uncertainty-based pass claim.
- Predeclare criteria before fitting; do not adopt plotting guides or baseline 1e-8 tolerances as experimental accuracy thresholds.

**Next action:** Recover original dataset uncertainty and source digitization records, propagate input/property and coordinate uncertainty, and resolve failed numerical/physical gates before declaring uncertainty-qualified validation.

**Evidence:** `docs/PARITY_COMPLETION.md`; `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `examples/bartolomey_pilot.json`; `tests/test_bartolomey_pilot_policy.py`; `docs/BARTOLOMEY_SOURCE_REVIEW.md`; `outputs/validation/bartolomey-pilot-01/summary/summary.json`; `docs/BARTOLOMEY_PILOT.md`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `references/paper/lecorre2025/metadata.json`; `references/paper/lecorre2025/figures6_7/metadata.json`

**Dependencies:** No additional matrix-row prerequisite.

### EXP-008: Evaluation report and case accounting

**Scope:** All attempted cases, including nonconvergence, physical inconsistency and excluded measurements

**Missing or unverified:** The existing Bartolomey 40-run accounting and its 29/32 sensitivity-screen result remain unchanged. The new frozen Le Corre campaign accounts for all 69 attempts: 69 executed, 63 natively converged, and 65 physically rejected under the original policy. The other runs remain not fully assessed, not full physical passes. The independent saved-array/XML/CSV audit passed 4708/4708 arithmetic/accounting checks. All failed convergence gates, unit conversions, missing/out-of-domain targets, graphical exclusions and source versions remain visible. Arithmetic-audit success does not establish experimental/MATLAB acceptance. The subsequent policy supersedes annular area-only rejection, while numerical failures, Bartolomey evidence and independent source-equation failures remain intact. Current policy, explicitly directed by R. W. Morse on 2026-11-14: ThreeField/FourField phase-volume closure is supplemental only, with no pass/fail role; original receipts remain immutable. Mixture/TwoFluid policy and other source-equation/numerical criteria are unchanged.

**Acceptance evidence required:**

- Publish paired measured/calculated tables with dimensional signed errors, bias, MAE and RMSE for defined populations.
- Report every attempted case and exclusion reason; do not hide nonconverged or physically inconsistent cases in aggregate scores.
- Archive inputs, code/property/data versions, settings, sensitivity and comparison scripts.
- Limit conclusions to measured quantities and tested fluid/geometry/regime/model configurations.

**Next action:** Retain complete reporting while resolving the explicitly diagnosed native/physical failures; improve uncertainty and independent-reference evidence without filtering failed cases or counting repeated predictions as independent measurements.

**Evidence:** `docs/PARITY_COMPLETION.md`; `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `outputs/validation/bartolomey-pilot-01/report.json`; `outputs/validation/bartolomey-pilot-01/summary/summary.json`; `outputs/validation/bartolomey-pilot-01/summary/all_runs.csv`; `tests/test_experimental_comparison.py`; `tests/test_bartolomey_pilot_policy.py`; `docs/BARTOLOMEY_PILOT.md`; `outputs/validation/bartolomey-pilot-01/independent_output_audit.json`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `references/paper/lecorre2025/physical_scope_review.json`; `outputs/validation/lecorre-2025-01/physical_scope_audit.json`; `tests/test_lecorre_database.py`; `tests/test_lecorre_runner.py`; `tests/test_lecorre_comparison.py`; `tests/test_lecorre_output_audit.py`; `tests/test_lecorre_common_domain.py`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `outputs/verification/annular-policy-01/reassessment.json`

**Dependencies:** EXP-005, EXP-006, EXP-007, EXP-014

### EXP-009: Bartolomey pilot

**Scope:** Frozen XML entries 1,22,29,31: four subcooled-boiling groups, Quality and Elevation observations; HEM and source TUTORIAL2D Saha-Zuber/Bestion configurations; 100/200/400 cells with tighter-iteration and pseudo-time-step checks at 200 cells.

**Missing or unverified:** Pilot infrastructure and descriptive comparisons executed: 40/40 runs converged and passed the predeclared steady mass/enthalpy, source discrete momentum, bounds, phase-area and boundary/heating gates. All 59 source measurements were compared under each model. Native numerical acceptance remains incomplete: entry 22 HEM changes by 0.0034520131 (100-to-200 cells) and 0.0043236369 (200-to-400); entry 29 Saha-Zuber/Bestion changes by 0.0050731955 (200-to-400), exceeding the unchanged 0.002 void-fraction mesh screen. All 16 tighter-iteration/pseudo-step screens passed. Experimental results are descriptive only; complete uncertainty, historical calibration independence, asymptotic convergence and independent MATLAB references are unestablished. This pilot is not a reproduction of the supplied 2025 papers. Saved-array diagnosis attributes row22 HEM failures to quality-zero interpolation brackets and row29 Saha-Zuber/Bestion failure mainly to mesh-dependent heated extent/power normalization; original failed criteria remain unchanged.

**Acceptance evidence required:**

- Select traceable representative records with matched geometry, heating, inlet state and measured void definition.
- Freeze the selected mixture thermal/void closures before evaluation.
- Demonstrate converged iterative/mesh settings and applicable balances; publish all paired measurements and errors.
- State whether uncertainty permits acceptance or only descriptive comparison.

**Next action:** Diagnose the three failed mesh screens, particularly saturation/heating-transition resolution, using separately identified follow-on cases. Retain this frozen campaign and thresholds. Establish numerical uncertainty and the remaining experimental/input uncertainty before advancing validation claims.

**Evidence:** `docs/PARITY_COMPLETION.md`; `examples/bartolomey_pilot.json`; `outputs/validation/bartolomey-pilot-01/case_registry.json`; `outputs/validation/bartolomey-pilot-01/report.json`; `outputs/validation/bartolomey-pilot-01/summary/summary.json`; `tests/test_bartolomey_adapter.py`; `tests/test_experimental_comparison.py`; `tests/test_bartolomey_pilot_policy.py`; `docs/BARTOLOMEY_SOURCE_REVIEW.md`; `docs/BARTOLOMEY_PILOT.md`; `outputs/validation/bartolomey-pilot-01/independent_output_audit.json`; `outputs/validation/bartolomey-pilot-01/mesh_diagnosis.json`

**Dependencies:** EXP-005, EXP-006, EXP-007, CORE-025, CORE-030

### EXP-010: Wurtz publication reproduction

**Scope:** Pinned companion TS 20 cases: base-film thickness, wave velocity and wave number density

**Missing or unverified:** All 21 source-selected TS 20 cases executed; all 52 present measured targets were paired and 11 missing targets retained. Source-default RMSE: base thickness 3.75347e-5 m, wave velocity 0.750053 m/s, number density 2.35742 m^-1. All 39 identifiable published solver dots and 15 distinct measured-film-flow correlation stars intersect their graphical envelopes. Across 33 base/sensitivity variants 33 converge natively and 33 recorded area-based failures under the original policy; these are now supplemental residuals, not acceptance failures. CONST-to-CONSTANT is an explicit runner-level spelling migration, never a global alias. This is calibration-associated descriptive reproduction; uncertainty, adequate adiabatic-development qualification and independent MATLAB execution remain unestablished. Source AFFNC scaling makes physical transition length proportional to dz^2/w, so refinement also changes blending and eligible domains. A labeled posthoc common-coordinate diagnostic covers 9/12 fully natively converged four-configuration sentinels; original pairwise metrics are retained and no convergence order or pure discretization uncertainty is claimed. Current policy, explicitly directed by R. W. Morse on 2026-11-14: ThreeField/FourField phase-volume closure is supplemental only, with no pass/fail role; original receipts remain immutable. Mixture/TwoFluid policy and other source-equation/numerical criteria are unchanged.

**Acceptance evidence required:**

- Pin exact TS 20 case IDs and the selected closure/OKAWACOEFS configuration.
- Compare mm only as a display conversion from stored metres; match m/s velocity and m^-1 number density separately.
- Establish adequate adiabatic development and numerical/physical eligibility at the observation location.
- Label this as publication/calibration-associated reproduction; do not infer coverage of all 3-9 MPa or annular-geometry measurements from the selected 7 MPa plot groups.

**Next action:** Clarify the preserved source AFFNC transition scaling and establish numerical uncertainty on matched domains, physical eligibility, adequate development and experimental uncertainty; compare independent MATLAB arrays and holdout groups separately from this calibrated 7 MPa pipe subset.

**Evidence:** `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `local-paper:LeCorre2025OpenSTREAM.pdf#page=11`; `docs/PARITY_COMPLETION.md`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `references/paper/lecorre2025/physical_scope_review.json`; `outputs/validation/lecorre-2025-01/physical_scope_audit.json`; `tests/test_lecorre_database.py`; `tests/test_lecorre_runner.py`; `tests/test_lecorre_comparison.py`; `tests/test_lecorre_output_audit.py`; `tests/test_lecorre_common_domain.py`; `references/paper/lecorre2025/figures6_7/digitized_figure6.csv`; `references/paper/lecorre2025/figures6_7/metadata.json`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `outputs/verification/annular-policy-01/reassessment.json`

**Dependencies:** EXP-005, EXP-006, EXP-007, EXP-013, EXP-014, CORE-028, CORE-033

### EXP-011: Sawai publication reproduction

**Scope:** Companion indices 1,2,5,6; 2.95 MPa; 4 mm tube; heated/adiabatic developing-wave measurements

**Missing or unverified:** All four selected rows execute under the frozen paper 0.2 s and companion 0.1 s settings. Each variant compares 12/16 targets for each quantity, excluding four out-of-domain points per quantity. Velocity/period RMSE are 0.703085 m/s and 0.0252651 s (0.2 s), versus 0.764504 m/s and 0.0101516 s (0.1 s). Graphical envelopes intersect at 2/24 retained paper-curve readings for 0.2 s and 24/24 for 0.1 s; this records a code/text/graphic discrepancy, not an exact-runtime claim. R. W. Morse now confirms 0.2 s as the intended setting; the main Figure 7 uses it and a separate appendix preserves both branches. Source-default entries 1 and 5 fail final wave-flow-per-perimeter point changes despite temporal stopping; only six of 12 measurement pairs per quantity are natively converged. Across 20 base/sensitivity variants 15 converge and 20 recorded area-based physical rejection under the original policy; annular area-only rejection is now superseded. Measurement uncertainty, source coordinates, calibration independence and exact MATLAB reference remain unresolved. Source AFFNC scaling makes physical transition length proportional to dz^2/w, so refinement also changes blending and eligible domains. A labeled posthoc common-coordinate diagnostic covers 9/12 fully natively converged four-configuration sentinels; original pairwise metrics are retained and no convergence order or pure discretization uncertainty is claimed. Current policy, explicitly directed by R. W. Morse on 2026-11-14: ThreeField/FourField phase-volume closure is supplemental only, with no pass/fail role; original receipts remain immutable. Mixture/TwoFluid policy and other source-equation/numerical criteria are unchanged.

**Acceptance evidence required:**

- Resolve and label paper versus companion relaxation settings without tuning them after viewing errors.
- Compare wave velocity and period at correctly transformed measurement locations, retaining equilibrium-period curves as predictions rather than measurements.
- Check downstream-domain eligibility, annular masks, iterative convergence and spatial/temporal sensitivity where applicable.
- Report the source-associated calibration status and all rejected/out-of-domain points.

**Next action:** Retain author-confirmed intended 0.2 s and recover the historical plot-producing inputs to explain the preserved graphical discrepancy. Investigate transition-region point failures and numerical sensitivity, and obtain uncertainty/independent-reference evidence; do not impose annular volume closure.

**Evidence:** `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `local-paper:LeCorre2025OpenSTREAM.pdf#page=11`; `local-paper:LeCorre2025OpenSTREAM.pdf#page=12`; `docs/PARITY_COMPLETION.md`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `references/paper/lecorre2025/physical_scope_review.json`; `outputs/validation/lecorre-2025-01/physical_scope_audit.json`; `tests/test_lecorre_database.py`; `tests/test_lecorre_runner.py`; `tests/test_lecorre_comparison.py`; `tests/test_lecorre_output_audit.py`; `tests/test_lecorre_common_domain.py`; `references/paper/lecorre2025/figures6_7/digitized_figure7.csv`; `references/paper/lecorre2025/figures6_7/metadata.json`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `outputs/verification/annular-policy-01/reassessment.json`

**Dependencies:** EXP-005, EXP-006, EXP-007, EXP-012, EXP-013, EXP-014, CORE-028, CORE-033

### EXP-012: Sawai unit/domain integrity

**Scope:** Eight XML cases; WaveTimePeriod in ms; stored length 1.648 m with final elevations 1.6923-1.7002 m

**Missing or unverified:** All eight source records are loaded with raw period milliseconds and explicit SI conversion. For the four selected rows, the final measurements at 1.6932,1.6926,1.6923,1.6932 m exceed the stored 1.648 m channel; eight quantity/location targets per variant are retained but excluded from within-domain errors. The paper itself displays measured points beyond the model-curve endpoint. Unit handling and strict exclusion are verified, but the original coordinate/digitization discrepancy is unresolved; no channel extension, coordinate shift or extrapolation was applied.

**Acceptance evidence required:**

- Convert milliseconds to seconds exactly once and preserve raw period values and units.
- Reconcile the source measurement/geometry coordinate definitions against the original Sawai article and documented digitization.
- Do not clamp, extrapolate, extend channel length or silently discard points to make comparisons look valid.
- Until resolved, report affected points as ineligible for within-domain error metrics with explicit reasons.

**Next action:** Recover original Sawai measurement coordinate and digitization records; any justified correction needs an explicit source-correction record and a new named campaign.

**Evidence:** `docs/PARITY_COMPLETION.md`; `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `local-paper:LeCorre2025OpenSTREAM.pdf#page=11`; `local-paper:LeCorre2025OpenSTREAM.pdf#page=12`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `tests/test_lecorre_database.py`; `tests/test_lecorre_runner.py`; `tests/test_lecorre_comparison.py`; `tests/test_lecorre_output_audit.py`; `tests/test_lecorre_common_domain.py`; `references/paper/lecorre2025/figures6_7/metadata.json`

**Dependencies:** EXP-001, EXP-006

### EXP-013: Companion configuration compatibility

**Scope:** NURETH21.mlx at pinned database commit versus supplied paper and pinned enum definitions

**Missing or unverified:** Literal CONST is rejected as expected and mapped narrowly to CONSTANT only in the publication-run configuration; historical enums already used CONSTANT. Both RELAXTW variants were frozen before outputs, and the plotted curves favor 0.1 s while coauthor R. W. Morse subsequently confirms 0.2 s as intended. This clarification does not identify the historical plot-producing runtime. Recovered historical demo differs in momentum, slip, friction, OAFBASERATIO and numerical defaults; scalar RELAXTCOND=0.5 is incompatible with five indexed RELAXX knots in the inspected historical source. The OAFBASERATIO string 0.2 does parse numerically. No inferred scalar expansion, global enum alias, governing-equation change or tolerance relaxation was made.

**Acceptance evidence required:**

- Preserve immutable original sources and document each discrepancy with exact anchors.
- Resolve historical target/version intent before claiming publication reproduction.
- Any CONST-to-CONSTANT compatibility mapping is explicit, narrow and tested; arbitrary unknown enums remain rejected.
- No governing equation, empirical coefficient or tolerance is changed merely to improve agreement.

**Next action:** Obtain plot-producing effective inputs and matching solver/property versions to explain historical execution; retain the author-confirmed intended Sawai 0.2 s setting and keep literal-source incompatibilities distinct.

**Evidence:** `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `references/paper/lecorre2025/source_history.json`; `references/paper/lecorre2025/NURETH21_2025_original.m`; `tests/test_lecorre_database.py`; `tests/test_lecorre_runner.py`; `tests/test_lecorre_comparison.py`; `tests/test_lecorre_output_audit.py`; `tests/test_lecorre_common_domain.py`

**Dependencies:** EXP-001

### EXP-014: Independent validation partition

**Scope:** Wurtz entrainment adjustment, Sawai relaxation selection, calibrated NUTHOS15 MRM cases and Bartolomey pilot/correlation-development overlap

**Missing or unverified:** The Bartolomey manifest was frozen in commit 4e76cc1 before prediction inspection, using the first XML entry in each experimental group and two unchanged source configurations; no coefficients were fitted to pilot measurements. Calibrated NUTHOS15 MRM entries 20 and 33 (TestIDs 22 and 35) are explicitly distinguished and not selected. Historical overlap of pilot groups with closure development remains unknown, so the campaign is not claimed as independent holdout validation. Complete calibration/evaluation registers for all datasets remain absent. The Le Corre manifest was likewise committed before prediction inspection. Wurtz uses the source measurement-informed OKAWACOEFS and its separate measured-film-flow correlation; Sawai uses both predefined relaxation choices. Neither was refitted. Both are explicitly calibration-associated reproductions, and 84 present source targets are not multiplied into independent evidence by repeated relaxation/mesh runs.

**Acceptance evidence required:**

- Record which experimental sources and cases influenced every tuned coefficient or selected closure.
- Freeze coefficients before evaluating held-out cases; split by experimental groups/source where appropriate rather than only random points.
- Report calibration-associated reproduction separately from independent validation.
- If no independent cases are available, state that limitation and avoid an independence claim.

**Next action:** Build source/group-level closure-development and calibration provenance, then freeze genuinely independent evaluation groups with justified uncertainty criteria; do not label these paper reproductions holdout validation.

**Evidence:** `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `local-paper:LeCorre2025OpenSTREAM.pdf#page=12`; `examples/bartolomey_pilot.json`; `docs/BARTOLOMEY_SOURCE_REVIEW.md`; `outputs/validation/bartolomey-pilot-01/report.json`; `tests/test_bartolomey_pilot_policy.py`; `docs/BARTOLOMEY_PILOT.md`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `references/paper/lecorre2025/figures6_7/metadata.json`

**Dependencies:** EXP-001, EXP-007

### EXP-015: Adamsson film-flow validation

**Scope:** Selected 7 MPa heated steam-water cases with multiple axial power profiles

**Missing or unverified:** No native measurement comparisons; annular-domain physical failures and input-generation fidelity must be assessed per case.

**Acceptance evidence required:**

- Preserve measured geometry, power profile and measurement location.
- Compare measured film flow directly; mark any inferred droplet flow as derived.
- Resolve applicable convergence/area/balance eligibility and report uncertainty and closure choices.
- Avoid claiming transferability beyond the tested conditions.

**Next action:** Extend the checked adapter/reporting pipeline after the initial mixture and publication-specific wave comparisons.

**Evidence:** `docs/PARITY_COMPLETION.md`

**Dependencies:** EXP-005, EXP-006, EXP-007, EXP-014, CORE-027, CORE-032

### EXP-016: Bennett thermal/dryout validation

**Scope:** Appropriate nonequilibrium mixture/two-fluid thermal cases and eligible annular dryout cases

**Missing or unverified:** No native experiment comparison; measured-onset inputs can confound claimed onset prediction; annular thermal-equilibrium models exclude post-dryout heat transfer.

**Acceptance evidence required:**

- Keep wall-temperature comparison separate from onset prediction and label measured quantities imposed as inputs.
- Treat missing onset location as missing, not zero.
- Use a framework/closure applicable to the thermal regime and qualify its limits.
- Report numerical and experimental uncertainties, failure cases and derived inlet-subcooling transformations.

**Next action:** Port selected database workflows with explicit observable roles and regime eligibility.

**Evidence:** `docs/PARITY_COMPLETION.md`; `docs/LITERATURE_ACCEPTANCE_REVIEW.md`

**Dependencies:** EXP-005, EXP-006, EXP-007, EXP-014, CORE-016, CORE-017, CORE-030

### EXP-017: Groeneveld CHF/dryout validation

**Scope:** Selected compatible records; calibration overlap of CHF correlations assessed

**Missing or unverified:** Outer critical-power/dryout search lacks native validation workflow and independent-data qualification.

**Acceptance evidence required:**

- Verify dimensional input derivations and independently test critical-power bracketing, convergence and nonconvergence handling.
- Separate axial-solver errors from outer-search errors.
- Document whether selected measured records supported the assessed CHF correlation's development.
- Preserve model-domain exclusions, measurement uncertainty and all attempted cases.

**Next action:** Port and verify the outer search only after compatible axial cases and database input generation are accepted.

**Evidence:** `docs/PARITY_COMPLETION.md`

**Dependencies:** EXP-005, EXP-006, EXP-007, EXP-014, CORE-017, CORE-027, CORE-032

### EXP-018: Model applicability versus promised future features

**Scope:** Single-component straight constant-area flow; annular thermal equilibrium through film dryout; pinned source overrides general overview prose

**Missing or unverified:** Documented limits lack a complete case-level domain/eligibility matrix; paper broad stability/consistency statements cannot waive observed numerical or physical failures. The Le Corre campaign now tags exact steady water/geometry/model configurations and distinguishes transition-region initialization, fully annular comparison domains and failed native/physical gates. Pinned-source clipping and one-way pressure/enthalpy coupling remain unchanged; graphical agreement does not expand model validity.

**Acceptance evidence required:**

- Tag each acceptance case with fluid, geometry, thermal regime, closure domain and supported boundary conditions.
- Treat experimental agreement only as evidence within the tested domain.
- Do not count proposed multicomponent, variable-area or thermally nonequilibrium annular extensions as missing translations unless supported by pinned upstream.
- Keep nonlinear convergence and mesh/timestep accuracy tests despite the paper's backward-Euler stability discussion.

**Next action:** Add case-level applicability gates and preserve explicit errors for unsupported paths.

**Evidence:** `docs/LITERATURE_ACCEPTANCE_REVIEW.md`; `docs/FEATURE_MAP.md`; `docs/LECORRE_REPRODUCTION.md`; `examples/lecorre_reproduction.json`; `outputs/validation/lecorre-2025-01/report.json`; `outputs/validation/lecorre-2025-01/analysis/analysis.json`; `outputs/validation/lecorre-2025-01/independent_output_audit.json`; `outputs/validation/lecorre-2025-01/common_domain_diagnostic.json`; `outputs/verification/lecorre-paper-extraction-replay.json`; `docs/LECORRE_PHYSICAL_REVIEW.md`; `references/paper/lecorre2025/physical_scope_review.json`; `outputs/validation/lecorre-2025-01/physical_scope_audit.json`

**Dependencies:** No additional matrix-row prerequisite.
