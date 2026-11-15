# Changes

## 0.2.1 — 2026-11-14

- Match the local GUI to OpenSTREAM's website logo, fonts and colors, with
  shorter controls and expandable help. Preserve all 163 fields, units,
  reference/default values and separate verification results.
- Update usage and installation instructions; prepare the project for public
  publication as `romanwilliammorse/OpenSTREAM_pyversion`.
- Record the remaining parity plan and the inspected external
  OpenSTREAM-database validation targets. No experimental validation executed.
- Governing equations, closure implementations and reference tolerances unchanged.

## 0.2.0 — Local browser GUI

- Four steady baseline presets and a comprehensive 163-field editor with
  units, reference/default provenance, unsupported-option checks, and JSON files.
- Isolated cancellable calculation jobs, saved history, offline interactive
  plots, CSV/NPZ/PNG/ZIP downloads, and a Windows desktop launcher.
- Scoped checks of each unchanged run against bundled recovered MATLAB arrays;
  separate convergence/reference/physical statuses retain known area failures.
- Numerical governing equations and closure implementations unchanged.

## 0.1.1 — 2026-11-14

- Correct MRM vapor-enthalpy NaN/Inf fallback to match the original source.
  Other thermal models retain their original fallback. No governing equations,
  closures, convergence controls or reference tolerances changed.
- Recover all four original MATLAB MCOS baseline archives using isolated native
  verification tools, with original arrays, object links, units and provenance.
- Verify original W/U/H profiles, initialization histories and mixture
  precursors; additionally check actual four-field base and frequency profiles.
- Add a reproducible four-baseline runner, independent audits, adversarial
  comparator tests and reference overlays. Confirm selected steady occupied-area
  inconsistencies are also present in the archived MATLAB calculations.
- Clarify diagnostic messages so reference agreement remains a separate check.

This release remains a partial scientific port. Full feature/option coverage,
transient MATLAB equivalence and experimental validation are not established.
