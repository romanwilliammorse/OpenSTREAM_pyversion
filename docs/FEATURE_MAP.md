# Feature map

Source anchors: OpenSTREAM `a614c7173822a93c1e64ac28d1541cbac028cbd8`, wrapper `a7c40902ff66faf6ed668986398bb1b9faa16e13`. Updated 2026-11-15, native version 0.2.1 with source-hash-tracked FourField precursor-selection correction; governing equations unchanged. `upstream_inventory.json` preserves all 41 enum definitions. **The full port is incomplete. All four TUTORIAL1 baselines pass their original W/U/H comparisons, initialization histories and mixture precursors against recovered MATLAB state. Broader numerical equivalence and experimental validation remain unestablished.** See ALL_BASELINES_VERIFICATION.md.

The requirement-level [acceptance matrix](ACCEPTANCE_MATRIX.md) and
[prioritized acceptance plan](ACCEPTANCE_PLAN.md) now link this feature summary
to separate implementation, native-test, MATLAB, physical-check and experimental
evidence, including the supplied 2025 literature. Declaration annexes enumerate
options and public methods without treating presence as correctness.

Current diagnostic scope: ThreeField/FourField phase-volume closure is
informational only, as directed by the project owner after inspecting the
original MATLAB OpenSTREAM convergence logic. Raw residuals remain available;
they do not change solver acceptance. Mixture/TwoFluid checks and all governing
equations, closure models and numerical convergence tolerances are unchanged.

The [matched diagnostic replay](MATCHED_DIAGNOSTIC_REPLAY.md) corrects a
source-confirmed FourField outer-sweep precursor selection while retaining the
distinct mixture handles used by its field closures. All four archived baselines
were rerun and still pass. The corrected Sawai case still fails point convergence;
TwoFluid's original 400-cell attempt still reaches its iteration cap. A separate
60-state-budget diagnostic converges at 39 s with unchanged tolerances and an
exact original 30-state prefix. These are native/source-audit results, not fresh
MATLAB equivalence. The original 69-case campaign remains a pre-correction record.

The [Sawai follow-up](SAWAI_OSCILLATION_DIAGNOSTIC.md) adds read-only constituent
tracing and exact proposal/source-sum audits for the 0.2 s/100-cell case. Signed
deposition dominates the observed late cycle; no further active translation
error was confirmed. All 215 reference arrays and coarse histories are
reproduced, with the original failed point criterion intact. This adds evidence
without promoting any framework or closure to broader equivalence or validation.

Implemented means native code exists. Tested identifies an actual check/run, not full branch coverage. Unsupported means explicit rejection or an unavailable API. Unverified means no executed reference comparison for that scope. Tests that expose a physical defect do not establish that physical criterion passed.

| Upstream component | Python equivalent | Implementation | Actual test evidence | Equivalence |
|---|---|---|---|---|
| OpenSTREAM-database Dataset/Bartolomey | database.py, experimental_comparison.py, run_bartolomey_pilot.py | Native 34-record XML reader, source input mapping, selection/provenance, coordinate-matched comparisons | 85 adapter/comparator/pilot-policy tests; frozen measured-versus-predicted campaign in BARTOLOMEY_PILOT.md | Source-mapping checks; MATLAB execution not performed; descriptive comparison is not uncertainty-qualified validation |
| OpenSTREAM-database Wurtz/Sawai and NURETH21 companion | database.py, run_lecorre_reproduction.py, compare_lecorre_results.py | Native 50/8-record readers, source input mapping, missing-value and coordinate/period handling; frozen demo and annular cases with explicit companion discrepancies | Adapter and campaign-policy tests; saved runs, independent arithmetic audit and bounded paper comparisons in LECORRE_REPRODUCTION.md | Original publication runtime unresolved; graphical comparisons are not full-precision MATLAB equivalence; physical and convergence failures retained |
| Input/Model/Options/Geometry/BoundaryConditions/InputSet and InputEnums | inputs.py | Declared defaults/enums, INP/JSON, validation, provenance | Input/default/unit/dimension/invalid-value/copy tests; original cases | Unverified |
| FluidProperties and CoolPropWrapper | properties.py | Native BICUBIC&HEOS, HEOS tension, SATURATED/PSYSTEM, original bounds | Saturation/property/shape/immutability tests; HEOS comparison; boundary discrepancy recorded | Unverified |
| Session and solver state | solver.py, output.py, multifield_output.py | Native progress/state, unit-labelled NPZ/CSV/JSON, new-directory enforcement | Serialization/units/no-overwrite tests, copied source-input hashes | MATLAB class-object/diary parity unsupported |
| MATLAB colon/interpolation/reshape/copy/setters | numerics.py, fields.py, annular.py, tf_fields.py | Explicit dimensions, column-major copy, cache order, source sharing, NaN bounds | Endpoint/tie/cache/shared-state tests and independent audits | Unverified |
| Public diagnostic method inventory | tools/audit_method_coverage.py, METHOD_COVERAGE.json | Source/AST declarations, inheritance and explicit alternatives | Source-reviewed, no correctness or completeness score; added missing diagnostic APIs tested | Unverified |
| Mixture fields and solver | fields.py, solver.py | Initialization, axial iteration, pseudo/physical time, closures and both MRM integrators | Original nine W/U/H profiles and ten initialization states pass recovered MATLAB baseline; 81 focused tests pass; native tutorials/sensitivity | TUTORIAL1 core verified; 14 supplementary diagnostics fail strict relative-only policy; other cases unverified |
| TwoFluid fields, REGIMES and solver | tf_fields.py, twofluid.py | Six equations, precursor pressure, source shallow-copy semantics | All 6 original W/U/H and 15 initialization states pass; native tutorials/transient checks; steady area defect confirmed in archive | TUTORIAL1 core verified; other cases unverified |
| AbstractFilm and ThreeField fields/solver | annular.py, threefield.py | Onset, film/drop equations, exchange/drag/friction and time loops | All 6 original W/U/H and 6 initialization states pass; native tutorials/transient checks; supplemental annular volume residual confirmed in archive | TUTORIAL1 core verified; transient mass and other cases unverified; volume diagnostic informational |
| FourField Base/Wave/Film/Drop and solver | ff_fields.py, fourfield.py | Base/wave transport, frequency, aggregate film/drop; one wall | All 9 original profiles plus actual base/frequency and 9 initialization states pass; supplemental annular volume residual confirmed in archive | TUTORIAL1 core and additional base/frequency verified; other cases unverified; volume diagnostic informational |
| SolverPlotter | output.py, multifield_output.py, plotting.py | Axial/frequency plots, saved-array time histories, space–time maps, GIF animation, slicing, physical/pseudo-time | All four schemas rendered; five PNGs/two GIFs inspected, decoded frame counts checked; dedicated tests | Full plot-option parity unsupported |
| Approved MATLAB objects/export | tools/export_matlab_reference.m | Portable export for all frameworks, fresh/approved sources | Actual archives inspected as MatlabOpaque; script source-reviewed, **not MATLAB-executed** | Unverified |
| Native MCOS recovery | tools/recover_mcos_reference.py, recover_twofluid_reference.py, recover_annular_reference.py | Named stored properties, object links, units, inputs, convergence and source-method reconstructions | All 4 actual archives recovered ; 6 + 7 + 11 extraction/audit tests; hashes unchanged | All 4 baseline exports; producing source/CoolProp version unknown |
| Reference comparison | tools/compare_matlab_reference.py; tools/verify_recovered_mixture.py; tools/verify_recovered_framework.py | Strict fresh-export comparator plus scoped archive comparators | 34 synthetic fresh-export tests; all 4 actual comparisons and 43 adversarial/real framework comparator tests | All 4 core baselines pass; full-output/branch equivalence remains unverified |

## Mixture selections

The optional local GUI adds a 163-field editor, four steady presets, isolated
jobs, progress/cancel/history, JSON configuration import/export, offline
interactive plots, and scoped archived-reference checks. GUI status and limits
are documented in GUI.md and GUI_VERIFICATION.md. It does not add physics or
increase the numerical-equivalence scope of the earlier full baseline audit.

| Capability | Implemented | Tested status / limits |
|---|---|---|
| VOID | HOMOGENEOUS, SLIP, BESTION, EPRI | Original HEM/slip/Bestion cases; EPRI smoke test |
| THERMALNONEQ | EQUILIBRIUM, SAHAZUBER, EPRI, MRM | Original equilibrium/Saha–Zuber/MRM; thermal EPRI smoke test |
| MRMTIMEINT | EULER, EXPONENTIAL | Both full original transient schedules and tightened checks; residuals explicitly reported |
| Friction | SPMTM BLASIUS; TPFM HOMOGENEOUS/SLIP/EPRI | Homogeneous identity and original EPRI case; SLIP source-inspected |
| Local loss | TPKM HOMOGENEOUS/SLIP/ROMIE | Original local-loss case; other branches source-inspected |
| Momentum | Gravity, wall, spatial/temporal acceleration, slip correction, local | Analytic adiabatic check and discrete sample/transient residuals |
| SPHTM | DITTUSBOELTER, SIEDERTATE, GNIELINSKI | Heat-transfer/energy checks in selected states; generalized branch unsupported |
| TPHTM / BTHTM | THOM; VAPOR/DOUGALL/BISHOP/MOECK/DELORME/CONDIEIV | Coefficient smoke/energy checks; DELORME one wall only |
| CBT / MFBT / BTMTM | All declared enums | NONE/ELEVATION exercised; other transitions largely source-inspected |
| THERMALRELAX | FOURIERX/TIMEX/VOID/HOMOGENEOUS/FOURIER | All five branches, units/time interpolation and pure-vapor boundary |
| INTTRANSH | BULK/SATURATED | Field branches and two-fluid exchange identities |
| Near-wall | All declared enthalpy/relaxation enums | Default QUALITY/RATIO exercised; other branches largely source-inspected |
| OAF | WALLIS/WALLIS_SIMP/LEVITAN, cached sigmoid | WALLIS exercised; others source-inspected; source caching retained |
| Multiple walls/time | Native arrays and schedules | Two-wall HEM and full original 0–5 s transient; arbitrary combinations unverified |

`field_notes.md` and saved mixture/MRM/sensitivity reports give branch-level evidence. Finite/positive values at one state are not empirical correlation validation.

## Two-fluid selections

Native equations exist for MOMENTLIQUID/GAS MIXTURE/SLIP/FULL; INTLENGTH CONSTANT; INTAREA DISPGAS2DISPLIQ; LOCRELVEL AREAMEAN/SCALED/DRIFT; BUBBLEDRAG and DROPDRAG CONSTANT/STOKES/VISCOUS/DISTORDED; INTNU CONSTANT/RANZMARSHALL/RELAXATION; INTTRANSH BULK/SATURATED. Tests exercise original mixture/full momentum and selected exchange/slip relations. The original 51-state transient converged numerically but reached a 43.361% area discrepancy. Broader combinations and two-fluid transient time-step sensitivity remain unverified.

**The original TUTORIAL1/3B numerical solution fails occupied-area consistency.** `diagnostics()` and metadata expose this; CLI returns status 3. It must not be presented as a physically consistent prediction. See `twofluid_notes.md`.

## Annular selections

Three-field implements all declared OAFENTRAINED, DEPOSITION, DEPENHANCEMENT, ENTRAINMENT, THINFILMFRIC, VAPORFRIC, MOMENTFILM and MOMENTDROP selections. Original TUTORIAL4A–F exercise default/full/equilibrium momentum, prescribed onset ratio, Govan and disabled exchange. The original 51-state TUTORIAL4D transient was executed; fully annular area/inventory checks fail. Two tightened 25-cell time-step cases failed point convergence, so time convergence is not established. Other branches are only source-inspected or unit-tested; broad multiwall coverage is absent. `threefield_review.md` and `threefield_transient.md` record applicability, dryout clipping and closure-iteration differences.

Four-field adds all declared OAFFILMSPLIT, BASEEQTHICK, MOMENTBASE, MOMENTWAVE, WAVEBASEINT, WAVEFREQUENCY and EQSTROUHAL relations. `fourfield_notes.md` records actual tests, tutorial outcomes, clipping, zero-slip NaNs and frequency stopping limitations. Only one wall is supported. An available enum/class is not proof of full operating-domain coverage.

## Explicit unsupported scope

- SPHTM=DITTUSBOELTERGEN: upstream matrix multiplication is incompatible with its vector arguments; no silent elementwise correction.
- Multiwall DELORME and four-field; two-fluid multiple walls with FULL momentum: unresolved source indexing/dimension behavior.
- NEARWALLRATIO endpoints 0/1: required diagnostics divide by zero. Upstream parser permits them; this port explicitly rejects that singular path.
- Annular DROPDRAG=DISTORDED: undefined upstream objects.
- Two-fluid LOCRELVEL SIMPLE: enum without an implemented source equation; FLOWREGIME selector is not legal in the upstream enum.
- Defective two-fluid FLOWREGIME/vapor.X subset and vapor.S diagnostic forms; error messages identify available alternatives.
- Annular Drop.RE refers to undefined Drop.MU; TwoFluid Vapor.XTR_CBT refers to missing Liquid.XTR_CBT. Both explicitly reject calls; REV is a different implemented diagnostic.
- MATLAB function expressions; ambiguous interpolation `cubic`; unknown selections.
- Remaining MATLAB plot styles, grouped diagnostic selections, masks/overlays, 3D/video export; MATLAB serialization and every tutorial workflow. Native saved-array history/space-time/GIF APIs exist, with documented selection limits.

## Remaining verification

`METHOD_COVERAGE.md/json` provide a reproducible declaration inventory, including inherited methods and partial/internal alternatives. Name matches do not prove equations, branch coverage, semantics or validation. Newly added MTRANSV is the actual source's unused transverse exchange diagnostic and was not inserted into the governing equations. Coordinate, obstruction-subset, transition and boundary-pressure diagnostic APIs have focused tests. Generic live-field transient/struct extraction, input writers and some interpolation convenience APIs still differ from upstream; saved-array plots cannot reconstruct unsaved closures.

Execute independent MATLAB exports and fixed-tolerance comparisons for all frameworks/transients. Resolve unsupported model paths under a documented compatibility policy. Investigate two-fluid area failure against MATLAB and the governing formulation. Extend closure-domain, annular-transient and multiwall checks. Validate separately against original experimental measurements. None of these remaining requirements is satisfied by the successful mixture milestone.
