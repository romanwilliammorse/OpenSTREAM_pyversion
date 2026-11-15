# Two-fluid implementation and verification record

The native implementation is in `src/openstream/twofluid.py` and `tf_fields.py`, translated from upstream `+Solvers/+TwoFluid` at commit `a614c7173822a93c1e64ac28d1541cbac028cbd8`. It uses the actual solved mixture precursor, as the MATLAB implementation does. It does not substitute a mixture result for the two-fluid calculation.

**Status:** the TUTORIAL1 archived MATLAB baseline is verified: all six directly stored phase W/U/H profiles pass the original `rtol=1e-8`, `atol=0` comparisons, as do all 15 initialization states and the embedded mixture precursor. The reference was recovered without MATLAB; no two-fluid equations or numerical implementation changed. See [twofluid_baseline_audit.md](twofluid_baseline_audit.md) for the recovered reference, fresh native run, convergence, object relationships and limitations. Other cases, closure combinations and transients remain numerically unverified against MATLAB. Experimental validation remains unperformed. The steady baseline's physical area-closure inconsistency is also present in the original MATLAB archive; baseline agreement does not make it a physically validated channel solution.

## Equations and numerical algorithm

Liquid and vapor each retain independently solved mass flow W [kg/s], velocity U [m/s], and specific enthalpy H [J/kg]. The solver advances their six transport equations sequentially: liquid mass, vapor mass, liquid momentum, vapor momentum, liquid enthalpy, vapor enthalpy. Axial differencing, backward-Euler time terms, underrelaxation, point criteria, pseudo-time criteria, and the original phase-flow threshold of 0.001 kg/s are preserved.

The mixture precursor supplies the pressure gradient, wall shear, wall heat, wall boiling partition, equilibrium quality, annular transition, and relaxation times. The combined two-fluid field calculates total flow, enthalpy, density, and velocity from phase data, while retaining the source's prescribed precursor quantities. In particular, it does **not** replace precursor XEQ with an equilibrium quality inferred from the evolved two-fluid enthalpy.

Supported phase momentum selectors are MIXTURE, SLIP, and FULL. FULL preserves the source's velocity bounds of zero to 1.5 times the corresponding precursor phase velocity, and freezes velocity when the old point-iteration phase flow is at most 0.001 kg/s. The enthalpy source also becomes zero below that flow threshold.

Implemented closures include constant interfacial lengths; DISPGAS2DISPLIQ interfacial area; AREAMEAN, SCALED, and DRIFT relative velocity; CONSTANT, STOKES, VISCOUS, and DISTORDED drag for both dispersed phases; CONSTANT, RANZMARSHALL, and RELAXATION interfacial heat/mass exchange; and BULK/SATURATED transferred enthalpy.

API:

```python
from openstream.twofluid import TwoFluidSolver

solver = TwoFluidSolver(input_set).solve()
liquid, vapor = solver.liquid[-1], solver.vapor[-1]
print(solver.STATE.name, solver.converged)
print(solver.balance_diagnostics)
solver.save("outputs/twofluid_run")
```

`converged` describes successful numerical iterations plus finite, positive-flow state bounds; it does **not** assert area closure or physical validation. The independent `balance_diagnostics` must also be inspected. Its area metric uses the solved absolute phase flows and velocities, not merely the normalized void-fraction formula.

## Actual executed original-input runs

All runs below use the original `models.inp`, `options.inp` DEFAULT, `geom.inp` TUTORIAL1, and `tutorial1.inp`. The total imposed heat is 87,500 W; inlet flow is 0.07 kg/s. Saved summaries: `outputs/twofluid_variant_checks.json`.

| Model input | Numerical convergence | Pseudo steps | Outlet mass defect [kg/s] | Outlet energy defect [W] |
|---|---:|---:|---:|---:|
| TUTORIAL3A | Yes | 13 | −6.5849580e−8 | +34.3567397 |
| TUTORIAL3B | Yes | 14 | −3.0761342e−7 | +30.0496631 |
| TUTORIAL1 | Yes | 14 | −3.0761342e−7 | +30.0496631 |

Saved full TUTORIAL3B arrays, units, inputs, convergence log, and plot are under `outputs/twofluid_tutorial3b/`. These are Python outputs, not reference data.

### Physical area closure fails in TUTORIAL3B

Independently calculate the occupied area:

`A_occupied = W_liquid/(rho_liquid U_liquid) + W_vapor/(rho_vapor U_vapor)`.

The result differs from the specified channel AREA by up to **41.0561%** (at z = 0.22 m) and **3.46731%** at the outlet. These are incompatible simultaneous absolute phase flows, velocities, densities, and channel area. The source's normalized slip-based VF makes liquid and vapor fractions sum to one, but that algebraic normalization does not ensure `A_occupied == AREA`.

Inspection identifies no pressure-correction step enforcing this constraint in the source; it instead supplies pressure from the precursor. The later TUTORIAL1 archive recovery confirms the same steady inconsistency directly in MATLAB-produced phase arrays: maximum occupied-area error **41.0561070690042%** at z=0.22 m, versus **41.0561070690021%** in the fresh native run. This particular steady error is therefore reproduced upstream behavior, not introduced by the Python translation. Its model-level cause still requires a separate review before any equation change. No fresh MATLAB execution occurred. The port preserves the source equations and exposes this failure rather than adjusting velocities or pressure to hide it. The separately observed **43.3609% transient** area discrepancy has not been compared with a MATLAB transient reference; the steady result does not establish transient equivalence.

The saved-array diagnosis in `tools/diagnose_twofluid_area.py` independently rewrites the source void formula as `VF = A_v,occupied / (A_l,occupied + A_v,occupied)`. On the original native sample the two forms agree to 2.22e-16. Thus unity of normalized fractions is not a test of absolute occupied area. At the worst node (z=0.22 m), occupied area is 8.57917e-5 m² against the specified 6.0821e-5 m²; reconstructing phase mass flows from the specified area and normalized fractions multiplies both actual phase flows by 0.708938. This is an inconsistency, not a corrected prediction. Three nodes are at the source vapor mass cutoff and eight at the vapor upper-velocity bound; those counts alone do not establish causation. Evidence and inspected plot: `outputs/verification/twofluid-area-01/`.

Reproduce without re-solving: `.\.venv\Scripts\python.exe tools\diagnose_twofluid_area.py outputs\cli-twofluid-01 --output outputs\twofluid-area-repeat`. The output directory must be new. A full default-progress CLI run completed and saved `outputs/cli-twofluid-01`; CLI tests verify that physical failure returns status 3 and numerical failure status 2.

### Independent energy-defect diagnosis

At the same instantaneous state, translated source terms satisfy

`HTOT_l + HTOT_v + H_l MTOT_l + H_v MTOT_v = LHGR`

to approximately 7.28e−12 W/m for the default TUTORIAL3B run. Interfacial mass and conservative interfacial momentum sources also cancel in automated tests.

The upstream method separately differences mass flow and *material specific enthalpy*. The discrete product rule therefore does not reproduce a conservative total enthalpy-flux difference exactly. At converged steady state its leading global energy defect is

`−Σ_cells [ΔW_l ΔH_l + ΔW_v ΔH_v]` [W].

This term is +30.8868818 W in the default TUTORIAL3B result, close to its observed +30.0496631 W defect; the remaining difference depends on point/pseudo-time convergence and suppressed source terms.

The following stricter numerical-control runs retained the same governing model. The source's original reference results were not changed, and no tolerance was relaxed. Controls were ERRORW = SSCONVW = 1e−10 kg/s; ERRORU = SSCONVU = 1e−7 m/s; ERRORH = SSCONVH = 1e−5 J/kg; ERRORP = SSCONVP = 1e−3 Pa; MAXITER = 200; SSMAXITER = 80. Saved evidence: `outputs/twofluid_mesh_checks.json`.

| Cells | Numerically converged | Mass defect [kg/s] | Energy defect [W] | Discrete product term [W] | Difference [W] |
|---:|---|---:|---:|---:|---:|
| 50 | **No: point convergence failed** | −4.1172702e−5 | +35.1543823 | +63.6372324 | −28.4828501 |
| 100 | Yes | −7.6462031e−12 | +30.8877714 | +30.8877926 | −2.11192e−5 |
| 200 | Yes | −1.2889079e−11 | +15.2088336 | +15.2088693 | −3.57184e−5 |

The two successful finer-grid cases show approximately first-order reduction of this energy defect and agreement with the discrete-product derivation. This explains a numerical consequence of the preserved algorithm; it does not validate the physical two-fluid solution or the failed coarse-grid run.

## Source semantics and explicit unsupported paths

- **Shallow MATLAB phase copying:** Liquid and Vapor inherit default `matlab.mixin.Copyable` with no `copyElement` override. Their pseudo-time copies share the `.mix` handle, which still points to physical time-zero liquid/vapor fields. The port deliberately preserves this object graph while copying W/U/H/ITR arrays independently. Thus aggregate quantities during initialization can read the original physical phases rather than the current pseudo-time phases. This is documented and tested, not silently repaired.
- **Multiwall FULL momentum:** source wall-force terms are wall vectors but U is scalar per node. This path raises `NotImplementedError`. Multiwall MIXTURE/SLIP equation paths exist but have not received end-to-end verification.
- **Relative velocity naming mismatch:** LOCRELVEL enumeration declares SIMPLE, but the implementation has no SIMPLE equation; it contains a FLOWREGIME branch that the enumeration disallows. SIMPLE raises an explicit unsupported error and FLOWREGIME is rejected by input validation. The port does not guess which was intended.
- **Regime subset dimensions:** `Liquid.FLOWREGIME(zIdx)` allocates a full-mesh result despite taking a subset. Full-mesh diagnostics are provided; subset calls raise an explicit error pending a documented correction.
- **Vapor diagnostic typos:** upstream `Vapor.X` always resets requested indices because its argument-count test is `nargin < 3`; upstream `Vapor.S` omits a required liquid-method argument. Full-domain `vapor.X()` and correct `liquid.S(vapor, index)` are available; the defective forms raise explicit errors.
- The source passes a phase's own enthalpy into the *other phase's* property functions in relative Reynolds/Nusselt calculations. This choice is retained, including the fluid layer's saturation clamping.

## Automated checks

`tests/test_twofluid.py` checks instantaneous mass/energy exchange cancellation, conservative interfacial momentum cancellation, pressure/gravity dimensions, prescribed-slip area/velocity identities, independent copied arrays plus intentionally shared mixture links, both original TUTORIAL3A/B runs, and unsupported options. Tests do not assert experimental accuracy or exact global conservation where the actual solver fails it.
