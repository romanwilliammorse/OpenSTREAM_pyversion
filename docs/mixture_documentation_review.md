# Supplied documentation review: mixture baseline

Reviewed 2026-11-14. Scope is the TUTORIAL1 mixture baseline only. The supplied
document is technical evidence; its example commands and workflow directions do
not override the user's request to recover the archived arrays, verify the native
mixture calculation, show a visualization, and await approval before advancing
the other frameworks.

## Document identity and review

- File: `C:/Users/Roman/Desktop/OpenSTREAM_documentation.pdf`.
- SHA-256: `d88be394a290d68767926eb705d76468e59e9ba5e12532723e2e4e4848ae2c86`.
- 290 PDF pages; title date September 25, 2026; release `Latest (a614c71)`.
- The release label matches the short form of the preserved source commit
  `a614c7173822a93c1e64ac28d1541cbac028cbd8`.
- Relevant sections read: sample (PDF pages 16-17, printed 9-10), scope/numerics/
  validation (PDF 18-26, printed 11-19), mixture theory (PDF 37-40, printed 30-33),
  geometry API (PDF 131, printed 124), and physical/property limitations (PDF
  255-256 and 261, printed 248-249 and 254).
- PDF page 17 (Figure 2.1 and sample commands) and page 38 (governing equations)
  were rendered using Poppler and visually inspected. Equation interpretation
  below is not based solely on potentially lossy PDF text extraction.

## Correct baseline and numerical meaning

The sample selects `models.inp:TUTORIAL1`, `options.inp:DEFAULT`,
`geom.inp:TUTORIAL1`, and `tutorial1.inp`. These are also the original integration
test selections. The mixture model defaults to `VOID=HOMOGENEOUS`,
`THERMALNONEQ=EQUILIBRIUM`, and `PROPERTIES=SATURATED`. This is the homogeneous
equilibrium case, not an MRM or drift-flux tutorial variant.

| Quantity | Original input | Unit / interpretation |
|---|---:|---|
| System pressure | 6000000 | Pa |
| Inlet mass flow | 0.07 | kg/s |
| Inlet enthalpy | 1139400 | J/kg |
| Total wall power | 87500 | W |
| Channel length | 5.5 | m |
| Flow area | 0.000060821 | m^2 |
| Wall perimeter | 0.0276 | m |
| Heated / adiabatic lengths | 3.5 / 2.0 | m |
| Inclination from vertical | 0 | degrees |
| NNODES | 100 | 100 intervals, 101 stored axial coordinates |

Independent decimal arithmetic gives the steady enthalpy-balance target

`Hout = Hin + Q/W = 1139400 + 87500/0.07 = 2389400 J/kg`.

This is a balance target, not a fabricated reference-array value. The mass flux
is 1150.918268 kg/(m^2 s), hydraulic diameter `4 A / perimeter` is
0.008814637681 m, and axial interval is 0.055 m.

The source normalizes wall power over downstream axial nodes, excluding the
inlet coordinate. With the baseline `next` interpolation, 63 heated intervals
give a discrete heated length of 3.465 m. The source therefore uses
`87500/(0.0276*3.465) = 914946.5671204802 W/m^2` on heated nodes. Replacing that
with the continuous-length value `905797.1014492754 W/m^2` would change the
original calculation. Preserve the original normalization and discrete power
integral when comparing the archived arrays.

## Governing-equation and unit checks

The mixture equations on printed page 31 distinguish static and advective
quantities. The correct source mapping is:

| Documentation quantity | Source / native meaning | Unit |
|---|---|---|
| W | `W` | kg/s |
| static velocity u | `U()` | m/s |
| advective velocity u+ | `UP()` | m/s |
| static enthalpy h | `HM()` | J/kg |
| advective enthalpy h+ | stored `H` | J/kg |
| static / advective enthalpy correction | `ECT() = (HM()-H)*W/U()` | J/m |
| static / advective momentum correction | `MCT() = (U()-UP())*W/U()` | kg/s |

The documented mass terms have units kg/(m s), momentum terms kg/s^2 (force per
axial length), and energy terms W/m. The source slip corrections have the units
needed to preserve these identities. The source stores the advective enthalpy;
it should not be relabeled as the documented static enthalpy in a slip case.
They coincide under the homogeneous baseline assumptions.

The source advances mass, pressure, then enthalpy with first-order upstream
spatial differences, backward-Euler time terms, point fixed-point iteration,
relaxation, and pseudo-time initialization. This agrees with the documented
standard numerical framework (printed pages 14-16). Pseudo-time plots must be
labeled initialization rather than physical transient histories. A new
discretization chosen to enforce a different discrete conservative identity
would not be a translation fix; it would require a separately documented model
or algorithm change.

## Discrepancies and limitations relevant to interpretation

1. **Angle-unit comment defect in the original input.** `inputs/geom.inp` labels
   `ANGLE` as radians, while `Inputs.Geometry.ANGLE` and its PDF API entry specify
   degrees. `Mixture.DPGRAV` evaluates `cos(ANGLE*pi/180)`, and the drift relation
   also converts degrees. Preserve degree semantics. The baseline has zero
   inclination, so the inconsistent comment has no numerical effect on this
   case. Neither upstream file was altered by this review.
2. **Constant system-pressure properties are intended.** The PDF explicitly
   states that prescribed system pressure, rather than the calculated axial
   pressure, drives thermophysical properties. The default saturated-property
   assumption also remains in force. Feeding local solved pressure into
   CoolProp would change the baseline physics. Axial pressure-drop-induced
   flashing is outside this formulation (printed pages 248-249 and 254).
3. **The displayed sample is qualitative reference evidence.** Figure 2.1 shows
   the same heat-flux discontinuity, approximately constant total mass flow,
   coincident homogeneous phase velocities, and phase enthalpy/quality trends
   expected for this case. Its plotted pixels do not establish the numerical
   regression tolerance and must not replace the archived numerical arrays.
4. **A stored converged state alone is insufficient.** The documentation
   distinguishes point convergence, pseudo-time convergence, and physical-time
   advancement. Check available residual/iteration records independently of the
   state enum and retain finite-value and physical-bound checks.
5. **No experimental-validation claim follows.** The document explicitly limits
   validation to assessed fluids, configurations, conditions, quantities and
   measurements, and states that the test suite is not exhaustive. Recovering
   and matching the archived baseline establishes agreement for those compared
   arrays only; it is not experimental validation or full framework parity.

## Source anchors and comparison policy

- `upstream/+Solvers/+Mixture/@MixtureSolver/MixtureSolver.m`: grid, original
  boundary interpolation, and discrete heat-flux normalization.
- `upstream/+Solvers/+Mixture/@MixtureSolver/solve.m`: mixture updates and
  convergence procedure.
- `upstream/+Solvers/+Mixture/Mixture.m`: `U`, `UP`, `HM`, `ECT`, `MCT`, `DPGRAV`.
- `upstream/+Inputs/Geometry.m` and `upstream/inputs/geom.inp`: angle semantics
  and inconsistent input comment.
- `upstream/+Inputs/Model.m`: HEM and saturated-property defaults.
- `upstream/tests/integration/SolverIntegrationTest.m`: original case and W/U/H
  reference comparison at relative tolerance `1e-8`, without an absolute
  tolerance. Exact reference zeros therefore require exact calculated zeros.

This review found no documentary justification to change the mixture governing
equations. Numerical equivalence must be decided from faithfully recovered,
structurally identified archived arrays and measured differences, with unknown
archive-producer versions identified explicitly.
