"""Run against an installed wheel from outside its source checkout."""
import argparse
import json
from pathlib import Path
import time

import openstream
from openstream.gui import create_app
from openstream.gui_schema import baseline

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
print('installed_module:', openstream.__file__, flush=True)
app = create_app(args.output)
client = app.test_client()
for resource in ('/', '/assets/app.js', '/assets/style.css', '/assets/plotly.min.js'):
    assert client.get(resource).status_code == 200, resource
for name in ('Mixture', 'TwoFluid', 'ThreeField', 'FourField'):
    assert len(client.get('/api/schema?framework='+name).json['fields']) == 163
    assert client.post('/api/validate', json=baseline(name)).json['is_reference']
job = client.post('/api/runs', json=baseline()).json
deadline = time.monotonic()+90
while job['status'] not in ('completed', 'failed', 'cancelled'):
    if time.monotonic() > deadline: raise TimeoutError('Installed-wheel worker did not finish')
    time.sleep(.2)
    job = client.get('/api/runs/'+job['id']).json
assert job['status'] == 'completed', job
assert job['reference']['status'] == 'passed', job
assert job['physical']['status'] == 'passed', job
data = client.get('/api/runs/'+job['id']+'/data').json
assert len(data['datasets']['physical']['z']) == 101
print(json.dumps({key: job[key] for key in ('id', 'framework', 'status', 'converged', 'reference', 'physical')}, indent=2), flush=True)
app.extensions['runs'].server_lock.close()
