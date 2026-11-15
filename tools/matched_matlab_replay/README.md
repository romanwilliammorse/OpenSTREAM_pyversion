# Matched MATLAB diagnostic replay

This kit is statically checked and has **not been executed in MATLAB**. It does not establish MATLAB equivalence or experimental validation. No matched MATLAB arrays for these cases were found in the local reference archives or inspected database history.

The original OpenSTREAM and CoolPropWrapper Git blobs are preserved in `pristine/`, with MIT licenses. The runnable `source/` differs only by two added observation calls per framework, immediately before the existing point and temporal convergence predicates. `kit_manifest.json` records both hashes, inserted text, source pins, and frozen input hashes. `checksums.json` covers every distributed file. No solver equation, update, tolerance, clipping, order of evaluation, or stopping predicate is replaced.

Run in a **fresh compatible MATLAB session** on any computer. MATLAB Online is a candidate only if that account/environment supports the required Python integration and can import CoolProp; access and that capability have not been established. The native Python application never requires this kit or MATLAB.

1. Transfer/unzip the entire kit. In MATLAB, change to its directory.
2. Configure `pyenv` to an interpreter supported by that MATLAB release. In that Python environment install `CoolProp==8.0.0` and the wrapper's dependencies from `source/+CoolPropWrapper/requirements.txt`. The native run used Python 3.12.14. Do not assume MATLAB Online can use the Windows interpreter.
3. Verify `py.importlib.import_module('CoolProp.CoolProp').get_global_param_string('version')` returns `8.0.0`.
4. Run the frozen Sawai case first:

```matlab
addpath(pwd)
run_matched_replay(1, fullfile(pwd,'results-sawai'))
```

Then the 400-cell two-fluid case:

```matlab
run_matched_replay(2, fullfile(pwd,'results-twofluid'))
```

Output directories must be new. Keep failed outputs and choose a new directory for any repeat. Return the entire result directories, including `receipt.json`, portable `manifest.json`, all CSV arrays, traces, input copies and logs. A successful exporter completion is not a solver-convergence claim; inspect recorded state and both point/temporal gates.

`trace/point_trace.csv` joins the native trace by `(time_s, node_zero_based, iteration)`. Each framework's `trace_schema.json` defines columns and units. MATLAB one-based node indices are also explicit. FourField traces cover MATLAB nodes 21–29; TwoFluid nodes 398–401. All pseudo-times at these nodes are retained. Each completed point iteration records directly stored phase W/U/H and wave frequency, actual source increments, exact thresholds and the point predicate. `temporal_trace.csv` records the source temporal maximum increments and point status before the existing stopping decision. FourField frequency is recorded but is **not included in the upstream temporal stopping predicate**.

`raw_locals.jsonl` records existing real numeric/logical locals of at most 16 elements at each selected point hook, including old/upstream/iterative values and locally retained update intermediates. It preserves MATLAB shapes and nonfinite values as explicit strings. Generic variables such as `Mtot` or `Unew` contain their last assignment at that hook; these are not snapshots of every preceding update stage. Unlisted or larger intermediates are not recorded. Raw-variable units must be read from the pinned source comments; unknown units must not be assumed dimensionless.

`portable/arrays` contains final state arrays and the source-retained initialization/pseudo-time histories, including their initial time-zero entries and precursor state, where exposed by the existing exporter. CSV rows are the first MATLAB dimension; remaining dimensions flatten in column-major order. The manifest records exact shapes, SI units or explicit `UNRESOLVED`, class and nonfinite counts. No extra derived-property export is performed before solving, to avoid possible property/cache side effects during the replay. The original exporter is adapted only for case-specific input locations and input equality assertions. Intermediate constructor operations and discarded iterations are not full-state checkpoints.

Frozen numeric inputs use 17 significant digits. The source's convenience writer uses 11 decimal places, so using it here would round the frozen data. The native MATLAB input parser remains unchanged; every parsed field is checked against the frozen JSON before solver construction. `CBTMULT` is recovered as constant one from the campaign's explicit constant-one guard and saved samples, not guessed from a generic callable placeholder. Both cases have one wall and one steady boundary state; the generator rejects other shapes.

Runtime requirements and exact MATLAB/Python/CoolProp versions are recorded during execution. MATLAB has not been discovered in the checked PATH, default installation directories or MathWorks registry locations on the development machine; this is not a statement about the user's access elsewhere. No external installation, sign-in, license acquisition or runtime execution has been performed by this preparation step.

The source explicitly selects `BICUBIC&HEOS` in `Inputs.FluidProperties`; the wrapper temporarily uses HEOS for surface tension. After constructor initialization, the kit reads the stored backend name (no property calculation) and requires `BICUBIC&HEOS`. This is separate from the CoolProp version check.

The project's existing full-array command is `python tools/compare_matlab_reference.py <MATLAB-output>/portable <native-case>/numerical --phase both --report <new-report.json>`. Its existing acceptance checks deliberately reject nonconverged cases and unavailable/dirty Git worktrees. This instrumented copy reports honest source-origin pins and unavailable runtime Git metadata, so that acceptance command is expected to reject it without an explicitly audited diagnostic-import extension. Do not blank its Git status, fabricate a clean checkout, or bypass convergence to obtain a passing claim. Use `tools/compare_matched_point_traces.py` for the strict, provenance-bound diagnostic point comparison when actual MATLAB outputs exist.
