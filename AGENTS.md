# OpenSTREAM project requirements

Roman W. Morse's project-wide instruction: **keep the governing equations and
closure models unchanged for this entire project.**

- Translate and preserve the pinned OpenSTREAM source and documented models.
  Correct a Python discrepancy only when source evidence confirms a translation
  error. Do not change the underlying model to obtain convergence or agreement.
- Numerical-control studies may vary explicitly authorized, source-supported
  input controls in separate preregistered cases. Keep physical inputs, closure
  coefficients and acceptance tolerances fixed unless the user explicitly
  authorizes a different study. Do not change application defaults implicitly.
- Preserve all original references, failed attempts, inputs and provenance.
  Keep native convergence, source agreement, MATLAB execution and experimental
  validation separate in the acceptance matrix and reports.
- No new closure, clipping rule, smoothing law or replacement numerical solver
  may be introduced as a remedy for a failed case.
- Maintain `docs/PROGRESS.md`, the acceptance matrix and reproducible outputs.
  Review this record when resuming work. MATLAB access is currently unavailable;
  continue useful native work without treating missing access as authorization
  to make an equivalence claim.
