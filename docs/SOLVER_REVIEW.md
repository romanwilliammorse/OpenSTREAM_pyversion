# Source review of solver translations

Reviewed against unchanged upstream `a614c7173822a93c1e64ac28d1541cbac028cbd8` on 2026-11-14. This is source/algebra inspection plus the explicitly identified native checks below. It is not a MATLAB numerical comparison or experimental validation.

## Mixture

The native axial sweep retains the upstream order: save old point values, update mass, integrate pressure from the upstream pressure with the source pressure-gradient components, update mixture enthalpy, then update thermodynamic/void caches before the MRM vapor equations. The backward-Euler old-time inventory and old-point velocity factors were inspected. MRM Euler and exponential expressions were checked algebraically against the MATLAB branch; the same relaxation parameters and source evaluations are retained. Physical-time and pseudo-time arrays are separate native states.

An initial translation called `Mixture.update(j)` unconditionally after assigning H(j). MATLAB's property setter discovers changed entries; when the assigned value is bitwise unchanged, the empty selection invokes an all-node update. This matters for cache refresh when W/P have changed but enthalpy has not. The implementation was corrected to call `update(None)` in that case. An instrumented three-node native run with `RELAXHM=0` observed all-node updates and unchanged H. No physical coefficient or tolerance was changed.

MATLAB uses one-based, column-major indexing. Native primary scalar fields are `(node,)`, wall-dependent fields `(node,wall)`, and saved output adds time as the first axis. MATLAB linear `(2:end)` copies are reproduced with explicit Fortran-order flattening where applicable; they omit only the first scalar, which is an upstream multiwall concern rather than a justification to silently omit every wall's inlet. Arrays used for old iteration/time values are copied, avoiding NumPy view mutation.

## Two-fluid

The six sequential equations in `twofluid._advance` were independently compared with `+TwoFluid/@TwoFluidSolver/solve.m`: liquid mass, vapor mass, liquid momentum, vapor momentum, liquid enthalpy, vapor enthalpy. Source normalization by the saved point-iteration W/U, the 1e-3 kg/s momentum/energy cutoff, momentum limits, relaxation and convergence controls agree algebraically. The phase clone's shallow `.mix` handle is intentional and matches MATLAB `matlab.mixin.Copyable`; reconnecting those phase links would change the calculation.

Review identified a missing supplied-precursor boundary-condition compatibility check; the two-fluid owner added equality checking of the effective BC records. Review of all individual two-fluid closures is not complete. The native energy deficit reported in the integration evidence must remain visible; equation agreement alone does not validate conservation under the source cutoff.

## Annular and four-field

Base/wave mass exchange, source evaluation order, equilibrium/full momentum, wave-frequency relaxation and onset initialization were compared with `Base.m`, `Wave.m`, `Film.m`, `Drop.m` and the four-field constructor/sweep. The source's four-field third onset-equilibrium iteration explicitly interpolates; the corresponding three-field branch is commented out. The implementations intentionally retain that difference.

MATLAB's binary `min`/`max` omit missing values by default. NumPy `minimum`/`maximum` propagate NaN and are not equivalent. For example, the original four-field dry-film split computes `min(0/0,1)`, which must produce one, not NaN. Native `fmin`/`fmax` preserve these semantics, including the source's nested velocity clamp order. This is a language translation correction. It is also a limitation of the source: a nonfinite intermediate force can be masked by the clamp. See [MathWorks min](https://www.mathworks.com/help/matlab/ref/double.min.html) and [MathWorks max](https://www.mathworks.com/help/matlab/ref/double.max.html).

Four-field `Film.copyElement` independently copies base/wave arrays and rebinds their `.film`, but their `.mix` remains the physical-time-zero precursor. The pseudo-time film's `.mix` is separately replaced. Native code retains that handle arrangement. Base copies W/U/H; wave copies W/U/H/FREQUENCY; neither copies ITR. Aggregate film copy ignores its `all` argument upstream, and the native method retains this behavior explicitly.

Four-field source convergence omits `timeDFw` despite a defined `SSCONVFW`. Native `STATE` preserves that stopping predicate, while `.converged` additionally checks frequency convergence and nested closure failures. No tolerance was relaxed. This stronger acceptance flag does not alter calculated arrays.

## Pending evidence

No MATLAB installation/runtime was available for execution. The portable exporter remains unexecuted in MATLAB. No numerical-equivalence claim follows from these reviews, native tests, or plots. Mesh/time sensitivity, supported branch coverage, raw conservation residuals and failures must be taken from the current verification reports rather than inferred from this document.
