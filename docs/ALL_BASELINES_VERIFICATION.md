# Four archived OpenSTREAM baseline cases verified

Checkpoint: 2026-11-14, native package 0.1.1. All four original TUTORIAL1 steady
baselines pass their original W/U/H regression criteria: relative tolerance
`1e-8`, absolute tolerance `0`, exact reference zeros. All stored initialization
histories and embedded mixture precursors pass the same core comparisons.
The full port is not complete; these four cases do not cover all closures,
transients, public methods or plotting options.

The complete workflow was executed in dependency order by
`tools/verify_all_baselines.py`. Authoritative current results, original-archive
recoveries, comparison JSON, numerical arrays, provenance, logs and figures are
under `outputs/baseline-parity-02/`. Each framework has `reference`, `native`
and `comparison` directories; `summary.json` records the overall result.

## Results

| Framework | Original core profiles passed | Initialization states | Largest physical relative difference |
|---|---:|---:|---:|
| Mixture | 9/9 | 10 | 6.22214e-13 |
| TwoFluid | 6/6 | 15 | 5.75239e-14 |
| ThreeField | 6/6 | 6 | 1.22500e-13 |
| FourField | 9/9 | 9 | 2.53961e-9 |

Every physical profile was compared at all 101 nodes, without interpolation,
fitting or changed tolerances. Four-field also passes three actual base-film
profiles and wave frequency; these are explicitly additional checks because
the upstream test's `film.basefilm` spelling omits the actual `film.base`.
Its largest additional physical relative difference is 4.10782e-11, for
wave frequency. The four-field velocity difference is larger than roundoff
but remains inside the original tolerance; it is not described as bitwise
agreement. Individual and full-history errors are retained in the JSON reports.

The common original inputs are TUTORIAL1/DEFAULT/TUTORIAL1/tutorial1.inp:
6 MPa, 0.07 kg/s, 87.5 kW, inlet H=1,139,400 J/kg, length 5.5 m,
area 6.0821e-5 m2, perimeter 0.0276 m and 100 cells. Source interpolation,
discrete heating normalization, pseudo-time controls and model defaults were
retained. Known historical duplicate-zero defaults and interpolation-name
capitalization are disclosed; unexplained input changes fail comparison.

## What was recovered and what was calculated

Original MAT archives are preserved at upstream commit
`a614c7173822a93c1e64ac28d1541cbac028cbd8`; the property wrapper is preserved
at `a7c40902ff66faf6ed668986398bb1b9faa16e13`. Original hashes and license
notices are unchanged. The verification-only mat-io reader is isolated from
the numerical package; normal operation still requires no MATLAB, Engine,
Octave or reference-reader package.

- Mixture W/H and caches are stored. U and phase W/U/H are evaluated from
  recovered state and fluid constants using the preserved source methods.
- Two-fluid liquid/vapor W/U/H are directly stored.
- Three-field film/drop W/U/H are directly stored.
- Four-field base/wave/drop W/U/H and frequency are directly stored. Aggregate
  film W/U/H use the original dependent-property formulas and zero-flow fallback.

Extraction preserves original dimensions, class/property paths and object
references, including the two-fluid pseudo-time phases' intentionally shared
physical mixture handle. Raw arrays and object graphs remain available.
Independent audit scripts separately calculated the comparisons from raw MCOS
objects without using the exported profile arrays or native field methods.

The archives do not establish the exact producing source commit or CoolProp
version. This is agreement with preserved MATLAB-produced data, not a fresh
execution of a fully identified MATLAB environment. A serialized R2024b path
is only a runtime hint. Experimental validation was not performed.

## Physical findings shared with the MATLAB archives

Current policy amendment: ThreeField/FourField phase-volume residuals are
informational only, following the original MATLAB OpenSTREAM convergence
logic and the project owner's instruction. The area-only rejection and CLI
exit descriptions below document the historical audit policy. Current annular
CLI acceptance follows numerical convergence; the TwoFluid area criterion
remains active. All archived states, residual values and comparison results
are preserved. See [the current diagnostics review](LECORRE_PHYSICAL_REVIEW.md).

Occupied area was independently evaluated from saved phase flow, velocity and
density as `sum(W/(rho*U))` [m2], and compared with the specified channel area.
For annular frameworks, acceptance is restricted to the stored fully annular
region, where the transition function is at least `1-1e-12`; upstream
initialization/blending quantities are excluded.

| Archived framework | Maximum occupied-area discrepancy | Domain |
|---|---:|---|
| TwoFluid | 41.056107% | Full channel; maximum at z=0.22 m |
| ThreeField | 7.485259% | Fully annular; 72 nodes starting at z=1.595 m |
| FourField | 11.241052% | Fully annular; 72 nodes starting at z=1.595 m |

These discrepancies are present in the original stored MATLAB states and
reproduced by Python. They therefore are not introduced by this port in the
checked steady cases. Their physical inconsistency remains; no pressure,
velocity or governing equation was altered to enforce area artificially.
The two-fluid archive also has a steady outlet mass defect of
-3.076134e-7 kg/s and energy-flux defect of +30.049663 W. Matching a source
calculation does not validate its physical predictions.

Native CLI exit status **3** is intentionally retained for these three cases
because physical-consistency checks fail. The baseline runner records that
status and can still pass the separate archived-numerical-agreement check.
Its exit status 0 never means that those physical failures disappeared.

Previously reported transient discrepancies (43.3609% two-fluid area,
11.2004% three-field area, 15.5181% four-field area, and annular storage/mass
residuals) have **not** been matched to transient MATLAB references. Do not
extrapolate this steady-case evidence to those findings.

## Correction and diagnostic limitations

One numerical translation correction was needed outside the steady baseline:
MRM Vapor.H now substitutes HG for NaN only, while the other thermal models
retain the source NaN-or-infinity fallback. This is exact source-branch
behavior, not a new governing equation. Synthetic invalid-state branch tests
and the original MRM transient workflows were run. All mixture baseline arrays
remain bitwise unchanged after this correction. Details: `mixture_followup.md`.

The strict relative-only comparison still fails for some supplementary
diagnostics. Physical-state failures number 14 mixture, 6 two-fluid, 2
three-field and 1 four-field; initialization has additional annular iteration
differences. All remain failures in the reports. For mixture, 11 DP/material
derivative discrepancies were independently reconstructed from the small
stored-state differences; three iteration-increment discrepancies could not
be reconstructed because the intermediate point iterates were not archived.
No tolerance was relaxed. Tiny or exactly zero reference diagnostics require
special care when interpreting a relative-only criterion.

The comparator validates archive/export/input-copy hashes, source and wrapper
targets, gravity, effective inputs, units, axes, finite core values, original
point/temporal thresholds, and precursor convergence. Film mass convergence
uses W/PERIM [kg/(s m)]. Actual four-field frequency residual DF is checked;
unused DFW zeros cannot replace it. Missing iteration values are accepted only
at explicitly recorded absent rows; arbitrary NaNs or infinities are rejected.

## Reproduce

The reader and updated native package are installed in the project environment.
In PowerShell, from `C:\Users\Roman\Documents\ChatGPT\OpenSTREAM`:

```powershell
.\.venv\Scripts\python.exe tools\verify_all_baselines.py --output outputs\my-four-baseline-check
```

Choose an unused output directory. This recovers original data, runs the four
native solvers, compares all baseline/initialization/precursor arrays and saves
PNG/SVG overlays. It requires neither a MATLAB installation nor an account.
The one-time optional-reader setup, if reproducing in a fresh checkout, is in
`tools/REFERENCE_READER.md`.

Focused regression and adversarial tests can be repeated with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests tools\test_recover_mcos_reference.py tools\test_recovered_mixture_comparison.py tools\test_recovered_twofluid.py tools\test_recover_annular_reference.py tools\test_recovered_framework.py -q
.\.venv\Scripts\python.exe tools\test_reference_comparator.py
```

The actual-reference tests expect the retained checkpoint fixtures in this
workspace. The complete suite log/JUnit XML are in `outputs/baseline-parity-01`.
The executed combined suite passed **212 tests in 88.84 s**, with three
documented warnings: one optional-reader pandas deprecation and two retained
four-field zero-slip drag warnings. The 212 comprise 129 native tests and
83 recovery/comparison tests, not a branch-coverage percentage.
The separate fresh-export comparator has 34 passing synthetic tests; its MATLAB
export script remains unexecuted. Detailed extraction/audit records are in
`twofluid_baseline_audit.md`, `annular_reference_audit.md`, and
`framework_comparator_review.md`.

## Remaining parity work

Baseline agreement is **4/4**, covering these four steady cases. Full-software
completion remains unquantified: alternative closure combinations, transient
reference comparisons, operating-domain coverage, unsupported options, public
API/input writers and remaining post-processing need individual acceptance
criteria and evidence. Additional approved transient/option reference outputs
would extend equivalence evidence; experimental data are a separate validation
requirement. Retained upstream defects must be documented before any proposed
model change. See FEATURE_MAP.md and PROGRESS.md for the current gaps.
