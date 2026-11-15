"""Verify that the Sawai diagnosis changes evidence, not physics or acceptance."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = 'bf5083ce2db9c2ac5c1279b3d7858ca1dd39bf9e'


def sha(data):
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def original(path):
    return subprocess.check_output(['git', 'show', BASELINE+':'+path], cwd=ROOT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    before, after, ledger_hashes = [], [], {}
    for part in ('core', 'interfaces', 'experimental'):
        path = f'docs/acceptance/{part}.json'
        a, b = original(path), (ROOT/path).read_bytes()
        before.extend(json.loads(a)); after.extend(json.loads(b))
        ledger_hashes[path] = {'before_sha256_lf': sha(a), 'after_sha256_lf': sha(b)}
    old, new = {r['id']: r for r in before}, {r['id']: r for r in after}
    if len(old) != 81 or set(old) != set(new):
        raise ValueError('Acceptance requirement inventory changed')
    fields = ['acceptance_criteria', 'implementation', 'native_tests', 'matlab', 'physical', 'experimental']
    differences = [(key, field) for key in old for field in fields if old[key][field] != new[key][field]]
    if differences:
        raise ValueError(f'Criteria/statuses changed: {differences}')
    core = {}
    for path in sorted((ROOT/'src/openstream').glob('*.py')):
        name = path.relative_to(ROOT).as_posix()
        if sha(path.read_bytes()) != sha(original(name)):
            raise ValueError(f'Native source changed: {name}')
        core[name] = sha(path.read_bytes())
    if len(core) != 25:
        raise ValueError('Native module inventory changed')
    frozen = json.loads((ROOT/'examples/matched_diagnostic_replay.json').read_text())
    preserved = {}
    for case in frozen['cases']:
        for name, expected in case['original_file_sha256'].items():
            actual = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError(f'Historical evidence changed: {name}')
            preserved[name] = actual
    checked = subprocess.run([sys.executable, str(ROOT/'tools/build_acceptance_matrix.py'), '--check'],
                             cwd=ROOT, capture_output=True, text=True, check=True)
    result = {'schema': 'openstream-sawai-oscillation-acceptance-integrity-v1',
              'baseline_commit': BASELINE, 'requirements': 81, 'identical_id_set': True,
              'unchanged_fields': fields, 'criteria_and_status_differences': differences,
              'updated_rows': [key for key in old if old[key] != new[key]],
              'ledger_sha256_lf': ledger_hashes, 'unchanged_native_modules_sha256_lf': core,
              'preserved_original_file_sha256': preserved,
              'audit_script_sha256_lf': sha(Path(__file__).read_bytes()),
              'matrix_check_stdout': checked.stdout,
              'limitation': 'Evidence-ledger and source integrity only; no new MATLAB or experimental acceptance.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2); stream.write('\n')
    print(f'PASS: 81 requirement IDs/criteria/status axes, 25 native modules and {len(preserved)} original files preserved.')


if __name__ == '__main__':
    main()
