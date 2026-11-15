# Results editor and CSV verification

Date: 2026-11-15. Scope: presentation and read-only export of saved native
calculations. No governing equations, closures, numerical controls, defaults,
reference arrays or scientific acceptance tolerances are changed.

## Delivered behavior

Completed runs offer separate Inputs, Boundary conditions, Geometry and Results
CSV downloads. Inputs include model settings and numerical options. Results use
one row per stored scalar, with dataset, quantity, units, original shape,
zero-based array/component indices and spatial/time coordinates. Physical time
and initialization pseudo-time remain distinct. NaN and infinity diagnostic
values remain explicit in CSV and become gaps in plots.

The original profile plot remains available. Add a plot creates another
independent figure. Each axis can select any saved quantity from the simulation,
initialization, mixture precursor or precursor initialization. Channel vectors
select a state; time vectors select a node. Wall/component axes remain explicit.
Vectors must have the same length after selection. Different grids, states or
vector directions are disclosed as pairing by index; no interpolation, sorting,
truncation or unit conversion occurs. Multiple series require compatible recorded
units on each shared axis. Each added figure supports Save PNG and removal.
Add legend puts the legend inside the upper-left plot area. Plot configurations
survive switching saved runs in the same page session, but are not saved across
page reloads. There are no titles embedded in exported figures.

Historical hosted runs obtain missing precursor-initialization plot data from
their original hash-verified NPZ artifacts without rewriting their manifests.
All cloud CSV routes use the existing password/session boundary. A complete CSV
is prepared before response headers and then streamed; preparation spills from
memory to a temporary file. Explicit limits are 16 MiB JSON metadata, 512 MiB
expanded data per archive and 512 MiB generated CSV. Original NPZ/ZIP downloads
remain available. Credentials and private storage URLs are absent from receipts.

## Evidence

Local HTTP verification:
`outputs/verification/gui-results-editor-01/local/20261115T233351Z-de26ad5e/receipt.json`.
The driver independently compares every exported scalar and exposed vector with
the original downloaded NPZ and submitted input files. It checks types, units,
shape, indices, missing/duplicate rows, signed zero and nonfinite values. It does
not import export implementation helpers or run the solver.

| Retained baseline | Result CSV scalar rows | Exposed field values | Datasets |
|---|---:|---:|---:|
| Mixture | 75,761 | 75,548 | 2 |
| TwoFluid | 98,603 | 98,172 | 4 |
| ThreeField | 83,747 | 83,325 | 4 |
| FourField | 100,112 | 99,687 | 4 |

All 358,223 result rows match exactly. Each case additionally has 216 input,
9 boundary-condition and 5 geometry scalar rows: 920 across four cases. The
FourField export retains 101 nonfinite initialization diagnostics. All 356,732
exposed field values agree with saved arrays, with nonfinite entries represented
as null gaps. Coordinates are checked separately.

Independent review also extracted all 101 precursor `vapor.X` values and all
101 final `film.U` values after selecting its singleton wall component; neither
array changed. Their units are dimensionless and m/s respectively. Browser
checks render this comparison, create a second independent figure, reject
1-versus-101 vector lengths, and place the legend inside the plot. Save PNG was
observed as a local downloaded image.

New automated tests cover exact export, corrupt artifact rejection before
response, immutable files/Blob data, unauthorized requests, incomplete runs,
resource bounds, stream cleanup, malicious textual cells and the independent
verification driver's detection of deliberate data corruption. Frontend tests
cover vector extraction, dimensions, units, state selection, missing data,
independent plot settings and internal legend placement. Full-suite and live
deployment results are recorded below after completion.

## Reproduction

```powershell
.\.venv-cloud\Scripts\python.exe -m pytest -q
node --test tests/gui_frontend_logic.test.cjs tests/gui_navigation.test.cjs tests/cloud_frontend.test.cjs
.\.venv-cloud\Scripts\python.exe tools/verify_results_editor.py --origin https://openstream-py.vercel.app --output outputs/verification/gui-results-editor-repeat
```

The HTTP driver prompts for the existing app password. It reads the four
retained baseline run IDs and compares them with their original artifacts in
`outputs/verification/hosted-http/20261115T175731Z-a0e1560b/`. Each invocation
creates a new dated evidence directory; no retained result is overwritten.

## Reuse and limits of the evidence

The existing vendored [Plotly.js](https://github.com/plotly/plotly.js) is MIT
licensed and maintained. Its [legend positioning](https://plotly.com/javascript/legend/)
supports the requested upper-left placement; local rendering requires no new
service or dependency. GitHub and Hugging Face reuse searches were completed.
The [MIT-declared intelligent-data-viz Space](https://huggingface.co/spaces/Yassineh13/intelligent-data-viz/blob/main/README.md)
uses Streamlit/Groq and reported a runtime error; the
[Streamlit data explorer](https://huggingface.co/spaces/JayroMartinez/streamlit-data-explorer/blob/main/README.md)
did not provide an identified license in the inspected README. Neither is a
suitable component for this Flask application; no code was copied from them.

This evidence establishes export/display fidelity for the tested saved arrays.
It adds no MATLAB-equivalence or experimental-validation claim. Existing
TwoFluid physical-review failures, FourField nonfinite diagnostics and Sawai
iteration sensitivity remain in the scientific record.

## Release checks

The first full regression pass reported 810 passed and two failures: a transient
Windows PermissionError while polling a worker's status file, and a checkpoint
test comparing the evolving GUI with a historical full-package fingerprint.
The status-read race was corrected with bounded retries. The current-release
test now explicitly exempts only `gui.py` and the new `gui_exports.py`, while
requiring exact recorded bytes for all 24 other existing top-level modules and
rejecting any other new/removed module. The original frozen replay manifest,
reference hashes and strict historical replay guards remain unchanged; replay
that exact historical checkpoint from its recorded checkout. This is a change
in the test's presentation scope, not an update of scientific reference data.

Final local regression: **829 passed**, with the two retained FourField
divide-by-zero/invalid-multiply warnings. All **24 frontend checks passed**.
The installable wheel and source distribution built successfully. Logs are
`pytest-final.txt`, `frontend-tests.txt` and `build.txt` under the evidence folder.
The acceptance integrity receipt preserves all 81 requirement criteria/status
axes and all 585 method classifications; only interface evidence and the GUI
source fingerprints changed.

Release commit `30f50efc36a0a3ee9e970d733c1fac13e8a6f190` was deployed as
`dpl_B7xFfaLN7SvkQppUResRyo7Pmiun`, READY at
<https://openstream-py.vercel.app>. Its
[GitHub Windows CI run](https://github.com/romanwilliammorse/OpenSTREAM_pyversion/actions/runs/43776224587)
passed. All four historical baseline CSV/vector checks also passed over HTTPS;
see `live/20261115T234316Z-71bbf5df/receipt.json` within the evidence folder.
Anonymous CSV access returned HTTP 401; login/logout succeeded. The FourField
results CSV was 10,521,009 bytes and streamed successfully. A browser download
had the same SHA-256 as the independently checked response:
`befc9c93238bb5fac90c20936eb5a0500a679385d19ad98b4e9d4255a64db05f`.

Fresh hosted FourField run `06d391c5a3f24635aef52631864dccf3` completed and
passed the unchanged archive comparison at rtol 1e-8, atol 0 (maximum reported
relative error 2.539607937805446e-9). Authentication, original downloads, array
shape checks and all four datasets passed. Numerical evidence is retained under
`fresh/20261115T234316Z-7f724d3d/`; its separate exact CSV/vector comparison is
`fresh-exports/20261115T234554Z-432d0204/receipt.json`. To repeat the latter,
run `tools/verify_results_editor.py` with its `CASES` tuple set to this one
FourField run and `--reference-root` pointing to that fresh evidence directory.
The same independent checks and no modified tolerances apply.

The hosted browser rendered precursor `vapor.X` against final `film.U`, with
the legend inside the upper-left plot bounds and all four CSV links visible.
`hosted-results-editor.png` records the interface; `cross-stage-plot.png` is
the downloaded PNG. The local browser also verified two independent added
figures, two series, per-run restoration, length rejection and PNG/CSV download.
No browser-console error was observed. The temporary local preview was stopped;
the hosted result tab remains open for use.
