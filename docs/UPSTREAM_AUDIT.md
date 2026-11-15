# Upstream audit and reference procedure

Audit date: 2026-11-14. This file records source inspection and reference-export infrastructure. Numerical test results belong in the verification report; neither this audit nor successful exporter/comparator tests establishes MATLAB equivalence.

Later checkpoint on the same date: the mixture archive was successfully decoded
without MATLAB and compared. See MIXTURE_BASELINE_VERIFICATION.md and
tools/REFERENCE_READER.md. The earlier ordinary-SciPy inspection below remains
accurate, but its inability to decode MCOS is not a requirement to run MATLAB.
Statements below about no actual comparison describe that earlier checkpoint;
the mixture's nine core comparisons have now passed.

## Preserved source

The unchanged clone is `upstream/`, obtained with `git clone --recurse-submodules`. The source anchor is OpenSTREAM `a614c7173822a93c1e64ac28d1541cbac028cbd8`, version `2026.0`, commit timestamp 2026-09-25T14:34:02-05:00. Its sole registered submodule, `+CoolPropWrapper`, is `a7c40902ff66faf6ed668986398bb1b9faa16e13`, timestamp 2026-09-25T14:00:35-05:00. Original license notices remain at `upstream/LICENSE` and `upstream/+CoolPropWrapper/LICENSE`; both use MIT terms, with their distinct copyright notices retained. The wrapper pins CoolProp 8.0.0 and also lists `nanobind` for its MATLAB integration.

`upstream_inventory.json` records all 41 model/option enumerations. Inspected source groups contain 7 input files (2,180 lines), 41 enumeration files (790 lines), 4 session files (466 lines), and 27 solver files (16,227 lines), excluding the property submodule, tutorials and documentation. Line counts describe source volume, not implementation completeness.

Important source locations:

| Subject | Preserved source |
|---|---|
| Official sample | `docs/source/Usage/runSampleScript.rst` |
| Sample inputs | `inputs/models.inp`, `options.inp`, `geom.inp`, `tutorial1.inp` |
| Governing equations, closures and numerics | `docs/source/Guides/theory/`, `+Solvers/` |
| Operating limits | `docs/source/Usage/scope_and_limitations.rst` |
| Input defaults and validation | `+Inputs/`, `+InputEnums/` |
| Tutorials 1–9 | `tutorials/*.mlx`, rendered `docs/source/_static/html/tutorial*.html` |
| Regression procedure | `tests/integration/SolverIntegrationTest.m` |
| Input/environment tests | `tests/unit/InputUnitTest.m`, `tests/environment/PythonSetupTest.m` |

The official sample selects **model TUTORIAL1**, options DEFAULT, geometry TUTORIAL1 and `tutorial1.inp`. The exploratory sandbox example instead selects model TUTORIAL2A. They should not be conflated when selecting reference inputs. The official steady case specifies 6 MPa system/inlet pressure, 0.07 kg/s mass flow, 1.1394 MJ/kg inlet enthalpy and 87.5 kW heating, with 3.5 m heated and 2.0 m unheated segments. The ideal steady enthalpy increase is 87,500 W / 0.07 kg/s = 1,250,000 J/kg, giving 2,389,400 J/kg outlet enthalpy. This is an independently computed balance target, not a MATLAB solution.

## Applicability retained from upstream

The formulations are one dimensional, use cross-sectional averages, and assume a straight channel of constant area. Multiple wall perimeters and nonuniform heating can represent tubes, annuli, simplified bundles and other equivalent channel shapes. These are not network, crossflow or three-dimensional CFD solvers. Flow is single-component, thermally expandable, and the demonstrated emphasis is co-current boiling flow. Thermophysical-property availability for another fluid does not validate the closures for that fluid.

The mixture and two-fluid frameworks include hydrodynamic and thermal nonequilibrium options. Three- and four-field formulations apply to annular flow and initialize separate film/drop fields at modeled annular onset; they generally assume thermal equilibrium. The four-field formulation additionally separates the base film and disturbance waves. Detailed fields depend on the mixture calculation, including its pressure gradient; three/four-field vapor quantities come from that mixture solution. Their implementation order therefore follows mixture → shared phase/film closures → two-fluid and three-field → four-field.

Upstream uses first-order upwind finite volumes, backward Euler, fixed-point iteration, and pseudo-time advancement for steady initialization. Pseudo-time history is not a physical transient. Mesh, time step, iterative tolerance, under-relaxation and transition initialization affect results. Reaching an upstream convergence state alone is not numerical verification or experimental validation.

## Regression archives: actual inspection

All four `tests/integration/references/TUTORIAL1-TUTORIAL1-DEFAULT/*.mat` files are MATLAB 5.0 containers with an MCOS object, not exported arrays. Using the project's Python environment with **SciPy 1.18.1**:

- `scipy.io.whosmat` raised `TypeError: 'NoneType' object is not iterable` for every archive.
- `scipy.io.loadmat` read `solver` as `MatlabOpaque`, with the original solver class and object metadata. It did not reconstruct usable field arrays.
- Headers identify Linux-generated archives created on 2026-08-23. They do not identify the original MATLAB, Python, CoolProp or source revision precisely enough to assume them.

`reference_archive_inspection.json` retains the observed headers, SHA-256 digests, file sizes, load results and SciPy version. The archives have not been changed. Parsing opaque metadata without faithfully reconstructing MATLAB objects would not create trustworthy numerical references.

The upstream integration suite checks four framework states, inlet pressure/mass-flow/enthalpy, mixture energy balance, transfer from final pseudo-time state to first physical state, save/reload, and W/U/H distributions. Field regressions use **relative tolerance 1e-8 and absolute tolerance 0**, so reference zeros require exact zeros. The energy test uses relative tolerance 1e-3 and absolute tolerance 1e-6 J/kg. The suite does not comprehensively test all pressure, void, exchange-term, transition, transient or closure combinations.

## MATLAB availability and export

No `matlab` or `octave` executable was found on PATH or under the checked standard `C:\Program Files\MATLAB` / `C:\Program Files\GNU Octave` locations. This is a bounded local availability check, not a search of every disk or evidence about account access. No MATLAB installation, license or MATLAB Online access is assumed. The port's normal execution does not use MATLAB, MATLAB Engine or Octave.

`tools/export_matlab_reference.m` is supplied for a separately available MATLAB environment. It is **not yet execution-tested in MATLAB**. It uses the unchanged upstream class API, copies the original input files, records effective model/options/geometry/boundary inputs, exports numerical arrays as 17-significant-digit CSVs, and writes a JSON manifest with array dimensions, units, convergence state and software metadata. Each output folder must be new; existing references are never overwritten. Known units are explicit; any optional diagnostic whose unit has not yet been audited is marked `UNRESOLVED`, never silently dimensionless. Source arrays containing NaN/Inf retain them in CSV. The exporter supports all four frameworks and both fresh runs and existing approved object archives.

On MATLAB Online, upload the preserved `upstream/` tree **including `+CoolPropWrapper`** and the `tools/` folder, or clone recursively in its environment when available. On any MATLAB host, first confirm Python/CoolProp import, using the upstream tested compatibility matrix as guidance. The preserved CI specifies MATLAB R2024b/Python 3.11, R2025b/Python 3.12 and R2026b/Python 3.13. Matching CoolProp 8.0.0 is important. Do not interpret a missing combination as automatically incompatible, or assume MATLAB Online can install/import required native modules without checking.

Run from the project folder in MATLAB:

```matlab
pyenv
py.importlib.import_module('CoolProp.CoolProp')
addpath('tools')
export_matlab_reference('upstream','reference_exports/sample')
export_matlab_reference('upstream','reference_exports/approved-mixture',Source='approved')
export_matlab_reference('upstream','reference_exports/twofluid',Framework='TwoFluid')
export_matlab_reference('upstream','reference_exports/threefield',Framework='ThreeField')
export_matlab_reference('upstream','reference_exports/fourfield',Framework='FourField')
```

Inspect `manifest.json` and `export.log`. The manifest must say `complete: true`; core W/U/H evaluation errors abort export. Optional method errors remain explicit. A fresh run's runtime metadata describes the solver execution. An approved-object export's runtime metadata describes **the exporter**, not the original archive producer. Require the recorded source and wrapper commits to match the anchors above; an unavailable Git executable leaves an explicit metadata limitation.

For the native mixture output schema, run in PowerShell:

```powershell
.\.venv\Scripts\python.exe tools\compare_matlab_reference.py reference_exports\sample outputs\sample --report comparison-sample.json
.\.venv\Scripts\python.exe tools\test_reference_comparator.py
```

The comparator requires matching source/submodule commits, clean source status, CoolProp versions, original input file digests, effective inputs (including G and sampled CBTMULT), convergence evidence, Z/TIME coordinates, core units, exact dimensional structure and finite core quantities. It now covers all four frameworks, recursively checks mixture precursors, and compares physical/initialization histories. Original W/U/H tolerances are unchanged; additional histories/base/frequency checks are explicitly provisional. It does no interpolation, exits nonzero on any failed comparison, and refuses to overwrite a report file. **34 synthetic comparator tests passed**; these test the machinery, not OpenSTREAM numerical agreement. No actual MATLAB comparison has been performed. The exporter explicitly traverses actual four-field `film.base`; the regression's `basefilm` spelling must not silently omit it. See REFERENCE_COMPARISON.md for the exact policy and known limitations.

## Reuse search

GitHub repository search (`OpenSTREAM language:Python`), an upstream fork listing, public web searches for a Python mixture-solver port, and Hugging Face model/dataset/Space API searches were performed on 2026-11-14. No compatible native thermal-hydraulic OpenSTREAM port was identified. This is a search result, not a proof that none exists. Five public forks were listed; identifiable active alternatives remained MATLAB projects. Unrelated streaming/media/VPN projects sharing the name were rejected. Hugging Face returned no model or dataset match; `yashm/OpenStream` is an MIT Streamlit app generator (source inspected), unrelated to two-phase thermal-hydraulics.

| Candidate | Maintenance/license inspected | Suitability and decision |
|---|---|---|
| [OpenSTREAM](https://github.com/OpenSTREAM-solvers/openstream) | MIT; upstream push 2026-09-25; 926-commit repository at inspection | Reuse governing implementation directly through translation and preserve source. |
| [CoolProp](https://github.com/CoolProp/CoolProp) | MIT; active, push 2026-11-14 | Reuse native Python AbstractState interface; retain upstream BICUBIC&HEOS choice and fixed system-pressure treatment. |
| [PyFluids](https://github.com/portyanikhin/PyFluids) | MIT; push 2026-06-30; maintained Python wrapper | Not an OpenSTREAM solver. Extra unit conventions/default Celsius and percent handling would complicate equivalence; use CoolProp directly. |
| [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause-style license text inspected; active 2026-11-14 | Reuse arrays/elementwise algebra with explicit dimensions. |
| [SciPy](https://github.com/scipy/scipy) | BSD-3-Clause; active 2026-11-14 | Reuse numerical and MAT inspection utilities where semantics match. |
| [Matplotlib](https://github.com/matplotlib/matplotlib) | Matplotlib license text inspected; active 2026-11-14 | Reuse plotting; solver remains independent of plots. |

The direct API searches are reproducible through [GitHub repository search](https://api.github.com/search/repositories?q=OpenSTREAM+language%3APython&per_page=100), [upstream forks](https://api.github.com/repos/OpenSTREAM-solvers/openstream/forks?per_page=100), and Hugging Face [models](https://huggingface.co/api/models?search=openstream), [datasets](https://huggingface.co/api/datasets?search=openstream), and [Spaces](https://huggingface.co/api/spaces?search=openstream). No code from unrelated candidates was copied.

## Suspected upstream defects and consequences

These are source-inspection findings, not demonstrated MATLAB failures. Do not silently repair them during translation.

1. `AbstractField.copyFlowProperties`, approximately lines 214–260, loops over target objects but always writes `targetObj(1)`. When passed multiple targets, later objects appear not to be copied. Current single-target calls may not expose this.
2. The same routine preserves inlet conditions with MATLAB linear indexing `(2:end)`, including wall matrices and struct arrays. Column-major indexing preserves only the very first scalar; inlet entries of walls 2 and later are overwritten. A Python slice `[1:, :]` would change that behavior and therefore may change multiwall transients or near-wall initialization. Preserve the observed semantics or explicitly reject the affected scope until reviewed.
3. Mixture `solve.m` sets SOLVEDNOTCONVERGED on point-iteration exhaustion but can later set INITIALSTEPCONVERGED when temporal changes satisfy thresholds. A small inter-step difference can therefore coexist with an unresolved point iteration. Report point convergence independently from the upstream state code.
4. The successful physical-transient path does not clearly assign SOLVEDCONVERGED after advancement. A state label alone cannot distinguish successful transient completion from initialization; retain explicit completion/history metadata.
5. Standard field properties use a fluid object constructed at each boundary-condition **system pressure**, not a property update at the solved local axial pressure. This is a deliberate upstream modeling convention unless demonstrated otherwise. Substituting local pressure would change density, quality, pressure losses and boiling onset and would not be a faithful port.

Experimental validation remains separate from all of the above. The companion OpenSTREAM-database is not an upstream submodule. No experimental cases have been executed or claimed validated in this work.
