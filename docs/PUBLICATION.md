# Public repository and GUI release

Published on 2026-11-14 to
[romanwilliammorse/OpenSTREAM_pyversion](https://github.com/romanwilliammorse/OpenSTREAM_pyversion),
with public visibility as requested. The initial complete source/evidence commit
is `9b3d67e8e56f30381a7ae127792de42079148546`; local and remote hashes matched.
Follow-up commits record documentation and verification evidence.

The upload retains Python source, GUI assets, tests, examples, licenses, inputs,
portable MATLAB reference arrays, numerical outputs, plots, historical failures,
and provenance. Original MATLAB source and CoolPropWrapper remain pinned Git
submodules; clone with `--recurse-submodules`. Local environments, caches,
scratch checkouts, build output and live process locks are excluded. See
[REPOSITORY_CONTENTS.md](REPOSITORY_CONTENTS.md) for the inventory policy.

The original documentation logo and locally served Lato/Roboto Slab fonts are
used with the documentation's blue header and dark sidebar. Supporting prose is
in expandable help; input units, reference/default values, errors and separate
verification statuses remain available. All 163 inputs remain in the editor.
Numerical equations and comparison tolerances were not changed for this release.

Local verification passed 84 GUI Python tests and five JavaScript tests. A live
mixture run through the new interface converged and passed its archived profile
comparison and implemented physical checks. PNG export and saved-run rendering
were checked. The four-field view retains its failed physical-consistency status.
The installed 0.2.1 wheel passed a separate real mixture calculation and asset,
reference-array and license-notice checks.

The initial [Windows CI run](https://github.com/romanwilliammorse/OpenSTREAM_pyversion/actions/runs/43659759994)
completed successfully, including clean recursive checkout, dependency/package
installation, all Python tests, JavaScript tests and distribution builds. Logs
and package fingerprints are retained under `outputs/verification/`. Results:
**213 Python tests passed, with two runtime warnings**, and **five JavaScript
tests passed**. The warnings originate in the preserved four-field drag/force
expressions (division by zero and invalid multiplication); they were recorded,
not suppressed or fixed by changing the governing model. The physical failures
documented for the multifield baselines remain failures even though tests of
their correct detection pass.

Publication and passing software tests do not establish complete OpenSTREAM
parity or experimental validation. The current evidence supports the four
selected archived steady baselines. Physical validation will use
[OpenSTREAM-database](https://github.com/OpenSTREAM-solvers/openstream-database);
no experimental comparison was executed in this release. The prioritized
remaining work is in [PARITY_COMPLETION.md](PARITY_COMPLETION.md).
