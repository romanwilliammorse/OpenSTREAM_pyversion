# Hosted Python startup repair

Date: 2026-11-15 (America/Chicago). Production recovered on commit
`af84aa138f7993fe897c70dbaf1b864b4f1c7190`, deployment
`dpl_5A7Jm7sBwcbgF3HPb15V2ydJSGDZ`, within the tested scope below.

## Confirmed failure

The supplied request `zf9lf-1794793633089-328672dd1e5c` was a `GET /` on
deployment `dpl_9wBZ7zBHTU6kPxzGvpraxQCcN5U2`. Its runtime log at
2026-11-16 01:47:16.532 UTC records Vercel's Python dependency installation
failing while extracting the CoolProp 8.0.0 wheel's
`CoolProp/include/all_fluids_CBOR.h` into temporary storage:
`No space left on device (os error 28)`. The Python process exited before
the Flask application could serve the page. Earlier failures affected Plotly,
NumPy and SciPy installation. These are startup failures, not input-validation
or numerical-convergence results.

The installer already used `--no-cache`; merely adding that flag would not
address the observed failure. Passing scientific tests and a Vercel READY
deployment state did not prove that independent hosted Python startup was safe.
The formatting release did not change the numerical code or dependency pins.
No causal connection between the color/font JavaScript and disk exhaustion was
established.

## Repair boundary

The repair separates the web/API environment from the calculation worker's
environment. The application already launches scientific calculations in
isolated Vercel Sandboxes. The web process should carry only the dependencies
needed for authentication, schema validation, saved-result delivery, and worker
orchestration. NumPy remains available for the existing schema and export code.

The implemented changes are a smaller pinned web requirements manifest, lazy
package-level exports, and serving the pinned Plotly JavaScript asset directly
without importing Python Plotly into the web process. Public solver classes
resolve through the original implementation when requested. The scientific worker keeps its existing full
`requirements-cloud.lock`, Python version, source, inputs, equations, closures,
tolerances and output comparison rules. No plotting controls are rolled back.
The renderer asset must match the installed pinned distribution and retain its
license; serving it directly changes packaging, not the figure controls.

`requirements.txt` and `requirements-web.lock` contain the same 25 pinned
packages. The worker lock retains its original 48 pins. Every web package
version is an unchanged subset of that worker lock. Scientific/plotting Python
packages and development/build tools are removed from the web manifest only;
NumPy, authentication dependencies and the official storage/Sandbox SDK remain.
Package import no longer eagerly loads solver and plotting modules merely to
serve a login page or validate JSON.

The directly served renderer is Plotly.js 4.1.1 from the installed Python
Plotly 7.1.0 distribution: 4,815,814 bytes, SHA-256
`3b6e15d45dbb7fca5bd2094291e961ddc5472cd887009e6009a56dab668d721f`.
Its MIT header and the existing project license notice are retained. The
JavaScript plot editor, CSS and HTML controls themselves are unchanged.

Existing Flask, Vercel SDK and NumPy components are reused. A GitHub check of
`caibingcheng/vercel-flask` found a basic BSD-3-Clause example, but its maintenance
and compatibility with this application's private authentication, storage and
Sandbox orchestration were not established. The Hugging Face
`SpacesExamples/flask-starter` example showed a runtime error and its applicable
license was not confirmed. Neither replaces the existing hosting architecture;
no third-party project code is copied into this repair.

## Local verification

Local packaging checks completed so far:

- A fresh isolated Windows environment installed exactly the 25 pinned web
  packages; `pip check` passed and the installed set contained no extra packages.
- The minimal-environment probe imported the actual application entrypoint,
  exercised login/authentication/CSRF, all four 163-field baseline schemas and
  validation routes, and rejected a negative-area input. It served Plotly
  without importing SciPy, CoolProp, Matplotlib or Python Plotly. A synthetic
  saved-array fixture checked inputs/boundary-conditions/geometry/results CSV
  values, units and dimensions, retained a legacy precursor nonfinite gap as
  JSON null, and left artifact bytes unchanged. This fixture is an interface
  test, not a new solver result or live storage test.
- 51 focused packaging/isolation/gateway checks and 36 frontend checks passed.
  The focused tests overlap the full suite; their counts must not be summed.
  The final full Python suite passed all 832 tests in 202.62 seconds, retaining
  two FourField divide-by-zero/invalid-multiply warnings. The warnings are
  recorded rather than suppressed; they do not become physical-validation
  evidence because the suite passed.
- The first full Python suite recorded 831 passes and one failure: the
  current-release Sawai source guard treated the changed package initializer
  as a numerical source change. The initializer only changes when the original
  classes are imported; it contains no equations or numerical controls. The
  current-release guard now explicitly excludes this import wrapper alongside
  its existing GUI exclusions, with separate public-class identity tests.
  Every remaining frozen hash and the exact source inventory checks remain
  enforced. The historical diagnostic manifest and strict replay command are
  unchanged. The failed run is retained as `full-python-tests.txt`; the passing
  rerun after this test-scope correction is `full-python-tests-final.txt`.
- The installable source archive and wheel built successfully; the receipt is
  `package-build.txt`.
- A CPython 3.12 Linux-wheel audit measured the full 48-package environment at
  104,937,518 compressed bytes and 349,270,602 uncompressed wheel-entry bytes.
  The 25-package web environment is 20,884,230 compressed bytes and 69,020,004
  uncompressed wheel-entry bytes: an independently checked 80.24% reduction
  in the latter. The 4,815,814-byte renderer asset is counted separately.
  These are wheel payloads, not a measured Vercel peak-disk requirement or
  deployed-function size; no cold-start latency guarantee follows from them.
- A strict source/ledger audit allows only the package initializer and hosted
  asset route to change among tracked Python modules. All other 30 package
  modules, three GUI controls/assets, full worker dependency manifests and all
  81 acceptance criteria/status sets match the retained formatting release.
  The generated acceptance matrix check passed.

## Production verification

The two live HTTP campaigns passed 22 and 26 requests respectively, including
the page, authentication, all four baseline loading/validation paths, matching
JavaScript/CSS (after newline normalization), byte-identical renderer delivery,
and six concurrent reads in each campaign. The
second campaign also passed all four CSV download routes. Receipts are
`live-startup.json` and `live-with-exports.json`.

A fresh FourField baseline, run `afa655391ef8460caadf7c735b3f1db7`, completed and
converged through the unchanged scientific worker. Independent comparison of
downloaded archived steady/initialization profiles passed the retained
`rtol=1e-8, atol=0` criteria, with maximum relative error
`2.539607937805446e-9`. Its checksummed artifacts and comparison are retained in
`live/20261116T020421Z-7f7fd114/summary.json`. Supplementary nonfinite diagnostic
entries remain: this does not claim that all arrays are finite, all operating
conditions work, or experimental validation has been established. No new MATLAB
execution was performed; archive-producer version uncertainties remain.

Runtime-log queries over the recorded post-deployment window found no disk-full
or dependency-installation failure, and no error/fatal records. The HTTP and
worker checks provide the positive service evidence; absence of log matches
alone is not a health test. GitHub CI run `43789798181` independently verified
the deployed commit: 832 Python tests, 36 frontend tests, isolated web-runtime
probe, and source/wheel builds passed, retaining the same two FourField warnings.
See `deployment-runtime-checks.json` and `github-ci.json`.

Browser inspection confirmed the retained plot controls and usable completed
results. Opening the job before durable publication left a stale “Could not
open run: Durable results are not ready” banner after completion. Refreshing
and reopening cleared it. The original and refreshed screenshots are retained
as `live-fourfield-result.png` and `live-fourfield-after-refresh.png`; this
pre-existing warning-lifecycle limitation is separate from the startup 500 and
was not changed by this packaging repair. `live-plot-controls.png` records the
retained presentation controls.

These observations cover one deployment and one new FourField calculation.
Concurrent requests do not establish independent cold starts, long-term
availability, or an exhaustive concurrency/performance guarantee.

Evidence is retained under `outputs/verification/hosted-startup-fix-01/`.
This infrastructure work adds no MATLAB-equivalence or experimental-validation
claim and changes no scientific acceptance criterion or status axis.
