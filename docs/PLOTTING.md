# Plot saved OpenSTREAM results

`openstream.plotting.SavedResults` plots portable native output without running
a solver or recalculating any property or closure. It supports the saved
Mixture, TwoFluid, ThreeField and FourField schemas. NumPy reads the arrays;
Matplotlib is imported only when a plot or animation is requested.

From the project directory in Windows PowerShell:

```powershell
.venv\Scripts\python.exe examples\plot_saved_results.py --output outputs\my-saved-plots
.venv\Scripts\python.exe -m pytest tests\test_plotting.py -q
```

The example defaults to the existing original-tutorial transient calculation
in `outputs/verification/native-sensitivity-01/transient-0.1` and the four-field
sample in `outputs/fourfield_official`. Supply `--mixture`, `--fourfield` and
`--output` to use other result directories. It refuses an existing output
directory, saves five PNG figures and two GIFs, and records hashes of the exact
source archives and metadata. It never edits the numerical results.

## Python API

```python
from openstream.plotting import SavedResults

data = SavedResults("outputs/verification/native-sensitivity-01/transient-0.1")
print(data.quantities)       # exact saved quantity names
print(data.arrays["H"].shape)  # (time, node), read-only
print(data.units["H"])       # J/kg

figure = data.history("H", nodes=[50, 100])
figure.savefig("enthalpy-history.png", dpi=170)
figure = data.space_time("H", times=slice(0, 21))
figure.savefig("enthalpy-space-time.png", dpi=170)
data.save_animation("H", "enthalpy.gif", times=slice(None, None, 2), fps=8)

four = SavedResults("outputs/fourfield_official")
figure = four.axial("film.wave.FREQUENCY", walls=0)
figure.savefig("wave-frequency.png", dpi=170)

initial = SavedResults("outputs/fourfield_official", phase="initialization")
figure = initial.history("film.wave.FREQUENCY", nodes=[50, 100], walls=0)
figure.savefig("frequency-pseudo-time.png", dpi=170)
```

For interactive display, use a suitable Matplotlib backend and `plt.show()`.
`animate(...)` returns a `FuncAnimation`; retain that object while displaying
it. The example selects the Agg backend for reproducible file rendering.

| Method | Selection and result |
|---|---|
| `axial(quantity, times=-1, nodes=None, walls=None)` | Axial lines at exact saved times; returns Figure |
| `history(quantity, nodes=-1, times=None, walls=None)` | Time histories at exact saved nodes; returns Figure |
| `space_time(quantity, wall=None, times=None, nodes=None)` | Node-centred time/space heat map for one wall; returns Figure |
| `animate(quantity, times=None, nodes=None, walls=None, fps=6)` | Animated axial profiles; returns FuncAnimation |
| `save_animation(quantity, filename, fps=6, ...)` | Save GIF using Pillow; refuses overwriting |

Selections accept a scalar index, an increasing list of indices, or a Python
slice. All indices are **zero based**. Negative indices count from the end:
`nodes=-1` means the outlet and `times=-1` means the last saved state. `None`
selects all entries. Duplicates, reversed ordering, empty selections and
out-of-range indices are rejected. These arguments select array entries, not
physical coordinates. There is no interpolation, resampling, averaging or
conversion between wall and aggregate quantities.

The stored layouts remain `(time,node)` or `(time,node,wall)`. A two-dimensional
quantity has no wall dimension and rejects a wall argument. Line plots can
display multiple wall series. A heat map must select one wall when multiple
are available. The same rules apply to phase quantities such as `liquid.H`,
`vapor.W`, `film.W`, `drop.U`, and `film.wave.FREQUENCY`.

Physical results come from `results.npz`. Initialization results come from
`initialization.npz`, and their axes and titles explicitly say **initialization
pseudo-time**. Pseudo-time is a convergence trajectory, not a physical transient.
One-state steady output supports axial plots; a history, heat map or animation
requires at least two time entries. Initialization may contain more entries
than physical output and is always indexed against its own TIME coordinate.

Units come from `metadata.json`; missing or `UNRESOLVED` units are errors.
`unit="C"` converts a stored temperature in K by subtracting 273.15. Other
conversions are rejected instead of relabeling unchanged numbers. Nonfinite
values are retained in the archive and shown as visible gaps with a warning
and plot annotation; an entirely nonfinite selection is rejected. Such gaps
can legitimately occur in iteration fields that were absent from a state.

## Relationship to upstream plotting

The implementation was compared with upstream `SolverPlotter.m`,
`AbstractField.transient/plotzt`, and the framework `plotz`, `plott` and `plotzt`
methods at commit `a614c7173822a93c1e64ac28d1541cbac028cbd8`.

- Axial/time slicing and individual wall selection correspond to upstream
  `zIdx`, `tIdx` and `wall`, with explicit conversion to Python's index origin.
- `phase="physical"` and `phase="initialization"` replace MATLAB's REAL and
  NULL solve modes without mixing their time coordinates.
- Animation updates line data and displays the exact saved time on every
  frame, with fixed axes across the selected frames. `fps` controls playback
  only; it does not imply real-time playback, especially for irregular times.
  GIF frame durations have 10 ms resolution, so some requested playback rates
  are quantized (for example, 8 frames/s was encoded as 120 ms per frame by the
  installed writer). The title therefore labels playback rate as nominal.
- `space_time(..., reverse_time=True)` preserves the upstream option's actual
  operation: subtract the final selected time. It does not reverse the data.
- Heat maps show the saved nodal values with nearest-cell shading and actual
  coordinates. They do not reproduce MATLAB's default interpolated surface
  shading or its full 3D presentation.

Unknown plotting keywords raise `NotImplementedError`. Unported MATLAB
options include automatic annular-region masks, obstruction/onset overlays,
multi-panel field presets, dual axes, arbitrary plot-options cells, 3D views,
surface shading modes, MATLAB GUI playback controls, and MP4/AVI export. Some
upstream plots compute additional closures on demand; this module only plots
quantities actually present in `.quantities`. For precursor pressure, heat and
energy quantities in a multifield result, open its `mixture` subdirectory
explicitly. The module does not infer or silently recalculate missing fields.

The plotting implementation follows the current primary Matplotlib API for
[FuncAnimation](https://matplotlib.org/stable/api/_as_gen/matplotlib.animation.FuncAnimation.html),
[PillowWriter](https://matplotlib.org/stable/api/_as_gen/matplotlib.animation.PillowWriter.html),
and [pcolormesh](https://matplotlib.org/stable/api/_as_gen/matplotlib.pyplot.pcolormesh.html).
GIF export uses the existing Pillow dependency of Matplotlib, with no ffmpeg,
MATLAB, MATLAB Engine or Octave requirement.

## Verification evidence

`tests/test_plotting.py` uses numerical fixtures in all four saved-data schemas
to check exact line values, nonuniform coordinate selection, multiwall
orientation, pseudo-time separation, Kelvin-to-Celsius conversion, fixed
animation limits, exact animation frame values, GIF frame count/timing,
nonfinite gaps and explicit error paths. These fixtures test plotting behavior;
they are not solver or experimental-validation results.

The plotting test file passes all 17 tests, including a visible title annotation
when saved metadata reports `physical_consistency: false`. Existing native two-fluid
`liquid.H` and three-field `film.W` archives were also loaded and rendered
without solving. A fresh-process import confirmed that this module does not
eagerly import Matplotlib.

The example rendering is saved under `outputs/saved-result-plots-02` with input
hashes in `provenance.json`. Its mixture history and heat map are physical
0–5 s tutorial results. Its four-field history, heat map and animation show
the saved initialization trajectory. Viewing a smooth plot or animation does
not establish numerical equivalence, mesh/time-step independence, conservation
or physical validation; those claims remain governed by the verification
reports for the underlying numerical result.
The five static figures and representative animation frames were visually
inspected. All 26 mixture and nine four-field GIF frames were decoded;
`render_verification.json` records frame counts, timing and the static-render
comparison. It makes no additional numerical-physics claim.
