# GUI component and reuse review

Reviewed 2026-11-14 for the local Windows Python 3.12 GUI. Searches included
GitHub repositories for OpenSTREAM/Python/GUI and Hugging Face Spaces for
OpenSTREAM. No compatible OpenSTREAM thermal-hydraulic GUI port was identified
in the returned results. This is a search outcome, not proof none exists.

Hugging Face returned `yashm/OpenStream` (MIT; Streamlit 1.32.0 in its card) and
`cyEdward/open_streamlit` (license `other`; Streamlit 1.56.0 in its card, updated
2026-04-22). Neither result established compatibility with the OpenSTREAM solver
API or reference input/verification requirements. No code was reused from
either. Name matches for media/streaming projects on GitHub were likewise
unsuitable for this scientific application.

Reused installed, maintained components:

| Component | Tested version | License | Role and compatibility |
|---|---|---|---|
| [Flask](https://github.com/pallets/flask) | 3.1.3 | BSD-3-Clause | Local HTTP API and static files; Python 3.12 compatible; current 3.1 documentation inspected |
| [Waitress](https://github.com/Pylons/waitress) | 3.0.2 | ZPL-2.1 | Windows-compatible WSGI server; bound explicitly to 127.0.0.1 |
| [Plotly.py / Plotly.js](https://github.com/plotly/plotly.py) | 7.1.0 Python distribution | MIT | Bundled local JavaScript for zoomable plots and PNG export; no CDN or hosted service |

GitHub repositories and release/official documentation pages were inspected.
All three installed from PyPI successfully in the existing CPython 3.12
environment; `pip check` passed. Exact direct and transitive GUI dependencies
are in `requirements-gui.lock`. Installed distribution license metadata was
checked; their license files are retained under `licenses/gui/`.

Flask and Plotly supply reusable serving and visualization infrastructure.
The OpenSTREAM-specific schema, provenance, runner, and comparison are local
adapters to the existing package. They do not implement alternative physics.
The solver imports no GUI package, preserving independent CLI/API operation.

Technical references: [Flask security and host restrictions](https://flask.palletsprojects.com/en/stable/web-security/),
[Flask configuration](https://flask.palletsprojects.com/en/stable/config/),
[Waitress server options](https://docs.pylonsproject.org/projects/waitress/en/stable/runner.html),
[Plotly offline source](https://github.com/plotly/plotly.py/blob/main/plotly/offline/offline.py).
