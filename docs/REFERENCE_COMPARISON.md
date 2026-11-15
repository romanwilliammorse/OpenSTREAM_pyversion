# Portable MATLAB reference comparison

This tooling compares exported numerical arrays. It neither runs MATLAB locally nor establishes experimental validity. No fresh MATLAB-runtime export has been executed in this workspace. The tests of this fresh-export comparator use temporary, explicitly synthetic fixtures. Separately, all four original archives were recovered natively and their scoped core comparisons passed; see [ALL_BASELINES_VERIFICATION.md](ALL_BASELINES_VERIFICATION.md). Archive recovery does not supply the unknown original producer versions or establish transient equivalence.

## Supported framework and array paths

The exporter uses the preserved source at OpenSTREAM `a614c7173822a93c1e64ac28d1541cbac028cbd8`, with CoolPropWrapper `a7c40902ff66faf6ed668986398bb1b9faa16e13`. Both commits are checked against fixed comparator anchors, not merely mutually agreeing manifest strings.

| Framework | Required W/U/H fields | Additional required quantity |
|---|---|---|
| Mixture | mixture, mixture.liquid, mixture.vapor | None |
| TwoFluid | liquid, vapor | None |
| ThreeField | film, drop | None |
| FourField | film, drop, film.base, film.wave | film.wave.FREQUENCY |

For every non-mixture framework, the precursor `solver.mixSolver` is separately compared against the native `mixture/` output directory, including its effective inputs and provenance. Native field keys map to `solver.<field>[time]` paths; nested base/wave and mixture-phase names follow the indexed parent field. Initialization uses `mixtureInit`, `liquidInit`, `vaporInit`, `filmInit` and `dropInit` and the native `initialization.npz` archive.

The actual upstream regression checks W/U/H at the first physical state with relative tolerance **1e-8** and absolute tolerance **0**. Those tolerances remain unchanged. Reference zero therefore requires exact zero. No interpolation, broadcasting, dimension squeezing, tolerance override or missing-field skip is allowed. Scalar phase arrays must be `(time,node)`; wall fields remain `(time,node,wall)`, including one-wall cases. MATLAB CSV arrays retain their original shape and column-major layout. Unit strings must agree with audited SI units; unknown or converted units do not silently pass.

Four-field `film.base` corrects an upstream test-path omission: the source object exposes `base`, while the regression lists `basefilm` and skips it. The port requires the actual base field and does not accept the misspelled alias as a substitute.

Wave frequency, histories and later physical times are **additional port regression checks**. They use the same fixed 1e-8 relative / zero absolute policy provisionally to detect numerical translation differences. This is deliberately strict; it is not a tolerance derived from an upstream frequency test, measurement uncertainty, mesh convergence or physical accuracy. Reports label these supplementary comparisons separately. Failure must be investigated and recorded; this tooling has no option to loosen the original tolerances.

## Execution

In a separately available compatible MATLAB installation, add the tools directory and export to a new directory:

```matlab
addpath('tools')
export_matlab_reference('upstream','reference_exports/fourfield_run', ...
    Framework='FourField', ModelID='TUTORIAL1');
```

Framework may be Mixture, TwoFluid, ThreeField or FourField. `Source='approved'` instead loads the matching preserved original MAT object in MATLAB. This exporter still requires MATLAB to reconstruct the class. Separate native structural MCOS readers now recover all four archives without MATLAB; see ALL_BASELINES_VERIFICATION.md and tools/REFERENCE_READER.md. Approved-archive runtime metadata describes loading/export, **not the unknown original producing runtime or source revision**. Keep that limitation with any comparison result.

Run the native case with identical effective inputs and save it to a separate new directory. On Windows, compare all saved physical and pseudo-time states with:

```powershell
.\.venv\Scripts\python.exe tools\compare_matlab_reference.py reference_exports\fourfield_run outputs\fourfield_case --report outputs\fourfield_comparison.json
```

The default is `--phase both`, with all indices. This requires identical physical and pseudo-time grids, including matching initialization history lengths. A different number of pseudo steps can prevent full-history comparison even when final arrays might agree; the mismatch is not hidden.

For a narrower comparison of physical state zero, explicitly use:

```powershell
.\.venv\Scripts\python.exe tools\compare_matlab_reference.py reference_exports\fourfield_run outputs\fourfield_case --phase physical --time-index 0 --report outputs\fourfield_initial_comparison.json
```

This selection still requires valid final initialization convergence evidence and includes base/frequency/precursor checks. `--phase initialization` selects initialization only. If supplied, `--time-index` applies to each selected phase and precursor; choose a valid common index. Existing report files and export directories are never overwritten.

## Provenance and convergence gates

Before numerical comparison, the tool requires complete reference metadata, matching fixed source/submodule commits, clean source status, recorded equal CoolProp versions, matching copied input-file SHA-256 digests, matching effective model/options/geometry/boundary values, gravity and sampled CBTMULT. Numeric input equality permits only 16 double-precision machine epsilons of relative conversion error, with exact zeros; this is not a solver tolerance. NaN input sentinels are allowed only as matching input values, never as matching numerical solution arrays. Scalar/row/column input-vector representations are normalized deliberately; field-array axes are not.

Native schema `openstream-python-v1` is supported. Earlier versionless multifield metadata is recognized only when it has an explicit matching framework and all required provenance fields. The four explicit class-name aliases, such as `TwoFluidSolver`, normalize to their matching framework names; this handles the actual earlier two-fluid writer. Old incomplete outputs missing required fields must be regenerated; the comparator does not invent metadata. Reference time/space coordinates must match within the existing fixed 1e-12 s/m absolute conversion tolerance.

The reference's converged STATE alone is insufficient. The comparator checks actual iteration counts and finite, nonnegative point residuals below the unchanged input tolerances in the **final pseudo-time state**, and point residuals at every selected physical state after zero. It derives final temporal changes from the last two pseudo states and checks the original stopping criteria. Intermediate pseudo steps may legitimately fail their point criteria; they are compared as trajectory arrays without requiring each to be converged.

This final-pseudo check matters for four-field base/wave because the source's flow-property copy omits ITR. Physical-state-zero residual arrays can therefore remain initialized zeros. The actual wave residual is `DF`; unused initialized `DFW` is not accepted in its place. The additional `SSCONVFW` check uses the source's existing input value but is explicitly labeled a port acceptance condition because the source steady stopping predicate omits it.

Numerical agreement is distinct from physical consistency. Reports expose native physical/balance diagnostics and prominently list reported physical-consistency failures. Such diagnostic failures do not turn matching arrays into numerical disagreement, and a matching result does not erase them. Experimental validation is never inferred. The native `converged` acceptance flag must still be true. In some frameworks that flag includes finite/positive bounds as well as numerical criteria. A false flag in a nonfinite or negative-state case therefore requires case-specific interpretation; the comparator does not assume numerical equivalence or infer why acceptance failed.

## Exporter source review and limitations

The exporter was inspected against the pinned public constructors, field names and methods. It traverses all physical/pseudo fields and precursor solvers, preserves inputs and version metadata, and exports zero-input W/U/H methods as well as stored properties. Core missing/empty/complex quantities abort export. Optional derived-method failures remain in `manifest.errors`; they are not silently converted to numerical values.

Clear tooling corrections made during this extension:

- Export actual `film.base`; preserve exact convergence object paths independently of MATLAB identifier sanitization.
- Export empty numeric inputs with their shape and an empty CSV, instead of losing their provenance.
- Record audited units for wave frequency/frequency residuals, film mass-flow residuals and annular velocity criteria, and mark CBTMULT dimensionless.
- Reject a complex core array instead of marking an export complete while silently dropping it.
- Handle MATLAB JSON's single-struct-object representation, and verify CSV row/column layout before reshaping.

The script remains **unexecuted in MATLAB**. No claim of MATLAB Online availability, CoolProp compatibility there, successful class reconstruction or export execution is made. The reference comparison covers the listed primary arrays, not every closure, pressure/temperature output, physical balance or experimental measurement.

## Tool verification

Run `.\.venv\Scripts\python.exe tools\test_reference_comparator.py`. The current focused run passed **34 tests** (13.544 s). Cases cover all four frameworks, precursor recursion, all physical and initialization states, exact zero and relative-tolerance boundaries, base-path/frequency requirements, wall dimensions, unit/NaN failures, provenance and source pins, actual point/temporal convergence, unused DFW rejection, physical-diagnostic separation, empty inputs, JSON single structs, actual legacy class-name metadata, invalid CSV layouts/path traversal, duplicate/missing states and index selections. Fixtures are temporary and labeled `synthetic-test`; none is an upstream numerical reference. No native or MATLAB reference output was replaced.

A separate read-only inspection of all four `outputs/release-01` native cases confirmed the required W/U/H/frequency array ranks, both NPZ archives and required provenance fields match these schema mappings. This is native format compatibility evidence, not a MATLAB comparison.
