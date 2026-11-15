# Input and thermophysical property port record

Source inspected: OpenSTREAM commit `a614c7173822a93c1e64ac28d1541cbac028cbd8`,
CoolPropWrapper commit `a7c40902ff66faf6ed668986398bb1b9faa16e13`.
The root project license preserves upstream attribution. No MATLAB code is
executed by these Python modules.

## Scope and mapping

| Upstream | Python | Implementation | Verification |
|---|---|---|---|
| `+Inputs/Input.m`, `.inp` and JSON readers | `inputs.read_input_file` | Implemented; strict duplicate/unknown/malformed input errors | Original input files and invalid cases tested |
| `+Inputs/Model.m` | `inputs.Model` | All 102 declared input defaults and enum choices transcribed | All original `models.inp` records parsed; selected defaults checked |
| `+Inputs/Options.m` | `inputs.Options` | All 49 declared defaults transcribed | All original `options.inp` records parsed; numerical defaults checked |
| `+Inputs/Geometry.m` | `inputs.Geometry` | All five fields and four derived geometry methods | Hydraulic diameter and multiple-wall fractions checked |
| `+Inputs/BoundaryConditions.m` | `inputs.BoundaryConditions` | All seven input fields, mesh/wall validation, inlet diagnostics | Steady/transient original files and multiwall reshape tested |
| `+Inputs/InputSet.m` | `inputs.InputSet` | File assembly and copied solver-dependent VAPORFRIC defaults | Original documented sample inputs tested |
| `+Inputs/FluidProperties.m` | `properties.FluidProperties` | Saturation constants, all enthalpy-dependent phase-property methods, validity clamping, QKMAX | Direct HEOS cross-check, dimensions, bounds, inversion, shape and thread-safety tests |
| `CoolPropWrapper.CoolPropWrapper` | Direct native CoolProp `AbstractState` | Required PQ, PT and HmassP operations | No MATLAB wrapper dependency; wrapper's BICUBIC/HEOS selection preserved |

Input support does **not** imply that every selected physical model or solver
framework is numerically implemented. The solver must reject unavailable
options. General MATLAB expression/function-handle input, MATLAB logging/UI,
input-file writing, property plotting and general CoolProp-wrapper convenience
methods have not been ported here. Callable CBTMULT values may be supplied
through the Python API; arbitrary MATLAB expressions are never evaluated.

`InputSet.official_sample()` selects **TUTORIAL1**, as specified by the documented
sample in `docs/source/Usage/runSampleScript.rst`. The sandbox example selects
TUTORIAL2A instead; both default to the same mixture HEM physics, but their input
metadata differs. Packaged original `.inp` files supply the no-argument API.

## Translation decisions

- All dimensional input units remain SI. `ANGLE` is degrees according to
  `Geometry.m`; the sample `geom.inp` labels it radians but supplies zero. The
  sample is therefore unaffected. Nonzero angles follow the source's degree
  convention, not the inconsistent file comment.
- MATLAB row/column vectors become one-dimensional NumPy vectors. WPOWER remains
  two-dimensional `(number of power segments, number of walls)` and is reshaped
  in MATLAB column-major order. For example `[1,2,3,4]` for two segments and two
  walls becomes `[[1,3],[2,4]]`.
- Default arrays, copied configurations and boundary arrays own their storage;
  changing one model's coefficients does not mutate another model.
- Fluid saturation records are immutable. Their native CoolProp scratch state is
  guarded by a lock, allowing solver copies to share the property record safely.
  Array-valued methods preserve the supplied shape; scalar input returns scalar
  output, avoiding accidental NumPy row-by-column broadcasting.
- The exact upstream backend is `BICUBIC&HEOS`. Surface tension uses `HEOS`, as
  the pinned MATLAB wrapper explicitly does. There is no replacement property
  model or hand-generated interpolation table. CoolProp manages its tables.
- QKMAX maximizes the original hydrodynamic heat-flux expression over triple to
  critical pressure. SciPy's bounded minimizer uses `xatol=1e-4 Pa`, corresponding
  to MATLAB `fminbnd`'s default absolute TolX. The minimizer implementations are
  not identical; QKMAX equivalence remains unverified until MATLAB export.
- Upstream clamping is preserved: `T(H)` clamps to HMIN/HMAX; liquid properties
  in PSYSTEM clamp to HMIN/HF; vapor properties clamp to HG/HMAX. SATURATED
  methods return saturation constants independently of the supplied enthalpy.
- Unknown input keys are errors rather than upstream warnings. Invalid numeric
  suffixes are errors rather than accepting MATLAB `textscan`'s numeric prefix.
  Invalid dimensions, non-finite inputs and non-increasing boundary times fail
  explicitly. Iteration limits above 255 are rejected rather than allowing
  MATLAB's uint8 assignment to silently saturate.
- The source's `ismembertol(...,1E-3)` power-mesh length check is represented as
  a relative 1e-3 tolerance against the larger of mesh sum and channel length.
  All-zero WPOWER is replaced with ones with an explicit warning, preserving
  the upstream behavior.

## Verification performed

On this Windows environment, the command

```powershell
$env:PYTHONPATH='src'
.\.venv\Scripts\python.exe -m pytest tests/test_inputs.py tests/test_properties.py -q
```

passed **21 tests** after the package solver imports were available, including
revalidation of directly mutated API inputs before solver construction. Versions:
Python 3.12.14, NumPy 2.5.4, SciPy 1.18.1, CoolProp 8.0.0, pytest 9.2.0.

At the sample pressure 6 MPa, native BICUBIC output includes:

| Quantity | Value | Unit |
|---|---:|---|
| TSAT | 548.734989992342 | K |
| RHOF | 757.9981336355253 | kg/m³ |
| RHOG | 30.818445364018114 | kg/m³ |
| HF | 1213922.7722144956 | J/kg |
| HG | 2784589.497265409 | J/kg |
| HFG | 1570666.7250509136 | J/kg |
| Surface tension | 0.019837286476609706 | N/m |
| Kutateladze velocity UC | 0.6212878914638131 | m/s |
| QK | 30073755.162476417 | W/m² |
| QKMAX | 30148141.82965512 | W/m² |

These are computed port outputs, **not MATLAB reference values or experimental
validation data**. Saturation density, enthalpy, heat capacity, viscosity and
conductivity were compared against direct HEOS evaluations at `rtol=2e-5`;
saturation temperature used `atol=1e-5 K`. The small nonzero tolerance permits
the known interpolation difference between bicubic tables and direct EOS
evaluation. Surface tension uses the same direct HEOS route and agrees at
`rtol=1e-12`. This establishes property-backend consistency, not solver fidelity.

Dimensional identities checked include alpha=k/(rho cp) [m²/s], Pr=mu cp/k [1],
and QK=rho_g h_fg UC [W/m²]. Pressure bounds, saturation density ordering, latent
heat positivity, diffusivity scale, QK≤QKMAX, scalar/array shape preservation,
independent default storage and concurrent property calls were tested.

An initial test incorrectly assumed exact PT→H→T inversion at the lower table
boundary. At 6 MPa, `HMIN=H(TMIN)` with TMIN=274.16 K returns
`T(HMIN)=274.1577197113357 K`, a -0.002280288664337604 K interpolation discrepancy.
The test was corrected to check the actual upstream **enthalpy-clamping**
contract, not to change or loosen the governing implementation. The ordinary
300–700 K inversion check passes at an unchanged 2e-4 K absolute tolerance.
The boundary discrepancy is retained and reported; no property correction is
applied. MATLAB equivalence across different CoolProp versions/table revisions
remains unverified.
