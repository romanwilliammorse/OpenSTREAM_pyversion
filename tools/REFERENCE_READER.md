# Reading the stored mixture reference without MATLAB

The verification-only reader uses `mat-io` 1.0.2 (BSD-3-Clause), not MATLAB,
MATLAB Engine, Octave, or a heuristic search for plausible numeric values.
The normal OpenSTREAM package has no dependency on this reader.

All four original archives are now supported by the verification tools. The
complete recovery, native solve, comparison and plotting workflow is:

```powershell
.\.venv\Scripts\python.exe tools\verify_all_baselines.py --output outputs\my-baseline-check
```

This requires a fresh output directory. Baseline agreement and physical
consistency have separate statuses; details are in docs/ALL_BASELINES_VERIFICATION.md.

```powershell
.\.venv\Scripts\python.exe -m pip install --target .venv\reference-reader -r tools\requirements-reference.lock
.\.venv\Scripts\python.exe tools\recover_mcos_reference.py --output reference_exports\recovered-mixture-new
.\.venv\Scripts\python.exe -m pytest tools\test_recover_mcos_reference.py -q
```

Choose a new output directory; overwriting any export is rejected. Original MAT
files are opened read-only and their SHA256 is checked before and after recovery.

The reader resolves MCOS class, object, property, and enumeration tables. It
retains handle-object identity, including each phase's reference to its parent
mixture. `object_graph.json` names each numeric property and records references;
`raw_arrays.npz` preserves original MATLAB dimensions. `results.npz` and
`initialization.npz` use the Python time/node/wall layout. The manifest identifies
which quantities were stored and which were reconstructed from saved state.

Mixture and phase velocity, phase mass flow, and phase enthalpy are MATLAB
methods, rather than stored properties. These are reconstructed using the
preserved source formulas and recovered fluid constants. This reconstruction
rejects models other than the baseline SATURATED/EQUILIBRIUM combination. It
does not import the Python solver or CoolProp. No MATLAB callbacks are executed.

The package's 1.0.2 enumeration reader cannot handle OpenSTREAM's name-only
enums: it assumes stored values exist, then mutates an integer class ID into a
string before calling `.item()`. The tool temporarily replaces that method with
a name/index-table reader, retaining unmodified raw enum metadata. The patch is
local to the call and restored afterward; package and archive files are unchanged.
Every decoder warning fails the export rather than silently omitting content.

Reuse investigation on 2026-11-14:

- [foreverallama/matio](https://github.com/foreverallama/matio): BSD-3-Clause,
  Python >=3.11, Windows CPython 3.12 wheel available. It supports generic MCOS
  classdef objects. The inspected repository HEAD was
  `18d538d5657e4e32e25d90c53a80c05a522540ac` (2026-11-10); installed version 1.0.2
  corresponds to release tag commit `f9be7123707c134292fbfb67fcacac14516f5f83`.
  Its complete checkout and license are retained at `tools/vendor/matio`.
  A standalone notice is also retained at `licenses/mat_io_LICENSE` and included
  in distributions; the inspection checkout itself is excluded from packaging.
- [bozdemir/mcos-decoder](https://github.com/bozdemir/mcos-decoder): MIT,
  groundTruth bounding-box-specific size/depth decoding, unsuitable for a
  scientific solver's named class properties; not reused.
- [WilliamGarrow/mat73-reader](https://github.com/WilliamGarrow/mat73-reader):
  Apache-2.0, focused on HDF5/v7.3 tables; these references are MAT5, so not reused.
- The targeted Hugging Face search found mirrored SciPy sources and unrelated
  datasets, not a suitable supported MCOS solver-object reader. No HF code reused.

Archive agreement is narrower than a fresh run of a known MATLAB/CoolProp
version. The archive does not establish its exact producing source commit or
CoolProp version. A serialized anonymous-function path mentions R2024b; that
path is retained as evidence, not presented as independent runtime metadata.
The original archive and reference tolerance remain unchanged. These checks do
not establish validation against experimental measurements.
