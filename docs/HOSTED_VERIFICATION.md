# Hosted interface verification

Date: 2026-11-15. **All four hosted baseline workflows and cancellation passed.** This report records the
hosted adapter separately from scientific parity and experimental validation.
The production interface is <https://openstream-py.vercel.app>; its shared
password is a deployment secret and is not recorded here.

## Scope and unchanged scientific source

The hosted application calls the existing `openstream.gui_worker` in a separate
Linux Sandbox process. It uses the existing input validator, numerical worker,
archived-reference comparison and saved-array plot-data generator. Hosting
changes authentication, execution transport, packaging and durable publication;
it does not change governing equations, closure models, tolerances or defaults.

The 25 top-level Python modules under `src/openstream/` are byte-identical in
Git between scientific source checkpoint
`e7ba765e9f3e75f482cea6f1fd9c3b38931680e9` and deployment commit
`ae7da5be960e1b4e20ad7a53e18c6b53b925d563`. This was independently checked using
committed blob bytes, avoiding Windows checkout newline conversion. The SHA-256
of their sorted JSON path-to-SHA-256 inventory is
`565fb11d08a4963a9ac67316727bd6a78563c9b4110838f939ec40005c90419f`.
Each worker also checks its supplied module hashes before and after execution.

The [worker provenance receipt](../outputs/verification/hosted-release/worker-provenance.json)
records all five terminal manifests' source hashes, actual Python/package
versions, publication state and artifact hashes, omitting private storage URLs.
The [source bundle inventory](../outputs/verification/hosted-release/source-bundle.json)
and [deployment/CI receipt](../outputs/verification/hosted-release/deployment-and-ci.json)
bind that evidence to the deployed Git commit and successful Windows CI job.

The archived GUI comparison retains `rtol=1e-8`, `atol=0`, and coordinate
`atol=1e-12`. Its scope is the selected TUTORIAL1 steady W/U/H profiles and
initialization histories; FourField additionally includes actual base-film
W/U/H and wave frequency. Supplementary diagnostics and mixture precursor
histories are outside that GUI comparison. Agreement is not a fresh MATLAB
execution, complete MATLAB parity, or validation against measurements.

## Local verification

Recorded test runs are separate snapshots and must not be added together:

| Run | Observed result | Scope |
|---|---:|---|
| Original project suite after introducing the adapter | 682 passed, reported tool result | Included 110 hosted tests at that checkpoint; console output was not retained as a file |
| Expanded focused hosted checks | 226 passed, reported tool result | Includes 21 offline HTTP-driver tests; console output was not retained as a file |
| Final full local project suite | 798 passed; 2 warnings; 200.43 s | Captured in `outputs/verification/hosted-release/local-pytest.txt` |

The two retained warnings are division by zero and invalid multiplication in
the original FourField drag diagnostics (`ff_fields.py:178` and `:140`). They
were not suppressed or resolved by changing an equation. The separate Windows
[CI run 43743883420](https://github.com/romanwilliammorse/OpenSTREAM_pyversion/actions/runs/43743883420)
also succeeded for `ae7da5b`; the 798 count above is the captured local result.

The focused checks cover authentication, CSRF, fixed session expiry, immutable
storage and collision handling, publication ordering, transport failures,
checksummed downloads, exact-session Sandbox operations, source integrity,
cancellation and deployment packaging. A real local 100-cell Mixture child
was compared with the archived physical and initialization profiles at the
unchanged tolerances. Fake SDK tests establish adapter behavior under controlled
conditions; they do not replace live provider or browser checks.

Relevant tests: `tests/test_cloud_auth.py`, `tests/test_cloud_gateway.py`,
`tests/test_cloud_manager.py`, `tests/test_cloud_storage.py`,
`tests/test_cloud_worker.py`, `tests/test_cloud_packaging.py`,
`tests/test_cloud_deployment_bundle.py`, and `tests/test_verify_hosted_gui.py`.

## Live storage and access checks

The real private Blob limiter received eight parallel claims: five were
admitted and three denied. Exactly five immutable objects were retained;
five authenticated readbacks succeeded and anonymous Blob access returned
HTTP 403. Evidence:
[`hosted-storage receipt`](../outputs/verification/hosted-storage/6d6993053d1b4e22972e0f54ec8e8329/receipt.json).

The live HTTP checks rejected anonymous API, application-script and file
requests with HTTP 401. Login without CSRF and authenticated requests without
CSRF or from another origin returned HTTP 403; an incorrect password returned
HTTP 401. Correct login and authenticated API access returned HTTP 200. The
session cookie had the `__Host-` prefix, Secure, HttpOnly and SameSite=Lax
attributes, with no Domain attribute. The first attempt also verified logout
and subsequent HTTP 401. Evidence is retained in each HTTP session's
`authentication_checks.json` and `summary.json`; credentials, cookies and CSRF
tokens are deliberately not saved.

## Deployment and retained failures

GitHub API HTTP 429 and the provider's `git_info_fail` prevented the repository
deployment route. The fallback uses an explicit allowlist of exact committed
source bytes, per-file SHA-1/SHA-256 and sizes, and retained licenses. Secrets,
untracked outputs, caches and the local `pyproject.toml` are excluded. No file
upload is accepted as proof that the application works. The GitHub deployment
connection remains unconnected pending account authorization; automatic
redeployment from GitHub is not established by this manual source-file release.

The deployed builder rejected a requirements include referring to the `.lock`
file. Root `requirements.txt` was flattened to the identical pinned dependency
list; a test checks equality with `requirements-cloud.lock`. The actual Blob
SDK's HTTP 400 existing-object message also required an explicit collision
whitelist; arbitrary provider errors remain failures rather than admitted
login slots.

| Attempt / evidence | Observed outcome | Cause and disposition |
|---|---|---|
| Mixture `1daa66819b3e470fa50ebd2e17d4ea7e`; [HTTP session 1](../outputs/verification/hosted-http/20261115T174732Z-72274e78/summary.json) | Native convergence reached; output failed. Driver received HTTP 409 while recovering status and did not resubmit. | Worker source lacked installed distribution metadata required by the unchanged output writer. Bootstrap packaging and status recovery were corrected. Original failed attempt retained. |
| Mixture `549779f66eec4602a88667a28c279d5c`, TwoFluid `5a59cdf152414d5fb522b6f179dfcd16`, ThreeField `3d93cb801b014d5face5506027219f44`; [HTTP session 2](../outputs/verification/hosted-http/20261115T175320Z-37b93b7b/summary.json) | All three reached native convergence and retained failed terminal statuses. Their retained `gui_verification.json` files report archived agreement; none completed the hosted workflow. | ZIP creation rejected the submitted-input timestamp before 1980. Tracebacks identify file metadata handling, not numerical equation failure. Empty 22-byte ZIPs and partial outputs are preserved. |

The second attempt used deployment commit
`f63e58542ea82ad4dd8ff46db4751781aa209bb2`, deployment ID
`dpl_D1wzYzRNANyEXo3EmECJyKYhTau7`, with 80 source files totaling 1,357,911
bytes. The driver was intentionally interrupted after three failed terminal
results. FourField `0f5377a1d77c4ed18f2ddbec3789232c` had already been submitted;
its terminal outcome was not observed by that interrupted driver. Cancellation
was not attempted. The incomplete original summary is unchanged; a separate
[`interruption record`](../outputs/verification/hosted-http/20261115T175320Z-37b93b7b/interruption.json)
records that limit.

Corrective deployment `ae7da5be960e1b4e20ad7a53e18c6b53b925d563`
(`dpl_4c32d5nAxmgZRSeFVVNBAqEKWQDY`, 80 files / 1,358,293 bytes) changes only
the wrapper: after verifying submitted-input bytes, it updates an input
timestamp earlier than 1980 using `os.utime`. Input content and the native ZIP
writer remain unchanged. The 28 worker tests pass with a real Mixture
regression using a simulated epoch timestamp. The following fresh live run
verifies the corrected deployment independently of those retained failures.

## Final live baseline and cancellation results

The [final HTTP session](../outputs/verification/hosted-http/20261115T175731Z-a0e1560b/summary.json)
ran from 17:57:31 to 18:00:58 UTC. It submitted each case once, observed terminal
publication, downloaded retained outputs, checked array shapes and primary
finite values, retrieved plot data, and independently repeated the archived
comparison against the downloaded numerical files. The driver reports all
five attempts passed. Its Python 3.12.14 is the local verification interpreter;
the hosted worker uses pinned Python 3.12.16.

| Framework | Run ID | Native convergence | Archived GUI profiles | Largest relative difference | Physical-review status |
|---|---|---|---|---:|---|
| Mixture | `47b8e605097f476db27a6869e551b037` | Passed | 18 records passed | 2.86867e-13 | Passed scoped checks |
| TwoFluid | `31bdc0a96f194ec1a3dac210568e4b28` | Passed | 12 records passed | 2.38511e-13 | Failed; retained |
| ThreeField | `8b87b512f1594e08a6d59082e4de90a8` | Passed | 12 records passed | 4.73873e-13 | Informational |
| FourField | `56c656bbe0bd4f6e908c190ab26d1f83` | Passed | 26 records passed | 2.53961e-9 | Informational |

These 68 comparison records include physical and initialization arrays; they
are not a count of verified model branches. Each comparison uses the unchanged
tolerances above. The original archive producer's exact MATLAB, CoolProp and
source versions remain unknown.

TwoFluid retains a maximum relative area-closure discrepancy of
0.41056107069003445 and an outlet discrepancy of 0.03467311857852917, against
the existing 1e-6 diagnostic tolerance. Its reported mass and energy residuals
are -3.0761341617002724e-7 kg/s and 30.049663123398204 W. These existing diagnostic
results were not converted to a pass because transport and archived comparisons
passed. ThreeField and FourField retain informational annular phase-volume
review; no extra annular closure criterion was introduced.

FourField retains 101 nonfinite entries in initialization
`film.wave.ITR.DF`. All primary/archive profiles and coordinates are finite;
the diagnostic entries remain visible in
[`array_checks.json`](../outputs/verification/hosted-http/20261115T175731Z-a0e1560b/04-FourField/array_checks.json).
The report does not label every diagnostic array finite.

The separate FourField cancellation run
`327cc37e04614aea8c071c7d9d112aa4` reached the terminal `cancelled` state.
It has no convergence or archived-comparison claim. Logout returned HTTP 200;
subsequent anonymous API access returned HTTP 401. Per-case verification files
retain download sizes and SHA-256 values. Authentication payloads and tokens
were not recorded.

## Acceptance impact and remaining work

Only interface evidence rows API-012, API-014 and API-016 are extended.
Their acceptance criteria and implementation/native/MATLAB/physical/experimental
status axes remain unchanged. Hosting tests cannot close gaps in source session
semantics, complete plotting options, tutorial operation coverage, or physical
validation.

The scripted hosted checks and full local suite above passed. The saved
[FourField browser viewport](../outputs/verification/hosted-release/hosted-fourfield.png)
was also visually inspected: it displays the model selector, collapsed saved-run
control, logo, completed result, separate convergence/reference/informational
statuses, and a mass-flow chart labeled in kg/s. This confirms one desktop
view; it does not establish every plot/control or mobile layout. The
[browser-verification receipt](../outputs/verification/hosted-release/browser-verification.json)
records the screenshot hash, observed controls, reviewer/operator distinction
and the limits of this viewport. A fresh
deployment-restart durability exercise and automatic GitHub deployment remain
outside this evidence. Native convergence, archived
agreement and physical-review statuses remain independent. Infrastructure
deadlines, failed setup and failed publication remain explicit failures.
Full MATLAB parity and experimental validation still require the outstanding
scientific acceptance work; this deployment adds no new experimental evidence.
