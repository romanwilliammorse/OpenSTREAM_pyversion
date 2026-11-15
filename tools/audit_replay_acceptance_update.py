"""Verify the matched-replay ledger update preserves all IDs/criteria/statuses."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '178ac2b4152b31016dc8847aebab139de0d88d2d'


def digest(data):
    return hashlib.sha256(data.replace(b'\r\n', b'\n')).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    original, current, sources = [], [], {}
    for part in ('core','interfaces','experimental'):
        name = f'docs/acceptance/{part}.json'
        before = subprocess.check_output(['git','show',BASELINE+':'+name], cwd=ROOT)
        after = (ROOT/name).read_bytes()
        original.extend(json.loads(before)); current.extend(json.loads(after))
        sources[name] = {'before_sha256_lf':digest(before), 'after_sha256_lf':digest(after)}
    old, new = {r['id']:r for r in original}, {r['id']:r for r in current}
    assert len(old)==len(new)==81 and set(old)==set(new), 'Requirement IDs changed'
    preserved = ['acceptance_criteria','implementation','native_tests','matlab','physical','experimental']
    differences = [(key,field) for key in old for field in preserved if old[key][field]!=new[key][field]]
    assert not differences, differences
    checked = subprocess.run([sys.executable,str(ROOT/'tools/build_acceptance_matrix.py'),'--check'],
                             cwd=ROOT,capture_output=True,text=True,check=True)
    generated = ['docs/METHOD_COVERAGE.json','docs/ACCEPTANCE_MATRIX.json','docs/ACCEPTANCE_MATRIX.md',
                 'docs/ACCEPTANCE_MATRIX.csv','docs/ACCEPTANCE_METHODS.csv','docs/ACCEPTANCE_OPTIONS.csv']
    result = {'schema':'openstream-matched-replay-acceptance-integrity-v1','baseline_commit':BASELINE,
              'requirements':81,'identical_id_set':True,'unchanged_fields':preserved,
              'criteria_and_status_differences':differences,
              'updated_rows':[key for key in old if old[key]!=new[key]],
              'source_ledger_sha256_lf':sources,
              'generated_artifact_sha256_lf':{name:digest((ROOT/name).read_bytes()) for name in generated},
              'audit_script_sha256_lf':digest(Path(__file__).read_bytes()),
              'matrix_check_stdout':checked.stdout,
              'limitation':'Ledger integrity and evidence inventory; no additional numerical acceptance, physical validation or MATLAB execution.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,indent=2);stream.write('\n')
    print('PASS: all81 IDs, criteria and status axes preserved; generated matrix current.')


if __name__=='__main__':
    main()
