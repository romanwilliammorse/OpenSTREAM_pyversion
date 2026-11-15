"""Bind a completed focused trace to frozen sources and complete window coverage."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import subprocess

from replay_matched_diagnostics import ROOT, digest, write_json, source_hashes


def audit(directory):
    manifest = json.loads((directory/'frozen_manifest.json').read_text())
    assessment = json.loads((directory/'assessment.json').read_text())
    if not assessment['observer_exact_numeric_equality']:
        raise ValueError('Observed replay did not preserve all reference arrays')
    for name,sha in assessment['artifact_sha256'].items():
        path = (directory/name).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError(f'Artifact path escapes trace directory: {name}')
        if digest(path) != sha:
            raise ValueError(f'Artifact differs from completed assessment: {name}')
    if assessment['manifest_sha256'] != digest(directory/'frozen_manifest.json'):
        raise ValueError('Assessment manifest hash differs')
    if assessment['native_source_sha256'] != manifest['native_source_sha256']:
        raise ValueError('Assessment numerical-source hashes differ from registration')
    expected_manifest = ROOT/'examples/sawai_oscillation_diagnostic.json'
    if digest(expected_manifest) != digest(directory/'frozen_manifest.json'):
        raise ValueError('Executed and current manifests differ')
    if digest(ROOT/'tools/trace_sawai_oscillation.py') != digest(directory/'executed_trace.py'):
        raise ValueError('Executed and current trace source differ')
    if source_hashes() != manifest['native_source_sha256']:
        raise ValueError('Numerical source no longer matches frozen observer run')
    original_trace = ROOT/manifest['corrected_reference_directory']
    coarse_reproduction = {name: {
        'previous_sha256':digest(original_trace/name),
        'new_sha256':digest(directory/name),
        'byte_equal':(original_trace/name).read_bytes()==(directory/name).read_bytes()}
        for name in ('update_trace.jsonl','point_trace.csv','temporal_trace.json')}
    if not all(row['byte_equal'] for row in coarse_reproduction.values()):
        raise ValueError('Coarse trace differs from the corrected replay; inspect before claiming unchanged trajectory')
    baseline = manifest['baseline_commit']
    helpers = {}
    for path in ('tools/replay_matched_diagnostics.py','tools/run_lecorre_reproduction.py'):
        raw = (ROOT/path).read_bytes()
        committed = subprocess.check_output(['git','show',f'{baseline}:{path}'], cwd=ROOT)
        if raw.replace(b'\r\n',b'\n') != committed.replace(b'\r\n',b'\n'):
            raise ValueError(f'Imported helper differs from registered baseline: {path}')
        helpers[path] = {'sha256':digest(ROOT/path), 'baseline_equal_after_line_ending_normalization':True}
    window = manifest['deep_window']
    expected = {(window['time_s'],node,it) for node in window['nodes_zero_based']
                for it in range(window['iteration_min'],window['iteration_max']+1)}
    coverage = {}
    record_count = 0
    with gzip.open(directory/'closure_trace.jsonl.gz','rt',encoding='utf-8') as stream:
        for row_text in stream:
            row = json.loads(row_text)
            if row['event_index'] != record_count:
                raise ValueError('Nonsequential event index')
            record_count += 1
            key = (row['time_s'],row['node_zero_based'],row['iteration'])
            if key not in expected:
                raise ValueError(f'Closure outside preregistered window: {key}')
            counter = coverage.setdefault(key,Counter())
            counter[row['stage']] += 1
            if row['stage']=='closure_return':
                counter[row['receiver_class']+'.'+row['method'].split('.')[-1]] += 1
    if set(coverage) != expected:
        raise ValueError(f'Missing points: {expected-set(coverage)}')
    required = ('Base.MTOT','Wave.MTOT','Base.UEQUIL','Base._secant','Wave.FTOT',
                'Drop.CONC','Drop.MDEP','Base.MWAVE','Wave.MBASE')
    for key,counter in coverage.items():
        if not counter['secant_trial'] or any(not counter[name] for name in required):
            raise ValueError(f'Incomplete closure or secant coverage at {key}: {counter}')
    schema = json.loads((directory/'deep_trace_schema.json').read_text())
    if record_count != schema['records']:
        raise ValueError('Deep schema record count differs')
    return {'schema':'openstream-sawai-trace-provenance-v1',
            'baseline_commit':baseline,
            'execution_command':r'.\.venv\Scripts\python.exe tools\trace_sawai_oscillation.py',
            'default_arguments':{'manifest':'examples/sawai_oscillation_diagnostic.json',
                                 'output':'outputs/verification/sawai-oscillation-01/deep-trace'},
            'executed_source_sha256':digest(directory/'executed_trace.py'),
            'executed_manifest_sha256':digest(directory/'frozen_manifest.json'),
            'assessment_sha256':digest(directory/'assessment.json'),
            'closure_trace_sha256':digest(directory/'closure_trace.jsonl.gz'),
            'imported_helpers':helpers,
            'coarse_trace_exact_reproduction':coarse_reproduction,
            'numerical_source_still_matches_frozen_run':True,
            'expected_points':len(expected),'observed_points':len(coverage),
            'deep_records':record_count,'all_required_points_and_closures_observed':True,
            'coverage':[{'time_s':key[0],'node_zero_based':key[1],'iteration':key[2],
                         'event_counts':dict(count)} for key,count in sorted(coverage.items())],
            'claims':'Source and trace integrity only; no MATLAB equivalence or physical validation claim.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace',type=Path,default=ROOT/'outputs/verification/sawai-oscillation-01/deep-trace')
    parser.add_argument('--output',type=Path,default=ROOT/'outputs/verification/sawai-oscillation-01/deep_trace_provenance.json')
    args=parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result=audit(args.trace)
    write_json(args.output,result)
    print(json.dumps({key:result[key] for key in ('expected_points','observed_points','deep_records','all_required_points_and_closures_observed')}))


if __name__=='__main__':
    main()
