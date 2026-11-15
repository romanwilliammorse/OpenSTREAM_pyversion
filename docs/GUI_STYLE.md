# GUI style and simplification

The 0.2.1 interface follows the [OpenSTREAM documentation](https://openstream.readthedocs.io/en/latest/Guides/tutorials.html).
Its rendered page was inspected directly: Lato body text, Roboto Slab headings,
blue `#2980b9` navigation header, charcoal `#343131` sidebar, `#404040` text and
`#fcfcfc` content background. The logo is the unchanged
`docs/source/_static/logo-transparent.png` from upstream commit
`a614c7173822a93c1e64ac28d1541cbac028cbd8`.

All four font assets are copied without modification from the PyPI
`sphinx_rtd_theme-3.1.0` wheel and served locally. License notices are in
`licenses/gui/`. The theme package is an asset source, not a runtime dependency.

The interface removes repeated workflow instructions and decorative text.
Field descriptions, provenance and applicability remain available in expandable
help. Units, input values, reference/default values, edits, errors and the three
verification statuses remain visible. The form retains all 163 inputs. Numerical
algorithms, equations, and reference-comparison tolerances are unchanged.

## Verification on 2026-11-14

- Compared the rendered local interface with the supplied documentation page.
  Confirmed the original logo, Lato/Roboto Slab fonts, blue header and dark sidebar.
- Counted 163 rendered input controls. Tested search, editing, reference reset,
  edited-only filtering, input checking, and restored baseline identification.
- Ran the mixture baseline through the updated interface: converged, archived
  profiles agreed, and implemented physical checks passed. Exported its PNG.
- Opened the completed four-field run: archived agreement and failed physical
  consistency remain separately visible, together with the pre-annular warning.
- All 84 GUI Python tests and five JavaScript logic tests passed. The numerical
  implementation was unchanged; the prior full-suite evidence is retained.
- Built and installed version 0.2.1 in an isolated wheel environment; verified
  assets, license notices, baseline files and a real mixture calculation.

Evidence: `outputs/verification/gui-restyle-tests.log`,
`gui-restyle-backend-tests.log`, `gui-0.2.1-package.json`, and the
`gui-clean-inputs.jpg` / `gui-clean-results.jpg` screenshots in that directory.
The existing local server retains its startup version label (0.2.0) until its
next restart; it serves the updated static interface and starts version 0.2.1
workers. This cosmetic update does not establish experimental validation or
expand the documented numerical-equivalence scope.
