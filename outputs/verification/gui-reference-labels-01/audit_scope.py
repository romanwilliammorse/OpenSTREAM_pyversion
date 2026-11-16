"""Verify this GUI-only revision leaves numerical sources/references unchanged."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
BASE = '7ebc897a114e2e4cd806fc8deebad694ca66f469'
paths = subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', BASE,
    'src/openstream', 'requirements.txt', 'requirements-web.lock', 'requirements-cloud.lock',
    'requirements.lock', 'requirements-gui.lock', 'app.py', 'vercel.json'], cwd=ROOT, text=True).splitlines()
preserved = {}
for path in paths:
    if '/gui_static/' in path or '/cloud/static/' in path:
        continue
    old = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)
    current = (ROOT/path).read_bytes()
    if Path(path).suffix in {'.py', '.json', '.toml', '.txt', '.lock', '.inp'}:
        old, current = old.replace(b'\r\n', b'\n'), current.replace(b'\r\n', b'\n')
    assert old == current, f'Unexpected source/reference/environment change: {path}'
    preserved[path] = hashlib.sha256(current).hexdigest()
changed_rows = []
for part in ('core', 'interfaces', 'experimental'):
    path = f'docs/acceptance/{part}.json'
    old = json.loads(subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT))
    current = json.loads((ROOT/path).read_bytes())
    assert [r['id'] for r in old] == [r['id'] for r in current]
    for a, b in zip(old, current):
        for key in set(a) | set(b):
            if key not in {'evidence', 'gap'}:
                assert a.get(key) == b.get(key), f'Acceptance criterion/status changed: {a["id"]}/{key}'
        if a != b:
            changed_rows.append(a['id'])
result = {'baseline_commit': BASE, 'checked_at': datetime.now(timezone.utc).isoformat(),
          'preserved_file_sha256': preserved, 'text_hashes_normalize_newlines': True,
          'changed_acceptance_evidence_rows': changed_rows, 'scientific_statuses_unchanged': True,
          'scope': 'Labels and comparison visibility only; no new manuscript equivalence or experimental validation.'}
output = Path(__file__).with_name('source-integrity.json')
with output.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, indent=2); stream.write('\n')
print(f'PASS: {len(preserved)} source/reference/environment files preserved; only evidence/gap fields updated.')
