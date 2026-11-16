"""Check baseline/custom eligibility through the live API without creating runs."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'tools'))
from verify_hosted_gui import HTTPClient

password = os.environ.pop('OPENSTREAM_VERIFY_PASSWORD')
client = HTTPClient('https://openstream-py.vercel.app', password)
rows = []
code, session, _ = client.json('GET', '/auth/session')
assert code == 200
client.set_csrf(session['csrf'])
code, session, _ = client.json('POST', '/auth/login', {'password': password})
assert code == 200
client.set_csrf(session['csrf'])
for framework in ('Mixture', 'TwoFluid', 'ThreeField', 'FourField'):
    code, baseline, _ = client.json('GET', '/api/baseline/' + framework)
    assert code == 200
    custom = deepcopy(baseline)
    custom['inputs']['model']['NNODES'] = 200
    for label, payload, expected in [('unchanged', baseline, True), ('changed', custom, False)]:
        code, checked, _ = client.json('POST', '/api/validate', payload)
        assert code == 200 and checked['valid'] and checked['is_reference'] is expected
        rows.append({'framework': framework, 'case': label, 'http_status': code,
                     'is_reference': checked['is_reference'], 'change_count': checked['change_count']})
assert client.json('POST', '/auth/logout', {})[0] == 200
output = Path(__file__).with_name('hosted-reference-policy.json')
with output.open('x', encoding='utf-8') as stream:
    json.dump({'checked_at': datetime.now(timezone.utc).isoformat(), 'passed': True, 'cases': rows,
               'scope': 'Live input validation only; no calculations created and no saved inputs changed.'}, stream, indent=2)
    stream.write('\n')
print('PASS: four unchanged and four modified settings checked; no runs submitted.')
