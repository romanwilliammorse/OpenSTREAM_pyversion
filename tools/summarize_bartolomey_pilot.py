"""Summarize saved pilot evidence without rerunning or filtering failed cases."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    report_path = args.campaign/'report.json'
    report = json.loads(report_path.read_text(encoding='utf-8'))
    manifest = json.loads((args.campaign/'frozen_manifest.json').read_text(encoding='utf-8'))
    if 'counts' not in report:
        raise ValueError('Campaign is incomplete; do not summarize a moving population')
    args.output.mkdir(parents=True, exist_ok=False)
    rows, groups = [], {}
    for run in report['runs'].values():
        stats = run.get('comparison', {}).get('summary', {})
        physical = run.get('physical', {})
        rows.append({'run_id': run['run_id'], 'entry_id': run['entry_id'], 'test_id': run['test_id'],
            'model': run['model'], 'cells': run['cells'], 'variant': run['variant'],
            'execution': run['execution'], 'converged': run['converged'], 'physical_passed': physical.get('passed'),
            'failed_checks': '; '.join(k for k, ok in physical.get('checks', {}).items() if not ok),
            'coordinate': run.get('comparison', {}).get('coordinate'),
            'n_total': stats.get('n_total'), 'n_compared': stats.get('n_compared'), 'n_excluded': stats.get('n_excluded'),
            'bias [1]': stats.get('bias'), 'MAE [1]': stats.get('mae'), 'RMSE [1]': stats.get('rmse'),
            'bias [percentage points]': 100*stats['bias'] if stats.get('bias') is not None else None,
            'MAE [percentage points]': 100*stats['mae'] if stats.get('mae') is not None else None,
            'RMSE [percentage points]': 100*stats['rmse'] if stats.get('rmse') is not None else None,
            'error': run.get('error'), 'warnings': '; '.join(run.get('warnings', []))})
        if run['cells'] != max(manifest['mesh_cells']) or run['variant'] != 'base':
            continue
        coordinate = run.get('comparison', {}).get('coordinate', 'unavailable')
        key = (run['model'], coordinate)
        group = groups.setdefault(key, {'model': key[0], 'coordinate': key[1], 'errors': [], 'runs': [], 'n_excluded': 0})
        group['runs'].append({'run_id': run['run_id'], 'execution': run['execution'], 'converged': run['converged'], 'physical_passed': physical.get('passed')})
        group['errors'].extend(p['error'] for p in run.get('comparison', {}).get('points', []) if p['status'] == 'compared')
        group['n_excluded'] += stats.get('n_excluded', 0)
    aggregates = []
    for group in groups.values():
        errors = group.pop('errors')
        n = len(errors)
        group.update(n_compared=n, bias=math.fsum(errors)/n if n else None,
                     mae=math.fsum(abs(e) for e in errors)/n if n else None,
                     rmse=math.hypot(*errors)/math.sqrt(n) if n else None,
                     error_unit='1', population='All available paired observations from fixed 400-cell base runs; statuses retained without filtering')
        aggregates.append(group)
    summary = {'schema': 'openstream-bartolomey-summary-v1', 'source_report_sha256': hashlib.sha256(report_path.read_bytes()).hexdigest(),
        'counts': report['counts'], 'finest_mesh_cells': max(manifest['mesh_cells']), 'aggregates': aggregates,
        'sensitivity': report['sensitivity'], 'experimental_status': report['experimental_status'],
        'matlab_comparison': report['matlab_comparison'], 'limits': [
            'Correlated points are descriptive samples, not independent statistical replicates.',
            'Reported absolute void error <0.04 does not include quantified digitization or propagated input/numerical uncertainty.',
            'No confidence interval, experimental acceptance pass, independent holdout claim, or asymptotic convergence claim is made.']}
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    with (args.output/'all_runs.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    md = ['# Bartolomey pilot results', '', 'Fixed cases and coefficients; descriptive comparison only.', '',
          '## Finest-mesh measured-versus-predicted errors', '',
          'All errors below are void-fraction percentage points (100 × dimensionless error).', '',
          '| Row / TestID | Model | Points compared / total | Bias [pp] | MAE [pp] | RMSE [pp] | Physical checks |',
          '|---|---|---:|---:|---:|---:|---|']
    for row in rows:
        if row['cells'] == summary['finest_mesh_cells'] and row['variant'] == 'base':
            def fmt(key):
                return f'{row[key]:.5f}' if row.get(key) is not None else 'unavailable'
            md.append(f'| {row["entry_id"]} / {row["test_id"]} | {row["model"]} | {row["n_compared"]} / {row["n_total"]} | {fmt("bias [percentage points]")} | {fmt("MAE [percentage points]")} | {fmt("RMSE [percentage points]")} | {row["physical_passed"]} |')
    md += ['', '## Predeclared numerical sensitivity checks', '',
           '| Row | Model | Check | Max void change [1] | Threshold [1] | Result |', '|---|---|---|---:|---:|---|']
    for s in summary['sensitivity']:
        change = s.get('max_void_change')
        md.append(f'| {s["entry_id"]} | {s["model"]} | {s["kind"]} | {change if change is not None else "unavailable"} | {s.get("threshold", "unavailable")} | {s["status"]} |')
    md += ['', 'Sensitivity is evaluated on identical compared point populations and requires both runs to be iteratively converged. It is not a proof of asymptotic convergence or a numerical uncertainty estimate.', '',
           'The source report and complete per-case input/provenance/array evidence remain in the parent campaign directory. Failed criteria and every excluded measurement remain explicit.', '']
    (args.output/'summary.md').write_text('\n'.join(md), encoding='utf-8')
    print(json.dumps({'counts': summary['counts'], 'aggregates': aggregates}, indent=2))


if __name__ == '__main__':
    main()
