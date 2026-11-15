"""Vercel Sandbox process adapter. Never executes numerical code in a request."""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import zipfile

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[1]
IMAGE = 'vercel/sandbox/universal@sha256:9b2669397f26336812ec6835c2f67db6a546074cbabb05db93bf5e669f71ec5d'
PYTHON_VERSION = '3.12.16'
REMOTE_ROOT = '/vercel/sandbox'

# Executed by the managed image's Python, before the pinned job interpreter is
# available. All source and inputs are files, never interpolated shell commands.
BOOTSTRAP = r'''import json,os,pathlib,subprocess,sys,zipfile
root=pathlib.Path('/vercel/sandbox')
directory=pathlib.Path(sys.argv[1])
try:
    with (directory/'bootstrap.log').open('w') as log:
        for args in [['uv','python','install','3.12.16'],
                     ['uv','venv',str(root/'venv'),'--python','3.12.16'],
                     ['uv','pip','install','--python',str(root/'venv/bin/python'),'-r',str(root/'requirements-cloud.lock')]]:
            subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,check=True)
    with zipfile.ZipFile(root/'source.zip') as archive:
        for info in archive.infolist():
            target=(root/'source'/info.filename).resolve()
            if not target.is_relative_to(root/'source'):
                raise ValueError('Invalid source bundle')
        archive.extractall(root/'source')
    os.environ['PYTHONPATH']=str(root/'source')
    executable=str(root/'venv/bin/python')
    os.execv(executable,[executable,'-m','openstream.cloud.worker',str(directory),directory.name])
except Exception:
    state=json.loads((directory/'status.json').read_text())
    state.update(status='failed',phase='Worker setup failed',error='Pinned cloud environment could not start. Bootstrap log retained in the worker.')
    (directory/'cloud_status.json').write_text(json.dumps(state))
    raise SystemExit(1)
'''


def source_bundle():
    """Ship the deployed package, including references, without mutable outputs."""
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PACKAGE.rglob('*')):
            relative = path.relative_to(PACKAGE)
            if not path.is_file() or '__pycache__' in relative.parts:
                continue
            if 'gui_static' in relative.parts or 'static' in relative.parts:
                continue  # Worker needs numerical/data modules, never the UI assets.
            if path.suffix not in ('.py', '.npz', '.json', '.inp'):
                continue
            archive.writestr('openstream/' + relative.as_posix(), path.read_bytes())
    return stream.getvalue()


def provenance():
    from .. import __version__
    lock = ROOT/'requirements-cloud.lock'
    return ({'git_commit': os.getenv('VERCEL_GIT_COMMIT_SHA', 'local-uncommitted'),
             'package_version': __version__,
             'module_sha256': {'src/openstream/'+p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sorted(PACKAGE.glob('*.py'))}},
            {'python_requirement': '3.12', 'python_version': PYTHON_VERSION,
             'dependency_lock_sha256': hashlib.sha256(lock.read_bytes()).hexdigest(),
             'sandbox_image': IMAGE})


class SandboxHandle:
    def __init__(self, sandbox, runtime, *, fresh=False):
        self.sandbox, self.runtime, self.fresh = sandbox, runtime, fresh

    def is_running(self):
        return (str(self.sandbox.status) == 'running'
                and self.sandbox.current_session_id == self.runtime['session_id'])

    def _active(self):
        if not self.is_running():
            raise RuntimeError('Cloud worker is no longer active')

    def prepare(self, files):
        self._active()
        for name, body in files.items():
            path = PurePosixPath(name)
            if not str(path).startswith(REMOTE_ROOT+'/jobs/') or '..' in path.parts:
                raise ValueError('Invalid cloud job path')
            self.sandbox.fs.mkdir(str(path.parent), recursive=True)
            self.sandbox.fs.write_bytes(str(path), body)
        if self.fresh:
            self.sandbox.fs.write_bytes(REMOTE_ROOT+'/source.zip', source_bundle())
            self.sandbox.fs.write_bytes(REMOTE_ROOT+'/requirements-cloud.lock', (ROOT/'requirements-cloud.lock').read_bytes())
            self.sandbox.fs.write_text(REMOTE_ROOT+'/bootstrap.py', BOOTSTRAP)

    def launch(self, job_dir):
        self._active()
        return self.sandbox.create_process('python3', [REMOTE_ROOT+'/bootstrap.py', job_dir], cwd=REMOTE_ROOT)

    def status_files(self, job_dir):
        self._active()
        from vercel.sandbox.sync import SandboxPathNotFoundError
        states = []
        for name in ('status.json', 'cloud_status.json'):
            try:
                states.append(json.loads(self.sandbox.fs.read_text(job_dir+'/'+name)))
            except SandboxPathNotFoundError:
                states.append(None)
        return tuple(states)

    def request_cancel(self, job_dir):
        self._active()
        self.sandbox.fs.write_text(job_dir+'/cancel.request', '')

    def stop(self):
        # Never resume an old sandbox, or stop a later session with the same name.
        if self.is_running():
            self.sandbox.stop()


class SandboxGateway:
    def __init__(self, timeout_seconds=2400):
        if type(timeout_seconds) is not int or not 60 <= timeout_seconds <= 2700:
            raise ValueError('Cloud worker duration must be 60-2700 seconds')
        self.timeout_seconds = timeout_seconds

    def create(self, run_id):
        if not re.fullmatch('[0-9a-f]{32}', run_id):
            raise ValueError('Invalid run ID')
        from vercel.oidc.credentials import get_credentials
        from vercel.sandbox.sync import create_sandbox, SandboxResources
        credentials = get_credentials()
        # Request-bound credential passed only to this isolated trusted worker.
        # Never put it in the source bundle, manifest, log, or browser response.
        env = {'VERCEL_OIDC_TOKEN': credentials.token,
               'VERCEL_PROJECT_ID': credentials.project_id, 'VERCEL_TEAM_ID': credentials.team_id,
               'BLOB_STORE_ID': os.environ['BLOB_STORE_ID'],
               'MPLBACKEND': 'Agg', 'MPLCONFIGDIR': REMOTE_ROOT+'/.matplotlib',
               'OMP_NUM_THREADS': '1', 'OPENBLAS_NUM_THREADS': '1'}
        sandbox = create_sandbox(name='openstream-'+run_id, image=IMAGE,
            persistent=False, execution_time_limit=self.timeout_seconds,
            resources=SandboxResources(vcpus=2), ports=[], env=env,
            tags={'application': 'openstream', 'run': run_id}, region='iad1')
        runtime = {'sandbox_name': sandbox.name, 'sandbox_id': sandbox.name,
                   'session_id': sandbox.current_session_id, 'timeout_seconds': self.timeout_seconds}
        return SandboxHandle(sandbox, runtime, fresh=True)

    def get(self, runtime):
        from vercel.sandbox.sync import get_sandbox, SandboxApiError
        try:
            sandbox = get_sandbox(name=runtime['sandbox_name'])  # Passive metadata lookup.
        except SandboxApiError as error:
            if error.status_code != 404:
                raise RuntimeError('Cloud worker status is temporarily unavailable') from None
            # Only a positive provider 404 establishes absence. Never resume a
            # removed worker, or mislabel a network failure as a stopped job.
            from types import SimpleNamespace
            sandbox = SimpleNamespace(status='stopped', current_session_id=None)
        return SandboxHandle(sandbox, runtime)
