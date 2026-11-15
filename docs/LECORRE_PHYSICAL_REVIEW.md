# OpenSTREAM convergence and supplemental diagnostics review

The phase-volume closure residual is a supplemental diagnostic for ThreeField and FourField, **not a convergence or acceptance criterion**. On 2026-11-14, R. W. Morse explicitly directed that it have no pass/fail role for these frameworks because the upstream solvers do not impose this criterion. Mixture and TwoFluid policy is unchanged. No closure model, governing equation, solver stopping rule or numerical tolerance is added or changed by this policy.

The numerical residual remains available, with its domain and any indeterminate values, without an annular area pass/fail threshold. It is not caused by counting wave intermittency twice. Numerical convergence, the source option named `FULL`, and graphical agreement still answer different questions from geometric consistency or experimental accuracy.

This review preserves all frozen inputs, saved calculations and original diagnostic receipts. The earlier receipts classified annular area discrepancies as physical failures; those historical classifications remain recorded but are superseded by the current policy for area alone. It covers the 33 completed 100-cell base runs in `outputs/validation/lecorre-2025-01`; refinement runs are outside this arithmetic review. Source: OpenSTREAM `a614c7173822a93c1e64ac28d1541cbac028cbd8`. Portable audit evidence is `references/paper/lecorre2025/physical_scope_review.json`.

The separate criterion-specific receipt `outputs/verification/annular-policy-01/reassessment.json` applies the current reporting policy to all 69 saved run records. It supersedes 61 annular area rejections, retains four TwoFluid area rejections and leaves four Mixture assessments unchanged. Native convergence remains 63/69. All 13 runs with saved negative-value flags retain those flags. This is a hash-bound reclassification of one diagnostic, not a new calculation, a broader physical audit or an overall validation/pass assessment.

The audit's original report hash resolves to `references/paper/lecorre2025/physical_scope_checkpoint_report.json`. Those bytes were recovered from the unchanged ordered run records and original serialization only after obtaining an exact match to the already recorded SHA256 `429ca74a0b8d9094d13c341754a3b376502bba7a84039352a7704a18544b01f4`. This checkpoint contains 37 attempted runs; the audit selected its 33 base runs. `checkpoint_recovery.json` records the method. At the original campaign checkpoint, all 95 per-run files hashed by the audit and all 25 native source fingerprints were independently checked unchanged. The current diagnostic-metadata revision is separately audited below.

The same read-only arithmetic was also executed after all 69 planned attempts
finished. `outputs/validation/lecorre-2025-01/physical_scope_audit.json` binds
that repeated 33-base-run review to the final campaign report and the executed
audit script. It preserves the earlier checkpoint and reaches the same base-run
results; it does not extend this physical review to the refinement runs.

## What MATLAB OpenSTREAM actually checks

The inspected upstream ThreeField and FourField solvers do not test a sum of phase occupied areas or a phase-volume closure residual when deciding convergence:

- `upstream/+Solvers/+ThreeField/@ThreeFieldSolver/solve.m:210–214` checks changes between iterations at each axial node in film flow per perimeter [kg/(s m)] and film/drop velocities [m/s]. Lines 242–248 check the corresponding pseudo-time changes against the steady-state tolerances.
- `upstream/+Solvers/+FourField/@FourFieldSolver/solve.m:293–300` checks base/wave flow per perimeter, field velocities and wave frequency [Hz] between point iterations. Lines 344–353 implement the pseudo-time check; frequency change is calculated at line 348 but is absent from the source stopping predicate at line 353.
- The mass-flow subtractions in ThreeField line 182 and FourField line 189 enforce `W_drop = W_mixture_liquid - W_film`. They do not impose a total occupied-area equality when field velocities differ.
- The optional `MOMENTDROP=ALGEBRAIC` closure uses the remaining area to prescribe droplet velocity in `upstream/+Solvers/+ThreeField/Drop.m:515–518`. This is an existing selected closure, not a global convergence criterion, and no case has been switched to it. The nearby phrase “Volumetric force residual” at line 559 refers to a force-density balance [N/m³], not volume closure.

The Python numerical convergence flags were already independent of this diagnostic: `src/openstream/threefield.py:111–114` checks source state, point/time convergence and nested/onset solves; `src/openstream/fourfield.py:105–109` additionally checks wave-frequency and nested-field convergence. The previous area flag affected a separate physical assessment and the CLI/GUI reporting policy, not the solved values or those convergence predicates. Removing its acceptance role does not clear any failed numerical criterion.

The source-scope receipt `outputs/verification/annular-policy-01/source_scope_audit.json` compares the implementation with commit `039afe6a723e542927dd7cc11610d610ded27c3e`. Its abstract-syntax-tree checks confirm unchanged numerical/closure code apart from diagnostic reporting metadata, unchanged solver convergence predicates, unchanged diagnostic arithmetic, unchanged archive-recovery arithmetic and unchanged GUI solver calls. This supports the limited claim that the policy update changes reporting rather than governing calculations; it is not a numerical-equivalence or experimental-validation test.

The final revision passed 490 Python tests (two retained FourField runtime warnings), 11 frontend JavaScript tests, and 13 separate archive-reader tests (one existing pandas-option deprecation warning). Logs are under `outputs/verification/annular-policy-01/`. The AST scope audit covers 25 native modules. An observed Windows progress-file `PermissionError` was fixed with a bounded, permission-only retry in GUI file I/O; the original failure trace and successful rerun are preserved in `gui-write-race-receipt.json`. This I/O correction adds no closure or convergence criterion.


## Meaning and units of the supplemental diagnostic

For field mass flow W [kg/s], density rho [kg/m³] and velocity u [m/s], W/(rho u) has units of occupied cross-sectional area [m²]. If the fields represent a geometrically closed partition of the channel, the following total equals its specified area. For the upstream annular formulation this is reported as a diagnostic identity, not an additional imposed equation:

`A_occ = (W_base/u_base + W_wave/u_wave + W_drop/u_drop)/rho_liquid + W_vapor/(rho_vapor*u_vapor)`.

The channel's geometric area is correctly specified. Upstream
`+Inputs/Geometry.m:109` and native `inputs.py:445` use
`Dh = 4*A/sum(PERIM)`, equivalently `A = Dh*P_wetted/4`. The diagnostic
compares the phase-state-implied occupied area with this known geometric
target; it does not recalculate or replace the channel geometry. A precise
name for the discrepancy is **phase-volume closure residual**. For TUTORIAL1,
`A=6.0821e-5 m^2` and `P_wetted=0.0276 m` imply `Dh=0.00881463768 m`.
The paper's rounded diameter must not silently replace the stored area.

The supplied paper's Equations (14) and (15), page 7, store **W_base/u_base** and **W_wave/u_wave** in the respective continuity equations. Those are already axial mass inventories [kg/m]. An extra multiplication by wave/interface fraction would alter those stated inventories. Upstream `+Solvers/+FourField/Film.m:75` defines film flow as base plus wave flow; its harmonic velocity at line 114 makes `W_film/u_film = W_base/u_base + W_wave/u_wave`. `+Solvers/AbstractFilm.m:47` likewise defines equivalent film thickness from W/(perimeter rho u). The wave thickness closure at `+Solvers/+FourField/Wave.m:96` is amplitude times interfacial fraction; it does not authorize applying that fraction again to W/u. Thickness/amplitude caps are separate closures, not enforcement of the total channel inventory.

Independent saved-array arithmetic reproduced the existing annular area maxima for all 31 annular base runs within **2.88e-16 absolute relative-area difference**. The equivalent-film inventory identity agreed within **6.94e-18 kg/m**. This audit imports no solver or adapter; under the recorded saturated-density assumption it also evaluates the algebraically equivalent expression `(liquid_inventory / precursor_liquid_inventory - 1)*(1 - precursor_void_fraction)`. Portable output arrays are explicitly treated as `(time,node)` and comparison profiles as `(node,)`.

## What the source coupling explains

The paper, page 4, states that the precursor mixture pressure gradient is reused without a pressure–velocity correction, and acknowledges conservation inconsistencies. Page 5 states that the three-field vapor solution comes from the mixture solver; page 7 retains the same droplet-flow subtraction for four fields. This is reflected directly in upstream:

- `+Solvers/+FourField/@FourFieldSolver/FourFieldSolver.m:17`: pressure gradient and vapor solution come from the mixture solver.
- `+Solvers/+FourField/@FourFieldSolver/solve.m:83` and line 94: precursor mixture states are copied/reused.
- The same file, line 189: droplet mass flow is mixture liquid flow minus film flow.
- Lines 218–290 update base, wave and droplet velocities using their selected equations; they do not solve a common pressure/volume correction. Velocity bounds and thin-film fallback remain part of these algorithms.
- `+Solvers/+ThreeField/Drop.m:498` provides a distinct `UALGEBR` option that computes droplet velocity from the area left by the precursor void fraction and film. That selected closure uses geometry explicitly; it does not impose a general acceptance requirement on other selections. Changing to it would change the requested model.

Consequently, matching the precursor liquid **mass flow** while independently changing field velocities does not preserve its liquid **volume inventory**. This supplies a source-backed structural explanation for possible area mismatch. It does not isolate the contribution of every closure, iteration bound or source defect in each new case. The paper's page-8 phrase about full momentum equations concerns the demonstration's selected field equations, with the stated base-force omission; it does not remove the precursor-coupling simplification or imply that every validation case selects every `FULL` option.

## Diagnostic domain and observed residuals

The reported annular maximum uses only `AFFNC >= 1 - 1e-12`, the numerically unblended annular region. All-region values in the transition/initialization region are descriptive. The original receipts applied a 1e-6 relative-area threshold; under the current ThreeField/FourField policy this threshold is not an acceptance criterion. An absent eligible domain or nonfinite/indeterminate area does not generate an area-based rejection or pass. Independent source-equation failures, finite-state requirements and numerical failures retain their own status.

| Current reconstruction | Maximum reported area discrepancy |
|---|---:|
| Two-fluid demonstration, whole channel | 41.056107% |
| Three-field demonstration, fully annular | 7.485259% |
| Four-field demonstration, fully annular | 7.488843% |
| Wurtz, range over 21 cases | 0.162442%–3.330946% |
| Sawai, range over eight case/relaxation variants | 0.958125%–2.549905% |

The runner's separate nonnegative-value flag examines all nodes. In the 33 base runs, negative `drop.W` occurred only for Sawai IDs 1 and 5, under both relaxation choices. **None of these negative nodes passed the fully annular mask.** ID 1 minima were approximately -1.18208e-5 kg/s at z=0.36256 m; ID 5 minima were approximately -7.70744e-6 kg/s at z=0.23072 m. Both minima have `AFFNC=0.00231054`. Some ID-1 tail values lie very close to the annular mask boundary, so they should be described as transition-region values, not silently deleted or declared harmless. The frozen whole-domain negative-value flags remain unchanged. The downstream area residual is retained separately as information.

## Archive agreement versus new-case attribution

`docs/ALL_BASELINES_VERIFICATION.md:68` documents area discrepancies independently recovered from the original TUTORIAL1 MATLAB archives: TwoFluid 41.056107%, ThreeField 7.485259%, FourField 11.241052% in their specified domains. Those particular shared numerical discrepancies are demonstrated and were not introduced by the Python port. The current paper FourField case has different settings and a different area maximum; it must not inherit the archived-case equivalence claim. ThreeField/FourField baseline rows retain separately demonstrated clipped-cell mass/storage residuals where present; their status must not be justified by area alone.

No full-precision MATLAB arrays for the newly reconstructed Wurtz/Sawai cases have been recovered. Their exact MATLAB discrepancy, generating version and causal attribution remain unverified. Paper-raster agreement provides narrower graphical evidence. Independent experimental validation remains unestablished because source-case calibration associations, uncertainty gaps, numerical failures and independent-reference gaps remain unresolved. Reclassifying the supplemental area diagnostic is not a validation result.

Reproduce this read-only audit into a new file:

```powershell
.venv\Scripts\python.exe tools\audit_lecorre_physical_scope.py --campaign outputs\validation\lecorre-2025-01 --output tmp\physical-scope-new.json
```
