# Sawai entry 1: exchange and thin-film source audit

Audit date: 2026-11-15. Scope: FourField, Sawai entry 1, `RELAXTW=0.2 s`, 100 cells, single wall, the existing corrected replay. This is a source review and independent inspection of saved native traces. It is not a matched MATLAB execution or experimental-validation result. No numerical source file was changed by this audit.

The source reviewed is OpenSTREAM commit `a614c7173822a93c1e64ac28d1541cbac028cbd8`. Native evidence is the corrected replay under `outputs/verification/matched-replay-01/native-after/sawai-01-paper-tw020-n100-base/`. The earlier outer-precursor correction is described separately in `replay_sawai_source_audit.md` and `MATCHED_DIAGNOSTIC_REPLAY.md`.

## Bounded finding

No additional active finite-state translation error was identified in the reviewed base/wave exchange formulas, signed Okawa deposition, thin-base equilibrium solve, positive-film clipping, or their sequential evaluation order. The saved final point iterations show alternating signs of droplet mass flow at all three failing nodes. The completed constituent trace identifies direct wave deposition as 98.87–99.75% of the final-pair wave-mass-source change. This is the dominant varying source term in the observed native two-cycle, not a full nonlinear-stability proof or a matched MATLAB result.

The final two-cycle is not accompanied by a switch between the thin-base equilibrium branch and the full base momentum branch, a failed nested secant solve, or an active zero clamp of base/wave film flow. Those alternative explanations can be excluded for the six final point iterations inspected here, not for every earlier iteration.

## Source-to-native checks

Paths in this table are relative to the repository; the MATLAB files are under `upstream/`.

| Quantity or operation | OpenSTREAM source | Native equivalent | Finding for the selected case |
|---|---|---|---|
| Base/wave deposition shares | `+Solvers/+FourField/Base.m:145–150,186–200`; `Wave.m:167–180,212–225` | `src/openstream/ff_fields.py:40–43,123,126` | Base uses EPSILON times BETA; wave uses the complementary share. Same single-wall dimensions and signs. |
| Turbulent exchange | `Base.m:202–219`; `Wave.m:228–240` | `ff_fields.py:44–48,127` | Same `min(abs(WLb), WLw)/WAVEMIXCOEF/WIDTH`, cap 10, and annular blend. The absolute value is applied only to base WL in both implementations. |
| Net exchange and opposing transfers | `Base.m:222–280`; `Wave.m:243–280` | `ff_fields.py:49–55,128–132` | Same evaporation, entrainment, deposition and thickness-relaxation signs; same positive/negative split and repeated turbulent exchange. No sign correction is justified by the method names or comments. |
| RISO target thickness | `Base.m:403–424` | `ff_fields.py:73–82` | Same coefficients, aggregate-film Reynolds number, aggregate film's vapor precursor, and half-hydraulic-diameter cap. |
| Base force with FULLNOP | `Base.m:283–383` | `ff_fields.py:56–72` | Same wall, wave shear, transferred-mass momentum, direct vapor shear and deposition forces; pressure and gravity omitted in both selected branches. |
| Wave force | `Wave.m:298–434` | `ff_fields.py:134–147` | Same drag, shear, pressure, gravity, deposition and base interaction terms. The previously documented floating-point grouping difference in FSHEAR remains; there is no causal evidence that it causes this finite two-cycle. |
| Signed droplet concentration | `+Solvers/+ThreeField/Drop.m:81–88` | `src/openstream/annular.py:154–156` | Both use absolute droplet W in the concentration denominator, then restore its sign. |
| Signed Okawa deposition | `Drop.m:159–187` | `annular.py:172–182` | Both use abs(CONC)+1e-6, the same coefficient and square-root law, reverse the sign for negative droplet W, and apply the annular blend. DEPENHANCEMENT=NONE. |
| Sequential mass update | `+Solvers/+FourField/@FourFieldSolver/solve.m:170–189` | `src/openstream/fourfield.py:215–223` | Base W is changed before computing wave MTOT. Wave W is then changed, positive-film constraints are applied, and droplet W is recomputed. Changing this to simultaneous source evaluation would change the algorithm. |
| Thin-base branch | `solve.m:219–234` | `fourfield.py:232–238` | Both test abs(base THICK)>THINFILMTHICK. At or below the limit they use UEQUIL without applying the outer RELAXUB factor. |
| Secant equilibrium solve | `+Solvers/AbstractFilm.m:329–357` | `annular.py:45–62,103–105` | Same current U, U+0.1 trial, secant formula, assignment-before-force-evaluation, iteration budget, force stopping tolerance, and final field-owned annular blend. |
| Wave thickness and frequency | `Wave.m:96–111,588–617,620–636`; `solve.m:198–202,249–260` | `ff_fields.py:113,164–173`; `fourfield.py:225–227,242–246` | Same amplitude/width/spacing construction, frequency relaxation and thin-wave momentum floor. No new closure is needed or inserted. |

The comparisons above concern finite scalar/single-wall values actually used by this case. They do not establish all-model behavior for NaNs, infinities, multiple walls, every optional correlation, MATLAB interpolation, or another property-library version.

## What the saved final iterations show

The following values come from `point_trace.csv` and `update_trace.jsonl` at pseudo-time 8 s, using zero-based node numbering. The grid is 0.01648 m. The point mass-flow criterion is the absolute iterate change per wetted perimeter, less than `1e-4 kg/(s m)`; it is not a relative mass error or a phase-volume criterion.

| Node | z (m) | Iteration 99 droplet W (kg/s) | Iteration 100 droplet W (kg/s) |
|---:|---:|---:|---:|
| 24 | 0.39552 | +7.503307511230739e-6 | -2.1268250318083604e-6 |
| 25 | 0.41200 | +6.639460312757653e-6 | -1.6556530384268658e-6 |
| 26 | 0.42848 | +5.935117183697956e-6 | -8.345217256092337e-7 |

At node 24, the wave MTOT values returned during iterations 99 and 100 are respectively `-0.3366425722045959` and `-0.19532619207855878 kg/(m² s)`. They use the droplet state left by the preceding iteration; droplet W is recomputed only after both film mass updates. Base MTOT values at the same two iterations are `-0.0336939976574418` and `-0.03392093543042424 kg/(m² s)`.

Wave W alternates between `0.0031134378650534648` and `0.0031230834813807417 kg/s` at that node. The associated per-perimeter increment is approximately `7.675963972e-4 kg/(s m)`, about 7.68 times the unchanged point tolerance. This is a diagnostic ratio, not an alternative acceptance threshold.

### Thin-base and clipping alternatives

At the six final iterations listed above, pre-momentum base thickness is approximately 47.23–57.62 micrometres, below the 100 micrometre switch. The calculation uses the saved base W/U, `PERIM=0.012566 m` and the recorded native saturated liquid density `823.1696030606413 kg/m³`. Both states of the alternating pair therefore take the same thin-base UEQUIL branch.

The six nested secants all stop after their first computed U2 (the third total force evaluation), with absolute trial-force residuals between `1.825947094294942e-5` and `3.3609855209351013e-4 Pa`, below the unchanged `UFEQUILTOL=0.001 Pa`. The force check applies to the secant trial before the source's final annular blend; it should not be misreported as a force-balance guarantee on the blended velocity.

All six base and wave mass proposals remain positive. POSFILM changes wave W by exactly zero and base W by at most `2.168404344971009e-19 kg/s` from saving the sum and subtracting wave W. It is therefore not an active zero-boundary crossing in this final pair. It would be incorrect to remove or modify POSFILM based on this observation.

## Algebraic interpretation and observed source decomposition

At one common evaluation state, with the same base/wave annular blend factor r, the opposing transfers obey

`MWAVE - MBASE = r*Mnet`.

The turbulent contribution cancels in that difference. Consequently, defining `E_b=MEVAP_b+MENT_b+MDEP_b`,

`MTOT_b = (1-r)*E_b + r*rho_l*(EQTHICK_b-THICK_b)/RELAXTB`.

This is an algebraic rearrangement of the retained source expressions for diagnosis, not a replacement implementation. Near r=1 the base mass source is only weakly sensitive to deposition, while the wave carries most of the net film deposition change. Because the solver updates base W before evaluating wave MTOT, the two separately evaluated source terms are not evaluated at exactly the same state; their same-state cancellation identity must not be presented as proof that an unconverged point iteration exactly conserves each discrete field equation.

For positive concentration C, the selected Okawa expression can be rearranged algebraically to

`MDEP = r_drop*s*0.0632*sqrt(sigma*C/D_h)`,

where `C=abs(CONC)+1e-6 kg/m³` and s is -1 when droplet W<0, +1 otherwise. This has units kg/(m² s). Near zero droplet flow, its square-root dependence and sign change create feedback through `W_drop=W_liquid-W_base-W_wave`; the observed constituent differences below identify this feedback as dominant in the retained final-pair mass-source change. The `1e-6` concentration offset also leaves finite one-sided signed limits at exactly zero. These are properties of the original selected source law; clipping the droplet flow, suppressing negative deposition, or smoothing that sign branch would change the retained source behavior.

The constituent trace is now complete. A separate, preregistered study of existing source-supported numerical controls is the next native investigation; it must retain the original failed attempt, governing equations and fixed convergence tolerances. The derivative calculation in the analysis receipt freezes other variables and is not an eigenvalue of the full sequential iteration. It cannot establish full-map stability or predict that a particular control change will converge without executing and checking that separate case.

## Completed constituent replay and independent review

The focused observer at `tools/trace_sawai_oscillation.py` records actual function returns and secant trials, with receiver classes and caller ancestry. Independent review found no extra closure evaluation or mutation of solver arrays: its state snapshots read stored base/wave/drop W, U, H and wave FREQUENCY, and copy small numeric locals before serialization. The 11 focused observer/provenance tests passed, including rejection of altered artifacts and incomplete trace windows.

`outputs/verification/sawai-oscillation-01/deep-trace/assessment.json` confirms exact numerical equality of all 215 archived corrected-reference arrays, including dtypes, shapes and values. The point, update and temporal trace files are also byte-identical to the retained corrected replay. `deep_trace_provenance.json` binds the executed observer, imported helper scripts, frozen manifest, numerical sources and artifact hashes; it confirms all 33 requested node/iteration groups (nodes 24–26, iterations 90–100, pseudo-time 8 s) and 22,770 detailed events. No additional numerical-source correction was made.

`deposition_cycle_analysis.json` reconstructs all 66 base/wave MTOT sums from direct-child returns exactly in source order. An independent extraction of the final two iterations reproduced the following constituent contrasts:

| Zero-based node | Wave MTOT change, iteration 100 minus 99 (kg/(m² s)) | Direct Wave.MDEP change (kg/(m² s)) | Direct deposition / total contrast |
|---:|---:|---:|---:|
| 24 | 0.14131638012603714 | 0.1409666766652726 | 99.7525% |
| 25 | 0.12154357569168725 | 0.1209831045111070 | 99.5389% |
| 26 | 0.09904939530803597 | 0.0979340357814805 | 98.8739% |

These ratios compare changes between two coupled native states. They are not fractions of total flow, physical errors, experimental accuracy scores, or isolated perturbation effects. At node 24, the underlying Drop.MDEP return in the wave-mass evaluation changes from `-0.048980787327754176` to `+0.09198783574460515 kg/(m² s)`; the droplet W used by those evaluations is the preceding iteration's value, respectively `-2.1268250318083604e-6` and `+7.503307511230739e-6 kg/s`. This timing is confirmed by the captured caller ancestry and primary state, so the final plotted droplet state must not be incorrectly paired with the source evaluated earlier in its own iteration.

## Attribution and acceptance consequence

The source audit supports the presence of the signed-deposition feedback and sequential update in both implementations. It does not establish that MATLAB with the exact same inputs and property backend reaches the same alternating states. That runtime claim remains unverified until matched MATLAB arrays/traces are available.

The original Sawai point-convergence failure remains open; its point tolerance, iteration budget, governing equations and closures remain unchanged. Numerical source agreement, native iterative convergence and agreement with experimental measurements are separate acceptance axes. No additional phase-volume convergence criterion is introduced for FourField.
