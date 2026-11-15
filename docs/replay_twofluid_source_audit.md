# TwoFluid 400-cell replay: source audit

Date: 2026-11-15. Target: `demo-twofluid-n400-mesh` in the frozen
`outputs/validation/lecorre-2025-01` campaign. This is a read-only inspection
of source and saved arrays, not a new solver execution or MATLAB run.

Pinned MATLAB source: `a614c7173822a93c1e64ac28d1541cbac028cbd8`.
Native checkout at inspection: `178ac2b4152b31016dc8847aebab139de0d88d2d`.
No numerical code, original result, acceptance criterion, model setting or
tolerance was changed during this audit.

## Finding

No confirmed governing-equation, indexing, source-update-order or iteration-limit
translation error was found in the inspected path. Both implementations permit
29 pseudo-time advances from 30 stored states at the source-default
`SSMAXITER=30`, `SSTSTEP=1 s`. The saved Python calculation exhausts that
limit with liquid enthalpy still changing at the outlet. This is a measured
native convergence failure; there is no matching MATLAB execution for this
400-cell case establishing whether MATLAB reaches the same failed limit.

Two implementation-expression differences merit explicit replay measurements:
the order of addition of force components, and redundant/short-circuited source
calls. Their algebraic expressions are equivalent for the inspected finite,
read-only path. They have not been demonstrated to cause the observed failure
and do not justify a change to equations, controls or reference tolerances.

## Independently checked saved evidence

Inputs: `outputs/validation/lecorre-2025-01/demo-twofluid-n400-mesh/effective_inputs.json`.
Arrays: the same directory's `numerical/initialization.npz` and
`numerical/mixture/results.npz`. The initialization arrays have shape
`(30,401)`, with time 0 through 29 s and axial position 0 through 5.5 m.
The source selections are one wall, saturated properties, `INTNU=RELAXATION`,
`INTTRANSH=BULK`, both phase momentum equations `FULL`, and
`AXIALINTERP=NEXT`. The mixture precursor converged.

Recomputing the final two-state differences directly from stored arrays gives:

| Temporal quantity | Maximum absolute change | Source threshold | Zero-based node | z [m] |
|---|---:|---:|---:|---:|
| Liquid W [kg/s] | 2.53826253765e-8 | < 0.001 | 400 | 5.5 |
| Vapor W [kg/s] | 1.39840994888e-7 | < 0.001 | 294 | 4.0425 |
| Liquid U [m/s] | 0.000264163636327 | < 0.001 | 245 | 3.36875 |
| Vapor U [m/s] | 0.000266927345059 | < 0.001 | 245 | 3.36875 |
| Liquid H [J/kg] | **2.07523442060** | **< 1** | 400 | 5.5 |
| Vapor H [J/kg] | 1.39698386192e-9 | < 1 | 223 | 3.06625 |

All final point criteria pass. Maximum point changes are liquid
`DH=0.09990499518 J/kg`, `DU=8.808422959e-5 m/s`,
`DW=4.027986028e-9 kg/s`; vapor `DH=9.313225747e-10 J/kg`,
`DU=8.838637633e-5 m/s`, `DW=3.213107985e-8 kg/s`. The final maximum point
iteration count is two. Limits remain `ERRORH=0.1 J/kg`,
`ERRORU=1e-4 m/s`, `ERRORW=0.001 kg/s`.

The last six maximum liquid-H temporal changes are 2.422273398,
2.364935377, 2.302930180, 2.234179276, 2.158421194 and 2.075234421 J/kg;
each maximum is at the outlet. This decreasing sequence is descriptive;
it does not prove eventual convergence or authorize extending the original run.
All six inlet W/U/H quantities are exactly unchanged across stored states.

The saved `NEXT` heating distribution has its last heated node at index 254,
z=3.4925 m, with nonzero heat flux 907742.2634423663 W/m². The independent
discrete sum `sum(q[1:])*0.0276*(5.5/400)` is 87500 W. The inlet is excluded
from this integral in both source implementations. The outlet failure is in
the adiabatic region; no heating-profile or channel-length change is proposed.

## Source correspondence

All MATLAB paths below start at `upstream/+Solvers/`; native paths start at
`src/openstream/`.

| Concern | MATLAB anchor | Native anchor | Audit conclusion |
|---|---|---|---|
| Mesh/time/property inheritance | `+TwoFluid/@TwoFluidSolver/TwoFluidSolver.m:123–127` | `twofluid.py:61–63` | Both inherit the solved precursor's mesh, times, properties and interpolated boundaries. |
| Phase initialization | `TwoFluidSolver.m:173–192` | `twofluid.py:68–76` | W/U come from the precursor; H uses liquid `min(H,HF)` and vapor `max(H,HG)`. Native `fmin/fmax` preserve the source NaN-selection convention. |
| Initial history length | `TwoFluidSolver.m:200–221`; `+TwoFluid/@TwoFluidSolver/solve.m:105` | `twofluid.py:104–109` | MATLAB preallocates 30 states and loops from 2; Python appends states for range(1,30). Neither performs a 30th advance. |
| Shared handles and independent arrays | `AbstractField.m:1,36,214–258`; `TwoFluidSolver.m:174–175,201–204` | `tf_fields.py:64–75`; `twofluid.py:77–82` | Phase copies preserve the shared `.mix` handle while copying W/U/H/ITR arrays. Do not relink each pseudo-time phase to a newly composed mixture. |
| Inlet preservation | `AbstractField.m:246–258` | `tf_fields.py:64–69` | MATLAB `(2:end)` maps to Python `[1:]`; W/U/H and iteration arrays retain the inlet. |
| Previous-time and upstream state | `+TwoFluid/@TwoFluidSolver/solve.m:114–143` | `twofluid.py:140–150` | Old-time values stay fixed throughout the current-node inner loop; upstream values come from the current axial sweep. |
| Sequential equation updates | `solve.m:145–214` | `twofluid.py:151–183` | Liquid W, vapor W, liquid U, vapor U, liquid H, vapor H, in that order. Source evaluations observe the same preceding updates. |
| Old point inventory in force/heat normalization | `solve.m:171–178,193–214` | `twofluid.py:162–183` | The normalizing W/U and advection velocity use saved old point-iteration values, not newly updated W/U. The 0.001 kg/s cutoff is unchanged. |
| Velocity bounds | `solve.m:174–178,196–200` | `twofluid.py:166–175` | Retains zero lower bound, 1.5 times precursor phase U upper bound, old-U fallback below cutoff, then relaxation. |
| Point stopping | `solve.m:217–232` | `twofluid.py:184–191` | Six strict `<` comparisons, inclusive MAXITER=100 point attempts. Native finite-state rejection is an additional explicit guard, not encountered in this saved case. |
| Temporal stopping | `solve.m:258–268` | `twofluid.py:112–119,194` | Six maxima of absolute consecutive-state changes, using the same strict source thresholds. |
| Failed initialization export | `solve.m:292–299` | `twofluid.py:118–121` | Both mark INITIALSTEPNOTCONVERGED and copy the final failed initialization state into physical time zero. This copying is not evidence of convergence. |
| Transient continuation | `solve.m:45–51` | `twofluid.py:123–130` | Both skip physical transient advancement when initialization fails. This case has one physical boundary state. |

The source constructor does not require a successful supplied precursor;
Python explicitly checks convergence and matching geometry/boundaries/mesh
(`twofluid.py:31–40`). Those guards pass for this case and cannot explain
its final liquid-H temporal failure. Python's aggregate `point_converged`
member is assigned when temporal convergence succeeds; for a failed temporal
initialization, use saved per-state/per-node point records rather than
interpreting its default false value as proof of a point failure.

## Selected dependent closures and array semantics

The current scalar-node, one-wall path avoids MATLAB linear-index versus
wall-matrix ambiguity. Native state vectors are `(node,)`; `_col` appends
the wall axis (`fields.py:18–23`), so selected source terms are `(1,)` for a
single node. A scalar `np.sum` over that one-wall source matches MATLAB
`sum(Mtot,2)` at that node. Multiwall FULL momentum is explicitly rejected;
this audit does not certify it.

- **Relaxation mass transfer:** MATLAB `+TwoFluid/Liquid.m:580–601` and
  native `tf_fields.py:148–155` use the same equilibrium-flow discrepancy,
  current vapor velocity, condensation/evaporation times, phase-availability
  caps and wall-perimeter fractions. The equilibrium total flow comes from
  the shared physical phase aggregate while XEQ comes from the precursor
  (`+TwoFluid/Mixture.m:131–143,241–254`; `tf_fields.py:33,45`). Replacing
  either with a current-pseudo-state alternative would change source behavior.
- **Source signs:** vapor total mass transfer is the negative of liquid
  transfer (`+TwoFluid/Vapor.m:520–534`; `tf_fields.py:235`). Liquid is
  updated first, so the vapor source is evaluated after that update in both
  solvers; instantaneous cancellation does not make these two sequential
  evaluations simultaneous.
- **Material enthalpy:** MATLAB `Liquid.m:813–823,875–903,920–921` and
  `Vapor.m:621–630,683–710,727–728` correspond to native
  `tf_fields.py:172–180,243–251` and `_Phase.HTOT:88`. For `BULK`, liquid
  interfacial evaporation heat and vapor interfacial condensation/wall-
  evaporation heat are zero. Vapor enthalpy is updated after liquid enthalpy.
- **Prescribed pressure/thermal forcing:** `DPDZ`, XEQ, wall heat,
  boiling partition and relaxation times retain precursor accessors
  (`+TwoFluid/Mixture.m:84–129,197–225,241–254,340–371`;
  `tf_fields.py:30–32,42–45,49–52`). No independent pressure correction
  or altered thermal model belongs in this replay.
- **Relaxation interpolation:** the source uses only the first
  `length(RELAXX)` entries of RELAXCONDT/RELAXEVAPT
  (`+Mixture/Mixture.m:1776,1864`), as does native
  `fields.py:410–416`. The third supplied condensation entry is therefore
  unused for this two-knot case in both implementations. Do not silently
  reinterpret it as a third physical knot.
- **Heating interpolation:** source precursor
  `+Mixture/@MixtureSolver/MixtureSolver.m:328–372,1234–1243` and native
  `solver.py:65–79`, `numerics.py:26–39` retain NEXT interpolation,
  source linear fallback where extrapolated values are NaN, and discrete
  total-power normalization excluding the inlet. MATLAB `(node,wall,time)`
  becomes native `(time,node,wall)` explicitly.

Dimensional checks of the sweep expressions are consistent: W/U is kg/m;
linear mass source times dz is kg/s; force [N/m] divided by W/U is m/s²;
linear heat [W/m] divided by W/U is J/(kg s). The enthalpy update therefore
returns J/kg, and its point and temporal criteria are absolute J/kg changes,
not rates or relative errors.

## Differences to measure before classifying a defect

1. **Force summation association.** MATLAB `Liquid.m:1151` sums gravity,
   pressure, wall, drag and condensation terms in that order. Native
   `tf_fields.py:199` adds wall last. Vapor has the analogous difference
   (`Vapor.m:961`; native line 267). The terms and signs are unchanged,
   but floating-point addition is not associative. Capture constituent
   terms and compare the literal source-ordered sum with the current sum;
   do not assume the observed 2.075 J/kg is caused by roundoff.
2. **Repeated pure source calls.** MATLAB MTOT/HTOT evaluate paired MINT/HINT
   outputs once (`Liquid.m:693–694,920–921`). Native separate convenience
   accessors evaluate the pair twice (`tf_fields.py:84–88,159`). No write to
   phase flow variables was found in the inspected selected closure path.
   Record call inputs/results if a replay diverges; duplicated evaluation
   alone is not proof of changed physics.
3. **Cutoff evaluation order.** MATLAB evaluates force/heat, divides by old
   W/U, then zeroes the result where old W<=0.001 kg/s. Native uses a
   conditional that skips the call/division there (`twofluid.py:165,173,178,181`).
   Finite selected states produce the same assigned zero/frozen velocity.
   Exceptions, warnings or hidden stateful behavior would differ; the frozen
   case has no recorded warnings. A targeted cutoff-side test should preserve
   both the numerical result and any documented domain/error semantics.

These findings do not establish full expression-by-expression equivalence
of every unselected drag/heat/flow-regime branch or of a different property
backend. They also do not establish MATLAB equivalence for the 400-cell run.

## Matched replay checks

Use the frozen effective inputs and a new output directory. Retain the original
failed result. A diagnostic observer should record, without changing update
order: old-time, upstream and old-iteration W/U/H; the six post-update values;
each mass/force/heat source component; phase-availability and 0.001 kg/s
cutoff decisions; velocity bounds; relaxation values; point iteration counts;
and the six temporal maxima with node locations. Include the outlet node 400
and the neighborhood of the saved heating boundary (254/255). Preserve the
shared-handle identities throughout initialization.

First compare an instrumented replay to the existing NPZ arrays and histories.
Then independently evaluate each recorded scalar update in literal MATLAB
expression order. Match the already converged 100-cell archived baseline
before interpreting differences in the 400-cell case. Capture missing MATLAB
intermediate states only if a source/data distinction cannot be resolved from
existing arrays; do not fabricate those reference iterates.

Existing targeted, executable checks (not rerun by this audit):

```powershell
.venv\Scripts\python.exe -m pytest tests\test_twofluid.py -k "phase_clone or instantaneous_interphase or pressure_and_gravity"
.venv\Scripts\python.exe -m pytest tools\test_recovered_twofluid.py
```

A separately labeled longer initialization used as a diagnostic must
preserve all equations and point/temporal tolerances and must
not replace the original 30-state failure. This audit does not run or propose
an unrecorded continuation as an accepted baseline result.

## Completed native replay and independent arithmetic audit

The ordered, matched replay in
`outputs/verification/matched-replay-01/native-before-02/` completed both frozen
cases. Its original observer receipt records exact numeric agreement of all
five saved NPZ files per case, including shapes and NaN positions. That
executed observer preceded a comparator improvement which also rejects dtype
changes; the independent follow-up checks all 185 TwoFluid and 215 FourField
array dtype pairs against the frozen originals and finds them identical.
The original report and executed script snapshot are preserved.

`tools/audit_matched_replay.py` imports no solver or property implementation.
Its final receipt is
`outputs/verification/matched-replay-01/native-before-02/independent_arithmetic_audit_02.json`.
It verifies 9,326 exact scalar-arithmetic and full-grid temporal-difference
checks for TwoFluid, and 13,368 for FourField; none of these pairs is nonfinite.
It also binds the frozen manifest hash and verifies complete coverage of the
declared traced node/time pairs. These are arithmetic checks of observed
inputs, not additional model equations or physical acceptance criteria.

For TwoFluid, the observer captured 416 point iterations at nodes 397–400.
The audit reconstructs mass proposals from recorded MTOT returns, normalized
force proposals from recorded FTOT returns, enthalpy proposals from the
recorded normalized heat term, relaxation, clipping and the six point changes.
All agree exactly. Force constituents and raw HTOT were not captured, so the
force-association and repeated-closure-call questions above remain unresolved.
No MATLAB execution or independent MATLAB intermediate iterate is available.

Every one of the 29 TwoFluid sweeps satisfies the point criteria. At the final
outlet iteration, the liquid-enthalpy point change is
0.0018038325943052769 J/kg, below ERRORH=0.1 J/kg. The final temporal change
there is 2.0752344205975533 J/kg, above SSCONVH=1 J/kg; the other five temporal
criteria pass. All six prescribed inlet W/U/H arrays remain exactly constant.
The last six enthalpy temporal maxima decrease from 2.4222733983770013 to
2.0752344205975533 J/kg, but the whole history is not monotone: it rises from
3.6999183455482125 at 6 s to 4.669314387254417 J/kg at 8 s. These observations
support investigating the initialization budget without presuming its outcome.

The observer and audit tests pass 30 checks without executing numerical cases
(`tests/test_matched_replay.py` and `tests/test_matched_replay_audit.py`). They
cover exact/error/nonfinite comparison semantics, observer cleanup and refusal
to replace an active tracer, source-anchor ambiguity, dimensional scalar
updates, clipping order, unit consistency and incomplete/drifted receipt
rejection. Passing these checks does not establish MATLAB equivalence or
experimental validity.

The separate, preregistered initialization-budget diagnostic subsequently
completed in `outputs/verification/matched-replay-01/twofluid-budget-60/`.
Only SSMAXITER changes from 30 to 60. Independent saved-array comparison
confirms the original prefix of all 16 initialization arrays has identical
values, dimensions and dtypes. The first liquid-enthalpy temporal maximum
below 1 J/kg occurs at 39 s: 0.9414000483229756 J/kg. All point and other
temporal criteria also pass. This identifies an insufficient native
initialization budget for the original 400-cell attempt under the unchanged
criteria; it does not establish matching MATLAB evolution or resolve the
retained TwoFluid physical checks. The original 29 s failure is preserved.

The post-correction ordered replay is separately stored in `native-after/`.
Its TwoFluid arrays remain exactly unchanged. The identical independent
auditor passes the same 9,326 TwoFluid and 13,368 FourField checks there,
recorded in `native-after/independent_arithmetic_audit.json`. The FourField
precursor correction and remaining Sawai failure are documented in
[the matched diagnostic report](MATCHED_DIAGNOSTIC_REPLAY.md).
