# Mixture comparison with the recovered MATLAB baseline

Verified on 2026-11-14. The native TUTORIAL1 mixture calculation passes all nine
upstream W/U/H regression comparisons against the preserved MATLAB-produced
archive. All 101 nodes were compared at the original relative tolerance
`1e-8`, absolute tolerance `0`. All nine profiles also pass across the ten
stored initialization states. This is agreement with this archived case,
not proof of every output, every mixture option, or experimental validation.

The numerical implementation was unchanged. Corrections were required in the
reference-reading tools: decode MCOS enumerations correctly and retain the wall
axis for one-wall diagnostic arrays. No governing equation, closure, numerical
tolerance, original reference, or upstream source file was changed.

## Evidence and provenance

- Original archive: `upstream/tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/tutorial1_MixtureSolver.mat`.
- Archive SHA256: `43311c4c2ec3440cc3366f94df1216b425d4270268887b7fb7bf921c0fb9ccb0`, unchanged after recovery.
- Portable reference: `reference_exports/recovered-mixture-02/`. The manifest includes units, original inputs, fluid constants, convergence, archive hashes and reader versions. `raw_arrays.npz` and `object_graph.json` preserve the original dimensions and named property/reference graph.
- Fresh native run: `outputs/mixture-baseline-recovery/native-before/`. The name records that this run preceded the comparison; it remains the accepted run because no solver corrections were needed.
- Final comparison and figures: `outputs/mixture-baseline-recovery/comparison-03/`.
- Independent source-formula audit: `outputs/mixture-baseline-recovery/independent-audit-02.json`.
- Executed checks: `outputs/mixture-baseline-recovery/verification-tests.log` and `.xml`: **81 passed**, one import-time pandas deprecation warning in the optional reader. No archive-decoding warning occurred.

Ordinary SciPy loading exposes an opaque MATLAB object. The verification-only
`mat-io` reader resolves its class/property/object tables. It is installed in a
separate dependency directory, without changing normal solver dependencies.
The reader, reuse investigation, BSD license and narrowly scoped enumeration
workaround are documented in `tools/REFERENCE_READER.md`.

W and H are directly stored. Mixture U and phase W/U/H are methods in MATLAB;
these seven profiles were reconstructed algebraically from the recovered state
and recovered fluid constants using the preserved MATLAB source formulas.
The recovery does not call the native solver or CoolProp. A second independently
written calculation checks the method formulas and parent-object references.
This distinction is explicit in the manifest; method results are not described
as directly saved arrays.

The original producing source commit and CoolProp version are unknown. The
archive header dates it 2026-08-23; a serialized function path mentions R2024b,
which is a version hint rather than proof of the producing runtime. Source
formulas were checked against preserved commit
`a614c7173822a93c1e64ac28d1541cbac028cbd8`. No fresh MATLAB execution occurred.

## Case, convergence, and physical checks

The case uses original `models.inp` TUTORIAL1, `options.inp` DEFAULT,
`geom.inp` TUTORIAL1 and `tutorial1.inp`: 6 MPa system pressure, 0.07 kg/s inlet
flow, 1,139,400 J/kg inlet enthalpy, 87,500 W heating, 5.5 m length,
6.0821e-5 m2 area, 0.0276 m perimeter and 100 axial cells. Models are SATURATED
properties, HOMOGENEOUS void and EQUILIBRIUM thermal behavior. Properties use
prescribed system pressure, as in the source.

Recovered effective inputs agree with six disclosed representation/history
differences: four old duplicate-zero local-loss/annular defaults versus single
zeros, and capitalization of the two interpolation names. Zero local losses
have no pressure contribution; the annular parameters are inactive. The
comparator accepts only these specific zero-valued differences and rejects
changed flow, nonzero loss or function values. The serialized CBTMULT is
`@(z)1`; it was inspected without execution. Full details are in
`mixture_translation_audit.md`.

Both implementations retain ten initialization states from pseudo-time 0 to
9 s. The final reference point increments are 5.50847e-9 kg/s, 0.00605647 Pa
and 0.0991306 J/kg, below the original 0.001 kg/s, 0.1 Pa and 0.1 J/kg
thresholds. Final temporal changes are 9.94442e-9 kg/s, 0.0113892 Pa and
0.177841 J/kg, below 0.001 kg/s, 1 Pa and 1 J/kg. Iteration counts agree.

The original discrete heat normalization is retained: 63 heated downstream
nodes at 0.055 m spacing give 3.465 m discrete heated length, heat flux
914,946.56712048 W/m2 and integrated power exactly 87,500 W.

| Independent check | Result |
|---|---:|
| Outlet H versus steady target | 2,389,399.98572348 versus 2,389,400 J/kg |
| Pressure drop | 156,497.61205468 Pa |
| Maximum departure from inlet mass flow | 7.90175e-10 kg/s |
| Native discrete mass residual | 5.15104e-13 kg/s |
| Native advective enthalpy residual | 7.42148e-10 W/m |
| Native discrete momentum residual | 0.000130212 Pa |
| Archived boundary enthalpy-flux imbalance | 0.000888687 W, relative 1.01564e-8 |
| Minimum pressure and density | 5.843502 MPa; 40.62416 kg/m3 |
| Outlet vapor quality and void fraction | 0.748393784; 0.986515413 |

Mass partition, inlet conditions, positive pressure/density, bounded quality/void
and initialization-to-physical transfer pass. The boundary-flux balance uses
`Wout*Hout-Win*Hin`; the existing native steady diagnostic uses
`Win*(Hout-Hin)`. Their small difference is due to the finite steady mass
departure, not a discrepancy between the archives. Neither substitutes for a
general total-energy validation. Previous mesh/time sensitivity and transient
energy limitations remain in `VERIFICATION.md`; they were not erased by this
steady regression result.

## Numerical agreement and remaining differences

| Profile | Maximum absolute error | Maximum relative error, nonzero reference |
|---|---:|---:|
| Mixture W | 1.38778e-16 kg/s | 1.98254e-15 |
| Mixture U | 5.25802e-13 m/s | 4.13057e-14 |
| Mixture H | 9.31323e-10 J/kg | 3.89773e-16 |
| Liquid W | 1.52656e-16 kg/s | 3.15182e-15 |
| Liquid U | 8.41993e-13 m/s | 4.15784e-14 |
| Liquid H | 3.49246e-9 J/kg | 2.87700e-15 |
| Vapor W | 1.38778e-16 kg/s | 6.22214e-13 |
| Vapor U | 4.61853e-13 m/s | 4.14420e-14 |
| Vapor H | 7.17118e-8 J/kg | 2.57531e-14 |

All 909 physical-state core values pass, including four exact reference zeros.
The supplementary initialization comparison checks 9,090 core values; its
largest relative error is 7.18944e-13.

Of 48 additional diagnostic profiles, 34 pass the same strict relative-only
policy. **Fourteen fail**, in both physical and initialization comparisons:
DP.Acc_s/Acc_t/Acc_z, DPSUM.Acc_s/Acc_t, ITR.DH/DP/DW and
MDER.H/H_t/H_z/U/U_t/U_z. They remain failures in the JSON report. This extra
policy is not an upstream acceptance requirement for these diagnostics.

The largest physical-state differences by diagnostic family are 1.472e-10 Pa
for pressure increments, 1.630e-9 J/kg for enthalpy iteration increments,
3.446e-7 J/(kg s) for enthalpy material derivatives and 6.596e-11 m/s2 for
velocity material derivatives. Some reference values are exactly zero or near
zero; tiny absolute errors therefore fail a zero-absolute relative criterion.
Cancellation and small property/evaluation-order differences are consistent
with this pattern, but bitwise diagnostic equivalence is not established.
No tolerance was increased to make these pass.

An inactive MRM infinity-handling translation difference is documented in
`mixture_translation_audit.md`. It does not affect this equilibrium baseline
and remains a separate follow-up. The other three frameworks were not translated,
modified, or compared in this checkpoint.

## Reproduce on this Windows machine

Use unused output directory names; all reference exports and comparison reports
refuse overwrite. Run from the project directory:

```powershell
.\.venv\Scripts\python.exe -m pip install --target .venv\reference-reader -r tools\requirements-reference.lock
.\.venv\Scripts\python.exe tools\recover_mcos_reference.py --output reference_exports\mixture-repeat
.\.venv\Scripts\python.exe -m openstream sample --framework mixture --output outputs\mixture-repeat --quiet
.\.venv\Scripts\python.exe tools\verify_recovered_mixture.py reference_exports\mixture-repeat outputs\mixture-repeat outputs\mixture-repeat-comparison
.\.venv\Scripts\python.exe tools\audit_recovered_mixture.py --native outputs\mixture-repeat --output outputs\mixture-repeat-independent.json
.\.venv\Scripts\python.exe -m pytest tools\test_recover_mcos_reference.py tools\test_recovered_mixture_comparison.py tests\test_inputs.py tests\test_properties.py tests\test_fields.py tests\test_solver.py -q
```

The reader installation is a one-time verification-tool setup and is already
complete on this machine. The two actual-reference comparator tests use the
preserved checkpoint paths; they require this workspace's recovered fixtures.
Source/runtime files and the pre-existing installation are unchanged.

Historical checkpoint: this mixture verification was shown to Roman, who then
approved continuation. All four baseline comparisons are now complete; see
ALL_BASELINES_VERIFICATION.md. The earlier 1/4 metric and approval pause are
superseded. These fractions do not measure full-software completeness.
