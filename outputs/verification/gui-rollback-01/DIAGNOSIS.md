# Hosted startup failure diagnosis

The screenshot request was matched exactly to Vercel runtime logs:
`gbvgb-1794791551007-ea69aa433ef7`, `POST /api/validate`,
2026-11-16 01:12:33.992 UTC, deployment
`dpl_36vDBqcvPKM7Hx5iu7eM6cwNV8yv` (commit `e09e11f`).

Vercel's runtime dependency installer failed while writing the Plotly 7.1.0
wheel cache to temporary storage: **No space left on device (os error 28)**.
The installer exited with code 2; the Python process exited with code 1.
Flask input validation and the numerical solver had not started. The failure
therefore does not establish bad user inputs or a governing-equation problem.

The same deployment logged similar startup extraction failures for SciPy,
NumPy and CoolProp. A focused 35-minute query returned 15 matching failure
records; this is a sample count, not an exhaustive failure rate. Successful
runtime installations taking 2.35 s and 3.16 s were also logged. Repeated
startup installation contributes delay, but the total perceived slowdown
has not been quantitatively attributed.

The formatting release changed only three GUI static files within `src`.
Comparison of `ce67394` and `e09e11f` shows no changes to Python modules,
`app.py`, dependency manifests, or `vercel.json`. Thus the color/font
JavaScript is not established as the cause of this server failure. The
redeployment exposed a startup packaging/resource failure in the shared
hosting configuration. The existing package imports solver and plotting
modules eagerly, and the hosted requirements include the scientific and
development dependencies in addition to the web layer.

An older warm deployment may restore service, but rollback alone cannot
establish that future cold starts are safe. The durable follow-up is to audit
a smaller web/API dependency environment while retaining the unchanged
scientific worker environment, then verify independent cold starts and
normal concurrent requests. No such change is made by this diagnostic audit.

Evidence: `exact-request-runtime-log.txt` and `startup-diagnosis.json`.
Temporary cache path names are redacted. No authentication data or private
storage URLs are included. The platform classifies these startup failures as
info/stderr, so an error-level-only log scan missed them.
