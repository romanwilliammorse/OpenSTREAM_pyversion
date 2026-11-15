# Python API and operating conventions

All solver implementations are independent of plotting. Importing the numerical core does not import pyplot. Matplotlib is loaded only by plotting/output operations. Native CoolProp supplies thermophysical properties at one prescribed system pressure per time step, matching upstream; the calculated axial pressure is not fed back into the equation of state.

## Inputs

`Model`, `Options`, `Geometry` accept `file_path`, `identifier` and uppercase overrides. `InputSet.from_files` parses the original four input sources. `InputSet.official_sample(input_directory=None)` selects model TUTORIAL1, options DEFAULT, geometry TUTORIAL1 and tutorial1.inp. This is the documentation's sample; the upstream sandbox uses TUTORIAL2A instead.

Inputs are copied and revalidated by solver construction. Unknown fields, unknown enum values, malformed numerical entries, invalid geometry/boundary values and unsupported expressions fail explicitly. MATLAB function handles in input files are not executed. Python callables may supply CBTMULT via the API; metadata includes evaluated values on the computational mesh, but an arbitrary callable's full behavior is not serializable.

Axial/time interpolation supports linear, nearest, next, previous, pchip, spline and makima. Only methods named in test evidence are numerically checked. MATLAB's ambiguous `cubic` name is rejected. Original axial-next interpolation, inlet exclusion from power integration, and linear fallback for exterior NaNs are retained. `NNODES` is the number of cells: node count is `NNODES+1`.

`Geometry.ANGLE` is in **degrees from vertical**, as defined in upstream Geometry.m and all gravity/drift equations. The original geom.inp description incorrectly labels it radians. The unchanged sample uses zero, so this inconsistency has no sample effect. No angle conversion was silently changed.

## Solver classes

`MixtureSolver(inputs).solve(progress=None)` returns the solver. Physical states are in `mixture`; pseudo-time states in `mixtureInit`. `TIME` and `Z` are coordinate arrays. `STATE` retains the upstream enum. `converged` additionally checks final point convergence; temporal convergence alone is insufficient. `history` contains step summaries. The complete state-wise point increments are in `state.ITR` dictionaries.

`TwoFluidSolver(inputs, mix_solver=None)` constructs/solves a required precursor mixture when none is supplied. `liquid`, `vapor` hold independent phase `W/U/H` arrays; `mixture` supplies aggregation methods. `liquidInit`/`vaporInit` hold pseudo-time histories. Read `twofluid_notes.md` for preserved source handle relationships and source cutoffs before interpreting phase energy balances.

`ThreeFieldSolver(inputs, mix_solver=None)` transports film and entrained droplets, with vapor and pressure gradient from its `mixSolver`. `film` and `drop` hold physical-time states; `filmInit`/`dropInit` hold pseudo-time states. Film `W/U` have a wall axis. `onset_diagnostics` records equilibrium iterations and the upstream tolerance-fallback rule. Conservation of the film/drop/mixture mass split is distinct from residual convergence of each field equation.

`FourFieldSolver(inputs, mix_solver=None)` exposes `film[k].base`, `film[k].wave`, aggregate `film[k]` and `drop[k]`, with wave `FREQUENCY` in Hz. Only one wall is supported. Native `converged` also requires frequency change below SSCONVFW, which the original steady predicate omits. See FEATURE_MAP.md for exact supported/tested selections. No assumption of full option parity is warranted from an available class name.

## Physical transient from original input

```powershell
.\.venv\Scripts\python.exe -m openstream run --inputs upstream\inputs --model TUTORIAL2D --boundary tutorial2_transient.inp --output outputs\transient
```

Or construct `InputSet.from_files` and change `options.TSTEP`. Each physical step starts from the previous solution with current inlet data. The initial state first undergoes pseudo-time convergence. Boundary schedules are interpolated to the colon-style time grid; the last requested endpoint is not forcibly appended if the step does not divide the interval.

## Outputs and plotting

`solver.save(new_directory)` writes portable arrays, units, effective inputs, input-file hashes and convergence information. NumPy archives use no pickled objects and can be read with `np.load(path, allow_pickle=False)`. The metadata uses string `NaN` for upstream input sentinels, rather than invalid JSON numbers. Numerical arrays preserve IEEE values, which must be checked before use.

`MixtureSolver.plotz(filename=None, time_index=-1)` returns a Matplotlib figure with six axial panels. The output layout follows the documented sample's quantities; this is a native plot, not MATLAB style/interactive-object parity. `save` writes a headless PNG. Annular/phase output contains separate native framework plots plus complete precursor mixture output.

`from openstream import SavedResults` exposes solver-independent saved-array plotting: `SavedResults(directory).history('H', nodes=-1)` for outlet histories, `.space_time('H')` for a map, and `.save_animation('H', 'new.gif')` for GIF export. Select `phase='initialization'` for explicitly labelled pseudo-time plots. See PLOTTING.md for all four schemas, wall/time/node slicing, temperature units and unsupported plotting options. Full MATLAB styling, grouped diagnostic displays, 3D/video export and saved MATLAB object compatibility remain incomplete.

Boundary diagnostics `bc.TSAT(fluid)`, `bc.HF(fluid)`, `bc.HG(fluid)`, `bc.TIN(fluid)`, `bc.DTIN(fluid)`, `bc.DHIN(fluid)` and `bc.XIN(fluid)` query the **boundary's pressure**, even if the immutable supplied FluidProperties object represents another pressure. TIN preserves the source's direct, unclamped query. `FluidProperties.transient(states, 'TSAT', [0, 2])` collects scalar property values into a 1D array using zero-based indices in the supplied order; enthalpy-dependent methods require explicit evaluation.

## Limits

The optional scientific-data API in `openstream.database` provides
`load_bartolomey(path)`, one-based source-row selection and `record.to_input_set()`.
The separate `openstream.experimental_comparison.compare_void_profile()` pairs
void measurements in their actual quality/elevation coordinates. See
[BARTOLOMEY.md](BARTOLOMEY.md) for a complete runnable example, override semantics,
the pinned dataset and descriptive-comparison limits.

Use straight constant-area channels, single-component fluids and the flow assumptions of the selected upstream framework. The forward sweep requires positive inlet mass flow. Two-phase properties require pressure strictly between triple and critical pressures. Property availability does not validate empirical closures for a fluid. Multidimensional networks, reverse flow and arbitrary operating regimes are outside this port's verified domain. Film/drop/base/wave frameworks apply to the documented annular formulations.

Both residuals and bounds must be examined. A returned upstream convergence state is not proof of conservation, numerical equivalence, physical applicability or experimental validation. See `VERIFICATION.md` for the actual checks and retained failures.
