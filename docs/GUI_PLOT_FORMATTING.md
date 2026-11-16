# GUI plot formatting verification

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

Hosted publication and verification are pending. These interface checks do not
establish additional MATLAB equivalence or experimental validation.
