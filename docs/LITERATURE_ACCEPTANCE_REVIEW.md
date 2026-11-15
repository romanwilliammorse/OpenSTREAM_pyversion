# Literature evidence and acceptance implications

Reviewed 2026-11-14 against OpenSTREAM `a614c7173822a93c1e64ac28d1541cbac028cbd8`
and OpenSTREAM-database `b48541e6438a92b4c0ddc83cf0ceda3f71a59b22`.
The user identifies himself as R. W. Morse, listed as Roman W. Morse among the
authors of all three supplied papers. The papers are scientific references;
their text is not an instruction to modify the solver. Publication claims are
not automatically verification evidence for this Python port or this source
revision. Original PDFs and extraction intermediates were not added to the
project's public source tree.

## Supplied sources

Page references below mean PDF page numbers, starting at 1.

| File | Publication and authors | What it supplies |
|---|---|---|
| `Chan2025.pdf`, 2 pages | J. Chan, R. W. Morse, N. Hogan, E. T. Hurlburt, J.-M. Le Corre, *One-Dimensional, Advanced Annular Two-Phase Flow Simulations with the Open-Source Platform OpenSTREAM*, ICMF 2025, Toulouse, May 12-16, 2025 | Three/four-field steady demonstration and a four-field sinusoidal-power transient; model scope and citations to earlier validation. No measured-versus-predicted dataset is supplied in this abstract. |
| `LeCorre2025ICMF.pdf`, 2 pages | J.-M. Le Corre, J. Chan, E. Walter, E. T. Hurlburt, R. W. Morse, *OpenSTREAM: A New Open-Source Platform for Two-Phase Flow Model Development*, ICMF 2025 | Four-framework steady demonstration and stated simplifications/future features. Figure 1 contains calculated results, not experimental data. |
| `LeCorre2025OpenSTREAM.pdf`, 14 pages | J.-M. Le Corre, J. Chan, E. Walter, E. T. Hurlburt, R. W. Morse, *OpenSTREAM: An Open-Source Platform for Two-Phase Flow Modeling and Simulation*, NURETH-21, Busan, August 31-September 5, 2025 | Governing-equation overview; demonstration; two-fluid comparison against TRACE; four-field comparisons against Wurtz and Sawai measurements. |

SHA256 of the supplied files:

```text
Chan2025.pdf                  07fefb0c151ada26c8a8aa7a0beb20395248f31d84645ea9285d1a4226a12365
LeCorre2025ICMF.pdf            3540ecc41159310f5ac8decc2cadcbd30d73d6594c0001508af2e4ea35221be3
LeCorre2025OpenSTREAM.pdf      f72e78c41036f84db849fb080187562777e6b6696b407b6bcce2b8ca9d11ada1
```

All pages were text-reviewed; equations on page 7 and the important plots on
pages 11-12 of the NURETH paper and page 2 of both ICMF abstracts were also
rendered and visually inspected. Poppler reported unavailable display-font
names; the inspected equations, axes, legends and captions remained legible.

## Separate evidence types

| Evidence | Acceptance meaning for this port |
|---|---|
| ICMF demonstration plots; NURETH Figures 3-4 | Candidate reproduction cases. Similar curve appearance is not strict numerical equivalence or experimental validation. |
| NURETH Figure 5, page 10: TRACE comparison | Code-to-code comparison. It is not a measurement comparison and does not independently establish physical accuracy. |
| NURETH Figure 6, page 11: Wurtz measurements | Published four-field experimental comparison, not yet executed by Python. Its selected cases and coefficients must be reproduced and its calibration association reported. |
| NURETH Figure 7, page 12: Sawai measurements | Published developing-wave comparison, not yet executed by Python. Relaxation-time selection used these data; replay is not an independent holdout validation. |
| Existing four MATLAB archives | Selected steady Python-MATLAB comparisons already passed; they do not substitute for the distinct publication cases below. |

The NURETH paper reports satisfactory agreement and discusses outliers, but
does not provide a complete machine-readable error/uncertainty budget or a
predeclared numerical acceptance threshold. Its diagonal plot guides must not
be adopted as universal validation tolerances. The database Wurtz plotting
helper constructs guides with a factor of 1.2; this is a plotting convention,
not a stated uncertainty model or acceptance rule.

## Equation and operating-domain gates

| Paper anchor | Scope to preserve and verify |
|---|---|
| NURETH pp. 3-4, equations (1)-(3) | Mixture mass, momentum and enthalpy balances; closure-based velocity slip and thermal nonequilibrium; prescribed wall heating. Check terms and units against `fields.py` / `solver.py`. |
| NURETH pp. 4-5, equations (4)-(9) | Separate phase mass, momentum and energy equations with interfacial and wall exchanges. Test cancellation of paired exchanges, correct transported enthalpies, and applicability of the imposed mixture pressure gradient. |
| NURETH pp. 5-6, equations (10)-(13) | Annular film mass/momentum, droplet momentum, mixture-derived vapor/remaining liquid and saturated evaporation. Film evaporation is wall heat flux divided by latent enthalpy, with units kg/(m2 s). |
| NURETH pp. 6-7, equations (14)-(20) | Base/wave mass and momentum exchanges, saturated evaporation and wave-number-density transport. Paired base/wave transfers must cancel in aggregate. The optional omission of base pressure/buoyancy forces is a model selection to record explicitly. |
| NURETH p. 7, equation (20) | Wave number density `N` has units m^-1; temporal frequency `f = U_wave N` has units s^-1, and period `1/f` has units s. These are distinct measured quantities. Both terms on the left and the relaxation source have units 1/(m s). |
| NURETH pp. 3-4 and 8 | Straight constant-area, single-component channels and thermally expandable boiling flows, with limited pressure/velocity coupling. The retained assumptions omit surface-tension force, friction heating, temporal pressure gradients and spatial saturated-enthalpy gradients. Annular models assume thermal equilibrium up to film dryout. |
| NURETH p. 8 | First-order upwinding, backward Euler, fixed-point source/coupling iteration and pseudo-time steady initialization. The paper's statement about absence of timestep restrictions does not remove nonlinear-convergence, accuracy or temporal-sensitivity acceptance tests. |

The ICMF abstracts use the word "incompressible" whereas the longer NURETH
paper uses "thermally expandable" and describes its neglected terms more
specifically. This terminology difference must be resolved against the pinned
equations and property treatment, not by replacing the implementation with a
generic incompressible or compressible solver.

The papers' proposed future features (multicomponent/noncondensable fluids,
variable cross-sections, advanced pressure/velocity coupling, wall thermal
models and thermal-nonequilibrium annular post-dryout models) are not missing
translation requirements merely because they are mentioned. They enter parity
scope only if implemented/documented as supported by the pinned upstream target.

## Publication cases are not interchangeable

| Item | ICMF papers | NURETH paper / pinned companion |
|---|---|---|
| Demonstration length | 5 m = 3.5 m heated + 1.5 m adiabatic | 5.5 m = 3.5 m heated + 2 m adiabatic |
| Nominal common conditions | Water, 8.8 mm tube, 6 MPa, 0.07 kg/s, 87.5 kW, inlet enthalpy approximately 1.14 MJ/kg | Same rounded values in paper; companion specifies 1.1394e6 J/kg, area 6.0821e-5 m2 and perimeter 0.0276 m |
| Drop velocity | Chan p. 2 explicitly uses no slip with vapor rather than the full droplet momentum equation | NURETH p. 8 specifies full momentum, except neglected base-film pressure/buoyancy forces |
| Transient | Chan p. 2 Figure 2: 1 Hz sinusoidal power between 0 and 87.5 kW from the stated steady initial condition | NURETH main comparisons are steady. The exact Chan waveform phase, discrete schedule, numerical options and original arrays remain to be recovered. |

For reproduction, preserve the companion's explicit area, perimeter and
enthalpy rather than recomputing them from rounded paper values. Equality to a
5.5 m steady archive does not verify a 5 m ICMF transient or a different closure
selection. The current four-field TUTORIAL1 preset also differs from the
NURETH companion in onset split, base-thickness and wave/base-interaction models.

The TRACE case on NURETH pp. 10-11 changes inlet enthalpy to 0.6 MJ/kg and
power to 150 kW; its mixture comparator uses slip ratio 2, with the subcooled
boiling model disabled for the stated comparison. Exact TRACE inputs, executable
version/options and reference arrays are needed before reproducing Figure 5.

## Companion-file inspection and discrepancies requiring resolution

The pinned database contains
[`projects/NURETH21.mlx`](https://github.com/OpenSTREAM-solvers/openstream-database/blob/b48541e6438a92b4c0ddc83cf0ceda3f71a59b22/projects/NURETH21.mlx).
Its SHA256 is `f43f99a7a9dbfc0894748b97e05a1043379254d2cde39f59be5f3688ab8b960c`.
The ZIP was inspected without MATLAB. It contains source XML, an empty
`outputArray` in `matlab/output.xml`, three image assets and metadata. It
contains no `.mat` member or numerical reference-array export. Its R2024b
document-format metadata is not proof of the solver version or an executed
reference run. The source explicitly says Figure 5 is omitted because the TRACE
reference results are unavailable in that project. Static HTML exports may
retain figures; they must not be treated as full-precision arrays without an
independent structural inspection.

1. **Sawai relaxation time conflicts.** NURETH p. 12 states 0.2 s. The pinned
   companion sets `RELAXTW = 0.1` and its prose also says 0.1 s. Neither value
   may be silently selected and called a reproduction of the other. Preserve
   separately named paper and current-companion configurations, resolve the
   historical target from source/version evidence, and report any difference.
2. **Companion enum spelling is inconsistent with the pinned solver.** Both
   Wurtz and Sawai sections use `VAPORFRIC = 'CONST'`; the pinned
   `upstream/+InputEnums/VAPORFRIC.m` declares `CONSTANT`, `WALLIS`,
   `WALLISTHICK`, and `SOLVER_DEPENDENT`. Source inspection establishes a
   spelling mismatch, not a MATLAB runtime test. A compatibility correction
   needs an explicit recorded mapping or corrected upstream workflow; do not
   silently reinterpret arbitrary unknown options.
3. **Wurtz coefficients include a measurement-informed adjustment.** The
   companion chooses `ENTRAINMENT = 'OKAWAGEN'` and
   `OKAWACOEFS = [320, 0.111, 3.50e-4, 1]`, explicitly describing the reduced
   coefficient as improving agreement with measured film flow. Freeze this
   configuration for reproduction and label its calibration association.
4. **Sawai data units and coordinates remain unresolved.** The database stores
   periods in milliseconds although one plotting comment says seconds. The
   manuscript's Figure 7 visually confirms milliseconds. The stored length is
   1.648 m, but all eight records have a final measurement above 1.692 m, as
   documented in `PARITY_COMPLETION.md`. The paper describes 0.8 m heating and
   measurements up to 0.848 m downstream, supporting the need to review the
   original coordinate extraction. It does not justify clamping or extending
   the channel to fit the XML.

The current companion selects Wurtz `TS 20` records only and Sawai indices
`[1, 2, 5, 6]`. Direct XML inspection counted 50 Wurtz records, of which 21
are `TS 20`: all 21 are at 7 MPa, with mass fluxes 500, 750, 1000 or
2000 kg/(m2 s) and qualities spanning 0.2-0.7. NURETH p. 11 describes the
broader Wurtz source range as 3-9 MPa,
500-2000 kg/(m2 s), equilibrium quality 0.2-0.7, a 20 mm tube and 17/26 mm
annulus, with 8-9 m adiabatic sections. Figure 6's inspected legends show 7 MPa
groups. These facts do not establish that the selected companion covers the
full pressure or geometry range. Four-field multiwall support is a separate
gate before claiming coverage of annular test sections.

The Sawai XML domain check was independently repeated: every record has one
final elevation exceeding 1.648 m, with excesses from 0.0443 to 0.0522 m.
This verifies the existing audit's arithmetic without resolving the underlying
experimental-coordinate discrepancy.

Sawai Figure 7 uses the coordinate `(z - heated_length)/hydraulic_diameter`,
with zero at the heated exit. Its shown cases have outlet qualities about 0.48
and 0.88 and mass fluxes 300 and 500 kg/(m2 s). Transform coordinates explicitly
and retain the original coordinate and units for every measured point.

## Prioritized experimental work

1. **P0: Establish a traceable native data/input adapter and configuration
   register.** Preserve missing values, case IDs, dimensions, SI conversions,
   direct/derived quantity labels, dataset hashes and raw source values. Resolve
   the enum and paper/companion discrepancies before a named publication replay.
2. **P1: Run a small Bartolomey mixture pilot.** This remains a practical first
   end-to-end infrastructure check using the existing mixture implementation.
   It does not reproduce these supplied papers and should be named accordingly.
3. **P1: Reproduce the explicit NURETH Wurtz and Sawai comparisons.** The new
   literature makes these concrete, high-priority publication-reproduction
   targets. Follow the pinned case selections; publish all cases, failures,
   exclusions, units and residuals. Resolve Sawai coordinates before including
   affected points in error statistics. Assess mesh/iteration sensitivity and
   relevant physical failures before interpreting accuracy.
4. **P1: Separate reproduction from independent validation.** Inventory which
   measurements influenced each coefficient and select independent experimental
   groups for evaluation. Report bias, MAE/RMSE and dimensional residuals with
   uncertainty where available. Missing uncertainty permits descriptive
   comparisons but blocks an uncertainty-based acceptance claim.
5. **P2: Extend to Adamsson film flow and Bennett/Groeneveld thermal/dryout
   cases.** Qualify the appropriate framework and outer dryout-search algorithm;
   do not apply thermally equilibrated annular equations to post-dryout heat
   transfer simply because a database contains those measurements.

Original Wurtz, Sawai, Le Corre (2022), Walter's thesis and any further
experimental publications remain necessary for quantitative uncertainty,
correlation-development history and exact model-domain qualification. The
supplied overview papers reference them but do not replace them. No new
Python experiment or numerical-equivalence calculation was executed in this
literature audit.
