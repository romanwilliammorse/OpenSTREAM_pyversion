# GUI usability verification — 2026-11-14

The acceptance matrix was completed and published as commit `2025bce` before
starting these GUI changes. This update changes presentation and navigation;
no solver equations, closure selections, reference arrays or tolerances changed.

## Delivered behavior

- The opening screen presents all four models before loading an input editor.
  The workspace retains an obvious Model selector when the sidebar is hidden.
- Results, saved history and the editor footer use `inputs.model.ID` as the
  case name. Historical names come from each immutable `submitted_inputs.json`,
  preserving `Run0001` rather than the normalized `RUN0001` in change metadata.
  Missing historical names have an explicit fallback. A missing submission
  does not hide other runs; opening that run reports the missing-input error.
- Saved runs restore their submitted model and inputs. New run submission uses
  the same captured input snapshot for validation and execution. Stale history
  responses cannot overwrite a newer selection or prematurely enable Run.
- Saved runs at the top left toggles the sidebar. Inputs survive collapsing
  and reopening it; this preference is retained in the browser. The original
  logo remains visible in the collapsed layout.
- Reference classification and the three separate scientific status cards
  retain their existing meaning. Renaming a case does not establish equivalence.

## Checks actually performed

Nine dependency-free Node tests passed, including exact case-name spelling,
Unicode/literal name handling, immutable validation/submission, duplicate-run
locking, and deliberately out-of-order history responses. Existing profile
grouping, derivative units, reference-time alignment, and import schema checks
also passed. JavaScript syntax and Git whitespace checks passed.

The existing Python local-request/input-boundary test passed (1 test).
Acceptance-matrix regeneration/integrity check passed with all 81 requirements.

Live browser checks on the existing local service at `127.0.0.1:8765` confirmed:

| Action | Observed result |
|---|---|
| Open/reload the app | Four model choices; editor initially hidden |
| Choose Mixture, then switch to Two-fluid and Three-field | Correct model and 163 input fields; old selected results cleared |
| Edit ID to Run0001, collapse/reopen sidebar | Footer preserves Run0001; editor and model selector remain usable |
| Open the existing Four-field Run0001 | Results title and footer preserve exact spelling; FourField and its saved inputs restored; plot loads |
| Inspect the existing custom result | Converged, MATLAB archive Unverified, Physical consistency failed remain separate |
| Enter Unicode and markup characters in ID | Rendered literally as text, with no inserted HTML elements |
| Reload after collapsing | Model chooser returns and sidebar remains collapsed |
| Inspect captured browser console | No warning/error entries |

Screenshots are in `outputs/verification/gui-usability/model-choice.png` and
`named-result.png`. Automated log: `outputs/verification/gui-usability/checks.log`.

No new numerical case or experimental comparison was run for this presentation
change. The user's three recent saved runs were read without modifying their
files. The full existing numerical suite is configured in Windows CI, along
with both frontend test files; CI results are separate from the local checks.
Narrow/mobile viewport rendering was not manually checked in this update.

## Reproduce the automated checks

From the repository root in PowerShell:

```powershell
node --check src/openstream/gui_static/app.js
node --test tests/gui_frontend_logic.test.cjs tests/gui_navigation.test.cjs
.\.venv\Scripts\python.exe -m pytest -q tests/test_gui.py::test_invalid_input_and_local_request_boundaries
.\.venv\Scripts\python.exe tools/build_acceptance_matrix.py --check
```

Refresh an existing browser tab with Ctrl+R to load the updated interface.
The desktop shortcut and local launch command are unchanged.
