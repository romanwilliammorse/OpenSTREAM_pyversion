# Repository contents and publication audit

This repository contains the native OpenSTREAM Python project and its retained
scientific evidence. Publishing the repository does not change the verification
scope or make failed physical checks pass. Read [PARITY_STATUS.md](PARITY_STATUS.md)
and [ALL_BASELINES_VERIFICATION.md](ALL_BASELINES_VERIFICATION.md) before interpreting
the archived results.

## Included project files

| Location | Purpose |
|---|---|
| `src/openstream/` | Numerical implementation, inputs, local GUI, bundled reference profiles and local assets |
| `tests/` | Native numerical/API/GUI tests and JavaScript chart/input tests |
| `tools/` | Reference recovery/export/comparison, sensitivity checks, release checks, provenance tools and launch helpers |
| `examples/` | Runnable Python examples |
| `docs/` | API, scientific audits, known limitations, feature maps and usage instructions |
| `licenses/`, `LICENSE` | OpenSTREAM and reused-component notices |
| `requirements*.lock`, `pyproject.toml` | Reproducible tested dependencies and package definition |
| `reference_exports/` | Preserved portable arrays and metadata recovered from the original MATLAB archives |
| `references/paper/` | Digitized published curve/marker readings, image-resolution bounds, source hashes and explicit extraction exclusions; not MATLAB output arrays |
| `outputs/` | Saved numerical outputs, plots, verification reports, logs and retained failed/development runs |
| `outputs/verification/matched-replay-01/` | Ordered before/after diagnostic replays, unchanged-input comparisons, source/handle audits, separate TwoFluid budget study and archived-baseline recheck |
| `outputs/verification/matched-matlab-replay-kit-02.zip` | Portable source/input/trace bundle for later MATLAB reference execution; statically checked, not executed in MATLAB |
| `output/pdf/LeCorre_2025_Reports_03/` | Current three source-linked PDFs: clean figure plates with main Figure 7 at 0.2 s, OpenSTREAM convergence/supplemental diagnostics review, and amended acceptance matrix |
| `output/pdf/Matched_Diagnostic_Replay_01/` | Later replay report and updated acceptance matrix; source-bound PDFs with retained text/numbers, A3 diagnostic plot and layout receipts |
| `output/pdf/LeCorre_2025_Reports/` | Preserved earlier PDF snapshot under the original diagnostic policy |
| `provenance/` | Source, environment and dependency fingerprints |
| `upstream/` | Original OpenSTREAM source as a pinned Git submodule, including its CoolPropWrapper submodule |
| `database/` | OpenSTREAM-database pinned at b48541e; includes the preserved experimental XML and MATLAB adapters |

The original OpenSTREAM commit is
`a614c7173822a93c1e64ac28d1541cbac028cbd8`; CoolPropWrapper is pinned at
`a7c40902ff66faf6ed668986398bb1b9faa16e13`. Clone recursively to obtain both:

```powershell
git clone --recurse-submodules https://github.com/romanwilliammorse/OpenSTREAM_pyversion.git
Set-Location OpenSTREAM_pyversion
```

For a checkout created without submodules, run
`git submodule update --init --recursive`. A source ZIP from GitHub does not
contain the contents of Git submodules. The installed Python package bundles
its normal-operation inputs and selected portable reference arrays, so MATLAB
source is not required to run the package.

## Which results are authoritative

- `outputs/validation/lecorre-2025-01/` retains the frozen Le Corre reconstruction:
  original attempts, effective inputs, numerical profiles, paper comparisons,
  measured errors and separately labeled refinement studies. Consult its
  `report.json` planned/attempted counts and `analysis/analysis.json` completeness
  flag: all 69 planned attempts completed. Read-only audits bind their results to
  the final report hash; the common-domain diagnostic supplements the original
  pairwise metrics without replacing them. Graphical agreement is distinct from MATLAB equivalence and experimental
  validation. `references/paper/lecorre2025/` preserves source history and
  digitization metadata; user-supplied whole papers are not redistributed.

- `outputs/validation/bartolomey-pilot-01/` contains the frozen first experimental
  comparison campaign: 40 native runs, 59 unique measurements, all raw inputs,
  errors and physical checks, plus three retained mesh-sensitivity failures.
  These are descriptive comparisons, not uncertainty-qualified validation.

- `outputs/baseline-parity-02/` is the completed four-framework archived baseline
  audit, including native results, recovered arrays, comparisons, initialization
  histories and mixture precursors. Its `summary.json` identifies the exact scope.
- `reference_exports/recovered-mixture-02/`, `recovered-twofluid-01/`,
  `recovered-threefield-01/`, and `recovered-fourfield-01/` retain portable archive
  recovery evidence. Recovery is distinct from a fresh MATLAB execution.
- `outputs/twofluid-transient-02/`, `outputs/threefield_transient_audited/`, and
  `outputs/fourfield-transient-audited/` contain the audited original transient
  cases and explicitly reported physical consistency failures. Those results
  are not verified MATLAB transient equivalents.
- `outputs/verification/native-sensitivity-01/` and the other named sensitivity
  records retain mesh/time-step evidence. Read each report's domain and acceptance
  conditions rather than treating the presence of output as a pass.
- `outputs/gui/` contains actual local GUI runs. Each run has submitted inputs,
  status, and (when completed) its own numerical output and `gui_verification.json`.
  `outputs/verification/gui-*` records the GUI release checks.
- Older directories and incomplete attempts remain available for auditability.
  For example, `outputs/sample-01/` is a failed serialization attempt, not a
  reference. Consult the run status/report and [PROGRESS.md](PROGRESS.md) rather
  than selecting a directory solely by name or modification time.

Results and reference files are intentionally retained, including failures.
Baseline arrays are never overwritten or adjusted to make a test pass. The
directory names identify different attempts or scopes, not interchangeable
copies of one verification result.

## Excluded local machinery

Python virtual environments, bytecode, test caches, build directories and local
distribution output are reproducible machine artifacts. `tmp/` contains scratch
PDF extraction/rendering material. GUI lock files and the server's activity log
are local process state. None belongs to the scientific source or accepted
reference evidence; the corresponding working files remain on the original
machine when ignored by Git.

`tools/vendor/matio/` is an external inspection checkout, not a dependency needed
by normal operation or an additional Git submodule. Its package, exact inspected
commits, license and recovery workaround are documented in
[`tools/REFERENCE_READER.md`](../tools/REFERENCE_READER.md). Install the pinned
optional reader from `tools/requirements-reference.lock` to reproduce recovery.
The standalone license notice is retained in `licenses/mat_io_LICENSE`.

## Sawai oscillation diagnostic

`docs/SAWAI_OSCILLATION_DIAGNOSTIC.md` records the source-unchanged 0.2 s/100-cell
follow-up. Its frozen manifest, observer, independent source-term analysis and
tests are retained in `examples/`, `tools/` and `tests/`. The complete replay,
hash-bound trace, numerical arrays and clean diagnostic plot are under
`outputs/verification/sawai-oscillation-01/`. The corresponding report and
acceptance-matrix PDF snapshot are under `output/pdf/Sawai_Oscillation_01/`.
The negative droplet iterates and failed point criterion remain available;
no matching MATLAB execution or experimental-validation pass is implied.

## Publication audit

`tools/audit_publication.py` performs a read-only inventory and a bounded
credential-pattern scan. It prints filenames and pattern labels only, never
matched values. It does not alter files, Git configuration, the index, or the
original reference archives. Generate a fresh report with:

```powershell
.\.venv\Scripts\python.exe tools\audit_publication.py --output outputs\verification\publication-audit.json
```

The 2026-11-14 initial inventory contained approximately **205 MB** of project
files, primarily saved results. No included file reached 50 MiB; the largest
result was approximately 9.3 MB. No configured credential pattern or suspicious
private-configuration filename was found. This is a pattern-scan finding, not
a claim that automatic scanning can prove absence of all sensitive content.
Binary arrays and images are inventoried and hashed, not semantically scanned
for credentials. Counts may change as GUI assets and reports are added; the
generated JSON report records its own timestamp and file hashes.

Historical environment reports, copied inputs, logs and recovery manifests
retain original local file paths, including Windows user-directory names.
These paths describe provenance and are not authentication credentials or
portable runtime configuration. They have not been rewritten inside preserved
evidence. New calculations should use the documented installation commands and
their own output directory; they do not require those original absolute paths.
