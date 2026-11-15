"""Local browser application; numerical work runs in an isolated process."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
from urllib.parse import urlsplit
import uuid

import numpy as np

from .gui_worker import write_json


TERMINAL = {'completed', 'cancelled', 'failed'}


class RunManager:
    def __init__(self, root):
        from .gui_lock import FileLock, worker_alive
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.server_lock = FileLock(self.root/'server.lock').acquire()
        self.processes = {}
        self.lock = threading.RLock()
        # A newly started server never assumes an old partial job completed.
        for p in self.root.glob('*/status.json'):
            state = json.loads(p.read_text(encoding='utf-8'))
            if state.get('status') not in TERMINAL and not worker_alive(p.parent):
                state.update(status='failed', phase='Interrupted', error='The application stopped before this run completed.')
                write_json(p, state)

    def directory(self, run_id):
        if not re.fullmatch(r'[0-9a-f]{32}', run_id): raise KeyError('Unknown run')
        path = self.root/run_id
        if not (path/'status.json').is_file(): raise KeyError('Unknown run')
        return path

    def status(self, run_id):
        from .gui_lock import worker_alive
        with self.lock:
            path = self.directory(run_id)/'status.json'
            state = json.loads(path.read_text(encoding='utf-8'))
            process = self.processes.get(run_id)
            if process and process.poll() is not None and state['status'] not in TERMINAL:
                state.update(status='failed', phase='Failed', error=f'Worker exited with code {process.returncode}; inspect worker.log.')
                write_json(path, state)
            elif process is None and state['status'] not in TERMINAL and not worker_alive(path.parent):
                state.update(status='failed', phase='Interrupted', error='Worker stopped before completing this run.')
                write_json(path, state)
            return state

    def history(self):
        return sorted((self.status(p.parent.name) for p in self.root.glob('*/status.json')),
                      key=lambda s: s['created_at'], reverse=True)

    def start(self, payload):
        from .gui_schema import validate_payload, assess_payload, framework_name
        payload = {**payload, 'framework': framework_name(payload.get('framework'))} if isinstance(payload, dict) else payload
        validate_payload(payload)
        assessment = assess_payload(payload)
        with self.lock:
            if any(s['status'] not in TERMINAL for s in self.history()):
                raise RuntimeError('A calculation is already running. Wait for it or cancel it before starting another.')
            run_id = uuid.uuid4().hex
            path = self.root/run_id
            path.mkdir()
            write_json(path/'submitted_inputs.json', payload)
            state = {'id': run_id, 'framework': payload['framework'], 'status': 'queued', 'phase': 'Starting',
                     'created_at': datetime.now(timezone.utc).isoformat(), 'progress': [], 'files': [],
                     'converged': None, 'error': None, **assessment,
                     'reference': {'status': 'not_compared', 'message': 'Comparison runs after the calculation.'},
                     'physical': {'status': 'not_checked', 'message': 'Consistency checks run after the calculation.'}}
            write_json(path/'status.json', state)
            python = Path(sys.executable)
            if python.name.lower() == 'pythonw.exe': python = python.with_name('python.exe')
            try:
                with (path/'worker.log').open('w', encoding='utf-8') as log:
                    process = subprocess.Popen([str(python), '-m', 'openstream.gui_worker', str(path)],
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                self.processes[run_id] = process
            except Exception as exc:
                state.update(status='failed', error=str(exc), phase='Worker could not start')
                write_json(path/'status.json', state)
                raise
            return state

    def cancel(self, run_id):
        with self.lock:
            state = self.status(run_id)
            if state['status'] in TERMINAL: return state
            p = self.processes.get(run_id)
            if p is None:
                # A worker surviving a server restart acknowledges cancellation
                # at its next progress callback; do not claim it has stopped yet.
                (self.directory(run_id)/'cancel.request').touch()
                return state
            if p and p.poll() is None:
                p.terminate()
                p.wait(timeout=10)
            state = self.status(run_id)
            state.update(status='cancelled', phase='Cancelled', error=None,
                         finished_at=datetime.now(timezone.utc).isoformat())
            write_json(self.directory(run_id)/'status.json', state)
            return state


def json_array(array):
    a = np.asarray(array, dtype=float)
    return np.where(np.isfinite(a), a, None).tolist()


def plot_data(directory, framework, is_reference):
    from .gui_reference import load_reference
    output = Path(directory)/'output'
    metadata = json.loads((output/'metadata.json').read_text(encoding='utf-8'))
    datasets = {}
    for name, filename in [('physical', 'results.npz'), ('initialization', 'initialization.npz')]:
        with np.load(output/filename, allow_pickle=False) as arrays:
            fields = {k: {'values': json_array(arrays[k]), 'unit': metadata['units'].get(k, ''),
                          'units': metadata['units'].get(k, '')} for k in arrays.files if k not in ('Z', 'TIME')}
            datasets[name] = {'z': arrays['Z'].tolist(), 'time': arrays['TIME'].tolist(), 'fields': fields,
                              'time_label': 'Physical time [s]' if name == 'physical' else 'Initialization pseudo-time [s]'}
        if is_reference:
            ref = load_reference(framework, name)
            datasets[name]['reference_fields'] = ref['fields']
            datasets[name]['reference_z'] = ref['z']
            datasets[name]['reference_time'] = ref['time']
    # Additional mixture pressure/quality/heat-flux plots for multifield cases.
    if (output/'mixture'/'results.npz').exists():
        mm = json.loads((output/'mixture'/'metadata.json').read_text(encoding='utf-8'))
        with np.load(output/'mixture'/'results.npz', allow_pickle=False) as arrays:
            datasets['precursor'] = {'z': arrays['Z'].tolist(), 'time': arrays['TIME'].tolist(),
                'time_label': 'Mixture precursor physical time [s]', 'fields': {
                    k: {'values': json_array(arrays[k]), 'unit': mm['units'].get(k, ''), 'units': mm['units'].get(k, '')}
                    for k in arrays.files if k not in ('Z', 'TIME')}}
    return {'datasets': datasets, 'metadata': metadata}


def create_app(output_root=None):
    from flask import Flask, jsonify, request, send_from_directory, abort
    from werkzeug.exceptions import HTTPException
    from .gui_schema import schema, baseline, validate_payload, assess_payload
    from . import __version__
    static = Path(__file__).parent/'gui_static'
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=2*1024*1024, TRUSTED_HOSTS=['127.0.0.1', 'localhost', '[::1]'])
    manager = RunManager(output_root or Path.home()/'Documents'/'OpenSTREAM'/'runs')
    app.extensions['runs'] = manager

    @app.before_request
    def local_only():
        if request.remote_addr not in (None, '127.0.0.1', '::1'): abort(403)
        if request.method == 'POST':
            origin = request.headers.get('Origin')
            if origin and (urlsplit(origin).netloc != request.host or urlsplit(origin).scheme != 'http'): abort(403)
            if request.headers.get('Sec-Fetch-Site') == 'cross-site': abort(403)
            if not request.is_json: abort(415, 'Use application/json requests')

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
        if request.path.startswith('/api/'): response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(Exception)
    def errors(exc):
        code = exc.code if isinstance(exc, HTTPException) else (404 if isinstance(exc, KeyError) else 400 if isinstance(exc, (ValueError, TypeError, NotImplementedError)) else 409 if isinstance(exc, RuntimeError) else 500)
        if code == 500: app.logger.exception('GUI request failed')
        return jsonify(valid=False, error=str(exc)), code

    @app.get('/')
    def index(): return send_from_directory(static, 'index.html')

    @app.get('/assets/<path:filename>')
    def assets(filename):
        if filename == 'plotly.min.js':
            import plotly
            return send_from_directory(Path(plotly.__file__).parent/'package_data', filename)
        return send_from_directory(static, filename)

    @app.get('/api/health')
    def health(): return jsonify(app='openstream-gui', version=__version__, output_root=str(manager.root), pid=os.getpid())

    @app.get('/api/schema')
    def get_schema(): return jsonify(schema(request.args.get('framework', 'Mixture')))

    @app.get('/api/baseline/<framework>')
    def get_baseline(framework): return jsonify(baseline(framework))

    @app.post('/api/validate')
    def validate():
        payload = request.get_json()
        validate_payload(payload)
        return jsonify(valid=True, **assess_payload(payload))

    @app.get('/api/runs')
    def history(): return jsonify(runs=manager.history())

    @app.post('/api/runs')
    def start(): return jsonify(manager.start(request.get_json())), 202

    @app.get('/api/runs/<run_id>')
    def status(run_id): return jsonify(manager.status(run_id))

    @app.post('/api/runs/<run_id>/cancel')
    def cancel(run_id): return jsonify(manager.cancel(run_id))

    @app.get('/api/runs/<run_id>/data')
    def data(run_id):
        state = manager.status(run_id)
        if state['status'] != 'completed': abort(409, 'Results are not ready')
        return jsonify(plot_data(manager.directory(run_id), state['framework'], state['is_reference']))

    @app.get('/files/<run_id>/<path:filename>')
    def download(run_id, filename):
        directory = manager.directory(run_id)
        state = manager.status(run_id)
        allowed = {f['name'] for f in state['files']} | {'worker.log', 'submitted_inputs.json'}
        if filename not in allowed: abort(404)
        return send_from_directory(directory, filename, as_attachment=True)

    return app
