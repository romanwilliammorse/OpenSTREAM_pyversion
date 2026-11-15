# Mixture follow-up: source semantics and diagnostic differences

2026-11-14. This follow-up preserves the governing equations, closure models,
convergence controls and original reference tolerances. It changes one
exception-handling branch in `src/openstream/fields.py`, and adds independent
verification tools/tests. No floating-point expression reordering was applied.

## Corrected MRM vapor-enthalpy fallback

Upstream `+Solvers/+Mixture/Vapor.m:131-143` distinguishes two branches:

- MRM calculates the mass-weighted vapor enthalpy across walls and substitutes
  saturated-vapor enthalpy HG only for NaN. Zero vapor flow produces 0/0, for
  which this fallback is expected.
- Other thermal models substitute HG for either NaN or infinity.

The native translation previously applied the second policy to both branches.
It now preserves infinity in the MRM branch, matching upstream. This prevents
an invalid infinite MRM value from being silently converted to a plausible
saturated value. It does not establish that a physically admissible MRM
calculation produces infinity, nor does it change finite-value equations.

`tests/test_mixture_mrm_semantics.py` uses explicitly synthetic invalid states
to test positive/negative infinity and NaN separately, plus valid multiwall
weighting, zero vapor flow, subset/scalar indexing, and nonmutation. A second
test retains the source's non-MRM fallback. These are branch/translation tests,
not physical predictions or experimental validation.

Executed focused tests: **36 passed**, including the new cases, field tests,
and transient balance/boundary tests. Evidence:
`outputs/mixture-followup/focused-tests.log` and `.xml`.

## Preserved baseline

The fresh run in `outputs/mixture-followup/native-after` remains numerically
converged. Every numerical array in both `results.npz` and
`initialization.npz` is bitwise identical to the prior accepted native mixture
run (`outputs/mixture-baseline-recovery/native-before`). Evidence:
`outputs/mixture-followup/baseline-unchanged.json`.

The recovered MATLAB comparison in `outputs/mixture-followup/comparison-after`
still passes all nine original W/U/H profiles and all ten initialization
states at `rtol=1e-8`, `atol=0`. The original reference and 14 supplementary
diagnostic failures remain unchanged. This equilibrium baseline does not
exercise the corrected MRM infinity branch.

Both original 100-cell, 51-state MRM transient runs also completed with numerical
convergence after the fix. Their mass/enthalpy residual maxima exactly equal
the previously recorded metrics: EULER 0.00237491305 kg/(s m) and
27.3036553 W/m; EXPONENTIAL 0.00257418798 kg/(s m) and 29.5939071 W/m.
These are the original loose-control residuals, not assertions of exact
conservation. Maximum momentum residuals were 11.6337028 Pa and 12.6048563 Pa.
The source convergence increments are distinct from these discrete-equation
residuals. Evidence: `outputs/mixture-followup/mrm-transient-after.json` and
`mrm-prior-comparison.json`. Original transient full arrays were not available
in that older summary, so only the listed metrics were checked for equality;
no transient MATLAB equivalence or full-array bitwise claim is made.

## Investigation of the 14 supplementary failures

`tools/audit_mixture_diagnostics.py` evaluates the original diagnostic
expressions independently from saved initialization arrays, without running
the solver or changing reference data. It checks nine pseudo-time advances
and all 100 non-inlet nodes, preserving the archived wall/node layout.
Results: `outputs/mixture-followup/diagnostic-audit.json`.

Eleven failing profiles are reconstructible from saved states:
DP.Acc_z/Acc_t/Acc_s, DPSUM.Acc_t/Acc_s, and
MDER.U_z/U_t/U/H_z/H_t/H.

- Every reconstructed archived value matches its stored diagnostic exactly.
- Native reconstructions also match exactly, except DP.Acc_s and its sum:
  maximum residuals 1.26218e-29 Pa and 8.83524e-29 Pa respectively, from the
  slightly different scalar multiplication/division grouping.
- Consequently the stored diagnostic differences are accounted for by the
  differences in their saved state inputs, to those residuals. The audit found
  no changed diagnostic governing expression causing these failures.

The source expressions differentiate nearby enthalpy/velocity values and, for
the homogeneous model, subtract nearly equal static and advective velocities.
For example, across all initialization states, maximum enthalpy material-
derivative difference is 6.50063e-7 J/(kg s), and slip-pressure difference is
1.35767e-13 Pa. 147 reference slip-pressure zeros differ from tiny native
nonzero values. These still fail a relative-only rule with zero absolute
tolerance; the investigation does not convert them to passing results.

The remaining three profiles are ITR.DW/DP/DH. Their old point-iteration values
are not saved, so they cannot be fully reconstructed from the archive. Their
maximum differences correspond to 8, 2 and 9 representable-number spacings
(ulps) of the respective stored W, P and H values. This measures numerical
scale, not a complete causal proof. Small archived/native property differences
and expression-order differences are known, but the archive's producing
CoolProp version and operation trace remain unknown.

No tolerances were increased and no equation was adjusted to remove these
failures. The successful nine-profile baseline establishes the original
regression requirement for this selected case; it does not establish bitwise
agreement of every diagnostic.

## Reproduce

Run from the project root and choose unused output paths:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_mixture_mrm_semantics.py tests\test_fields.py tests\test_transient.py -q
.\.venv\Scripts\python.exe -m openstream sample --framework mixture --output outputs\mixture-followup-repeat --quiet
.\.venv\Scripts\python.exe tools\verify_recovered_mixture.py reference_exports\recovered-mixture-02 outputs\mixture-followup-repeat outputs\mixture-followup-repeat-comparison
.\.venv\Scripts\python.exe tools\audit_mixture_diagnostics.py reference_exports\recovered-mixture-02 outputs\mixture-followup-repeat outputs\mixture-followup-repeat-diagnostics.json
.\.venv\Scripts\python.exe tools\verify_mrm_transient.py --output outputs\mixture-followup-repeat-mrm.json
```

The final command exercises both MRM integrators on the original 100-cell,
51-state transient schedule. Its checks are independent native residual
checks; no matching transient MATLAB reference has been recovered.
