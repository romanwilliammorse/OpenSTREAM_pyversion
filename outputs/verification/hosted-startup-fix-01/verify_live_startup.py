"""Read-only hosted startup/validation probes; never submits a calculation.

Password is supplied through OPENSTREAM_VERIFY_PASSWORD. Run with a new output
path and optionally a completed run ID to check saved CSV delivery. Timings are
observations from this client, not cold-start or performance guarantees.
"""
from concurrent.futures import ThreadPoolExecutor
from copy import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools'))
from verify_hosted_gui import HTTPClient

output = Path(sys.argv[1])
if output.exists():
    raise FileExistsError('Choose a new evidence path')
password = os.environ.pop('OPENSTREAM_VERIFY_PASSWORD')
origin = 'https://openstream-py.vercel.app'
client = HTTPClient(origin, password)
report = {'origin': origin, 'started_at': datetime.now(timezone.utc).isoformat(), 'requests': [],
          'limitation': 'Observed requests only; concurrency does not establish independent cold starts.'}

def request(method, path, payload=None, active=client):
    start = time.perf_counter()
    code, body, _ = active.request(method, path, payload)
    report['requests'].append({'method': method, 'path': path, 'http_status': code,
                               'elapsed_seconds': time.perf_counter() - start})
    assert code == 200, f'{method} {path}: HTTP {code}'
    return body

try:
    request('GET', '/')  # Anonymous root redirects to the login page.
    client.set_csrf(json.loads(request('GET', '/auth/session'))['csrf'])
    client.set_csrf(json.loads(request('POST', '/auth/login', {'password': password}))['csrf'])
    request('GET', '/')
    report['assets'] = []
    for filename in ('app.js', 'style.css', 'plotly.min.js'):
        body = request('GET', '/assets/' + filename)
        expected = (ROOT/'src/openstream/gui_static'/filename).read_bytes()
        # Controls' text line endings may differ by Git checkout platform.
        if filename != 'plotly.min.js':
            body, expected = body.replace(b'\r\n', b'\n'), expected.replace(b'\r\n', b'\n')
        assert body == expected, f'Deployed asset differs: {filename}'
        report['assets'].append({'file': filename, 'sha256': hashlib.sha256(body).hexdigest(),
                                  'bytes': len(body), 'matches_local_source': True})
    for framework in ('Mixture', 'TwoFluid', 'ThreeField', 'FourField'):
        baseline = json.loads(request('GET', '/api/baseline/' + framework))
        check = json.loads(request('POST', '/api/validate', baseline))
        assert check['valid'] and check['is_reference']
    # One authenticated session, independent clients; only read-only requests.
    def parallel_read(index):
        active = HTTPClient(origin, password)
        for cookie in client.jar:
            active.jar.set_cookie(copy(cookie))
        path = '/api/health' if index % 2 == 0 else '/api/schema?framework=FourField'
        return len(request('GET', path, active=active))
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert all(pool.map(parallel_read, range(6)))
    if len(sys.argv) > 2:
        for kind in ('inputs', 'boundary-conditions', 'geometry', 'results'):
            body = request('GET', f'/api/runs/{sys.argv[2]}/export/{kind}.csv')
            assert len(body.splitlines()) > 1
    request('POST', '/auth/logout', {})
    assert client.request('GET', '/api/health')[0] == 401
    report['passed'] = True
except Exception as error:
    report['passed'] = False
    report['error'] = client.redact(f'{type(error).__name__}: {error}')
report['finished_at'] = datetime.now(timezone.utc).isoformat()
output.write_text(json.dumps(client.redact(report), indent=2) + '\n', encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'requests': len(report['requests']), 'output': str(output)}))
raise SystemExit(0 if report['passed'] else 1)
