# Mixture translation audit, 2026-11-14

Scope: independent comparison of the native mixture implementation with the
preserved OpenSTREAM source at `a614c7173822a93c1e64ac28d1541cbac028cbd8` and
its recovered approved TUTORIAL1 mixture archive. No governing equation or
numerical implementation was changed during this audit.

## Executed independent verification

Run `.venv\Scripts\python.exe tools\audit_recovered_mixture.py --output NEW_REPORT.json`. The script
reads the original archive and the fresh native run in
`outputs/mixture-baseline-recovery/native-before`; it does not call native
mixture/phase methods to construct the reference W/U/H arrays. It writes
a new JSON file and refuses to overwrite an existing one. `--archive` and
`--native` select other paths explicitly. The executed report including
independent global balances is
`outputs/mixture-baseline-recovery/independent-audit-02.json`; its earlier
version remains preserved as `independent-audit.json`.

All nine original W/U/H comparisons passed at relative tolerance `1e-8` and
absolute tolerance zero. The largest observed relative difference was
`6.222142509110722e-13` for vapor mass flow. The four exactly zero archived
vapor-flow entries remained exactly zero in Python. Selected absolute errors:

| Quantity | Maximum absolute difference |
| --- | ---: |
| Mixture W | 1.38778e-16 kg/s |
| Mixture H | 9.31323e-10 J/kg |
| Mixture U | 5.25802e-13 m/s |
| Liquid U | 8.41993e-13 m/s |
| Vapor H | 7.17118e-8 J/kg |
| Cached mixture density | 2.94449e-11 kg/m3 |

The original archive SHA256 remains
`43311c4c2ec3440cc3366f94df1216b425d4270268887b7fb7bf921c0fb9ccb0`.
All compared scalar fluid constants agree to relative error at most
`1.03818e-11` (HMIN, a property-validity limit). The saturated densities agree
within relative errors `1.80e-15` and `1.68e-14` for liquid and vapor.
These comparisons establish this saved-case agreement; they do not establish
experimental validation or universal mixture-branch equivalence.

Independent checks on the archived arrays recover exactly 87,500 W from the
discrete wall heat flux. The largest mass-flow departure from 0.07 kg/s is
7.90175e-10 kg/s. Outlet minus inlet enthalpy flow is 87,500.0008886872 W,
giving a global steady energy-flux defect of 8.88687e-4 W, or 1.01564e-8
relative to the input heat. This flux balance uses both actual endpoint mass
flows, not an assumption that the small pseudo-time mass residual is exactly
zero. The independent steady outlet-enthalpy target is 2,389,400 J/kg;
the saved value is 2,389,399.9857234764 J/kg. Pressure and density remain
positive; saved vapor quality and void fraction remain in [0,1]. These are
conservation/feasibility checks, not comparisons with measured experiments.

## Authoritative regression policy

`upstream/tests/integration/SolverIntegrationTest.m:560` defines the regression
comparison. At the first stored physical state it compares W [kg/s], U [m/s], and
H [J/kg] for `mixture`, `mixture.liquid`, and `mixture.vapor`. The relative
tolerance is `1e-8`; no absolute tolerance is supplied. Exactly zero reference
values therefore require exactly zero native values. Pressure, void fraction,
cached density, pseudo-time arrays, and independent balances are useful
supplemental checks, but should not be represented as the nine original tests.

The case selects model TUTORIAL1, options DEFAULT, geometry TUTORIAL1, and
`tutorial1.inp`: 100 axial cells, 5.5 m channel length, 6 MPa system/inlet
pressure, 0.07 kg/s inlet mass flow, 1,139,400 J/kg inlet specific enthalpy,
87,500 W total heat input, 6.0821e-5 m2 coolant area and 0.0276 m wetted
perimeter. The initial model defaults are SATURATED properties, HOMOGENEOUS
void fraction, and EQUILIBRIUM thermal behavior.

## Stored-state method reconstruction

The U and phase W/H quantities are methods rather than independent saved arrays.
For this case, they can be evaluated from the archived W, H, rho, x, xeq, vf,
AREA, HF, HG, RHOF, and RHOG without calling CoolProp or executing a solver.
The resulting arrays must be identified as evaluations of pinned-source methods
on recovered state, not as directly stored arrays.

- Mixture U: `(W / rho) / AREA`; source `Mixture.m:422`.
- Vapor W: `x * W`; liquid W: `(1-x) * W`.
- Vapor U: `(Wv / AREA) / vf / RHOG`, replacing only NaN with mixture U;
  source `Vapor.m:108`.
- Liquid U: `(Wl / AREA) / (1-vf) / RHOF`, replacing NaN or `1-x < 0.01`
  with mixture U; source `Liquid.m:107`.
- Vapor H for EQUILIBRIUM: let `q = min(x, xeq)` and evaluate
  `(H-(1-q)*HF)/q`, replacing NaN or Inf with HG; source `Vapor.m:120`.
- Liquid H: evaluate `(H-x*Hv)/(1-x)`, apply MATLAB's elementwise
  `min(result, HF)`, then replace NaN or `1-x < 0.01` with HF;
  source `Liquid.m:123`.

Phase object references must identify the correct parent mixture. The source
`Mixture.m:2844` copy override reconstructs both phase objects with references
to the copied mixture. Identifying arrays by similar numerical values would
not establish the correct reference graph. The decoded phase.mix links were
checked by Python object identity and both identify the physical mixture.
FluidProperties and InputSet are MATLAB value classes, so their decoded
copies are distinct objects; their scalar properties and effective inputs
were compared by value and agree with the containing solver's copies.

## Findings outside the active baseline

The native `src/openstream/fields.py:579` Vapor.H uses one `isfinite` fallback
for both MRM and other models. Upstream `Vapor.m:131-143` replaces only NaN for
MRM, but both NaN and Inf for the other models. Consequently an infinite MRM
weighted vapor enthalpy would remain infinite upstream but become HG in the
native method. This branch is inactive for TUTORIAL1, and the audit has not
established that a valid MRM calculation can produce such an infinite value.
It is a translation difference, not a proposed physical-model correction.
It remains pending a targeted branch fix/test; no baseline evidence justifies
changing the governing equations or tolerances.

## Floating-point evaluation order

The native Mixture.U currently evaluates `(W / AREA) / rho` while MATLAB
evaluates `(W / rho) / AREA`. Native PHI2F also multiplies by FW before dividing
by FWL, whereas MATLAB groups `FW/FWL`. These are algebraically equivalent
but can differ by roundoff. The recovered baseline comparisons pass unchanged;
neither difference required a numerical implementation change for this case.

## Archive/source history

The archive was first added by commit
`1ca3733f5128b0bdb509ec29d15db8d721b63aec` on 2026-08-24. Its header creation
date is 2026-08-23. The archive-add commit is not proof of the producing commit,
MATLAB release, or CoolProp version.

A Git comparison between that commit and the preserved source found no change
to mixture solve.m or the baseline phase/mixture governing formulas. Changes
include plotting APIs and moving inputSet into the base field class. Model
defaults for KLOC, KLOSS, KBLOCKRATIO, and KTUNING changed from duplicate zeros
to a single zero; CBTKEFFECT changed its scalar default declaration. Other
changes concern dimensions of parameters used by other frameworks. The actual
saved input graph was inspected. KLOC, KLOSS, KBLOCKRATIO, and KTUNING do contain
two zeros in the archive and one in the native case. These duplicate zero
local losses have no pressure-loss contribution: KIDX maps each zero position
to the same inlet node, and assigning zero KLOSS twice leaves the same zero
loss array. Duplicating a zero-position column in KDIST also leaves its
minimum-distance reduction unchanged. KBLOCKRATIO and KTUNING are
inactive for this mixture case. The only other effective value differences
are the capitalization of interpolation names (`next`/`NEXT`,
`linear`/`LINEAR`), normalized by the Python interpolation routine. MATLAB
row/column vectors were compared with explicitly normalized Python vector
orientation, preserving element order. CBTMULT was separately inspected as
the serialized function `@(z)1`, never executed. Its serialized matlabroot
path contains `R2024b`; this is an archival runtime hint, not a complete
producer version record.
