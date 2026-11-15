"""GUI orchestration checks against real numerical jobs, not mocked solver data."""
import json
import time
import zipfile

import numpy as np
import pytest

from openstream.gui import create_app, plot_data
from openstream.gui_schema import baseline


@pytest.fixture
def app(tmp_path):
    application = create_app(tmp_path/'runs')
    yield application
    application.extensions['runs'].server_lock.close()


def finish(manager, run_id):
    deadline = time.monotonic()+150
    while time.monotonic() < deadline:
        state = manager.status(run_id)
        if state['status'] in ('completed', 'failed', 'cancelled'): return state
        time.sleep(.1)
    manager.cancel(run_id)
    pytest.fail('GUI worker timed out')


@pytest.mark.parametrize('framework', ['Mixture', 'TwoFluid', 'ThreeField', 'FourField'])
def test_real_baseline_run(app, framework):
    client = app.test_client()
    body = baseline(framework)
    assert client.post('/api/validate', json=body).json['is_reference']
    response = client.post('/api/runs', json=body)
    assert response.status_code == 202, response.json
    run_id = response.json['id']
    manager = app.extensions['runs']
    state = finish(manager, run_id)
    assert state['status'] == 'completed', state
    assert state['converged'] is True
    assert state['reference']['status'] == 'passed', state['reference']
    assert state['physical']['status'] == {'Mixture':'passed', 'TwoFluid':'failed',
                                           'ThreeField':'informational', 'FourField':'informational'}[framework]
    if framework in ('ThreeField', 'FourField'):
        assert state['physical']['diagnostics']['phase_volume_closure_role'] == 'informational'
        assert state['physical']['diagnostics']['max_unblended_annular_area_closure_relative'] > .01
        assert 'informational' in state['physical']['message']
    assert state['progress']
    data = client.get(f'/api/runs/{run_id}/data').json
    assert len(data['datasets']['physical']['z']) == 101
    assert data['datasets']['physical']['reference_fields']
    json.dumps(data, allow_nan=False)
    directory = manager.directory(run_id)
    with zipfile.ZipFile(directory/'results.zip') as archive:
        assert 'submitted_inputs.json' in archive.namelist()
        assert 'output/gui_verification.json' in archive.namelist()
    downloaded = client.get(f'/files/{run_id}/output/results.npz')
    assert downloaded.status_code == 200
    assert client.get(f'/files/{run_id}/../../pyproject.toml').status_code == 404


def test_invalid_input_and_local_request_boundaries(app):
    client = app.test_client()
    assert client.get('/api/health').json['app'] == 'openstream-gui'
    assert len(client.get('/api/schema?framework=Mixture').json['fields']) == 163
    data = baseline('Mixture')
    data['inputs']['bc'][0]['PRESSURE'] = -1
    assert client.post('/api/runs', json=data).status_code == 400
    assert not list(app.extensions['runs'].root.glob('*/status.json'))
    assert client.post('/api/validate', json=baseline(), headers={'Origin': 'https://example.com'}).status_code == 403
    assert client.get('/api/health', headers={'Host': 'example.com'}).status_code == 400
    assert client.post('/api/validate', data='{}').status_code == 415
    assert client.get('/api/runs/not-a-run').status_code == 404
    assert client.get('/api/health', environ_base={'REMOTE_ADDR':'192.168.1.2'}).status_code == 403


def test_cancel_and_single_active_job(app):
    client = app.test_client()
    first = client.post('/api/runs', json=baseline()).json
    assert client.post('/api/runs', json=baseline()).status_code == 409
    result = client.post(f"/api/runs/{first['id']}/cancel", json={})
    assert result.status_code == 200
    assert result.json['status'] == 'cancelled'
    assert app.extensions['runs'].processes[first['id']].poll() is not None
    assert client.get(f"/api/runs/{first['id']}/data").status_code == 409


def test_custom_case_does_not_claim_reference_agreement(app):
    payload = baseline('Mixture')
    payload['inputs']['model']['NNODES'] = 20
    client = app.test_client()
    response = client.post('/api/runs', json=payload)
    state = finish(app.extensions['runs'], response.json['id'])
    assert state['status'] == 'completed', state
    assert state['is_reference'] is False
    assert state['reference']['status'] == 'not_compared'
    data = client.get(f"/api/runs/{state['id']}/data").json
    assert 'reference_fields' not in data['datasets']['physical']


def test_worker_failure_is_reported(app):
    # Finite positive numeric values can still lie outside CoolProp's domain.
    payload = baseline()
    payload['inputs']['bc'][0]['PRESSURE'] = 1e10
    client = app.test_client()
    response = client.post('/api/runs', json=payload)
    assert response.status_code == 202
    state = finish(app.extensions['runs'], response.json['id'])
    assert state['status'] == 'failed'
    assert state['error']
    assert state['converged'] is None
    assert state['reference']['status'] == 'not_compared'


@pytest.mark.parametrize('physical,expected', [(None,'informational'), (False,'failed')])
def test_informational_annular_report_preserves_explicit_status(physical, expected):
    from openstream.gui_worker import physical_report
    diagnostic={'physical_consistency':physical,'phase_volume_closure_role':'informational',
        'max_unblended_annular_area_closure_relative':.2}
    report=physical_report(diagnostic)
    assert report['status']==expected and report['diagnostics'] is diagnostic
    if physical is None:
        assert 'informational' in report['message'] and 'not established' in report['message']
    else:
        assert 'failed' in report['message']


@pytest.mark.parametrize('blocked_attempts', [2, 10])
def test_status_replace_permission_retry_is_bounded(tmp_path, monkeypatch, blocked_attempts):
    from openstream import gui_worker
    target = tmp_path/'status.json'
    target.write_text('{"state": "old"}', encoding='utf-8')
    real_replace = gui_worker.os.replace
    attempts, sleeps = [], []
    permission_error = PermissionError('destination temporarily open')
    def replace(source, destination):
        attempts.append((source, destination))
        if len(attempts) <= blocked_attempts:
            raise permission_error
        real_replace(source, destination)
    monkeypatch.setattr(gui_worker.os, 'replace', replace)
    monkeypatch.setattr(gui_worker.time, 'sleep', sleeps.append)
    if blocked_attempts == 10:
        with pytest.raises(PermissionError) as exc:
            gui_worker.write_json(target, {'state': 'new'})
        assert exc.value is permission_error
        assert json.loads(target.read_text()) == {'state': 'old'}
        assert json.loads(target.with_suffix('.json.tmp').read_text()) == {'state': 'new'}
        assert len(attempts) == 10 and sleeps == [.02]*9
    else:
        gui_worker.write_json(target, {'state': 'new'})
        assert json.loads(target.read_text()) == {'state': 'new'}
        assert not target.with_suffix('.json.tmp').exists()
        assert len(attempts) == 3 and sleeps == [.02]*2


def test_status_replace_other_errors_are_not_retried(tmp_path, monkeypatch):
    from openstream import gui_worker
    attempts, sleeps = [], []
    error = FileNotFoundError('replacement source unavailable')
    def replace(source, destination):
        attempts.append((source, destination))
        raise error
    monkeypatch.setattr(gui_worker.os, 'replace', replace)
    monkeypatch.setattr(gui_worker.time, 'sleep', sleeps.append)
    with pytest.raises(FileNotFoundError) as exc:
        gui_worker.write_json(tmp_path/'status.json', {'state': 'new'})
    assert exc.value is error
    assert len(attempts) == 1 and not sleeps
