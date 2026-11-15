# Licenses and reused components

Optional GUI dependencies are Flask 3.1.3 (BSD-3-Clause), Plotly 7.1.0 (MIT),
and Waitress 3.0.2 (ZPL-2.1), plus their pinned dependencies in
requirements-gui.lock. Exact direct-component license texts are retained in
licenses/gui. See GUI_COMPONENT_REVIEW.md for search and reuse decisions.

The GUI uses the preserved OpenSTREAM logo from the pinned upstream source
under the retained project notice. Lato and Roboto Slab web fonts are copied
unchanged from sphinx-rtd-theme 3.1.0. Theme MIT, SIL Open Font License, and
Apache 2.0 notices are retained in licenses/gui. The visual design follows the
official OpenSTREAM documentation's Read the Docs theme; no network font or
theme service is required during operation.

The source translation retains OpenSTREAM's MIT notice in the repository LICENSE and unchanged upstream/LICENSE. The pinned CoolPropWrapper submodule retains its own MIT LICENSE and is preserved for comparison; its MATLAB code is not a normal-operation dependency. An exact additional copy is in licenses/CoolPropWrapper_LICENSE. Built wheels and source distributions include both notices and this file; dependency wheels retain their own license notices.

Native runtime components are CoolProp (MIT), NumPy (BSD), SciPy (BSD and bundled third-party notices) and Matplotlib (Matplotlib license and bundled notices). Their distributions include their own authoritative license texts. No source from unrelated candidate solvers, PyFluids or Hugging Face projects was copied. Python itself is supplied separately under the PSF license.

Reproducible versions are pinned in pyproject.toml and requirements.lock. Search, suitability, maintenance and compatibility evidence is in UPSTREAM_AUDIT.md. Installation of a package does not imply suitability of every empirical model for every fluid or regime.

The optional reference-recovery tools use mat-io 1.0.2 under BSD-3-Clause,
installed separately under .venv/reference-reader with its dependency notices.
An inspected source checkout and LICENSE are preserved under tools/vendor/matio;
that inspection checkout is excluded from distributions. An additional exact
notice is retained in licenses/mat_io_LICENSE and bundled. The normal solver
does not import mat-io, pandas or h5py. See tools/REFERENCE_READER.md and
tools/requirements-reference.lock for provenance, reuse evaluation and the
documented local enumeration-reader workaround. No MAT archive was modified.
