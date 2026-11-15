# Le Corre NURETH-21 reproduction: source contract and discrepancies

Target: J.-M. Le Corre, J. Chan, E. Walter, E. T. Hurlburt and R. W. Morse,
*OpenSTREAM: An Open-Source Platform for Two-Phase Flow Modeling and
Simulation*, NURETH-21 (2025), supplied as `LeCorre2025OpenSTREAM.pdf`.
This is distinct from the two ICMF abstracts and from the Bartolomey pilot.
Reproduction means retaining the specified cases and physics; it does not
mean choosing parameters that make the Python curves resemble a figure.

## Immutable targets and evidence levels

| Source | Identity | Evidence supplied |
|---|---|---|
| Supplied 14-page paper | SHA256 `f72e78c41036f84db849fb080187562777e6b6696b407b6bcce2b8ca9d11ada1` | Published conditions, model descriptions, plotted predictions and measurements |
| OpenSTREAM | `a614c7173822a93c1e64ac28d1541cbac028cbd8` | Pinned governing equations, closure implementations, defaults and numerics |
| CoolPropWrapper | `a7c40902ff66faf6ed668986398bb1b9faa16e13` | Property-backend/version target |
| OpenSTREAM-database | `b48541e6438a92b4c0ddc83cf0ceda3f71a59b22` | Experimental records and companion workflow |
| `database/projects/NURETH21.mlx` | SHA256 `f43f99a7a9dbfc0894748b97e05a1043379254d2cde39f59be5f3688ab8b960c` | Executable case definitions and their sequential inheritance; no numerical output-array entries |

The pinned companion is a later source artifact, not proof that its current
defaults, property version and solver revision generated every published
curve. The supplied PDF's plot panels are raster graphics, not embedded
full-precision arrays. Extracted plot coordinates, if used, are digitized
paper evidence with finite graphical resolution. They must not be described
as recovered MATLAB numerical arrays. The original four TUTORIAL1 archive
comparisons retain their own scope and do not certify these publication cases.

Original PDFs and full extracted paper text remain local. Citations, source
hashes, derived comparison data and analytical descriptions identify the
publication without redistributing it.

## Figure-to-case contract

| Figure | Native calculation target | Compared quantities | Scope condition |
|---|---|---|---|
| 3, PDF p.9 | One shared boiling-water case, separately solved by Mixture, TwoFluid, ThreeField and FourField | Prescribed wall heat flux; liquid/film/drop/base/wave mass flows; void fraction and equilibrium quality with source field definitions | Sequential companion model inheritance retained; full profiles and onset mask saved |
| 4, PDF p.9 | ThreeField/FourField results from the same demonstration | Film/base thickness, wave amplitude, field velocities, wave frequency and equilibrium frequency | Use the source annular-flow plotting range, not pre-onset initialization values as physical annular predictions |
| 5, PDF p.10 | Two-fluid and mixture comparison against TRACE | Phase variables for 0.6 MJ/kg inlet enthalpy and 150 kW | Complete reproduction unavailable: companion explicitly omits the missing TRACE reference case/results |
| 6, PDF p.11 | FourField, every Wurtz1978 record whose `TestName` is exactly `TS 20` | Outlet base-film thickness, wave velocity and wave number density | 21 source records; fixed measurement-informed entrainment coefficient; missing measured targets remain missing |
| 7, PDF p.12 | FourField, Sawai1989 one-based rows 1, 2, 5 and 6 | Axial wave velocity, wave time period and equilibrium period | Preserve separate paper `RELAXTW=0.2 s` and companion `RELAXTW=0.1 s` configurations; out-of-domain measurements explicitly excluded from interpolation |

The companion's Wurtz subset is a 7 MPa pipe subset. The paper's description
of the broader source experiment includes other pressures and an annulus;
those broader conditions are not silently added to the Figure 6 selection.

## Exact demonstration inputs and inheritance

All quantities below are the companion's stored values in SI units. Do not
replace explicit area/perimeter/enthalpy with values recomputed from the
paper's rounded 8.8 mm diameter and 1.14 MJ/kg inlet description.

| Input | Value | Unit |
|---|---:|---|
| Fluid | water | single component |
| Pressure | 6,000,000 | Pa |
| Mass flow | 0.07 | kg/s |
| Inlet enthalpy | 1,139,400 | J/kg |
| Total power | 87,500 | W |
| Length | 5.5 | m |
| Area | 0.000060821 | m2 |
| Perimeter | 0.0276 | m |
| Wall segment lengths | `[1.75, 1.75, 2.0]` | m |
| Relative wall power | `[1.0, 1.0, 0.0]` | 1 |
| Axial interpolation | `NEXT` | source selection |

The common option structure starts with `Dataset.inputOptions()`. Generated
input files obtain `NNODES=100` from `Dataset.makeInputFiles`; other unspecified
values retain pinned source defaults and the source writer's `%.11f` numeric
round-trip. No extra physical transient is introduced. The companion makes
no numerical-control override beyond axial interpolation. In particular,
the source defaults include `MAXITER=100`, `SSMAXITER=30`, `SSTSTEP=1 s`,
and `PROPERTIES=SATURATED`. These are reproduction settings, not a claim
that their numerical error is sufficiently small in every case.

The four model configurations are cumulative:

1. **Mixture:** no additional model overrides; homogeneous equilibrium.
2. **TwoFluid:** retain Mixture settings, then set `INTNU=RELAXATION`,
   `RELAXX=[-0.5,1.0]`, `RELAXCONDT=[0.5,0.5,0.01]`,
   `MOMENTLIQUID=FULL`, `MOMENTGAS=FULL`, `DROPDRAG=VISCOUS`.
3. **ThreeField:** retain the TwoFluid option structure, then set
   `MOMENTFILM=FULL`, `MOMENTDROP=FULL`, `DROPDIAM=0.001 m`.
4. **FourField:** retain the ThreeField option structure, then set
   `MOMENTBASE=FULLNOP`, `MOMENTWAVE=FULL`,
   `WAVEBASEINT=VAPORSHEARDROPMASS`, `OAFFILMSPLIT=RATIO`,
   `OAFBASERATIO=0.3`, `BASEEQTHICK=YPLUS`.

The demo inherits `RELAXTW=0.2 s` from the pinned model default, consistent
with the paper's demonstration description on PDF p.8. This differs from
the later explicit Sawai companion override discussed below.

## Exact experimental model selections

Each experimental section restarts from its dataset's fresh
`inputOptions()`; it does not inherit the demonstration or the other
experimental section. Geometry, heating, pressure, enthalpy and mass flow
come from the selected source XML records through the translated
`Dataset.makeInputFiles` contract. Preserve full effective input snapshots.

| Selection | Wurtz Figure 6 | Sawai Figure 7 |
|---|---|---|
| `THERMALNONEQ` | pinned default | `EPRI` |
| `VOID` | `BESTION` | `EPRI` |
| `TPFM` | pinned default | `EPRI` |
| `OAFENTRAINED` | `EQUILIBRIUM` | `EQUILIBRIUM` |
| `DEPOSITION` | `OKAWA` | `OKAWA` |
| `ENTRAINMENT` | `OKAWAGEN` | `OKAWA2003` |
| `OKAWACOEFS` | `[320, 0.111, 0.000350, 1]` | pinned default |
| `OAFFILMSPLIT` | `EQUILIBRIUM` | `EQUILIBRIUM` |
| `MOMENTBASE` | `FULLNOP` | `FULLNOP` |
| `MOMENTWAVE` | `FULL` | `FULL` |
| `VAPORFRIC` | source literal `CONST`; recorded migration to `CONSTANT` | same recorded migration |
| `VAPORFRICCST` | `0.005` | `0.005` |
| `WAVEBASEINT` | `VAPORSHEAR` | pinned default |
| `WAVEMIXCOEF` | pinned default | `2` |
| `THINFILMTHICK` | pinned default | `0.0001 m` |
| `THINWAVETHICK` | pinned default | `0.00001 m` |
| `SHAPEFACTORCOEF` | pinned default | `[132500, 2, 1, 0]` |
| `EQSTROUHAL` | pinned default | `SAWAI` |
| `RELAXTB` | pinned default | `0.5 s` |
| `WAVEFREQUENCY` | pinned default (`RELAXATION`) | `RELAXATION` |
| `RELAXTW` | pinned default (`0.2 s`) | `0.2 s` paper / `0.1 s` companion, separately named |

Wurtz outlet wave number density is `FREQUENCY/U_wave`, in m^-1; the stored
database `WaveNumberDensity` is the comparison target. It must not be
replaced by a recomputed frequency/velocity ratio without recording that
transformation and its rounding/correlation consequences. Base thickness
is stored in metres; paper axes use millimetres. Sawai wave period is
computed by the source as `1/FREQUENCY`, in seconds, and plotted in
milliseconds. Stored Sawai `WaveTimePeriod` numbers are milliseconds even
though one source plotting comment says seconds.

For Sawai, both measured and predicted coordinates use
`(z - heated_length)/Diameter`, with `heated_length=0.8 m` and
`Diameter=0.004 m`. Preserve raw elevations in metres and raw period
values in milliseconds beside SI values. A transformed coordinate does
not bring a measurement beyond `Length=1.648 m` inside the computational
domain.

## Discrepancy register fixed before comparison

| ID | Source discrepancy or limitation | Required treatment | Acceptance linkage |
|---|---|---|---|
| LC-001 | Current companion and pinned 2026 implementation are not a documented publication-producing runtime/source bundle | Identify them as the current-companion reconstruction; retain paper and source hashes, complete inputs and actual property versions | EXP-001, EXP-013 |
| LC-002 | Companion uses `VAPORFRIC='CONST'`; pinned enum accepts `CONSTANT`, `WALLIS`, `WALLISTHICK`, `SOLVER_DEPENDENT` | Keep literal input rejection. At the publication runner only, explicitly map this one documented spelling to the intended fixed coefficient 0.005; log original/effective selections. Do not add a global alias or choose a different friction law | EXP-001, EXP-010, EXP-011 |
| LC-003 | Paper Figure 7 selects 0.2 s relaxation; companion code and prose select 0.1 s | Execute separately labeled paper-value and companion-value branches. Do not select the better-fitting result after inspection | EXP-001, EXP-011, EXP-014 |
| LC-004 | Each selected Sawai record contains a measured elevation outside the stored 1.648 m channel | Retain every raw measurement; mark out-of-domain exclusions explicitly. No clamping, extrapolation, coordinate shifting or length extension to obtain agreement | EXP-006, EXP-012 |
| LC-005 | Sawai measurement period comment conflicts with numerical values and plot units | Record raw milliseconds; convert by 0.001 to seconds for calculation/error accounting, and use explicit plot units | EXP-006, EXP-012 |
| LC-006 | Wurtz `OKAWACOEFS` reduction and Sawai relaxation selection are measurement-informed | Call these calibration-associated reproduction cases, not independent holdout validation | EXP-014 |
| LC-007 | Original TRACE case/results are absent from the companion | Mark Figure 5 not reproduced. Rounded paper conditions alone do not define the exact TRACE or OpenSTREAM closure/numerical configuration | EXP-004 |
| LC-008 | Numerical arrays for the published predictions are absent; plot panels are raster images | Report digitized/visual comparisons at their stated resolution. Do not apply archived-array tolerances or claim MATLAB equivalence from graphical similarity | EXP-002, EXP-010, EXP-011, EXP-013 |
| LC-009 | Existing annular physical-consistency failures and frequency stopping limitations may occur in these new cases | Save original output and diagnostics, require separate numerical/frequency/onset/nested-closure checks, and retain failed physical criteria even if curves agree | CORE-028, CORE-033, EXP-008 |

## Acceptance and accounting protocol

This protocol is established before evaluating the newly calculated errors.

- **Input fidelity:** case selection, model choices, inherited defaults,
  explicit stored geometry/boundary values, properties and units must be
  traceable. Every deliberate difference has a named discrepancy/variant.
  A missing publication-time value remains unknown; a pinned default is a
  documented reconstruction choice, not recovered historical metadata.
- **Reproduction first:** execute the companion-derived 100-cell controls
  without tuning. Any tighter-control or mesh follow-up is a separate
  configuration retaining the original attempt and reason for the change.
  Scientific options are not silently changed after failures.
- **Convergence:** save source solver state, the stricter native convergence
  flag, precursor convergence, wave-frequency convergence, onset convergence,
  nested closure failures, iteration histories, warnings and execution/export
  errors. A source `SOLVEDCONVERGED` state alone does not close all these gates.
- **Physical consistency:** use the existing source-equation and integrated
  diagnostics, including mass/transported enthalpy, phase partitions, positivity,
  finite state, frequency and occupied-area geometry. The existing relative
  annular area criterion is 1e-6. Apply it only to numerically unblended annular
  nodes (`AFFNC >= 1 - 1e-12`). No eligible region means unknown, not pass.
  Retain the source's clipping and one-way mixture pressure/energy coupling.
  Do not invent a total-energy or independent multifield-pressure validation
  claim from the transported-enthalpy/precursor equations.
- **Matched quantities:** compare Wurtz outlet quantities and Sawai
  within-domain axial quantities in identical units. Keep measured, derived,
  equilibrium-reference and paper-digitized quantities distinct. Preserve
  missing/out-of-domain observations and all attempted cases.
- **Comparison statistics:** signed prediction-minus-reference errors,
  bias, MAE and RMSE are descriptive. No universal relative error is computed
  near zero. Unknown measurement/digitization/numerical uncertainty prevents
  an uncertainty-qualified experimental pass. Plot guide bands are not a
  general acceptance threshold. Graphical comparisons cannot establish
  full-precision agreement; the original archive tolerances remain unchanged.
- **Numerical sensitivity:** report differences at matched coordinates only
  when both configurations satisfy their convergence/domain gates. No
  asymptotic order or continuum uncertainty estimate is claimed without a
  suitable refinement sequence. A failed source-default run remains failed
  even if a separately named tighter run converges.
- **Status axes:** implementation, native checks, MATLAB equivalence,
  physical consistency and experimental comparison remain independent in
  `docs/acceptance/experimental.json`. New evidence changes only the rows
  and scopes it supports; all 81 existing requirement IDs and criteria stay
  stable. Figure 5 and unverified publication-time metadata remain open.

## Source locations

- `database/projects/NURETH21.mlx`: source case definitions and plotting logic.
- `database/@Dataset/Dataset.m`: `inputOptions`, selection and dataset behavior.
- `database/@Dataset/makeInputFiles.m`: stored-input/default/override mapping.
- `database/+Wurtz1978/@Wurtz1978/plotResults.m`: outlet target definitions.
- `database/+Sawai1989/@Sawai1989/plotResults.m`: axial coordinate and period display.
- `upstream/+Inputs/Model.m`, `upstream/+Inputs/Options.m`: pinned defaults.
- `upstream/+InputEnums/VAPORFRIC.m`: accepted friction choices.
- `src/openstream/output.py`, `twofluid.py`, `threefield.py`, `fourfield.py`,
  `multifield_output.py`: existing portable outputs and diagnostic scope.

Execution evidence and measured/graphical discrepancies must be added from
the saved campaign, not inferred from this source contract. Until that evidence
is recorded, the document makes no new numerical or experimental pass claim.
