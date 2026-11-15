# Sawai entry 1: FourField source audit before matched replay

This is the pre-correction source audit. Its code anchors and statements about the original Python selection refer to the recorded pre-change files. The isolated correction and focused regression results are recorded at the end; they do not replace or rewrite the original calculation evidence.

Review date: 2026-11-15. Reviewed Python checkout: `178ac2b4152b31016dc8847aebab139de0d88d2d`; pinned MATLAB source: `a614c7173822a93c1e64ac28d1541cbac028cbd8`; database: `b48541e6438a92b4c0ddc83cf0ceda3f71a59b22`.

**One concrete precursor-selection difference was found.** During steady initialization, MATLAB's outer FourField sweep uses a copy of the physical-time-zero mixture, while Python `_advance` uses the aggregate film's copy of the final mixture initialization state. The source deliberately retains both objects. Their primary W/P/H values agree in the saved Sawai calculation, but their cached quality/void fraction and derived phase velocities do not. This establishes a difference in the translated object selection; it does **not** establish that this difference causes the observed point nonconvergence, or that any proposed correction reproduces MATLAB's Sawai results.

No numerical implementation, model, tolerance, acceptance ledger or saved calculation was changed for this audit. Work comprised source inspection, reading existing NPZ/JSON/MCOS files, array comparisons and a property-only CoolProp evaluation. No new solver execution or MATLAB execution was performed. A separate unchanged replay is needed before an isolated source-correction experiment.

## Frozen case and observed failure

Case directory: `outputs/validation/lecorre-2025-01/sawai-01-paper-tw020-n100-base`. This is Sawai entry 1, `A_G300`, with the author-confirmed wave relaxation time 0.2 s. The earlier companion variant uses 0.1 s and is not substituted here.

| Input or control | Frozen value |
|---|---|
| Mesh | 100 cells, 101 nodes; L = 1.648 m; dz = 0.01648 m |
| Geometry | Area 1.2566e-5 m²; one perimeter 0.012566 m; hydraulic diameter 0.004 m; angle 0° |
| Boundary condition | 2.95 MPa, 0.0037699 kg/s, 507550.5738 J/kg, 5127.0792 W |
| Wall lengths and relative powers | [0.4, 0.4, 0.424, 0.424] m and [1, 1, 0, 0]; heated length 0.8 m |
| Precursor models | THERMALNONEQ=EPRI, VOID=EPRI, TPFM=EPRI; SATURATED properties |
| Film/drop exchange | OAFENTRAINED=EQUILIBRIUM; DEPOSITION=OKAWA; ENTRAINMENT=OKAWA2003; DEPENHANCEMENT=NONE |
| Film structure | OAFFILMSPLIT=EQUILIBRIUM; BASEEQTHICK=RISO; WAVEMIXCOEF=2; RELAXTB=0.5 s |
| Momentum | MOMENTBASE=FULLNOP, MOMENTWAVE=FULL, MOMENTDROP=SLIP, DROPSLIP=1; WAVEBASEINT=VAPORSHEAR |
| Friction and bounds | VAPORFRIC=CONSTANT, VAPORFRICCST=0.005, THINFILMFRIC=TURBULENT; POSFILM=true |
| Thickness thresholds | THINFILMTHICK=1e-4 m; THINWAVETHICK=1e-5 m |
| Frequency | WAVEFREQUENCY=RELAXATION, EQSTROUHAL=SAWAI, RELAXTW=0.2 s |
| Iterations | MAXITER=100, SSMAXITER=30, SSTSTEP=1 s |
| Point tolerances | ERRORWF=1e-4 kg/(s m); ERRORUF=ERRORUD=0.01 m/s; ERRORFW=0.1 Hz |
| Relaxation | RELAXWB=RELAXWW=RELAXFW=0.5; RELAXUB=RELAXUW=0.2 |

The saved base run stops at pseudo-time 8 s with `STATE=INITIALSTEPCONVERGED`, but `converged=false`. Its final wave-flow increments are:

| Python index | MATLAB row | z [m] | abs(delta WL_wave) [kg/(s m)] | Equivalent abs(delta W_wave) [kg/s] | Iterations |
|---:|---:|---:|---:|---:|---:|
| 24 | 25 | 0.39552 | 0.0007676067362375749 | 9.645746247561366e-6 | 100 |
| 25 | 26 | 0.41200 | 0.0006608969629151584 | 8.304831235991882e-6 | 100 |
| 26 | 27 | 0.42848 | 0.0005390922720904800 | 6.774233491088973e-6 | 100 |

The mass-flow tolerance converted by the stored perimeter is 1.2566e-6 kg/s. These are iteration increments, not equation residuals or measurement errors. All other final point-increment maxima are below their original point thresholds: base flow 7.34043252721e-5 kg/(s m), base speed 0.000427330906 m/s, wave speed 0.00755708417 m/s, frequency 0.0657039082 Hz, and drop speed 0 m/s. The onset is Python index 23 / MATLAB row 24, z=0.37904 m.

The separate `sawai-01-paper-tw020-n100-tight` run has MAXITER=200 and tolerances reduced by ten, and stops at 10 s. It fails both wave-flow and wave-speed point criteria at the same three indices. It must not be confused with the base replay. Existing `tests/test_lecorre_runner.py:121` checks that the declared tight variant changes only numerical controls.

## Confirmed precursor-object distinction

Use P for `mixSolver.mixture(1)` (physical-time-zero precursor), S for `mixSolver.mixtureInit(end)`, and S_k for the per-pseudo-time copy of S. These names refer to objects, not an assumption that their values differ.

| Object or reference during initialization | MATLAB construction | Python construction | Finding |
|---|---|---|---|
| Aggregate `filmInit(k).mix` | Copy of S; `FourFieldSolver.m:245-250` | Deep copy of S; `threefield.py:42-47` | Same intended source |
| `dropInit(k).mix` | Same S_k as film; `FourFieldSolver.m:255` | Same `mix` assigned to film and drop; `threefield.py:47` | Same intended sharing |
| `filmInit(k).base.mix`, `.wave.mix` | Remain P after film copy | Explicitly rebound to `self.film[0].mix`; `fourfield.py:37-41` | Same intended source |
| Base/wave `.film` | Rebound to copied aggregate film; `Film.m:303-312` | Deep-copy cycle retains copied parent | Same intended ownership |
| **Outer sweep local `mix`** | **Copies of P; `solve.m:83`** | **S_k through `mix=film.mix`; `fourfield.py:194`** | **Different source object** |

MATLAB `Film.copyElement` shallow-copies the aggregate, copies its base/wave children and rebinds only their `.film` references (`upstream/+Solvers/+FourField/Film.m:292-314`). `initializeBaseAndWave()` with no other arguments returns without replacing existing children (`Film.m:197-203`). Base/Wave constructors originally copied the physical mixture handle (`Base.m:59-65`, `Wave.m:59-65`). `Mixture.copyElement` shallow-copies stored/cache properties, then creates Liquid/Vapor wrappers pointing to the copied mixture (`upstream/+Solvers/+Mixture/Mixture.m:2859-2863`); it does not refresh the H-dependent caches.

This graph was also checked by reading the original TUTORIAL1 FourField MCOS archive without running MATLAB. Every recovered initialization film has an S_k distinct from P; its base/wave `.mix` point to P, its drop `.mix` points to S_k, and base/wave `.film` point to the corresponding copied film. The local `solve` variable is not a saved object, so its P-copy origin is established by source line 83, not by a claim to recover that local variable.

### Expression-level map

All MATLAB anchors below are in `upstream/+Solvers/+FourField/@FourFieldSolver/solve.m` unless another class is named.

| Expression | MATLAB precursor | Python precursor before replay | Anchors / consequence |
|---|---|---|---|
| Onset used to redistribute pre-annular W | Local copy of P | S_k | MATLAB 130-133; Python 196-200. Both saved states give index 23 here. |
| Drop W = mixture liquid W - aggregate film W | Local copy of P | S_k | MATLAB 189; Python 219. Different cached-quality-derived liquid W is used. |
| Base full-momentum velocity ceiling and final blending | Local copy of P | S_k | MATLAB 229-231; Python 232-233. The thin-base fallback is separate and remains field-owned. |
| Wave full-momentum velocity ceiling and final blending | Local copy of P | S_k | MATLAB 258-260; Python 241-242. This branch is selected. |
| Drop full-momentum blending | Local copy of P | S_k | MATLAB 290; Python 250. Inactive: selected drop option is SLIP. |
| Drop SLIP velocity, deposition and concentration | `drop.mix` = S_k | S_k | `ThreeField/Drop.m:66-89,136-187,478-495`; `annular.py:150-173,206`. Preserve this source reference. |
| Aggregate-film entrainment | `film.mix` = S_k | S_k | `AbstractFilm.m:67-124,408-444`; `annular.py:107-148`. Preserve this reference. |
| Base/wave inherited shear, gravity/buoyancy and their own blend calls | Child `.mix` = P | P | `AbstractFilm.m:163,224,234-261`; native `annular.py:81-97`, plus `ff_fields.py` explicit blend calls. Preserve this reference. |
| Base equilibrium thickness and wave equilibrium frequency | `.film.mix` = S_k for precursor RE/U | S_k | `Base.m:418-420`; `Wave.m:484-512`; native `ff_fields.py:81,158-159`. Preserve this reference. |
| Wave drag relative velocity versus drag Reynolds number | FDRAG uses `wave.mix` = P; REV uses `wave.film.mix` = S_k | Same split | `Wave.m:365,656`; native `ff_fields.py:139,175`. Do not collapse these two references into one. |
| Thin-base secant equilibrium blending | Child `.mix` = P | P | `AbstractFilm.m:337-357`; `annular.py:45-62`. Preserve this reference. |

The correct source-faithful experiment is therefore **not** to replace all field `.mix` references. It is to isolate the outer-sweep precursor selection during initialization while preserving all child and aggregate references. For transients MATLAB selects `mixSolver.mixture(tIdx)` (`solve.m:94`), which is also the aggregate film's physical-time mixture; that separate path should retain its corresponding time index.

### Numerical relevance and why the verified baseline did not expose it

Comparing the saved Sawai physical precursor (`numerical/mixture/results.npz`, time 0) with its final pseudo-time precursor (`numerical/mixture/initialization.npz`, last time) gives exact W/P/H/DP.Tot/HFLUX/MRM.WV agreement. Derived properties differ at Python indices 14-100. In particular:

| Python index | Physical liquid U [m/s] | Final-init liquid U [m/s] | Physical vapor U [m/s] | Final-init vapor U [m/s] | Physical minus final-init liquid W [kg/s] |
|---:|---:|---:|---:|---:|---:|
| 24 | 1.1214470067230262 | 1.1221461081993387 | 2.9535430150439983 | 2.9527956390242710 | 1.335678632800874e-9 |
| 25 | 1.2188211837503427 | 1.2199722607291201 | 3.2679517141658380 | 3.2668545687733808 | 9.272078296124198e-10 |
| 26 | 1.3155582107704613 | 1.3172918546783159 | 3.5822911060776885 | 3.5808076234823676 | 6.354121629900678e-10 |

Whole-profile maximum absolute differences are 0.0334043972886 m/s for liquid speed, 0.00619159375018 m/s for vapor speed, and 6.30894477069e-9 kg/s for liquid flow. They are not numerical differences from a MATLAB Sawai run. They are differences between two existing native objects that the pinned MATLAB algorithm uses for distinct roles.

The native H setter/copy cascade is order dependent for cached quantities (`fields.py:99-128,196-226`); equality of final primary arrays is insufficient to assume equality of all getters. This audit does not establish whether these cache differences themselves exactly match MATLAB for Sawai. The isolated replay should record cached x/vf/rho and derived phase values directly rather than reconstructing only W/P/H.

For TUTORIAL1, the recovered MATLAB physical and final-init cached W/P/H/x/vf/rho arrays are exactly equal. The saved native baseline also has exactly equal physical/final-init U, liquid/vapor W/U and DP.Tot. Thus its successful profile comparison is compatible with this newly identified object-selection discrepancy; it did not exercise unequal precursor caches. No baseline result is withdrawn or overwritten by this finding.

## Update, dimensions and closure audit

The outer point-update sequence otherwise matches the inspected one-wall MATLAB source (`solve.m:137-300`; `fourfield.py:202-256`):

1. Copy prior-time arrays while retaining the first inlet element; save previous-time, upstream-node and point-iteration values by value.
2. Evaluate base MTOT and relax base W; then evaluate wave MTOT using the **updated base W** and relax wave W.
3. Save aggregate W, clip wave W to zero, compensate base W from saved aggregate W, then clip base W. Recompute drop W afterward.
4. Update and relax frequency using the saved iteration wave velocity but current W-dependent frequency source.
5. Update base velocity, then wave velocity using the newly updated base state, then drop velocity.
6. Compare six absolute point increments with strict `<` tests. Exhaustion retains the final iterate and reports point nonconvergence.

Changing to simultaneous source evaluation, clipping both fields independently, or replacing this loop by a different nonlinear solver would change the algorithm. Internal base/wave exchange terms cancel when evaluated at one shared state, but the sequential outer update evaluates them at different states; the algebraic cancellation test is not proof of an exactly converged discrete balance.

`_copy_arrays` uses Fortran-order flattening and preserves only linear element zero (`ff_fields.py:15-25`), matching MATLAB `(2:end)` copying (`Base.m:603-608`, `AbstractField.m:241-257`). Film intentionally ignores its `all` option while delegating to children (`Film.m:279-283`, `ff_fields.py:237-239`). Base copies W/U/H; wave also copies FREQUENCY. `.copy()` on saved point and upstream rows prevents NumPy views from changing the iteration history. Single-wall shapes are (101,1) for base/wave and (101,) for droplets; array arithmetic is elementwise, and multiwall inputs are explicitly rejected rather than silently broadcast into a new interpretation.

For either film component the source mass update is

`W_new = U_iter * (W_up + (W_old/U_old)*(dz/dt) + P_wet*Mtot*dz) / (U_iter + dz/dt)`.

Every term in the parentheses is kg/s; U and dz/dt are m/s. MTOT is kg/(m² s), perimeter is m. Film momentum force is N/m², so `F*dz/(rho*thickness)` is m²/s², consistent with the other numerator terms and a final velocity in m/s. DELTAFREQ is Hz/m, so the wave-frequency update retains Hz. The source does not impose an additional volume-closure equation or acceptance gate.

| Active closure / boundary | Inspection result and anchors |
|---|---|
| Base/wave mass split, transfer signs and double occurrence of turbulence | Source expressions retained, including `min(abs(WLb),WLw)` without taking abs(WLw), its cap 10, and subsequent blending. `Base.m:217-280`, `Wave.m:257-280`; `ff_fields.py:44-55,128-132`. |
| POSFILM and signed deposition | Source order retained; negative droplet W is not clipped. Concentration/deposition retain their negative-flow sign. `solve.m:180-189`, `ThreeField/Drop.m:81-88,159-187`; `fourfield.py:215-219`, `annular.py:150-173`. |
| RISO base equilibrium thickness | Same coefficients [5.37e-5,-0.64,1.21] and D_h/2 cap; `Base.m:403-424`, `ff_fields.py:73-82`. |
| SAWAI equilibrium Strouhal and relaxation | Same [77.67,-1.3,0.46], same frequency conversion and 0.2 s relaxation; `Wave.m:474-486,512,633-636`, `ff_fields.py:155-173`. |
| Shape, width, amplitude and wave drag | Same selected coefficients, width min, NaN width fallback, amplitude cap, and inverse-square drag expression. `Wave.m:449-453,588-617,652-681`, `ff_fields.py:148-178`. Zero-slip infinity-times-zero remains a source singularity; no analytic limit was substituted. |
| Thin-base fallback | FULLNOP still uses UEQUIL when abs(base thickness) <=1e-4 m; it is not a fully inertial base update everywhere. `solve.m:223-233`, `fourfield.py:228-234`. FULLNOP omits pressure/gravity in Base.FTOT even within that secant solve (`Base.m:379-383`, `ff_fields.py:68-72`). |
| Nested secant | Same initial U, U+0.1, then iterations 3..UFEQUILMAXITER, same force evaluation after assigning each trial, same final field-owned blend. `AbstractFilm.m:337-357`, `annular.py:45-62`. Native additionally records nested failure metadata. |
| Okawa entrainment inner iteration | Same slip initialization, finite iteration limit, 0.01 relative-slip threshold, laminar wall factor used internally, source final Cv/delta and transition across Re=270..370. `AbstractFilm.m:408-464`, `annular.py:107-133`. |

Using the saved final base W/U, the stored perimeter and CoolProp 8.0.0 saturated liquid density 823.1696030848586 kg/m³ at 2.95 MPa gives base thicknesses 57.6064, 52.4556 and 47.2453 µm at indices 24-26. Allowing the saved final base-speed increment in the previous-iteration velocity does not approach 100 µm. Thus the final base updates use the source thin-film secant fallback. This is a calculation from saved states and the native property backend, not a MATLAB branch trace. Earlier inner iterations may switch branches and must be captured in the replay.

The source sigmoid values computed from index 23 and `[0.1,0]` are approximately 0.997689460837, 0.999994636682 and 0.999999987579 at indices 24-26. Python preserves the shift of both node and onset from one-based to zero-based indices (`Mixture.m:2153-2155,2204-2207`; `fields.py:530-538`). Neither an index offset correction nor a new blending law is justified by this check.

## Proven distinctions, possible effects and limits

- **Confirmed source-object selection discrepancy:** the local outer precursor described above. Preserve both original objects in a diagnostic fixture and compare only the affected expressions. Numerical effect and relevance to the persistent wave-flow increment remain unquantified pending replay.
- **Known status distinction, not a calculation change:** MATLAB logs a warning but sets INITIALSTEPCONVERGED after its temporal predicate even if final point iterations fail (`solve.m:353-359`). Native preserves that STATE and returns a separate false `.converged` (`fourfield.py:103-109,155-174`, `threefield.py:109-113`). Frequency is logged but omitted from the original temporal stopping predicate. This explains the saved status combination without changing or relaxing its criteria.
- **Finite arithmetic grouping differences exist:** wave FSHEAR multiplies BETA last in MATLAB (`Wave.m:396-397`) and first in Python (`ff_fields.py:143`); film buoyancy divides DP by dz before multiplying thickness in MATLAB (`AbstractFilm.m:243-245`) and multiplies before division in Python (`annular.py:94`); ENTNUM computes `(Cw/Cv)*(rhoF/rhoG)` in MATLAB (`AbstractFilm.m:433`) versus sequential multiplication/division in Python (`annular.py:114`). These are the same finite real arithmetic, but not a promise of identical floating-point rounding. No causal attribution to them is established.
- **Nonfinite paths are not general equivalence claims:** native has an explicit nonfinite-primary-state exception and nested-failure records. MATLAB's `eps=1` secant expression retains a literal `0*previous_U + U_trial`, while Python directly assigns U_trial; this can differ if the old value is nonfinite. No evidence yet shows that path in these finite saved states. Do not change the source expression or add a new gate on speculation.
- **Interpolation remains unexecuted across runtimes:** onset uses the same third-iteration linear interpolation and later fallback structure (`FourFieldSolver.m:302-329`, `fourfield.py:65-101`). Native reports seven onset iterations and the original 1e-4 kg/(s m) tolerance, but no matched MATLAB onset trace exists. SciPy/MATLAB interpolation and property-library differences remain possible until compared on identical intermediate inputs.

The source and existing test inspection found no other demonstrated active finite-state error in indexing, copy semantics, sequential source order, selected coefficient values, clipping order or strict point tolerances. This is a bounded audit of one operating case, not full framework parity or physical validation.

## Required replay evidence before a correction claim

Record the unchanged attempt first: exact submitted/effective inputs, original input/source hashes, physical and final-init precursor caches, object identities, all outer iterations at indices 23-27, source terms before each mass assignment, pre/post POSFILM values, trial/bounded/relaxed/blended velocities, frequency update terms, thin-base branch selection and secant trials. Preserve original arrays and failures.

Then use a targeted diagnostic fixture in which P and S have deliberately distinct cached phase values to verify the expression-level object map. If a source-selection correction is made, change only the outer initialization precursor choice, retain field handles and all equations/controls, and repeat the same case into a new directory. Compare every saved array and the complete failed-iteration trajectory; rerun the original archived baseline comparison to demonstrate that its established agreement is retained. An improved native convergence result alone would not establish MATLAB equivalence, and an unchanged failure would not disprove the source-selection finding.

Existing relevant tests were inspected, not newly rerun here: `tests/test_fourfield.py` (field identities, exchange signs, copy and NaN-bound semantics), `tools/test_recover_annular_reference.py` (actual MCOS graph and stored profiles), and `tests/test_lecorre_runner.py` (frozen identity/inputs and numerical variants). They do not currently supply a matched Sawai MATLAB trace or test the outer-sweep selection with unequal P/S caches.

## Evidence hashes

Paths below are relative to the frozen base-case directory unless stated otherwise. Hashes are SHA-256 of existing bytes.

| Artifact | SHA-256 |
|---|---|
| effective_inputs.json | `f60b6bd005de5febbb7aa225adbd5728a5db3f4b1cca129142113e86a151c859` |
| numerical/initialization.npz | `2538243681aa03fee6606ce402622783ee536887c3c81ea2a1f4ab6f49deab5e` |
| numerical/metadata.json | `af3d4e35eaa010302fe9b45efa44f1c9f61b0c2653eb084e44376f96c5a885d7` |
| numerical/mixture/results.npz | `62305ec2f2f4d63b5f8bfe208e72c31563c67f42d7b52e8e91bc352da729722b` |
| numerical/mixture/initialization.npz | `cc4c1f543c5c83dcc61d404bfcd03dff306fcf0b081ba5f14c7d55c8c2d804af` |
| Original TUTORIAL1 FourField MAT archive | `fd28edab74cad654721572c4644461dc20fef27ed4a3d617458b9717e13eacf1` |

At the initial audit, raw `fourfield.py`, `ff_fields.py`, `annular.py` and `fields.py` hashes were checked equal to those recorded in the frozen run's `native_source_sha256`; the audit did not substitute a later numerical implementation. The later annular informational-status policy is separate diagnostic metadata and does not explain these cached precursor differences.

## Reproducible object evidence and isolated correction

`tools/audit_replay_precursor_handles.py` reads the frozen NPZ arrays and the independent original TUTORIAL1 MCOS archive without invoking a solver. Its receipt, `outputs/verification/matched-replay-01/precursor_handle_audit.json`, records all input/archive/source hashes, array differences with units and coordinates, and all nine archived initialization handle graphs. Its SHA-256 is `ddb9192cce4aba1c9fecaac5a389a2cbf9a6f434fccadb48062e1c0ca2c24d74`. It was generated before the numerical source correction. To repeat against the currently available source without overwriting this historical receipt:

```powershell
.\.venv\Scripts\python.exe tools\audit_replay_precursor_handles.py --output outputs\verification\matched-replay-01\precursor_handle_audit_repeat.json
```

After the unchanged replay completed, only the confirmed FourField local-selection difference was corrected: `_advance` now requires an explicit `sweep_mix` keyword; steady initialization supplies `self.mixSolver.mixture[0]`, and transient step k supplies `self.mixSolver.mixture[k]`. The field-owned aggregate film/drop final-init handles and base/wave physical precursor handles are preserved. No equation, coefficient, tolerance, iteration limit, clipping operation, field closure or ThreeField implementation was changed.

`tools/audit_replay_precursor_change.py` checks the entire FourField module AST against pre-change Python commit `178ac2b4152b31016dc8847aebab139de0d88d2d` after applying only those four specified AST edits. It also requires all other 24 native Python modules to match that commit byte-for-byte after line-ending normalization. The successful receipt is `outputs/verification/matched-replay-01/precursor_change_audit.json`, SHA-256 `72731afe31cfe3cf35bcd2f4e451ca564dd892ca13116b9cfbe343f685524640`.

The focused `tests/test_fourfield.py` run passed 12 tests in 49.66 s, with the two existing zero-slip wave-drag warnings. Three new cases cover: (1) deliberately equal primary W/P/H but unequal derived phase caches, checking the physical precursor's drop mass and base/wave/drop FULL bounds and blending; (2) the same fixture with drop SLIP, verifying that the closure still uses its own final-init precursor; and (3) initialization versus transient precursor dispatch. The analytic fixtures isolate source selection and are not physical validation. This focused run includes the original sample invariant tests; it does not itself replace the separate archived MATLAB baseline comparisons or matched Sawai replay.

At this checkpoint the corrected matched replay and all-four-framework archive comparison are separate integration work. No improved convergence, causal explanation of the wave-flow failure, matched Sawai MATLAB equivalence, or physical validation is claimed from the source audit and analytic tests alone.
