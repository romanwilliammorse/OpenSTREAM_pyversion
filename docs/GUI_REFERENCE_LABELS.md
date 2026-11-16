# GUI reference labels and custom cases

Date: 2026-11-15 (America/Chicago). Presentation change only; only the checks
explicitly recorded below are claimed, never inferred from a reference label.

The unchanged ThreeField and FourField starting cases display
`Referenced against “Le Corre 2025”`. The expanded details give the full
citation: J.-M. Le Corre, J. Chan, E. Walter, E. T. Hurlburt and R. W. Morse,
*OpenSTREAM: An Open-Source Platform for Two-Phase Flow Modeling and
Simulation*, NURETH-21 (2025), Figures 3–4. The short author-year label also
identifies reference curves in plot legends.

R. W. Morse supplied the association of the three/four-field references with
the attached Le Corre manuscripts. The NURETH demonstration uses a 5.5 m
channel (3.5 m heated plus 2 m adiabatic), as does TUTORIAL1. The separate
Le Corre ICMF abstract and Chan 2025 demonstration use a 5 m channel; they
are not silently substituted for this case.

The actual numerical comparison still uses the immutable recovered
`tutorial1_ThreeFieldSolver.mat` and `tutorial1_FourFieldSolver.mat` archives.
The expanded details identify that target explicitly. Direct provenance of
these archives to the published curves remains unverified; the manuscript
association is not a new full-precision paper-data comparison. Existing paper
digitizations remain separate evidence under `references/paper/lecorre2025`.
The archive producer's source, MATLAB and CoolProp versions remain unknown.

Mixture and TwoFluid retain the source label `OpenSTREAM TUTORIAL1` because
no manuscript association has been assigned to their current GUI references.
“Chan 2025” and “Dunbar 2025” were examples of the requested short-label style,
not instructions to attribute an unsupported paper to a model.

A selected run shows a comparison only when its server-assessed input record
explicitly identifies the unchanged baseline and contains no reported edits.
Custom or ambiguous cases hide the reference status card and reference curves,
including stale reference arrays that may be present in old saved plot data.
Changing an unsent editor form does not relabel the selected saved result.
Native convergence and informational diagnostics remain separate.

Only the shared browser presentation and its checks change. Governing
equations, closure models, defaults, solver controls, reference arrays,
tolerances, saved results and backend comparison logic remain unchanged.

Verification evidence: `outputs/verification/gui-reference-labels-01/`.
The 38 frontend/navigation/cloud checks passed, including custom-case
suppression, reference provenance and unchanged raw plotting values. All 100
focused Python checks passed (schema, reference, local GUI, frozen numerical
source hashes and web isolation). Local browser inspection confirmed the short
default-case label, expanded provenance and reference legend names. A saved
FourField Run1 with two changed inputs had no visible reference card and only
four native legend entries. Screenshots are `local-default.png`,
`local-custom.png` and `local-custom-summary.png`.

Production deployment `dpl_4zFCxCirTLYD1psbUtrWipiZw2EA`, commit
`19edeca09c0d71eb837c1f6a4615f06626fa967d`, passed the 26-request HTTP campaign
in `hosted-http.json`. Checks covered matching JavaScript/CSS after newline
normalization, exact Plotly renderer bytes, authentication, all four baseline
validations, saved FourField CSV delivery and six concurrent reads. The
separate `hosted-reference-policy.json` passed all eight cases: each unchanged
framework was reference-eligible and each version with `NNODES=200` was
ineligible. No new calculation was submitted by these checks. Hosted API and
asset checks are distinct from the local visual inspections above.

GitHub CI workflow `43792594208` passed for the same source commit: 849 Python
tests with two retained FourField numerical warnings, 38 frontend checks,
isolated web-runtime/dependency checks and installable-package builds.
The receipt is `github-ci.json`. No scientific acceptance criterion or status
is promoted by this presentation change.
