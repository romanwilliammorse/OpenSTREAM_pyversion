# Sawai numerical-control study: independent design review

Date: 2026-11-15. This design is specified before inspecting any new control-study predictions. The project-wide constraint is to preserve OpenSTREAM's governing equations and closure models. This study changes only named, source-exposed numerical controls in separately stored attempts; it does not change the production defaults, original failed case, mesh, model settings, boundary conditions or acceptance tolerances.

## Fixed question and initial grid

The case is Sawai entry 1, FourField, 100 cells, `RELAXTW=0.2 s`. The numerical wave mass-flow relaxation factor `RELAXWW` is distinct from the physical wave-frequency relaxation time `RELAXTW`; the latter remains fixed.

Use the full eight-case Cartesian grid:

| Numerical control | Values |
|---|---|
| RELAXWW | 0.5, 0.25, 0.1, 0.05 |
| MAXITER | 100, 250 |

The 0.5/100 combination is a fresh reference attempt, not a replacement for the saved corrected failure. Hold `RELAXWB=0.5`, momentum/frequency relaxation, `SSTSTEP=1 s`, `SSMAXITER=30`, onset/closure iteration limits and every `ERROR*`/`SSCONV*` value fixed. In particular, `ERRORWF=1e-4 kg/(s m)` retains its original strict inequality.

The source declaration in `upstream/+Inputs/Options.m:15` makes MAXITER a positive `uint8`. The planned larger value must therefore lie in the representable 1-255 range. A native value of 400 must not be described as the same source-supported setting. The selected 250 is larger than 100 and also preserves even iteration parity when comparing the previously observed two-cycle. No global option-validation or numerical-source change is needed for this study.

This grid isolates wave-mass relaxation and point-iteration budget, and permits checking their interaction without also varying base relaxation. Do not add a coupled base/wave relaxation grid after seeing results and call it preregistered. If the eight cases do not resolve the numerical question, freeze a separate follow-up design first.

Doubling SSMAXITER is not initially informative for a case whose original source temporal predicate already stops at 8 s. Retain the distinction between exhaustion of a temporal budget and temporal stopping with failed point iterations. A later temporal-budget variant is justified only if a study case actually exhausts that budget; preserve such an attempt separately.

## The small-increment trap

For an unclamped mass update with numerical relaxation alpha, the actual point increment obeys

`W_after - W_before = alpha*(W_proposal - W_before)`.

Reducing alpha can therefore make the unchanged point-increment test pass while leaving a larger unrelaxed equation defect. A native convergence flag alone is insufficient evidence that the previous cycle has been resolved at comparable numerical accuracy. Preserve that flag exactly as computed; add transparent supplementary diagnostics rather than changing the stopping predicate or adding a closure equation.

When actual proposal locals are captured, record `W_proposal-W_before` separately from relaxation and clipping. Do not divide the final clipped increment by alpha and assume that it equals the unrelaxed defect. A point observer should record only already evaluated values, preserve the unobserved solution, and cover all relevant nodes or disclose its restricted coverage.

## Source-equation residual and a fixed comparison scale

For each field phi=base,wave, each interior node j, the final initialization state n and the preceding stored state n-1, define the common-final-state mass residual

`R_phi[j] = W_phi[j] - W_phi[j-1]`

`           + (dz/dt)*(W_phi[j]/U_phi[j] - W_phi_old[j]/U_phi_old[j])`

`           - P_wet*MTOT_phi(final common state,j)*dz`.

R has units kg/s. `W/U` has units kg/m; multiplication by dz/dt gives kg/s. The source is kg/(m^2 s), so `P_wet*dz*MTOT` is kg/s. The associated unrelaxed proposal defect at this common state is

`D_phi[j] = -U_phi[j]/(U_phi[j]+dz/dt)*R_phi[j]`.

This follows algebraically from the existing OpenSTREAM mass-update expression; it is not a replacement equation. D has units kg/s. It differs from a defect observed inside the sequential point update because velocities, droplet mass and other fields can change later in that update. Label the two diagnostics distinctly.

Use the original reference relaxation, alpha_ref=0.5 for both mass fields, to define a fixed supplementary ratio across every candidate:

`q_phi[j] = 0.5*abs(D_phi[j])/(P_wet*ERRORWF)`.

Report this ratio and, if a supplementary screen is used, retain the strict `q<1` condition. This is equivalent to an unrelaxed defect below `2e-4 kg/(s m)`; its scale is derived from the unchanged original relaxation and point tolerance, rather than fitted to the new predictions. It is not an OpenSTREAM convergence criterion or a physical-validation gate, and it must never overwrite the solver's reported status. A lower-alpha native pass with q>=1 remains a numerical-adequacy concern in this comparison.

Save per-node MTOT, R, D and q, not only maxima. Evaluate on a copied final object graph after primary numerical arrays have been saved, preserving its original mixture/field handle relationships. Verify saved primary arrays and native state/flags remain unchanged after supplementary evaluation. Retain diagnostics and warnings from the copy separately. Fluid property objects are immutable and their existing deepcopy implementation returns the same protected object; do not bypass that contract.

Record full-interior maxima and a separately frozen unclamped annular mask from the corrected reference: j>=reference OAFIDX, reference base W>0 and reference wave W>0. Reuse that exact node set for every candidate; report each candidate's actual mask additionally. Keep the original onset definition and report all excluded nodes/counts. The qualification mask must be nonempty and its R/D/q values finite. A candidate that loses positive base/wave flows or usable finite velocities at those fixed nodes is ineligible for this unclamped-equation screen; do not silently shrink the mask. Record any observed projection/clipping corrections as well; positive final flows alone do not prove every earlier update was unclamped. Zero denominators or nonfinite source/velocity values must be flagged as unavailable/failed diagnostics rather than replaced by zero. Boundary node j=0 has prescribed data and is not an interior residual equation.

Also retain the raw steady residual `W_j-W_(j-1)-P_wet*MTOT*dz`, without the initialization storage term, as a descriptive quantity in kg/s. Do not apply a newly invented tolerance to this different residual or conflate pseudo-step consistency with physical experimental validation.

## Case assessment and isolation checks

Record these axes separately for every attempted case:

1. Execution completion, exceptions and all warnings, including unsuccessful cases.
2. Original source STATE, native point/temporal/frequency/nested/onset flags and elapsed time.
3. Per-node final increments, iteration counts, temporal histories, selected cycle observations and clipping information.
4. Reference-scaled common-state mass defects, raw mass residuals and descriptive steady residuals, with units and declared masks.
5. Finite-state checks and retained signed flow bounds; annular phase-volume information remains supplemental with no convergence role.
6. Differences in final W/U/frequency/period profiles between control settings, with absolute and reference-scaled differences. No post hoc profile tolerance is introduced.
7. Exact original-input/reference and source-hash checks, and exact comparison of mixture precursor result and initialization arrays.

MAXITER is passed through the common Options object and can affect the mixture precursor as well as FourField. Exact precursor comparisons are therefore necessary before attributing differences solely to the FourField point loop. If a precursor differs, report an isolation failure and its extent; do not silently substitute an old precursor or call the result a pure FourField-control effect.

A qualified numerical-control candidate means a separately identified numerical configuration satisfies the unchanged native convergence contract, original onset/nested checks, exact precursor identity and finite-state requirements, while both base/wave reference-scaled mass-defect ratios remain strictly below one on the nonempty fixed unclamped annular mask. The supplementary screen must also be applicable there as defined above. These diagnostics support a bounded claim of improved numerical adequacy. They do not mean that the frozen 0.5/100 attempt passed, that a new default is selected, that the solution is mesh-independent, or that MATLAB equivalence or experimental validation is established. Ranking may describe convergence cost and diagnostic magnitude; choosing a production default needs a separate decision and broader-case evidence.

## Review limits

This review inspected the pinned source declarations, current FourField mass update and diagnostics, the previous Sawai diagnostic and output structure. It runs no solver and changes no numerical source. Numerical-control results are not known at the time of this design. The source-preserving experiment can proceed without MATLAB access; the matched MATLAB runtime question remains open.
