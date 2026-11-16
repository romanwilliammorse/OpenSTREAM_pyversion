# Local graphical interface — 0.2.1

Double-click **OpenSTREAM GUI** on the Windows Desktop. The shortcut starts a
local server and opens your default browser at `http://127.0.0.1:8765`. It reopens
the existing server on subsequent launches. No MATLAB, account, internet
connection, external plotting service, or cloud execution is used.

1. The opening screen asks you to choose **Mixture**, **Two-fluid**,
   **Three-field**, or **Four-field**. The **Model** selector above the editor
   remains available when the sidebar is hidden.
2. Leave the reference values unchanged for the first run. Click **Check**,
   then **Run**.
3. In **Results**, the first figure provides the original axial-profile presets.
   Solid lines show Python results; dotted lines show the recovered MATLAB
   profiles where available. Drag to zoom; double-click to reset the axes.
4. Select **Initialization (pseudo-time)** to inspect the initialization states.
   These states are not a physical transient. Multifield runs also expose the
   **Mixture precursor** and its saved initialization dataset.
5. Choose **Add a plot** to make another independent figure. Select a dataset,
   quantity, state/node and component for each axis. For example, select
   mixture precursor `vapor.X` for X and physical-result `film.U` for Y,
   choosing the film's wall component. **Add series** adds another compatible
   curve to that figure. **Add legend** places its legend inside the upper-left
   plot bounds. Each added figure has its own **Save PNG** and removal controls.
6. Download **Inputs CSV**, **Boundary conditions CSV**, **Geometry CSV**, or
   **Results CSV** independently. **Download ZIP** still provides the original
   arrays, metadata, inputs, convergence history, verification report and plots.

The vector editor supports both axial slices at a selected state and time
histories at a selected node. Every selected axis must produce the same number
of values as its paired axis. Unequal lengths are rejected; values are never
silently interpolated, sorted or truncated. Equal-length vectors from different
grids or states are paired by their saved index, with that distinction shown.
Physical time and initialization pseudo-time remain separate. Nonfinite values
remain gaps in the plots. Additional series on shared axes must have matching
units; no automatic unit conversion is performed. Figure settings are retained
when switching saved runs within the current page session.

CSV downloads always use that completed run's saved inputs and arrays. Inputs
CSV contains the model and numerical controls; boundary conditions and geometry
have separate files. Typed JSON in `value_json` preserves strings, numbers,
booleans and array elements. Shapes and zero-based indices identify the elements.
Results CSV uses one row per saved numeric element across physical results,
initialization and any mixture precursor datasets. Columns retain quantity,
unit, dtype, array shape, full indices, time/node/component indices, time in
seconds, axial position in metres and value. `NaN`, `Infinity` and `-Infinity`
remain explicit. This long format includes diagnostic vectors and coordinate
arrays; it does not discard values that fail a physical review. Exports are
generated without rewriting original run files or rerunning a calculation.

Use **Import** to load input JSON and **Export** to save the current inputs.
The interface uses the OpenSTREAM website's logo, fonts and colors; detailed
field help and status explanations expand when needed.

Set **ID** in the Physical model inputs to name your case. The name appears in
the run title, saved-run history, and editor footer, preserving the spelling
you entered. Opening a saved run restores its submitted inputs and model.
Use **Saved runs** at the top left to hide or show the sidebar; its visibility
is remembered in this browser. Collapsing it does not change your inputs.

The editor exposes **163 input fields**: 102 model, 49 numerical controls,
5 geometry, and 7 boundary-condition values. It includes search, section links,
reference/default columns, units, source provenance, per-field reset, and an
edited-only filter. Inactive parameters remain visible with applicability
notes. Changing the framework loads that framework's original steady preset;
save edited inputs first if you want to retain them.

**Reference** means the TUTORIAL1 starting case. **Default** means the upstream
input-class default, which can differ from the case value. Four baseline presets
are supplied; edits create a custom case. Exact effective input identity is
checked on the server before permitting a baseline comparison. A custom run is
never labelled MATLAB-equivalent merely because its solver converged.

Arrays use JSON such as `[3.5, 2]`; matrices use rows such as `[[1], [0]]`.
`WPOWER` rows correspond to axial `WMESH` segments and columns to walls in
`PERIM`. `KTRELAX` accepts the quoted string `"NaN"` for the upstream automatic
sentinel. `CBTMULT` accepts a constant multiplier; general Python callables
remain available through the Python API. The GUI accepts exactly one steady
boundary record. Transient scheduling and arbitrary function editing are not
included in this release.

Three statuses are reported separately:

- **Convergence:** the native solver's convergence result.
- **MATLAB archive:** unchanged baseline physical and initialization W/U/H
  profiles, plus FourField base-film profiles and wave frequency, compared at
  `rtol=1e-8`, `atol=0`. Reference zeros must match exactly. The GUI comparison
  excludes supplementary diagnostics and embedded precursor histories; the
  broader earlier audit is documented in ALL_BASELINES_VERIFICATION.md.
- **Physical consistency:** Mixture and TwoFluid retain their implemented checks.
  ThreeField and FourField display **Informational diagnostics** for phase-volume
  closure, because the original MATLAB OpenSTREAM frameworks do not impose it
  as a convergence or acceptance criterion. Historical area-only rejection
  labels are displayed under this current policy; their original assessments
  remain unchanged in Run details and downloaded files. Pre-onset annular fields
  are initialization quantities. No experimental-validation pass is claimed.
  Executed database comparisons are documented in BARTOLOMEY_PILOT.md and
  LECORRE_REPRODUCTION.md; they do not automatically validate a GUI run.

Results on this machine are saved in `outputs/gui/<unique-run-id>/`, with
submitted inputs outside the numerical `output/` subdirectory. New runs never
overwrite earlier runs or archived baselines. Only one job runs at a time.
**Cancel** stops the isolated worker; completed earlier runs remain intact.
Closing the browser leaves the local server running so it can be reopened.

## Install or launch from PowerShell

From the repository root with 64-bit Python 3.12 installed:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock -r requirements-gui.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation -e '.[gui]'
.\tools\install_gui_shortcut.ps1
.\OpenSTREAM-GUI.cmd
```

For a standalone installed package, use `pip install 'openstream_python-0.2.1-py3-none-any.whl[gui]'`
or install the wheel followed by `requirements-gui.lock`, then `openstream-gui`.
The default standalone output directory is `%USERPROFILE%\Documents\OpenSTREAM\runs`.
For repository cloning and initial setup, see [the README](../README.md).

For a visible console server (Ctrl+C stops it):

```powershell
.\.venv\Scripts\python.exe -m openstream.gui_launcher --output-root outputs\gui
```

Use `--port 8766` if another application occupies port 8765, and `--no-browser`
when launching a server for automated tests. The service binds only to the
loopback interface. An OS lock prevents competing servers from using one output
directory; live workers surviving a server restart remain recoverable. A stale
lock file alone does not indicate a running process. Server logs are written
beside the selected output root; each run has a separate `worker.log`.
