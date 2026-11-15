# Independent four-field review

Reviewed `ff_fields.py` and `fourfield.py` against the pinned upstream commit
`a614c7173822a93c1e64ac28d1541cbac028cbd8`: FourField `Base.m`, `Wave.m`,
`Film.m`, `Drop.m`, solver initialization and `solve.m`, plus inherited
AbstractFilm and AbstractField behavior. This is a source and saved-native-data
audit, not a MATLAB execution comparison or experimental validation. No new
full solver run was performed for this review.

## Actionable findings

1. **Onset bounds:** four `EQUIL` branches originally retained `np.clip`, whereas
   upstream uses `max(min(guess,W),0)`. MATLAB's default NaN-omitting behavior
   requires `np.fmax(np.fmin(guess,W),0)` in that order. A NaN guess becomes W
   for positive W; `np.clip` leaves NaN. Reported to the owner for correction.
   The saved default onset residuals are finite, so this is not evidence that
   the saved sample changes. The MathWorks primary documentation for
   [min](https://www.mathworks.com/help/matlab/ref/double.min.html) and
   [max](https://www.mathworks.com/help/matlab/ref/double.max.html) specifies
   the default `omitmissing` behavior, including binary operations.
2. **Frequency residual export:** upstream initializes `ITR.DFW` but writes
   actual point frequency errors to `ITR.DF`. The port preserves that naming
   mismatch. At review time the exporter enumerated only the first state's
   keys, so both saved NPZ files omitted later states' actual `DF` and retained
   unused zero `DFW` arrays. Reported to the owner: export actual DF with Hz
   units and explicitly distinguish missing/unused entries. Base/wave
   physical-time-zero ITR values also remain their initialized zeros because
   the upstream final copy excludes ITR; final pseudo-time diagnostics are the
   relevant convergence evidence. This requires output handling, not a change
   to the transport equations.
3. **Upstream coefficient units:** Model.m labels all `WAVEDRAGCOEF` entries
   dimensionless, but `REV = rho_g * (U_g-U_w) * coefficient[0] / mu_g` requires
   the first coefficient to have length units. Dimensional consistency treats
   its default 0.02 as 0.02 m; the other two entries are dimensionless. This is
   an inferred documentation defect, not a reason to alter the correlation.

## Source behavior confirmed

- Initialization follows the actual order: initial unit base/wave arrays;
  onset drop equilibrium; cumulative film evaporation; algebraic base velocity;
  equilibrium or ratio film split; wave velocity set to half vapor velocity;
  saturated liquid enthalpies; equilibrium frequency; then constant pre-onset
  base flow with nonnegative compensating wave flow. The four-field third onset
  guess is interpolated, unlike the commented-out three-field branch.
- Film is dependent: `W = W_base + W_wave`,
  `U = W/(W_base/U_base + W_wave/U_wave)`, and H equals base H. The zero-total-W
  velocity fallback to base velocity is preserved.
- MATLAB copies base/wave arrays and rebinds their `.film` references, but keeps
  their `.mix` handles pointing at the physical precursor. Changing the parent
  film's pseudo-time `.mix` and calling `initializeBaseAndWave()` with no other
  arguments does not rebind those handles. The port explicitly restores this
  asymmetry. Base/wave TIME and DT also retain the original values; the sweep
  uses the parent film's pseudo-time DT, as the source does.
- Copy operations use MATLAB column-major linear `2:end`. Film's `all` option
  is not forwarded to the component copies upstream; the port retains that
  behavior. A single wall is explicitly required, avoiding unsupported
  multiwall linear-index formulas rather than silently changing them.
- Update order is base mass, wave mass, joint positivity operation, algebraic
  droplet partition, wave frequency, base momentum, wave momentum, and droplet
  momentum. Wave mass sees the newly updated base. Consequently, cancellation
  of contemporaneous exchange expressions does not prove exact cancellation
  of the sequentially evaluated transported sources.
- Positivity preserves the original combined film flow before flooring wave
  flow, then floors the compensating base flow. It is not a conservative source
  limiter. FULLNOP omits base gravity and pressure forces, as named upstream.
- Binary NaN bounds in the inspected base/wave closures and primary updates
  use `fmin`/`fmax` in the source order. Explicit NaN and infinity replacements
  in EPSILON, BETA, WIDTH, TBASE, and related dryout diagnostics match the source.
- Point convergence includes wave-frequency change. The original steady stop
  omits it. Python retains that original stop/STATE and separately requires
  frequency convergence for its stronger `converged` flag.

The dimensional audit found base/wave mass sources in kg/(m² s); multiplying by
perimeter and axial cell length gives kg/s. Their forces are N/m², and division
by liquid density times thickness gives m/s². Wave `DELTAFREQ` is Hz/m; the
discrete frequency update is in Hz. Spacing, amplitude, width and thickness are
in metres. No other equation or update-order discrepancy was identified in the
inspected single-wall path.

## Saved native evidence and limits

Independently opened `outputs/fourfield_official/results.npz` and
`convergence.csv`. All saved base/wave/drop W, U and H arrays are finite.
Base and wave W minima are zero; minimum drop W is 0.0117275733053 kg/s.
Minimum base/wave/drop velocities are 1.51836556948, 0.759182785082, and
1.51836557016 m/s. Frequency spans 21.0401216914–202.840033499 Hz.
Recomputed `base.W + wave.W - film.W` is exactly zero. The CSV has eight
pseudo-time advances, ending at 8 s with point convergence true and frequency
change 0.0603654303544 Hz, below the original 0.1 Hz threshold.

Metadata reports raw maximum base/wave mass residuals of
0.000430585693434 and 0.000424136966741 kg/s. These residuals were not independently
recomputed in this review and must remain visible; iteration convergence and
algebraic field partition do not establish full discrete conservation.

Evidence SHA-256 at inspection:

| Artifact | SHA-256 |
|---|---|
| results.npz | `420da282e72715a2d1bd72c1d506f07356e69a480b625a7edbcc217a5730e1ec` |
| convergence.csv | `5888809fa8bc1342a41f66d4a6e7596fff65af4b70a1d5c931b7a30beb9a03a1` |

This review does not establish MATLAB numerical equivalence, experimental
validity, four-field mesh/time-step sensitivity, transient accuracy, multiwall
support, or comprehensive closure-domain coverage. Energy remains supplied by
the precursor mixture; this framework does not independently evolve base/wave
enthalpy equations.
