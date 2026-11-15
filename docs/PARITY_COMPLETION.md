# Completing the native port and its verification

Audit date: 2026-11-14. Numerical target: OpenSTREAM
`a614c7173822a93c1e64ac28d1541cbac028cbd8`, CoolPropWrapper
`a7c40902ff66faf6ed668986398bb1b9faa16e13`. Experimental-data target:
[OpenSTREAM-database, commit b48541e](https://github.com/OpenSTREAM-solvers/openstream-database/tree/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22).

The four original steady baseline cases agree with the archived MATLAB primary
profiles, initialization histories, and mixture precursors. This establishes
selected-case numerical agreement. It does not establish complete API/option
parity, transient equivalence, or accuracy against measurements. Physical
validation is to use the external experimental datasets in OpenSTREAM-database,
as requested. The database inspection below is preparation, not an executed
validation study.

## Next concrete milestone

Build a native reader and input adapter for the pinned database, then run a
small, explicitly selected **Bartolomey void-fraction case set** end to end with
the mixture framework. Preserve raw XML values and units, review generated
geometry/heating/boundary inputs, calculate at the experimental coordinates,
and publish errors and numerical-sensitivity results. Add Adamsson film-flow
cases next, followed by appropriate Wurtz/Sawai wave measurements and
Bennett/Groeneveld thermal/dryout cases. This order is an implementation
recommendation, not a claim that these cases will pass physical validation.

In parallel, recover additional approved MATLAB outputs or execute the existing
reference exporter in any available compatible MATLAB environment for transient
and alternative-closure cases. MATLAB remains unnecessary for normal Python
operation. The pinned core regression directory contains only four TUTORIAL1
MAT archives; the database repository's inspected tree contains XML data and
MATLAB application scripts, not additional transient solver reference archives.
Saved figures or Live Script outputs must be inspected before treating them as
portable numerical reference data.

## Completion work and acceptance evidence

| Workstream | Remaining work | Evidence required to close it |
|---|---|---|
| Requirements and branch map | Convert the existing declaration inventory into an acceptance ledger for public operations, closures, input combinations, regimes, and documented limits. Classify implemented, tested, unsupported, and unverified separately. | Every in-scope requirement has a source anchor, Python path, explicit domain, and executed acceptance test or documented source defect. Method-name counts are not completion percentages. |
| MATLAB numerical equivalence | Extend beyond four steady cases to physical transients, alternative closures, onset/boiling/dryout transitions, multiwall behavior, boundary conditions, and derived/iteration diagnostics. | Independent reference arrays with inputs, dimensions, units, grid/time axes, source/property versions, convergence histories, and immutable hashes. Preserve original `rtol=1e-8`, `atol=0` core criteria and exact reference zeros. Investigate supplementary failures rather than changing tolerances to pass. |
| Missing native interfaces | Finish generic live-field transient/struct extraction, public interpolation conveniences, input writers/default reporting, session/output behavior, and remaining post-processing operations. | Equivalent user workflows run without MATLAB. Document deliberate native replacements for MATLAB-only formats; verify round trips, signatures, subsets, arrays, and errors. A portable NPZ alternative is not MATLAB object serialization. |
| Unsupported or ambiguous paths | Resolve generalized Dittus–Boelter, ambiguous `cubic`, multiwall DELORME/FourField/TwoFluid FULL momentum, and source-defective diagnostics under a documented compatibility policy. | Separate a translation omission from an invalid source expression. Define behavior from source evidence before implementing it. Defective source options retain explicit errors unless an independently reviewed model/API correction is introduced and versioned separately. |
| Numerical verification | Establish converged mesh/time-step sequences, stricter iterative convergence, local/global mass and enthalpy balances, applicable momentum balances, physical bounds, and operating-limit tests for each applicable framework. | Report finite-state, phase/area, balance, and discretization errors with units and domain masks. Demonstrate decreasing numerical error where a convergence claim is made; do not infer an order from failed or non-asymptotic runs. |
| Experimental validation | Port OpenSTREAM-database loading/input generation/comparisons and evaluate suitable source measurements with uncertainty and model-domain controls. | Traceable measured-versus-calculated tables and plots, signed bias/MAE/RMSE with units, uncertainty treatment, exclusions, numerical uncertainty, and independent evaluation cases. Passing a MATLAB comparison or an internal conservation check is not experimental validation. |
| Reproducible release | Complete clean-clone installation, GUI/CLI/API examples, pinned dependency/asset notices, portable paths, CI regression jobs, and release evidence. | A fresh machine/CI runner installs the package and executes the declared checks, examples, and selected reference comparisons. Preserve reference results and failure reports; keep generated local environments and credentials out of source control. |

The existing method audit lists 585 non-constructor interface entries across
25 mapped classes, including inherited repetitions: 447 name candidates,
54 partial/internal alternatives, 77 infrastructure/presentation gaps,
5 explicitly unsupported entries, and 2 setter-contract reviews. These are
declaration classifications, not verified numerical requirements or an estimate
of remaining effort. A full-parity percentage is not defensible yet.

## All nine tutorial workflows need acceptance

The pinned source includes `tutorial01` through `tutorial09` Live Scripts.
Selected calculations from them have native evidence; the complete interactive
workflows are not all accepted. Use the original scripts and
[tutorial descriptions](https://github.com/OpenSTREAM-solvers/openstream/blob/a614c7173822a93c1e64ac28d1541cbac028cbd8/docs/source/Guides/tutorials.rst)
as requirements:

| Tutorial | Remaining workflow acceptance |
|---|---|
| 1 — Quick start | Repeat the original quick-start input/solve/inspection/saving/plotting workflow in an installed package. Retain the four already passing framework baseline comparisons as separate regression evidence. |
| 2 — Mixture | Cover fixed-slip/drift-flux and thermal-nonequilibrium branches, pressure/local losses, wall transfer, and physical transients, with reference outputs where available. |
| 3 — Two-fluid | Verify phase diagnostics/exchange and hydrodynamic/thermal nonequilibrium; compare physical transients and convergence histories. |
| 4 — Three-field | Verify onset initialization, entrainment/deposition variants, film/drop momentum, annular-domain diagnostics, and successful sensitivity studies. |
| 5 — Four-field | Verify base/wave decomposition, wave frequency/geometry, equilibrium/relaxation variants, transient outputs, and all legal wall configurations. |
| 6 — Input files | Complete input writers, INP/JSON conversion and round trips, default reporting, functions/sentinels, vector/matrix orientation, and unsupported-value errors. |
| 7 — Convergence | Reproduce point versus pseudo-time versus physical-time distinctions, stopping behavior, relaxation dependence, and failure/reinitialization semantics. |
| 8 — Mesh/time step | Reproduce all defined steady/transient comparisons, including peak/transition behavior and computational effort; establish convergence only where the executed sequences support it. |
| 9 — Visualization | Complete time/elevation selection, surfaces, animation/export, result extraction/tables, saving/reloading, and explicitly document unavailable MATLAB-specific styling/interaction. |

The current GUI intentionally provides steady presets; its omission of
transient scheduling is a GUI limit, not evidence that native transient solvers
are absent.

## External experimental datasets inspected

The following six dataset packages/readmes and selected MATLAB adapters were
inspected at database commit `b48541e6438a92b4c0ddc83cf0ceda3f71a59b22`.
The source XML files live under each package's `+src` directory. Software and
documentation are MIT licensed; the database's own license guidance retains
the original publications' attribution and any separate data-reuse conditions.
Source citation is required even when the data are read through this adapter.
The repository states that it has no automated test suite.

| Dataset and pinned source | Measured targets / applicable workflow | Audit points before quantitative validation |
|---|---|---|
| [Bartolomey](https://github.com/OpenSTREAM-solvers/openstream-database/tree/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22/%2BBartolomey) | Subcooled-boiling void fraction for mixture and suitable two-fluid cases; the inspected XML has 34 records with noncontiguous IDs. | Digitized from NUREG/IA-0025 figures. Some measurements use equilibrium quality, others elevation; empty coordinates are missing data. Review digitization and experimental uncertainties separately. |
| [Adamsson2006](https://github.com/OpenSTREAM-solvers/openstream-database/tree/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22/%2BAdamsson2006) | Film mass flow in heated steam-water tubes; primarily ThreeField, with suitable FourField assessment. | Tables manually transcribed. At 7 MPa, 750–1750 kg/(m² s), multiple axial heating profiles. Preserve measurement-position/power-profile construction; the plotted droplet-flow estimate is derived, not independently measured. |
| [Wurtz1978](https://github.com/OpenSTREAM-solvers/openstream-database/tree/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22/%2BWurtz1978) | Film flow, base thickness, wave velocity/frequency/amplitude/spacing and related quantities. | Selected Risø-372 tables, manual transcription; an adiabatic equilibrium representation is used. Some quantities are missing. Frequency is Hz; period is its reciprocal in seconds. Distinguish direct measurements from correlation/derived comparisons. |
| [Sawai1989](https://github.com/OpenSTREAM-solvers/openstream-database/tree/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22/%2BSawai1989) | Eight cases, wave velocity and period at four axial locations, mainly FourField. | Digitized data, nonuniform heated/unheated domain, millisecond period exception, and out-of-domain measurement coordinates described below. |
| [Bennett1967](https://github.com/OpenSTREAM-solvers/openstream-database/tree/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22/%2BBennett1967) | Post-CHF wall temperature and onset/dryout; separate thermal-nonequilibrium and annular-dryout assessments. | OCR/transcription from AERE-R-5373; temperatures K, inlet subcooling J/kg. Missing onset elevation is not zero. Supplying measured onset as an input can assess downstream wall temperature, but cannot independently validate prediction of that onset. |
| [Groeneveld2019](https://github.com/OpenSTREAM-solvers/openstream-database/tree/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22/%2BGroeneveld2019) | CHF/critical power and selected film-dryout predictions against NUREG/KM-0011. | Audit derived mass flow, power and inlet enthalpy; port and verify the outer dryout power search separately from the axial solver. Identify calibration/training overlap: data supporting a CHF correlation are not automatically an independent validation set for that correlation. |

Dataset-specific uncertainty statements above are from the repository readmes;
the original publications have not been independently re-audited in this port.
Their quantitative uncertainties must be recovered before an uncertainty-based
acceptance claim. The inspected database dependency checker requires upstream
OpenSTREAM `~=2026.0`; native-adapter compatibility must be tested by behavior,
not inferred from the Python package's unrelated version number.

### Two Sawai data issues already identified

1. **Period units:** the root README's general all-SI statement has a documented
   exception. `+Sawai1989/README.md` says `WaveTimePeriod` is stored in
   milliseconds. The XML includes values such as 64.3567; its plotting method
   multiplies predicted seconds by 1000 and plots the measured values directly
   on a millisecond axis, although one code comment incorrectly says seconds.
   Convert the measured period once (`ms × 0.001 = s`) in a native SI adapter,
   retain the raw value/unit, and test this conversion explicitly.
2. **Axial domain:** all eight inspected XML records specify `Length=1.648 m`,
   but each has a final `Elevation` between 1.6923 and 1.7002 m, exceeding the
   domain by 0.0443–0.0522 m. This is a data/coordinate inconsistency requiring
   review against the original source. Do not silently extrapolate, clamp the
   coordinate, or extend the modeled channel. Retain the raw record and mark
   these points ineligible for within-domain error metrics until resolved.

These findings do not establish which original geometry or coordinate is
correct, and no source data or governing equation was changed during this
audit. They prevent an honest claim of a complete, all-point Sawai comparison
under the presently stored domain.

### Required native validation adapter

Translate the behavior of
[`@Dataset/Dataset.m`](https://github.com/OpenSTREAM-solvers/openstream-database/blob/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22/@Dataset/Dataset.m),
[`makeInputFiles.m`](https://github.com/OpenSTREAM-solvers/openstream-database/blob/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22/@Dataset/makeInputFiles.m),
dataset-specific classes, and application workflows, while calling the existing
native numerical API. A runnable implementation must:

1. Pin/hash inputs and retain original identifiers, repeated XML fields,
   missing values, units, direct/derived status, original citations and any
   conversion. Never substitute zero for an unavailable measurement.
2. Generate identical geometry, fluid, pressure, inlet enthalpy, mass flow,
   total power and axial heating representation. Check `mass flow = mass flux
   × area`, power against the integrated heat flux, wall-mesh length and sensor
   positions, with rounding/transcription differences recorded rather than
   silently normalized away.
3. Document all closures, options and empirical coefficients before comparing
   predictions. Preserve the experiment's measured quantity definition,
   domain and observation coordinates. Use interpolation only for comparison
   to within-domain measurement locations, record its method, and assess its
   numerical error; this is distinct from the no-interpolation MATLAB
   regression comparisons.
4. Demonstrate applicable numerical convergence and balances first. Report
   model failures and nonconverged cases as outcomes rather than dropping them
   from aggregate validation statistics.
5. Compute signed errors, bias, MAE and RMSE with physical units. Use relative
   errors only where the measured denominator is meaningfully nonzero. Compare
   with combined measurement/digitization/numerical uncertainty where justified;
   where uncertainty is unknown, report it as unknown instead of inventing a
   statistical pass band.
6. Separate calibration from evaluation by experimental source/group, and
   retain holdout cases. Report validation only for the tested quantity, fluid,
   geometry, operating range and model configuration.

## Retained source defects and physical findings

The steady MATLAB archives themselves contain occupied-area discrepancies:
41.056107% for TwoFluid, 7.485259% for ThreeField, and 11.241052% for FourField;
the annular figures apply only in the fully annular region. These shared
failures are not evidence of a new Python translation error. Native transient
area/mass failures have not yet been checked against transient MATLAB outputs.
Full physical validation cannot be inferred from either result. See
[the baseline report](ALL_BASELINES_VERIFICATION.md).

Source-defective methods such as annular `Drop.RE` (undefined `Drop.MU`),
TwoFluid `Vapor.XTR_CBT` (missing `Liquid.XTR_CBT`), and the invalid annular
DISTORDED drag path require explicit documented handling. A change to their
underlying model is a separately reviewed correction, not a translation fix.
Likewise, unresolved multiwall MATLAB indexing needs source-intent evidence;
substituting different physics to remove an error would not establish parity.

Completion is reached only when the agreed requirement ledger is closed and
its numerical-equivalence evidence is reproducible. Experimental validation
remains a bounded claim about measured cases and model domains; even a complete
software translation cannot make an imperfect source model universally valid.

## Existing evidence

- [Feature and unsupported-option map](FEATURE_MAP.md).
- [Method-inventory scope and limits](METHOD_COVERAGE.md).
- [All four archived baseline comparisons](ALL_BASELINES_VERIFICATION.md).
- [Portable MATLAB reference-export/comparison procedure](REFERENCE_COMPARISON.md).
- [GUI checks and release limits](GUI_VERIFICATION.md).
- [Database repository README](https://github.com/OpenSTREAM-solvers/openstream-database/blob/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22/README.md)
  and [license](https://github.com/OpenSTREAM-solvers/openstream-database/blob/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22/LICENSE).
