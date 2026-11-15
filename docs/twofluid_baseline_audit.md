# Two-fluid archived baseline verification

Date: 2026-11-14. The original TUTORIAL1 two-fluid baseline has been recovered
without MATLAB and compared with the fresh native run. All six phase W/U/H
profiles pass the original `rtol=1e-8`, `atol=0` policy, including exact zeros.
All 15 initialization states pass the same six comparisons. The embedded
mixture precursor also passes its nine profiles and ten initialization states.
No two-fluid numerical implementation or governing equation was changed.

This establishes agreement with the saved case. It does not establish all
closure, transient, boundary or API parity, nor experimental validation.

## Preserved reference and executed evidence

- Original archive: `upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/tutorial1_TwoFluidSolver.mat`.
- SHA256: `40f0c9a8f080d6ffe3887947dc5794eb756b5fa0e2ce650ff37a88003e69798d`.
- Recovered reference: `reference_exports/recovered-twofluid-01/`.
- Fresh native run: `outputs/baseline-parity-01/TwoFluidSolver/`.
- Independent report: `outputs/baseline-parity-01/twofluid-independent-audit.json`.
- Recovery and direct-array checks: `tools/test_recovered_twofluid.py`, **7 passed**, one mat-io import-time pandas deprecation warning. No decoder warning occurred.

The six phase fields are directly saved arrays, unlike the mixture's phase
accessor methods. The recovered NPZ changes only the explicit layout from
MATLAB node-column state arrays to Python `(time,node)` arrays. No interpolation,
fitting, solver execution or CoolProp evaluation constructs these reference
values. Raw arrays retain their MATLAB dimensions in `raw_arrays.npz` and named
object/property paths in `object_graph.json`. The embedded precursor is labeled
as part of this two-fluid archive, not as a separate standalone mixture file.

All effective inputs are checked. The only differences are the previously
documented duplicate-zero defaults for KLOC/KLOSS/KBLOCKRATIO/KTUNING and
capitalization of interpolation names. These do not change this case's physics.
The MATLAB function descriptor `@(z)1` is inspected, never executed.

The baseline is 6 MPa, 0.07 kg/s, 87,500 W, 5.5 m length, 100 cells, inlet
enthalpy 1,139,400 J/kg, channel area 6.0821e-5 m2 and perimeter 0.0276 m.
The exact producing source/CoolProp versions remain unknown. No fresh MATLAB
run or experimental comparison was performed.

## Numerical comparison

| Direct stored profile | Maximum absolute error | Maximum relative error at nonzero reference |
|---|---:|---:|
| Liquid W | 1.24900e-16 kg/s | 2.60557e-15 |
| Liquid U | 3.87246e-13 m/s | 2.28908e-14 |
| Liquid H | 3.95812e-9 J/kg | 3.33096e-15 |
| Vapor W | 7.45931e-17 kg/s | 5.75239e-14 |
| Vapor U | 5.36460e-13 m/s | 4.14420e-14 |
| Vapor H | 9.31323e-10 J/kg | 3.34456e-16 |

All 606 physical-state values pass. The one exactly zero physical vapor-flow
entry matches exactly. All 9,090 initialization values pass, with maximum
relative difference 6.22214e-13. These comparisons use every stored node and
state; none is discarded or remeshed.

Reference initialization spans pseudo-time 0 through 14 s. The source strict
point and temporal stopping conditions all pass. Largest final phase point
increments are 1.64939e-8 kg/s, 8.25587e-5 m/s and 0.0989828 J/kg against
limits 0.001 kg/s, 0.0001 m/s and 0.1 J/kg. Largest final temporal changes are
7.34108e-8 kg/s, 0.000247607 m/s and 0.751237 J/kg against limits
0.001 kg/s, 0.001 m/s and 1 J/kg. The detailed per-phase records and all
iteration counts are retained in the manifest.

The raw object graph confirms the source's shallow-copy behavior: all 30
initialization phase objects reference the group containing physical time-zero
liquid and vapor objects. The physical liquid/vapor handles identify each other
through the same group, and that group identifies the proper mixture precursor.
The native translation intentionally retains these relationships.

## Physical inconsistency reproduced from the MATLAB archive

Using archived SATURATED densities, compute independently:

`A_occupied = W_liquid/(rho_liquid*U_liquid) + W_vapor/(rho_vapor*U_vapor)`.

Each term has units m2. The largest discrepancy is at z=0.22 m:

- Specified channel area: 6.0821e-5 m2.
- Archived occupied area: 8.579173488043905e-5 m2.
- Relative discrepancy: **41.0561070690042%**.
- Native discrepancy: **41.0561070690021%**.
- Archived outlet discrepancy: 3.46731185785%.

Thus this steady area inconsistency is present in the original MATLAB-produced
state. It is not introduced by the Python translation. Normalizing phase void
fractions to sum to one does not enforce the absolute channel area constraint.
No pressure, velocity, closure or governing equation was adjusted to hide it.

The archived outlet total-flow defect is -3.07613416156e-7 kg/s and the outlet
enthalpy-flux excess over supplied power is +30.04966312334 W. These agree with
the previously recorded native results. The stronger 43.3609% transient area
failure is a separate native transient finding; this steady archive comparison
does not establish whether that transient result agrees with MATLAB.

Tests that assert preservation of this known failure are regression checks,
not declarations of physical validity. A future model correction must be a
separate documented change from this compatibility port.

## Reproduce

Use new output names and run from the project directory:

```powershell
.\.venv\Scripts\python.exe tools\recover_twofluid_reference.py --output reference_exports\twofluid-repeat
.\.venv\Scripts\python.exe -m openstream sample --framework twofluid --output outputs\twofluid-repeat --quiet
.\.venv\Scripts\python.exe tools\audit_recovered_twofluid.py reference_exports\twofluid-repeat outputs\twofluid-repeat --output outputs\twofluid-repeat-audit.json
.\.venv\Scripts\python.exe -m pytest tools\test_recovered_twofluid.py -q
```

The solver CLI returns exit status 3 for this known physical-consistency
failure while retaining the numerically converged results. The independent
comparison returns zero when the original core comparisons pass. The test
using the fresh checkpoint has explicit fixture paths; it is not silently
skipped when the archived fixtures are unavailable.
