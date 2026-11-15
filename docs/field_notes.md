# Mixture-field translation record

Source baseline: OpenSTREAM `a614c7173822a93c1e64ac28d1541cbac028cbd8`, especially `+Solvers/+Mixture/Mixture.m`, `Liquid.m`, `Vapor.m`, and `+Solvers/AbstractField.m`. The MIT license is retained at the project root and in the preserved upstream checkout.

## Implemented field equations

`src/openstream/fields.py` contains the translated mixture thermodynamic quality, actual quality, void fraction, density, static and advection velocities, phase flow rates, phase enthalpies, phase temperatures, viscosity and Reynolds numbers. Slip momentum and energy inventory corrections retain the upstream definitions and units (kg/s and J/m respectively).

The following selectors have native implementations:

| Model group | Implemented selectors | Checks performed |
|---|---|---|
| Thermal nonequilibrium | EQUILIBRIUM, SAHAZUBER, EPRI, MRM field terms | Equilibrium conservation identities; Saha–Zuber limits; EPRI finite/bounded states; original TUTORIAL2A–G runs, including MRM |
| Void fraction | HOMOGENEOUS, SLIP, BESTION, EPRI | Homogeneous phase velocity identity; prescribed slip; original tutorial runs; EPRI finite/bounded states |
| Single-phase friction | BLASIUS | Independent Darcy pressure-gradient calculation |
| Two-phase wall multiplier | HOMOGENEOUS, SLIP, EPRI | Homogeneous identity; EPRI TUTORIAL2F run; SLIP formula inspected but no isolated numerical test |
| Local multiplier | HOMOGENEOUS, SLIP, ROMIE | TUTORIAL2G checks HOMOGENEOUS; other two formula-inspected only |
| Post-transition friction | TPFM, VAPOR | TPFM exercised by defaults; VAPOR formula-inspected only |
| Single-phase heat transfer | DITTUSBOELTER, SIEDERTATE, GNIELINSKI | Both phases finite and positive in one two-phase condition; wall heat partition and wall-energy identities |
| Boiling heat transfer | THOM | Wall energy and temperature checks |
| Critical boiling transition | NONE, ELEVATION, BIASI, BEZRUKOV | NONE and ELEVATION exercised; BIASI/BEZRUKOV formula-inspected only |
| Minimum film boiling | NONE, CONSTANT | NONE exercised; CONSTANT formula-inspected only |
| Post-boiling heat transfer | VAPOR, DOUGALL, BISHOP, MOECK, DELORME (one wall), CONDIEIV | Finite, positive coefficients in one heated two-phase condition; these are implementation smoke checks, not correlation validation |
| Thermal relaxation | TIMEX, FOURIERX, VOID, HOMOGENEOUS, FOURIER | Units and prescribed-time interpolation; finite positive two-phase states in all five branches |
| Interfacial transfer | BULK, SATURATED | Both field branches translated; MRM tutorial default exercised |
| Near-wall relaxation | QUALITY, VOID, FILM | QUALITY exercised in tutorials; other branches formula-inspected only |
| Near-wall enthalpy | RATIO, FILM | RATIO exercised; FILM formula-inspected only |
| Annular onset | WALLIS, WALLIS_SIMP, LEVITAN | WALLIS exercised; other branches formula-inspected only |

All numerical agreement with executed MATLAB remains **unverified** until portable reference exports are supplied. A finite-positive check does not validate a closure's applicability or predictive accuracy. No experimental validation has been performed.

## MATLAB semantics preserved

- Axial state vectors are one-dimensional; wall quantities explicitly use `(nodes, walls)`. All multiplication/division in the translated field formulas is elementwise, except the deliberately unavailable defective selector below.
- Python indices are zero-based. A scalar index returns scalar state properties and one-dimensional wall values; a vector returns node-major arrays.
- `MFLUX` follows changes to `W` immediately. Cached quality, void fraction, density, and advection velocity update only through `Mixture.update()`, reproducing the `H` setter cascade. The first H assignment uses upstream's equilibrium-quality shortcut, even for nonequilibrium selectors.
- Copying preserves the first *linear* element of a wall array, using MATLAB column-major order, and copies all remaining entries without shared writable arrays. This intentionally preserves the upstream multiwall inlet-copy issue below. H-triggered updates select changed H indices, or all indices when no H changes.
- The EPRI thermal model computes departure quantities using old cached quality before assigning the new quality. Its global first-match search uses column-major order.
- EPRI void iteration retains 100 iterations and absolute void-fraction tolerance 0.001. Wall-temperature iteration retains 20 iterations and 0.1 K tolerance. Failed iterations issue warnings; no tolerance is relaxed.
- Elementwise source min/max uses NumPy `fmin`/`fmax` to preserve MATLAB's default missing-value omission; the order of nested bounds is preserved. This matters for the all-vapor homogeneous-evaporation relaxation limit, where an intermediate 0/0 becomes NaN and the source's final bound yields 1e−6 s. See [MathWorks max](https://www.mathworks.com/help/matlab/ref/double.max.html) and [MathWorks min](https://www.mathworks.com/help/matlab/ref/double.min.html). Logical-index floors (such as the two-fluid relative Reynolds-number floor) retain NaN rather than being converted to a different operation.
- Prescribed relaxation interpolation is linear with endpoint clamping. Local obstruction locations use the nearest mesh node, with first-node tie handling. Repeated local indices use the last supplied assignment, as in MATLAB.
- The annular-onset index and nodal sigmoid retain first-call caching. The sigmoid uses the upstream **node-index** scaling, not a substituted spatial-width interpretation.
- Pressure loss terms retain the sign convention of negative pressure changes in the field equations. Stored positive-drop diagnostics are assembled by the solver.

## Suspected upstream defects and limits

These have not been repaired by changing the governing model:

1. **Generalized Dittus–Boelter matrix multiplication.** `Liquid.m` and `Vapor.m` use `c(1).*Re.^c(2)*Pr.^c(3)`, with matrix `*` between generally column-shaped vectors. The default `DITTUSBOELTER` branch uses correct elementwise multiplication. `SPHTM=DITTUSBOELTERGEN` raises `NotImplementedError`; deciding to change `*` to `.*` would be a documented upstream correction requiring its own reference test.
2. **Multiwall flow copying.** `AbstractField.copyFlowProperties` uses `(2:end)` on wall matrices, preserving only the first scalar rather than all inlet-wall entries. Inlet entries for wall 2 onward can be overwritten during transient copying. The port reproduces this behavior in column-major order and tests it explicitly.
3. **Cached annular onset.** `OAFIDX` and `sigm` cache their values permanently on first invocation. `HNEARWALLEQ` invokes these during the sweep, even if the enthalpy ratio is one. Thus near-wall transition diagnostics can retain a premature onset location. The port retains this cache behavior; it does not silently recalculate onset.
4. **DELORME wall indexing.** The source uses `mix.HFLUX(zIdx)` with linear indexing, while nearby expressions are wall-dependent. Multiwall DELORME is explicitly unavailable pending review; the one-wall formulas are translated.
5. **Small remaining liquid fraction.** Upstream forces liquid enthalpy to HF and liquid velocity to mixture velocity when `1-X < 0.01`. This regularization can alter exact phase reconstruction close to all-vapor flow. It is retained. Conservation-identity tests avoid this explicitly regularized interval.
6. **Correlation operating domains.** Fractional powers and divisions in several upstream correlations have physical-domain restrictions. Positive/bounded results at one test condition do not establish validity for arbitrary fluids, geometry, pressure, quality, Reynolds number, or wall flux. No new universal validity range is asserted.
7. **Near-wall fraction endpoints.** The input parser retains upstream's inclusive range 0 to 1, but the solver rejects endpoints: zero divides by the near-wall flow area, while one divides by the remaining bulk mass flow. This is an explicit native capability restriction pending a defined diagnostic limit; no alternate fraction or physical model is selected.

## Reproduction

From the project root after installation:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_fields.py -q
```

The independent field suite contains 30 tests. Original-input mixture runs TUTORIAL2A–G completed with convergence and their actual numerical summaries were saved in `outputs/mixture_variant_checks.json`. Those saved summaries are generated Python results, **not** MATLAB reference data.

## Full MRM transient executions

Both EULER and EXPONENTIAL integrations executed the complete original `tutorial2_transient.inp` schedule with model TUTORIAL2E, 100 cells, dt = 0.1 s, and 51 physical states. Both reported numerical convergence. Default-control maximum independently evaluated mixture-equation residuals were:

| Integration | Mass residual [kg/(s m)] | Energy residual [W/m] |
|---|---:|---:|
| EULER | 0.0023749131 | 27.3036553 |
| EXPONENTIAL | 0.0025741880 | 29.5939071 |

These residuals are measured limitations of the default loose point controls, not passing strict balance results. Both final outlet enthalpies were approximately 1,764,400 J/kg, versus approximately 2,389,400 J/kg initially. Evidence is saved in `outputs/mrm_transient_checks.json`.

Independent checks with the same full boundary schedule, 25 cells, dt = 0.25 s, and stricter ERRORW = 1e−8 kg/s, ERRORH = 1e−3 J/kg, ERRORP = 1e−3 Pa also converged:

| Integration | Mass residual [kg/(s m)] | Energy residual [W/m] | Momentum residual [Pa] |
|---|---:|---:|---:|
| EULER | 2.1182143e−8 | 3.0739045e−4 | 2.4728970e−4 |
| EXPONENTIAL | 9.8489045e−8 | 8.8300072e−4 | 9.8256615e−4 |

Evidence is saved in `outputs/mrm_transient_tight_checks.json`. These residuals evaluate the translated mixture mass, material-enthalpy and momentum equations, including slip inventory corrections. They are not independent verification of the MRM vapor integrator against MATLAB and do not claim exact conservative total-energy balance. The mesh and timestep differ between the two tables, so this is evidence of achieved residual control, not a clean tolerance-only sensitivity study.

Reproduction (new result paths are required):

```powershell
.\.venv\Scripts\python.exe tools\verify_mrm_transient.py --output outputs\mrm_recheck.json
.\.venv\Scripts\python.exe tools\verify_mrm_transient.py --tight --output outputs\mrm_tight_recheck.json
```
