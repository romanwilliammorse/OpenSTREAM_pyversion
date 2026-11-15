# GUI verification — 0.2.0

Verified locally on Windows with CPython 3.12.14, 2026-11-14. This release adds
the graphical interface. The existing solver equations and closures were not
changed. Comparing the earlier baseline source hashes identified only three
changed existing Python modules: the version in `__init__.py` and neutral plot
titles in `output.py` / `multifield_output.py`. New GUI modules are separate.
The preserved upstream checkout and CoolPropWrapper submodule remain clean.

## Executed automated checks

- **213 pytest tests passed**, with two existing four-field initialization
  warnings (division by zero in wave drag and its subsequent invalid product).
  They remain visible in the log; they did not invalidate the finite compared
  baseline profiles. Log: `outputs/verification/gui-release-tests.log`; JUnit:
  `outputs/verification/gui-release-tests.xml`.
- That total comprises 129 existing native tests and 84 GUI tests: 39 input
  schema/validation tests, 29 reference tests, 8 OS-lock tests, and 8 backend/job
  tests. The backend tests execute all four real solvers, plus an edited mesh,
  invalid pressure, cancellation, a property-domain failure, output downloads,
  local request restrictions, and failure reporting.
- **5 JavaScript logic tests passed** using Node's built-in test runner:
  `tests/gui_frontend_logic.test.cjs`. These test primary-profile grouping,
  exclusion of diagnostic derivatives, time-aligned reference overlays, and
  input schema version validation. JavaScript syntax also passed.
- `pip check` passed in the project environment and separate wheel environment.
  An installed wheel outside the source package ran a real mixture worker,
  passed reference and physical checks, served all local assets, and exposed
  all four 163-field schemas. See `outputs/verification/gui-wheel-smoke.log`.

Reproduce the main checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
node --test tests\gui_frontend_logic.test.cjs
.\.venv\Scripts\python.exe -m build --no-isolation
```

Node is only used to check frontend logic during development; it is not a GUI
runtime dependency. Numerical equivalence tests for recovery-tool internals
from the earlier archive audit were not rerun here; those files and references
were unchanged.

## Actual local app runs and browser checks

All four unedited baseline presets completed in the local app, saved new
outputs, and passed the bundled comparisons at `rtol=1e-8`, `atol=0`, with exact
reference zeros. The GUI compares primary physical and initialization profiles;
FourField also includes actual base-film W/U/H and wave frequency. No
interpolation is used to make comparisons pass. Known supplementary diagnostic
disagreements and unknown archive producer versions remain outside this claim.

Mixture passed its stated consistency checks. TwoFluid, ThreeField and FourField
reported their known failed physical area checks separately from passing
reference agreement. These failures were not converted to numerical crashes or
hidden by changing tolerances. See the saved `gui_verification.json` files under
`outputs/gui/` and the earlier ALL_BASELINES_VERIFICATION.md for scope.

The actual rendered browser interface was inspected, including the input
editor, reference/default columns, mixture profile, four-field wave frequency,
separate status cards, and annular-domain warning. Search, invalid negative
pressure, per-field reset, framework change, real runs, cancellation, saved
history, initialization state selection, precursor pressure, JSON save/load,
and PNG export were exercised. The downloaded JSON passed server validation
and matched the baseline; the downloaded PNG decoded at 2100 by 1275 pixels.
No browser error or warning logs were reported during these checks.

The Desktop shortcut was created with the project's `pythonw.exe` and launcher
arguments. The launcher module's existing-server path was tested; the GUI was
opened and verified through the browser-control tool. Direct shell activation
of the shortcut was blocked by automatic tool policy, so no claim is made of
observing a physical double-click on the shortcut.

## Failures corrected during development and remaining limits

Initial integration exposed NumPy boolean JSON serialization, a resolved
solver-default adapter, and mixed-unit chart grouping. These were corrected;
new checks preserve raw solver-dependent defaults, serialize scalar types,
and keep diagnostic derivatives out of phase-profile groups. An initial wheel
smoke environment lacked dependencies; installing both pinned requirements
files in the isolated environment resolved that setup error.

Only four steady starting cases and one boundary record are offered. General
`CBTMULT` functions, transient scheduling, and full MATLAB plotting/API parity
remain outside this GUI. All declared inputs remain visible, but individual
closure combinations have their existing unsupported/unverified statuses.
Keyboard/screen-reader accessibility was not independently audited; explicit
labels and keyboard-native controls are present. No fresh MATLAB execution or
experimental validation was performed for this release.
