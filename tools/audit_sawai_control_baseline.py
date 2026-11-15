"""Independently audit baseline mass-defect arithmetic without running a solver."""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(case):
    assessment = json.loads((case/'assessment.json').read_text())
    if assessment['case_id'] != 'ww50-it100' or assessment['execution'] != 'completed':
        raise ValueError('This audit requires the completed unchanged reference control')
    for name, expected in assessment['artifact_sha256'].items():
        if sha(case/name) != expected:
            raise ValueError(f'Changed case artifact: {name}')
    if not assessment['all_215_reference_arrays_exact'] or not assessment['precursor_exact']:
        raise ValueError('Baseline reference reproduction was not established')
    meta = json.loads((case/'frozen_state.json').read_text())
    inp = json.loads((case/'effective_inputs.json').read_text())
    spec = importlib.util.spec_from_file_location('control_analyzer', ROOT/'tools/analyze_sawai_control_study.py')
    analyzer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(analyzer)
    with np.load(case/'frozen_state.npz', allow_pickle=False) as data:
        arrays = {name: data[name] for name in data.files}
    constants = meta['constants']
    p, dz, dt = [float(constants[name]) for name in ('PERIM_m', 'DZ_m', 'DT_s')]
    tolerance = float(inp['options']['ERRORWF'])
    fields = []
    for field in ('base', 'wave'):
        w, u, old_w, old_u, source = [arrays[name] for name in
            (f'current.{field}.W', f'current.{field}.U', f'previous.{field}.W',
             f'previous.{field}.U', f'{field}.MTOT')]
        result = analyzer.mass_defect(w, u, old_w, old_u, source, p, dz, dt, tolerance)
        checks = []
        with localcontext() as context:
            context.prec = 60
            decimal = lambda x: Decimal.from_float(float(x))
            dp, ddz, ddt = map(decimal, (p, dz, dt))
            for node in range(1, len(w)):
                dw, du, dup, dow, dou, ds = map(decimal,
                    (w[node], u[node], w[node-1], old_w[node], old_u[node], source[node]))
                storage = ddz/ddt*(dw/du-dow/dou)
                transfer = dp*ds*ddz
                exact_residual = dw-dup+storage-transfer
                direct_proposal = du*(dup+dow/dou*ddz/ddt+transfer)/(du+ddz/ddt)
                exact_defect = direct_proposal-dw
                rearranged_defect = -du/(du+ddz/ddt)*exact_residual
                # 60-digit Decimal operations need not be bit-identical after
                # cancellation; this checks the algebra far below double error.
                if abs(exact_defect-rearranged_defect) > Decimal('1e-55'):
                    raise ValueError('High-precision residual/proposal identity failed')
                scale = float(abs(dw)+abs(dup)+abs(storage)+abs(transfer))
                bound = 32*np.finfo(float).eps*max(scale, np.finfo(float).tiny)
                residual_difference = abs(result['residual_kg_s'][node]-float(exact_residual))
                defect_difference = abs(result['unrelaxed_defect_kg_s'][node]-float(exact_defect))
                if residual_difference > bound or defect_difference > bound:
                    raise ValueError(f'Floating-point arithmetic exceeded the declared roundoff allowance: {field}/{node}')
                checks.append({'node_zero_based': node,
                    'residual_difference_kg_s': residual_difference,
                    'direct_proposal_defect_difference_kg_s': defect_difference,
                    'roundoff_allowance_kg_s': bound})
        fields.append({'field': field, 'interior_equations_checked': len(checks),
            'max_residual_difference_kg_s': max(c['residual_difference_kg_s'] for c in checks),
            'max_direct_proposal_defect_difference_kg_s': max(c['direct_proposal_defect_difference_kg_s'] for c in checks),
            'max_reference_scaled_ratio': float(np.max(result['reference_scaled_ratio'][1:])),
            'checks': checks})
    bound_files = ['assessment.json', 'frozen_state.npz', 'frozen_state.json', 'effective_inputs.json']
    return {'schema': 'openstream-sawai-control-baseline-arithmetic-review-v1',
        'case_id': assessment['case_id'], 'solver_executed': False,
        'equations_checked': sum(f['interior_equations_checked'] for f in fields),
        'decimal_precision': 60, 'all_arithmetic_checks_passed': True,
        'roundoff_rule': '32*binary64 epsilon times the L1 magnitude of the four residual terms; an arithmetic check, not a solver acceptance tolerance.',
        'native_converged_before_output': assessment['native_converged'],
        'native_converged_after_output': assessment['native_converged_after_output'],
        'fields': fields, 'case_artifact_sha256': {n: sha(case/n) for n in bound_files},
        'audit_tool_sha256': sha(__file__),
        'analyzer_sha256_at_review': sha(ROOT/'tools/analyze_sawai_control_study.py'),
        'limits': ['Independent arithmetic of the saved baseline source returns only; closure values themselves are not independently validated.',
                   'No alternate numerical-control case is evaluated by this audit.',
                   'No MATLAB-equivalence, full stability or experimental-validation claim.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', type=Path, default=ROOT/'outputs/verification/sawai-control-study-01/ww50-it100')
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/verification/sawai-control-study-01/baseline_arithmetic_review.json')
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = audit(args.case)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({k: result[k] for k in ('equations_checked', 'all_arithmetic_checks_passed')}))


if __name__ == '__main__':
    main()
