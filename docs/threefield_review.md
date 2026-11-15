# Independent three-field port review

Reviewed `src/openstream/annular.py` and `src/openstream/threefield.py` against
the pinned upstream commit `a614c7173822a93c1e64ac28d1541cbac028cbd8`, specifically:

- `+Solvers/AbstractFilm.m`
- `+Solvers/AbstractField.m::copyFlowProperties`
- `+Solvers/+ThreeField/Film.m` and `Drop.m`
- `+Solvers/+ThreeField/@ThreeFieldSolver/ThreeFieldSolver.m` and `solve.m`
- Applicable input defaults and enums.

The original review below is an independent source and native numerical audit.
It did not execute MATLAB or validate against experiments. A later archived
baseline comparison is now complete, as described immediately below.

## Archived TUTORIAL1 comparison, 2026-11-14

The preserved MATLAB three-field archive was recovered without MATLAB and
compared with a fresh native TUTORIAL1 run. All six original film/drop W/U/H
profiles pass at the unchanged relative tolerance `1e-8` and absolute tolerance
zero. All six initialization states also pass these core checks. Maximum
relative differences are 1.22500e-13 for the physical state and 5.29623e-13 over
initialization. Final archived point and temporal convergence criteria pass.
No numerical implementation, governing equation or reference was changed.

Independent occupied-area accounting from the saved MATLAB values confirms a
**7.4852594% maximum discrepancy in fully annular flow**, with 1.6066443% at the
outlet. Thus this specific steady physical inconsistency exists in the
original archive as well as the native result. This does not resolve the
separate transient area/mass-storage failures or validate the model against
measurements. The producing source/CoolProp runtime remains incompletely
identified; this was an archive comparison, not a fresh MATLAB execution.

See [annular_reference_audit.md](annular_reference_audit.md) for recovery,
object/array mapping, units, convergence, independent comparison reports and
the annular-domain definition. Other tutorial, transient, multiwall and
closure-combination equivalence remains unverified unless separately recorded.

## Findings affecting conservation claims

### Film positivity clipping leaves a real mass-equation residual

The original source applies

```matlab
film(tIdx).W(zIdx,:) = max(film(tIdx).W(zIdx,:),0);
```

after its relaxed film mass update when `POSFILM=true`. The Python port preserves
this operation. It is a constraint on the solution, not a flux-limiting
modification of the mass source. If the net evaporation/entrainment demand would
make the film flow negative, the returned film can be zero while the original
unconstrained mass equation retains a positive residual.

For the documented TUTORIAL1 input (its three-field momentum settings are FULL),
the largest film mass-equation residual is **0.0002535411383029291 kg/s** at
zero-based node 63, z=3.465 m. At that node:

- Film flow is clipped to 0 kg/s.
- Upstream-node film flow is approximately 0.0001706 kg/s.
- Net source MTOT is approximately −0.27940512 kg/(m² s).
- The local source is evaluated with the unchanged original correlations and
  prescribed film heat flux.

This occurs at the end of the discrete heated region. Recomputing every source
point by point leaves the same clipped-node residual. Therefore it must not be
attributed to vectorization or removed by increasing the test tolerance.

On positive-film nodes the maximum pointwise residual is
**2.192487437724768e-6 kg/s**, below the preselected **5.52e-6 kg/s** criterion
(`2 * ERRORWF * max(PERIM)`). A valid test separates the unclipped mass equation
from the clipped branch, checks that a clipped state has the expected residual
sign, and reports the nonzero clipping defect explicitly. Exact total mass
partition is enforced algebraically through
`drop.W = mixture.liquid.W − sum(film.W)`, but that identity does not prove that
the local film transport equation is conserved at clipped nodes.

No change to the positivity floor or to the underlying evaporation/entrainment
model was made during this review. A physical dryout/source correction would be
a model change requiring separate justification and validation.

### Vector and pointwise closure evaluations have different stopping histories

Upstream `AbstractFilm.ENTNUM` iterates until the maximum relative slip change
over the **requested indices** is below `ENTNUMTOL`. The three-field solver
requests a single axial node. A postprocessor requesting the whole mesh forces
all nodes through the iteration count required by the slowest node and can
therefore obtain different approximate entrainment values at the unchanged
tolerance. The Python implementation retains this behavior.

For the same TUTORIAL1 result, at zero-based node 18 (z=0.99 m):

| Quantity | Single-node call | Whole-mesh call |
|---|---:|---:|
| Entrainment number [1] | 1.69100658 | 1.66963502 |
| Film entrainment mass flux [kg/(m² s)] | −0.87596183 | −0.86489111 |
| Drop deposition mass flux [kg/(m² s)] | 0.64741510 | 0.64741510 |

The source difference contributes 1.68053606e-5 kg/s to the recomputed film
balance. The maximum residual on positive-film nodes is 1.50839343e-5 kg/s when
using a whole-mesh source call, versus 2.19248744e-6 kg/s for the single-node
calls used by the actual solver. Verification must use the solver's pointwise
closure call semantics. This does not justify relaxing `ENTNUMTOL` or the mass
residual acceptance criterion. Higher closure-iteration accuracy and its effect
on the solution remain a separate sensitivity task.

Govan deposition also has a source-level vector dependence: MATLAB's `if
conc/rhog < 0.3` selects one branch for the entire vector argument. The port's
`np.all(...)` reproduces this semantics. Its pointwise solver calls are the
appropriate path for discrete residual checks.

## Equation, units, indexing and state audit

The inspected equations and update order match the source algebra:

- Film evaporation retains `−HFLUX/HFG` [kg/(m² s)], with the original ratio of
  quality gradients and annular-region blend in initialization.
- Film mass flow per wetted perimeter is W/P [kg/(m s)]; film thickness
  `W/(P rho_f U_f)` is in metres. Multiplying MTOT by perimeter and cell length
  gives kg/s, consistent with the film mass update and storage term.
- Film momentum exchange terms are N/m²; dividing by `rho_f * thickness` gives
  m/s². Droplet force terms are N/m³; dividing by `rho_f` gives m/s². The port
  retains these distinct normalizations.
- Film wall friction, wall/vapor shear, pressure-gradient force, gravity,
  deposition momentum exchange, droplet drag and entrainment momentum exchange
  preserve source signs, coefficients and annular-region blending.
- Full film momentum retains the source's thin-film fallback, velocity bounds
  and relaxation. Full droplet momentum retains its separate update and blend.
- Algebraic, slip, complete equilibrium and simplified equilibrium switches map
  to the corresponding source branches. The nested equilibrium secant method
  preserves its two starting states, update formula and iteration limits.
- Default `VAPORFRIC=SOLVER_DEPENDENT` resolves to WALLIS for the three-field
  framework, as in the upstream model's solver-dependent map.
- The source copies linear elements `2:end` to preserve the first element. The
  Python implementation uses column-major flattening and therefore preserves
  only the first `(node,wall)` element for multiwall arrays, not the whole inlet
  row. This potentially surprising behavior is deliberate source fidelity.
- Film/drop pseudo-time states own independent flow arrays; their shared
  precursor mixture for the same time index is reconstructed explicitly. Fluid
  property records remain immutable.
- Onset equilibrium retains the source's original fallback that increases its
  effective tolerance by ten after specified interpolation/nonmonotonicity
  failures. Both original and effective tolerances are recorded. None of the
  original tutorial variants below invoked that fallback.
- `DROPDRAG=DISTORDED` remains an explicit unsupported error because the pinned
  upstream branch refers to undefined liquid/vapor variables. It is not silently
  replaced with another correlation.

The reviewed `converged` property initially checked only outer and point
iterations. A failed onset equilibrium or nested secant/entrainment iteration
could therefore coexist with `converged=True` despite a warning. This was
reported to the implementation owner, who is strengthening the Python summary
status while retaining upstream STATE separately. No nested failure occurred
in the six original tutorial cases reviewed here.

Source behavior also warrants care outside the demonstrated conditions. Vapor
shear on film uses a squared relative velocity without a sign factor; the
source formula therefore remains positive if film velocity exceeds vapor
velocity. The demonstrated variants remain in positive co-current flow. This
review does not validate flow reversal or extrapolation outside the documented
model limits. A supplied mixture precursor is checked for matching mesh,
geometry and boundary conditions. Its closure/model compatibility still
requires care when reusing an externally supplied precursor.

## Original TUTORIAL4A–F checks

All cases use the unchanged original `models.inp`, `options.inp` DEFAULT,
`geom.inp` TUTORIAL1 and `tutorial1.inp`, selecting the indicated model ID.
The full evidence is saved in `outputs/threefield_variant_checks.json`, including
the reviewed Python source SHA-256 hashes, convergence histories, onset
iterations, actual warnings, positive-flow bounds and clipped-node lists.

| Model ID | Main variation | Converged | Max positive-film residual [kg/s] | Clipped node/wall pairs | Outlet film flow [kg/s] | Outlet drop velocity [m/s] |
|---|---|---|---:|---:|---:|---:|
| TUTORIAL4A | Defaults | Yes | 2.31112e-6 | 1 | 0.00588079 | 28.33088 |
| TUTORIAL4B | Onset drop ratio 0.30 | Yes | 2.23879e-6 | 1 | 0.00588174 | 28.33088 |
| TUTORIAL4C | Equilibrium film/drop momentum | Yes | 2.18779e-6 | 1 | 0.00588198 | 25.63919 |
| TUTORIAL4D | Full film/drop momentum | Yes | 2.19249e-6 | 1 | 0.00588152 | 25.74565 |
| TUTORIAL4E | Govan deposition/entrainment | Yes | 4.34864e-6 | 0 | 0.00321069 | 28.33088 |
| TUTORIAL4F | Deposition/entrainment disabled | Yes | 4.44523e-18 | 53 | 0 | 28.33088 |

All six runs had finite primary arrays, nonnegative film/drop flow, positive
film/drop velocities, exact liquid/total algebraic mass partition within
floating-point roundoff, zero recorded nested failures, and zero captured
warnings. The unchanged positive-film residual criterion is 5.52e-6 kg/s.
The largest unrestricted film residual is **0.0008842670865417791 kg/s** in
TUTORIAL4F, whose film is clipped to zero at 53 node/wall pairs; the positive
film balance alone must not be presented as a full-field conservation result.

No experimental comparison, MATLAB numerical-equivalence comparison,
three-field transient sensitivity, multiwall annular sensitivity or comprehensive
closure-domain validation was performed in this original TUTORIAL4A–F review.
The later passing TUTORIAL1 archive comparison above does not establish
equivalence for these six variants or their transient behavior.

## MATLAB missing-value semantics audit

The official MathWorks documentation for
[min](https://www.mathworks.com/help/matlab/ref/double.min.html) and
[max](https://www.mathworks.com/help/matlab/ref/double.max.html) specifies
`omitmissing` as the default, including the binary forms `min(A,B)` and
`max(A,B)`. Numeric NaNs are omitted, with an all-NaN result remaining NaN.
This fact was checked against the primary documentation; it was not checked by
executing MATLAB in this environment.

NumPy `minimum`, `maximum` and `clip` propagate NaN and therefore are not general
substitutes for these MATLAB expressions. Binary `fmin` and `fmax`, preserving
the original nesting order, reproduce the relevant behavior. For example,
`max(min(NaN,W),0)` returns W when W is positive, whereas
`min(max(NaN,0),W)` returns zero.

A reachable mismatch was found in the annular evaporation initializer:
`max(0,diff(X)./diff(XEQ))`. If both quality differences are zero, MATLAB turns
the quotient NaN into zero before the subsequent nonfinite-to-one cleanup.
The original Python `maximum` allowed NaN through and the cleanup changed it
to one. In ordinary adiabatic cells the wall heat flux is zero so this does not
change their evaporation source; it remains a translation error. The owner
replaced the corresponding binary operations in `threefield.py` and
`annular.py` with `fmin`/`fmax`, retaining the model's existing bounds and
nonfinite cleanup. No alternate physical correlation was introduced.

The audit also identified NaN-omitting reduction semantics in nested secant
and entrainment convergence checks. A MATLAB `max(abs(residual),[],'all')`
can omit a failed component if another component is finite. Source stopping
semantics and the Python acceptance diagnostics must be kept distinct: a
nonfinite force or iterate must not be presented as a trustworthy converged
solution even if the original reduction would have omitted it. This was
reported to the owner for the corresponding reduction and diagnostic review.
The outer three-field sweep already rejects nonfinite primary states before
its temporal maximum reductions. `numerics.py` contains no binary min/max
translation; its explicit NaN interpolation fallback follows the source.

The saved six-variant evidence above predates this missing-value patch and
retains hashes identifying the exact code run. It has not been overwritten.
