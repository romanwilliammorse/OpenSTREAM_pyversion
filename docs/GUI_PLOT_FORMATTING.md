# GUI plot formatting verification

**Release status: withdrawn at the user's request.** The user reported
slowness and a hosted `FUNCTION_INVOCATION_FAILED` error after this release.
The GUI is being restored to pre-formatting commit
`ce67394295ac5b5de4a2cbb54b9c533e387dcd7d`. This document and its evidence
are retained as a historical record, not a statement of current GUI features.
The runtime log for request `gbvgb-1794791551007-ea69aa433ef7` at
`2026-11-16T01:12:33.992Z` shows a dependency-installation failure on
`POST /api/validate`: unpacking Plotly 7.1.0 into Vercel's temporary wheel cache
failed with `No space left on device (os error 28)`, installer exit 2 and Python
exit 1. This preceded application validation and solver execution. Other
observed installation failures mention NumPy, SciPy and CoolProp. All Python
modules and dependency declarations were unchanged; these logs do not prove
that the JavaScript update caused disk pressure. See
`outputs/verification/gui-rollback-01/`. Restored-release verification remains
pending. Passing tests below do not establish performance or reliability for
every hosted request.

Date: 2026-11-15. This update changes browser presentation only. No Python
module, solver equation, closure, physical input, numerical control, reference
array, saved calculation or CSV export is changed.

## Scope

The default GUI plot font is Times New Roman, with Times/serif fallbacks. Font
settings apply to labels, ticks, legends and hover text, including browser PNG
exports. Times New Roman is installed on the tested Windows machine; proprietary
font files are not copied into the repository or hosted application.

Both the original axial-profile figure and added figures expose axis labels,
numeric limits and tick controls. Blank labels use the automatic text. Enter
both limits or leave both blank for the automatic range.
Ticks can use automatic placement, a starting position plus positive spacing,
or explicit positions and optional matching labels. Reset axes restores the
automatic view even after interactive zooming. Custom labels only change text;
data and recorded units remain unchanged. Invalid numeric settings are rejected
explicitly. Figure titles remain absent from PNG exports.

Each series has independent line/point visibility, line pattern, marker symbol,
color, width and size. Original archived-profile overlays retain their dotted
default until changed explicitly. Settings remain separate by figure and run
within the current page session, as in the existing editor. They do not persist
through a page reload. Legends remain inside the upper-left plot bounds.

The red annotations in the user's screenshot identify controls to expose;
they are not interpreted as a request to color the axes red.

## Implementation and reuse

The existing MIT-licensed vendored Plotly library supplies
[axis limits/ticks](https://plotly.com/javascript/reference/layout/xaxis/),
[line and marker styling](https://plotly.com/javascript/reference/scatter/),
and [layout fonts](https://plotly.com/javascript/reference/layout/).
No new service or dependency is introduced. GitHub/Hugging Face component
evaluation for this editor is recorded in `GUI_RESULTS_EDITOR.md`; this update
continues using the selected renderer.

A fresh GitHub/Hugging Face search also considered Plotly's
[React chart editor](https://github.com/plotly/react-chart-editor), which is
MIT licensed and provides similar controls. It requires React and
react-plotly.js; the existing application uses a plain JavaScript frontend.
The existing Plotly API already supplies all requested formatting capabilities,
so introducing that separate editor and dependency stack is unnecessary.
No third-party editor source was copied. Maintenance/compatibility of that
alternative was not certified for the installed Plotly version.

## Verification record

Evidence is retained under `outputs/verification/gui-plot-formatting-01/`.

- 36 frontend checks passed, including 12 new formatting checks.
- 61 focused Python checks passed for cloud authentication/packaging, GUI
  exports and status reporting. The numerical suite was not rerun locally for
  this presentation-only change.
- The saved-vector audit checked 404 X/Y pairs from a retained FourField run:
  formatting leaves array values, shapes, units and the source document intact.
- Chrome on Windows rendered Times New Roman. Primary-figure limits, labels,
  spacing, invalid-limit rejection, and automatic reset after zoom passed.
- A two-series figure used mixture-precursor X against physical base-film and
  wave mass flow. Blue dashed squares and red triangles were independently
  confirmed in the rendered SVG. Explicit tick positions/labels rendered and
  were cleared when automatic ticks were restored. No console errors appeared.
- Save PNG produced `formatted-figure.png` (2100 by 1275 pixels), visually
  inspected for labels, limits, spacing, font, independent styles, upper-left
  legend and absence of a figure title. The browser download-event waiter
  timed out, but the actual completed file was recovered from Downloads and
  inspected; this was an automation limitation, not an export failure.

Published source commit: `2a10aa3ee39fae31cb04b0a2e3082610864a894b`.
Vercel production deployment `dpl_6iqY9Bw79YnEA1RW2XyDir1UvZyX` was observed READY
at https://openstream-py.vercel.app. `hosted-assets.json` records authenticated
JavaScript/CSS equality against that Git commit, anonymous asset denial, and
successful API access.
These interface checks do not establish additional MATLAB equivalence or
experimental validation.

The live browser check also passed. Fresh default FourField run
`4d0bb0a72b1d44e68d5424caa9bf0707` completed and displayed Converged,
Archived profiles agree, and Informational diagnostics. The two-series
formatting example rendered with the requested font, labels, ranges, ticks,
line pattern, markers and independent colors. The live PNG is byte-identical
to the inspected local example; see `hosted-browser-checks.json`,
`hosted-formatting-ui.png` and `hosted-formatted-figure.png`.

The broader GitHub Actions run
[43782808772](https://github.com/romanwilliammorse/OpenSTREAM_pyversion/actions/runs/43782808772)
completed successfully after hosted verification: 829 Python tests passed
with two warnings; 35 frontend tests passed; wheel and source distribution
builds passed. The CI frontend command excludes the separate cloud frontend
test, which is included in the local 36-test command. See `ci-completed.json`
and the retained CI summary in the evidence directory. The earlier pending
receipt is preserved as a timestamped observation.
