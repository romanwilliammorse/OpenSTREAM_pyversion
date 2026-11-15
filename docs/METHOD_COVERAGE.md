# Public numerical-method inventory

Regenerate the machine-readable audit from the project directory:

```powershell
.venv\Scripts\python.exe tools\audit_method_coverage.py
```

The script uses only Python's standard library. It reads MATLAB declarations
and Python ASTs, resolves the repository-local inheritance chains, and writes
`docs/METHOD_COVERAGE.json`. It does not import or execute numerical classes.
Each record includes source location, declaring class, native candidate,
signature, explicit unsupported statements and relevant review notes. The
report hashes the inspected source files and feature map.
Current fingerprints normalize CRLF to LF so Git's Windows newline conversion
does not invalidate an unchanged declaration inventory; no other text
normalization is applied. Original archive/PDF hashes remain exact binary hashes.

This is **not a completeness score or correctness test**. A method with the
same name can contain untested or unsupported branches, have different argument
semantics, or be mathematically wrong. The parser is specific to the pinned
repository's indentation and declaration style; dynamically generated native
methods and MATLAB built-in inherited APIs are outside its analysis. Restricted
private/protected methods, general CoolPropWrapper utilities, GUI/logging and
tutorial parity are outside the numerical-method scope. Literal feature-map
token presence does not establish that prose fully documents a capability.

The independent review found and then prompted these diagnostic additions:

- Mixture `MTRANSV`: source transverse wall-vapor exchange in kg/(s m), with its
  fixed 0.01 s relaxation. It remains an unused diagnostic; it was **not added
  to MTOT or to any solver update**.
- Mixture `KLOCZ` and `KIDX(i)` subset selection: actual mesh locations and node
  indices, preserving nearest-node ties, obstruction ordering and duplicates.
- Mixture Liquid/Vapor `TIME()` and `Z(i)` accessors.
- Two-fluid Vapor `XTR_SUB/SAT/ITM/ANN` forwarding diagnostics.
- BoundaryConditions saturation/inlet property queries at the boundary
  pressure and FluidProperties numeric property-series aggregation, added by
  the implementation owner after the inventory. These require pressure-aware
  behavior; returning constants from a fluid record at another pressure is not
  source-equivalent.

Two source defects now produce explicit errors: annular `Drop.RE` calls an
undefined `Drop.MU`, and two-fluid `Vapor.XTR_CBT` calls undefined
`Liquid.XTR_CBT`. The former must not be replaced with the different
vapor-relative `REV` diagnostic. Four-field Drop inherits the same RE error.

`tests/test_diagnostic_api.py` passes six focused tests covering dimensions,
transverse-exchange cancellation, equilibrium null exchange, scalar/vector/wall
shapes, subset/duplicate/tie semantics, coordinate-copy behavior, transition
forwarding and explicit defective-method errors. Initial fixture construction
failed because its four obstruction locations lacked four corresponding loss
coefficients; the fixture was corrected without changing validation or any
numerical tolerance.

Remaining public API differences include generic live-field `transient` and
struct extraction, public interpolation convenience wrappers, MATLAB input-file
writers/default-report utilities, and full plotting options. Some numerical
operations already exist through internal helpers or alternative native APIs;
the report labels these as partial/internal alternatives instead of calling
them missing physics. SavedResults only accesses saved quantities and cannot
reconstruct arbitrary unsaved closures. Passing this declaration audit does
not establish MATLAB equivalence, branch coverage or physical validation.
