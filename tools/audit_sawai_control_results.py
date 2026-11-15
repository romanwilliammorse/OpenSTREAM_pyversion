"""Audit all eight saved control cases with Decimal; never import/run a solver."""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
POINTS = [('film.base.ITR.DWL', 'ERRORWF'), ('film.base.ITR.DU', 'ERRORUF'),
          ('film.wave.ITR.DWL', 'ERRORWF'), ('film.wave.ITR.DU', 'ERRORUF'),
          ('film.wave.ITR.DF', 'ERRORFW'), ('drop.ITR.DU', 'ERRORUD')]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def verify(directory, hashes):
    directory = directory.resolve()
    for name, expected in hashes.items():
        path = (directory/name).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or sha(path) != expected:
            raise ValueError(f'Changed or escaped artifact: {path}')


def arrays(path):
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def audit(study):
    analysis_path = study/'analysis/analysis.json'
    analysis = read(analysis_path)
    manifest = read(study/'frozen_manifest.json')
    if sha(study/'frozen_manifest.json') != analysis['manifest_sha256']:
        raise ValueError('Analysis manifest binding differs')
    verify(study/'analysis', analysis['output_sha256'])
    if [r['case_id'] for r in analysis['cases']] != [r['case_id'] for r in manifest['cases']]:
        raise ValueError('Registered case inventory differs')
    fixed = np.array(manifest['frozen_reference_mask']['nodes_zero_based'], dtype=int)
    saved = arrays(study/'analysis/mass_defects.npz')
    cases, snapshots = [], {}
    for row in analysis['cases']:
        case_id = row['case_id']; directory = study/case_id
        assessment = read(directory/'assessment.json')
        if assessment['execution'] != 'completed' or sha(directory/'assessment.json') != row['assessment_sha256']:
            raise ValueError(f'Completed assessment binding differs: {case_id}')
        verify(directory, assessment['artifact_sha256'])
        state = arrays(directory/'frozen_state.npz'); snapshots[case_id] = state
        meta = read(directory/'frozen_state.json'); constants = meta['constants']
        inputs = read(directory/'effective_inputs.json')
        p, dz, dt = [float(constants[k]) for k in ('PERIM_m', 'DZ_m', 'DT_s')]
        tol = float(inputs['options']['ERRORWF'])
        field_checks = []
        for field in ('base', 'wave'):
            prefix = f'{case_id}.{field}.'
            discrepancy, bounds, ratios = [], [], []
            with localcontext() as context:
                context.prec = 60
                d = lambda value: Decimal.from_float(float(value))
                dp, ddz, ddt, tolerance = map(d, (p, dz, dt, tol))
                for j in range(1, len(state['Z'])):
                    w, u, left, old, old_u, source = map(d, (
                        state[f'current.{field}.W'][j], state[f'current.{field}.U'][j],
                        state[f'current.{field}.W'][j-1], state[f'previous.{field}.W'][j],
                        state[f'previous.{field}.U'][j], state[f'{field}.MTOT'][j]))
                    storage = ddz/ddt*(w/u-old/old_u); transfer = dp*source*ddz
                    residual = w-left+storage-transfer
                    proposal = u*(left+old/old_u*ddz/ddt+transfer)/(u+ddz/ddt)
                    defect = proposal-w
                    if abs(defect+u/(u+ddz/ddt)*residual) > Decimal('1e-55'):
                        raise ValueError('60-digit proposal/residual identity differs')
                    ratio = Decimal('0.5')*abs(defect)/(dp*tolerance)
                    exact = np.array([float(residual), float(defect), float(ratio)])
                    actual = np.array([saved[prefix+k][j] for k in
                                       ('residual_kg_s', 'unrelaxed_defect_kg_s', 'reference_scaled_ratio')])
                    bound = 32*np.finfo(float).eps*float(abs(w)+abs(left)+abs(storage)+abs(transfer))
                    allowance = np.array([bound, bound, .5*bound/(p*tol)])
                    errors = np.abs(actual-exact)
                    if not np.all(np.isfinite(actual)) or np.any(errors > allowance):
                        raise ValueError(f'Arithmetic roundoff allowance exceeded: {case_id}/{field}/{j}')
                    discrepancy.append(errors); bounds.append(allowance); ratios.append(float(ratio))
            ratios = np.asarray(ratios); errors = np.asarray(discrepancy); allowances = np.asarray(bounds)
            maxima = {'frozen_reference_mask': float(ratios[fixed-1].max()),
                      'all_interior': float(ratios.max())}
            for mask, maximum in maxima.items():
                reported = row['mass_defects'][field][mask]['reference_scaled_ratio']['max_abs_finite']
                if abs(maximum-reported) > allowances[:, 2].max():
                    raise ValueError('Reported mass-defect maximum differs')
            field_checks.append({'field': field, 'interior_equations_checked': len(ratios),
                'max_residual_difference_kg_s': float(errors[:, 0].max()),
                'max_direct_proposal_defect_difference_kg_s': float(errors[:, 1].max()),
                'max_ratio_difference_dimensionless': float(errors[:, 2].max()),
                'roundoff_allowance_kg_s_min_max': [float(allowances[:, 0].min()), float(allowances[:, 0].max())],
                'ratio_maxima_decimal': maxima})
        init = arrays(directory/'numerical/initialization.npz')
        point = max(float(np.abs(init[key][-1].reshape(-1)[1:]).max()/inputs['options'][option])
                    for key, option in POINTS)
        if point != max(v['normalized']['max_abs_finite'] for v in row['point_metrics'].values()):
            raise ValueError('Reported point ratio differs')
        drop_w, drop_u = state['current.drop.W'], state['current.drop.U']
        minimum = float(drop_w.min()); negative_fixed = fixed[drop_w[fixed] < 0].tolist()
        if minimum != row['signed_bounds']['current.drop.W']['all_nodes']['minimum_finite'] or negative_fixed != row['signed_bounds']['current.drop.W']['fixed_annular_mask']['negative_node_indices']:
            raise ValueError('Reported signed droplet bounds differ')
        cases.append({'case_id': case_id, 'fields': field_checks, 'point_ratio': point,
            'minimum_drop_flow_kg_s': minimum, 'negative_drop_flow_fixed_nodes': negative_fixed,
            'minimum_drop_velocity_at_negative_flow_m_s': float(drop_u[drop_w < 0].min()),
            'artifact_sha256': {name: sha(directory/name) for name in
                ('assessment.json', 'effective_inputs.json', 'frozen_state.json', 'frozen_state.npz', 'numerical/initialization.npz')}})
    profiles = []
    for pair in analysis['profile_comparisons']:
        left, right = snapshots[pair['first']], snapshots[pair['second']]
        metrics = {}
        for name, published in pair['metrics'].items():
            key = 'current.'+name.replace('PERIOD', 'FREQUENCY')
            a, b = left[key], right[key]
            if name.endswith('PERIOD'): a, b = 1/a, 1/b
            delta = float(np.abs(a-b).max()); denominator = float(np.abs(b).max())
            relative = delta/denominator if denominator else (0. if delta == 0 else None)
            if delta != published['max_absolute'] or relative != published['relative_linf_to_second']:
                raise ValueError(f'Reported profile metric differs: {name}')
            metrics[name] = {'max_absolute': delta, 'relative_linf_to_second': relative,
                             'unit': published['unit'], 'bitwise_identical': a.tobytes() == b.tobytes()}
        profiles.append({'first': pair['first'], 'second': pair['second'], 'metrics': metrics})
    return {'schema': 'openstream-sawai-control-independent-results-audit-v1',
        'solver_executed': False, 'governing_equations_changed': False,
        'decimal_precision': 60, 'input_conversion': 'Decimal.from_float: exact stored binary64 values',
        'equations_checked': sum(f['interior_equations_checked'] for c in cases for f in c['fields']),
        'all_arithmetic_and_report_metric_checks_passed': True,
        'roundoff_rule': '32*binary64 epsilon times L1 residual-term magnitude; ratio allowance scales by 0.5/(P*ERRORWF). Arithmetic check only; no scientific acceptance threshold is changed.',
        'cases': cases, 'profile_comparisons': profiles,
        'artifact_sha256': {name: sha(study/name) for name in
            ('frozen_manifest.json', 'analysis/analysis.json', 'analysis/mass_defects.npz')},
        'audit_tool_sha256': sha(__file__),
        'limits': ['Saved source returns are inputs, not independently validated closures.',
                   'No solver reruns, MATLAB comparison, dynamical-stability proof or experimental-validation claim.',
                   'Native and supplementary qualification statuses are not modified.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, default=ROOT/'outputs/verification/sawai-control-study-01')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(); output = args.output or args.study/'independent_results_review.json'
    if output.exists(): raise FileExistsError(output)
    result = audit(args.study)
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'equations_checked': result['equations_checked'], 'all_checks_passed': True}))


if __name__ == '__main__':
    main()
