# Le Corre 2025 paper references

These files preserve inspected source evidence and recoverable graphical coordinates from the user-supplied `LeCorre2025OpenSTREAM.pdf`. They are **not original MATLAB result arrays**. Graphical agreement does not establish numerical equivalence or experimental validation.

| File | Contents |
|---|---|
| `digitized_curves.csv` | 294 visible samples from 22 named Figure 3/4 series |
| `metadata.json` | Paper/image hashes, axis calibration, extraction method and exclusions for Figures 3/4 |
| `figures6_7/digitized_figure6.csv` | 39 model-prediction dots and 15 separately identified correlation stars |
| `figures6_7/digitized_figure7.csv` | 24 visible wave-velocity/period model-curve samples for Sawai TestIDs 1, 2, 5 and 6 |
| `figures6_7/metadata.json` | Figure 6/7 source hashes, calibration, marker matching and exclusions |
| `NURETH21_2025_original.m` | Original historical database project script, retained under the upstream database MIT license |
| `source_history.json` | Historical/current version differences, source-level execution blockers and figure semantics |
| `figure5_source_gap.json` | Recovered primary thesis provenance and unresolved exact TRACE-case input/array gap |
| `physical_scope_review.json` | Independent audit of 33 native base runs; derived diagnostic evidence, not original reference data |
| `physical_scope_checkpoint_report.json` | Exact-byte recovered campaign report resolving the earlier physical-audit report hash |
| `checkpoint_recovery.json` | Exact SHA256 verification and method for that checkpoint recovery |

The original user PDF, whole-paper extracted text and embedded paper images are not redistributed here. The historical project script is reproduced byte-for-byte from the pinned database revision recorded in `source_history.json`; `database/LICENSE` contains its license notice.

## Units and reading bounds

All numerical values carry explicit units. Figure 4 film dimensions and Figure 6 thickness are converted from plotted millimetres to metres. Figure 7 periods are converted from plotted milliseconds to seconds; the horizontal coordinate is `(z - 0.8 m) / 0.004 m` for the specified Sawai cases.

The recorded bounds are conservative **three-image-pixel graphical reading envelopes** in each axis. They account for inspected tick placement and visible line thickness. They are not statistical confidence intervals, measurement uncertainties or solver acceptance tolerances. Curve comparisons should propagate both the horizontal and vertical reading bounds.

Figure 6 base-thickness stars evaluate the Le Corre 2022 correlation using **measured film flow**. They must not be treated as calculated `base.THICK` outputs; those are the dots. Figure 6 TestIDs were assigned only from source legend mass flux and measured horizontal values within the reading bound, independently of Python predictions. Overlapping or partially hidden markers were excluded.

## Reproduction

Use a separate Python environment with the pinned optional extraction packages
in `tools/requirements-paper.lock`; these are not required for normal solver
operation or comparison with the already extracted CSV files. The tools reject
an uninspected paper hash and an existing output directory, so use fresh directories:

```powershell
py -3.12 -m venv .paper-venv
.\.paper-venv\Scripts\python.exe -m pip install -r tools/requirements-paper.lock
.\.paper-venv\Scripts\python.exe tools/extract_lecorre_reference.py --paper C:/Users/Roman/Desktop/LeCorre2025OpenSTREAM.pdf --output tmp/paper-reference-new
.\.paper-venv\Scripts\python.exe tools/extract_lecorre_reference_extra.py --paper C:/Users/Roman/Desktop/LeCorre2025OpenSTREAM.pdf --database database --output tmp/paper-extra-new
```

No native prediction is read by either extractor. Saved raw image positions permit independent visual review. Missing dash segments, obscured curves and ambiguous components remain excluded rather than reconstructed.

Figure 5 is a separate TRACE/post-CHF code-comparison case. The companion project explicitly lacks the original TRACE reference results. No guessed full case or fabricated reference arrays are included here.
