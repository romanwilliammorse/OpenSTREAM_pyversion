# Four-field translation and verification status

`openstream.FourFieldSolver` translates the pinned upstream four-field constructor, axial sweep, base-film and disturbance-wave classes. It reuses the native mixture precursor and translated annular/drop closures. No MATLAB, MATLAB Engine or Octave is called during native operation.

```python
from openstream import InputSet, FourFieldSolver

solver = FourFieldSolver(InputSet.official_sample()).solve()
print(solver.converged, solver.diagnostics())
solver.save("outputs/my_fourfield_case")  # new directory required
base = solver.film[0].base
wave = solver.film[0].wave
```

W [kg/s], U [m/s], H [J/kg] and wave FREQUENCY [Hz] are `(node,wall)` arrays. Drop arrays are `(node,)`. Axial positions Z are metres; physical and pseudo times are seconds. The film's dependent W is base.W+wave.W; U is the source residence-inventory weighted value `W/(Wbase/Ubase+Wwave/Uwave)`. Its H is base.H. The physical model retains saturated film/drop enthalpy and prescribed pressure/vapor from the mixture precursor; it is not a replacement independent four-field energy/pressure solution.

Coefficient units are not uniform within every array. `WAVEDRAGCOEF[0]` is a length in metres in `Re = rho_v * (U_v-U_wave) * WAVEDRAGCOEF[0] / mu_v`; its remaining entries are dimensionless. `RELAXTB` and `RELAXTW` are seconds. `WAVEMIXCOEF` is dimensionless: dividing W/perimeter [kg/(s m)] by it and wave width [m] yields a mass flux [kg/(s m²)]. Wave momentum forces are N/m²; droplet forces are N/m³, with the density/thickness factors in the respective momentum equations preserving m/s².

## Implemented and tested scope

Actual source branches are translated for OAFFILMSPLIT RATIO/EQUILIBRIUM; BASEEQTHICK RISO/MFVAL/COEFS/YPLUS; MOMENTBASE ALGEBRAIC/EQUILIBRIUMS/EQUILIBRIUM/FULL/FULLNOP; MOMENTWAVE ALGEBRAIC/EQUILIBRIUM/FULL; WAVEBASEINT VAPORSHEAR/VAPORSHEARDROPMASS; WAVEFREQUENCY EQUILIBRIUM/RELAXATION; EQSTROUHAL RISO/SAWAI/MFVAL/CUSTOM/CSTFREQ. Shared drop, deposition, entrainment and friction branches are described in the feature map. Translation status does not establish every branch combination is tested.

The unmodified official sample input (TUTORIAL1/DEFAULT/TUTORIAL1/tutorial1.inp) completed in eight pseudo-time steps. Final point iterations were converged, as were the source temporal criteria and the additional native wave-frequency check. Primary state was finite, masses nonnegative, velocities and frequency positive. The all-field mass partition error was 1.39e-17 kg/s.

The later 2026-11-14 archive comparison recovered the original MATLAB object without MATLAB. All nine original film/drop/wave W/U/H profiles pass at unchanged `rtol=1e-8`, `atol=0`; the actual base-film W/U/H and wave frequency also pass as four explicit supplementary checks. All nine initialization states pass those primary comparisons. The largest relative difference is 2.53961e-9 for wave velocity. Final archived point/temporal convergence passes, including actual wave `ITR.DF`; the additional frequency temporal check also passes. No numerical implementation or governing equation was changed. See [annular_reference_audit.md](annular_reference_audit.md) for source mapping, raw-state provenance, the independent audit and precise limits. This establishes the selected archived TUTORIAL1 agreement, not equivalence for every tutorial/closure/transient or experimental validation.

`tests/test_fourfield.py`: seven tests passed in the initial focused run. Checks cover the original-file sample, source cancellation of internal base/wave mass exchange and shear, dimensions, field mass partition, physical bounds, MATLAB NaN-boundary behavior, copy/handle semantics, independent frequency/nested-failure acceptance, invalid zero relaxation, portable outputs and retained dryout residuals. Two warnings arise from the source zero-slip wave-drag expression described below.

`tools/verify_fourfield.py` runs original TUTORIAL5A–E records from the preserved upstream inputs and retains actual convergence, warnings and physical diagnostics in `outputs/fourfield_tutorials/verification.json`, with NPZ/CSV/JSON and plots per case. No source input or numerical tolerance is modified. The original Tutorial 5 explicitly describes its closures as demonstrations rather than validated predictions; the native port carries the same limitation.

To reproduce the separate original transient workflow, use `.\.venv\Scripts\python.exe tools\verify_fourfield.py --cases F --output outputs\fourfield_transient_repeat`. Tutorial F means TUTORIAL5E plus `tutorial2_transient.inp`; there is no TUTORIAL5F model record. The output directory must not already exist.

All five original steady tutorial cases completed with finite/nonnegative primary masses, positive velocities/frequency, point convergence, frequency convergence and no nested closure failures:

| Original model | Pseudo steps | Final frequency change [Hz] | Maximum total mass partition error [kg/s] |
|---|---:|---:|---:|
| TUTORIAL5A | 8 | 0.0549634 | 1.39e-17 |
| TUTORIAL5B | 7 | 0.0468854 | 1.39e-17 |
| TUTORIAL5C | 7 | 0.0719217 | 1.39e-17 |
| TUTORIAL5D | 8 | 0 | 1.39e-17 |
| TUTORIAL5E | 8 | 0.0731868 | 1.39e-17 |

The saved TUTORIAL5A axial plot was visually inspected: axes, units, legends and subfield curves are legible. Enthalpy curves coincide because these fields use saturated liquid enthalpy. This is a rendering/usability check, not a check against MATLAB plot values.

The full original transient workflow also completed: TUTORIAL5E with `tutorial2_transient.inp`, 0–5 s at the unchanged 0.1 s step, 101 spatial nodes and 51 saved times. Initialization took eight pseudo steps; all 50 physical advances met their point criteria (maximum 16 iterations). Native STATE was SOLVEDCONVERGED and `.converged` was true. Independent checks of every saved time found zero nonfinite primary values, nonnegative mass flows, minimum velocity 0.75918 m/s, minimum frequency 13.3624 Hz and maximum total mass partition error 1.39e-17 kg/s. `outputs/fourfield_tutorial5f/verification.json` retains the checks and actual warnings. Both final axial and wave-frequency plots were visually inspected. The frequency steady flag describes initialization, not an assumption that a changing physical transient must be steady.

## Source issues retained and exposed

1. **Missing wave-frequency steady stopping check.** The source logs timeDFw but omits SSCONVFW from the stopping predicate. Native STATE preserves that predicate. Native `.converged` additionally requires the frequency criterion and absence of nested solver failures; this does not change arrays or continue iterations past the source stop.
2. **POSFILM modifies local equations near dryout.** The source clips wave W to zero then compensates base W and clips it. Native sample raw final pseudo-time mass residuals reach approximately 4.31e-4 kg/s for base and 4.24e-4 kg/s for wave. These are much larger than the point-change criterion converted by perimeter. A positive base alone does not mean its equation was unconstrained: zero wave flow can trigger base compensation. Diagnostics retain raw, wet and both-fields-positive annular residuals separately. Roundoff agreement of total partitions is bookkeeping and does not establish every local equation is satisfied.
3. **Zero-slip wave drag.** DRAGCOEF contains a Reynolds-number inverse square; FDRAG subsequently multiplies by squared relative velocity. At exactly zero slip this evaluates infinity times zero, yielding NaN, even though algebraic cancellation could yield a finite limit. The original full-momentum nested min/max then selects zero for a NaN trial velocity. The port retains this order and emits warnings. Replacing this with an analytic limit would be a model/numerical correction requiring a separately documented change and reference checks.
4. **MATLAB NaN handling.** Binary min/max default to ignoring NaNs. Native fmin/fmax retain this behavior, including `min(0/0,1)=1` in the dry-film split and the exact nesting order of onset and momentum bounds. Using NumPy minimum/maximum or clip would change boundary results.
5. **Copies and logging.** Base copy excludes ITR; wave copy excludes ITR but includes FREQUENCY. Film copy ignores `all`; original first-node states remain. The source initializes DFW but writes DF, so both names may appear. Pseudo-time base/wave `.mix` links remain the physical-time-zero precursor after film `.mix` replacement, matching source shallow-handle behavior.
6. **Upstream regression spelling.** Actual field property is `film.base`, whereas part of the upstream regression traversal refers to `basefilm`. Native API exposes `.base` and a convenience `.basefilm` alias; the portable exporter traverses `.base` explicitly to avoid silently omitting it.
7. **Onset deposition comment differs from implementation.** The four-field EQUIL comment says enhanced deposition is disabled, but its actual call is `drp.MDEP(zIdx)`, whose default enables enhancement. The port follows the executable source. Three-field EQUIL explicitly passes the disabled flag and is intentionally different. The default NONE enhancement makes no difference in the standard examples.

## Unsupported and unverified

The later independent inventory audit exposes a physical failure that is separate from the preceding numerical successes. The original steady sample has 11.2411% maximum occupied-area discrepancy in fully annular flow; the original transient reaches 15.5181%. In a fixed control volume from 2.31 to 5.5 m that remains annular at all stored times, transient mass storage plus outflow minus inflow reaches 0.00642295 kg/s (9.17564% of the inlet). Metadata now records `physical_consistency: false`, and CLI/audit runs return 3. Numerical `.converged` remains true because the equations and iterations are unchanged. Final evidence is `outputs/fourfield-transient-audited/TUTORIAL5F`; all 26+26+70+70 numerical arrays have identical dtype, shape and bytes to the earlier original run. Pre-annular fields are initialization quantities and are excluded from physical-domain acceptance.

The recovered MATLAB TUTORIAL1 state independently exhibits **11.2410517% maximum fully annular occupied-area discrepancy**, with 1.0737049% at the outlet. This specific steady inconsistency is therefore confirmed in the original stored result, rather than attributable solely to the native translation. The transient 15.5181% area discrepancy and 0.00642295 kg/s mass-storage defect still lack equivalent archived-reference evidence; their attribution remains unresolved. Passing the steady regression does not waive any of these physical failures.

Multiple-wall four-field calculations raise `NotImplementedError`: several source closures use linear `U(zIdx)` indexing while other terms are wall matrices, so a corrected multiwall interpretation cannot be silently substituted. Nonpositive RELAXTB, RELAXTW or WAVEMIXCOEF is rejected because the source divides by them. Upstream broken DROPDRAG=DISTORDED remains explicitly unsupported in the annular framework. Unsupported enum values fail input validation or branch dispatch.

Numerical equivalence beyond the selected TUTORIAL1 archived profiles is unverified. The MATLAB exporter is prepared but has not run in MATLAB, and the original archive's exact producing source/CoolProp runtime is not established. Four-field mesh/time-step sensitivity, all closure combinations, conservative transient momentum/energy validation and full upstream plotting-option parity remain unverified unless newer execution evidence is recorded elsewhere. Experimental validation has not been performed. Native convergence and source translation alone establish neither general equivalence nor physical validity.
