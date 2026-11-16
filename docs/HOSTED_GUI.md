# Hosted OpenSTREAM GUI

The hosted interface uses the same editor, input validation, native calculation
worker, reference comparisons and plotting data as the Windows application.
Hosting does not establish additional MATLAB equivalence or experimental
validation. The scientific acceptance matrix remains authoritative.

## Reference display

Unchanged ThreeField/FourField cases use the short label “Le Corre 2025”.
Expanded details identify the NURETH-21 manuscript and the actual TUTORIAL1
archive; the author-supplied association does not establish direct provenance
to published curves. Custom or ambiguous inputs hide reference status and
overlays. Mixture/TwoFluid remain labeled OpenSTREAM TUTORIAL1 until a source
association is established. See `GUI_REFERENCE_LABELS.md` for scope and checks.

## Architecture and access

The Vercel Flask application authenticates a shared password on the server.
Only its scrypt hash and a randomly generated session secret are configured as
deployment secrets. The password is not included in the repository or browser
JavaScript. Sessions use Secure, HttpOnly, SameSite=Lax cookies, an eight-hour
absolute lifetime and CSRF protection for mutations. A fixed-window, atomic
private-Blob login limiter admits five attempts per client IP per minute.
Signing out removes the session; an expired-session dialog retains unsaved
editor inputs. Users with the shared password share run history.

Each calculation runs once in an isolated Vercel Sandbox with no public ports,
two vCPUs and a 40-minute wall-clock allowance including setup and publication.
Python 3.12.16 and `requirements-cloud.lock` are installed in that worker.
The exact deployed source bundle is transferred; top-level Python module hashes
are verified before and after execution. A small worker packaging manifest
installs that source as an editable `openstream-python` distribution, preserving
the version metadata required by the native output writer. `openstream.gui_worker` performs the
calculation unchanged. No solver, closure, equation, tolerance or application
default is changed by the hosting adapter.

Submitted inputs precede worker creation. Inputs, source/environment metadata,
outputs, plots and hashes are retained in a private Blob store. A terminal
manifest is published only after its referenced artifacts. The GUI exposes
completed results only after that durable publication. Downloads require an
authenticated session and verified size/SHA-256; private Blob URLs and worker
credentials are not sent to the browser. History survives application restarts.
Cancellation uses the native worker's cancel request; acknowledgement is not
misrepresented as completed cancellation. Stopped workers are never resumed or
automatically retried. Interrupted and failed attempts remain in history.

The application admission limit of two active calculations is best effort
across concurrent function instances, not an atomic distributed quota.
Provider account quotas remain applicable; resource exhaustion must be reported
as a failure, not as a numerical result. Bootstrap or publication failures may
leave temporary worker evidence available only until the sandbox expires.

## Deployment

Production address: `https://openstream-py.vercel.app`.
Project: `openstream-py`; region: `iad1`; private store: `openstream-py-results`.

The project is connected to `romanwilliammorse/OpenSTREAM_pyversion` through
the Vercel GitHub app. Pushes to `main` trigger production builds. Inspect build
logs and the deployed commit before treating a Git deployment as verified.
The original tested release used the explicit source-file deployment path;
its receipts remain preserved in `outputs/verification/hosted-release/`.

Required deployment environment variables:

- `OPENSTREAM_PASSWORD_HASH`: Werkzeug scrypt password hash.
- `OPENSTREAM_SESSION_SECRET`: cryptographically random secret, at least 32 characters.
- `OPENSTREAM_PUBLIC_ORIGIN`: the exact HTTPS production origin.
- `BLOB_STORE_ID`: connected private Blob store identifier.
- `OPENSTREAM_CLOUD_JOB_SECONDS=2400`.
- `OPENSTREAM_CLOUD_MAX_ACTIVE=2`.

Enable project OIDC and connect the private Blob store. The official
`vercel-sandbox` and `vercel-blob` Python SDKs provide the resource interfaces.
The SDK's MIT license is retained in `licenses/vercel-python-sdk-MIT.txt`.
Repository search selected these maintained, compatible official components;
the Hugging Face search identified no suitable reusable hosting component.

The root `app.py` is the Vercel entry point. `.vercelignore` excludes the local
package manifest **from the deployment only** so the Python builder uses
`requirements.txt`. The startup repair separates that web/API manifest from
the full scientific worker environment: its pins match `requirements-web.lock`,
while Sandbox calculations retain `requirements-cloud.lock`. The deployed
builder previously rejected a `.lock` include, so the web pins are copied into
`requirements.txt` and checked for equality. See `HOSTED_STARTUP_FIX.md` for the
failure evidence, repair boundary and observed verification status.
It also excludes research outputs, local environments, upstream checkouts and
secrets. Normal `pip install .[gui]` and Windows launchers are unchanged.
The worker image is pinned by digest in `cloud/gateway.py`.

Production should use application password authentication. Vercel account SSO
protection must not prevent ordinary invited users from reaching the password
page. Do not disable application authentication to diagnose platform access.

## Reproducible local checks

```powershell
py -3.12 -m venv .venv-cloud
.venv-cloud\Scripts\python -m pip install -r requirements-cloud.lock
.venv-cloud\Scripts\python -m pip install --no-deps -e .
.venv-cloud\Scripts\python -m pytest -q
```

Hosting tests cover authentication/CSRF/expiry, immutable storage, transport
errors, publication ordering, checksummed downloads, source integrity,
cancellation and one real Mixture child against archived profiles. Cloud SDK
test doubles do not by themselves establish deployed provider compatibility.
The deployment verification record distinguishes local tests from live runs.

Relevant provider documentation:
[Python runtime](https://vercel.com/docs/functions/runtimes/python),
[Sandbox SDK](https://vercel.com/docs/sandbox/python-sdk-reference),
[private Blob Python SDK](https://vercel.com/docs/vercel-blob/python-sdk-reference).
