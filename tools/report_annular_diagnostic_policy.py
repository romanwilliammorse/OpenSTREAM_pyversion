"""Report the user-directed annular diagnostic policy without rewriting runs."""
import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--campaign', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
if args.output.exists():
    raise FileExistsError(args.output)
path = args.campaign/'report.json'
original = path.read_bytes()
report = json.loads(original)
rows = []
for name, run in report['runs'].items():
    physical = run.get('physical', {})
    diagnostic = physical.get('source_field_diagnostics', {})
    annular = run['framework'] in ('ThreeField', 'FourField')
    rows.append({'run_id': name, 'framework': run['framework'],
        'native_converged': run['native_converged'],
        'recorded_physical_status': physical.get('status'),
        'phase_volume_role': 'informational' if annular else 'existing_policy_unchanged',
        'recorded_area_rejection_superseded': annular and diagnostic.get('physical_consistency') is False,
        'recorded_area_diagnostic_rejected': diagnostic.get('physical_consistency') is False,
        'relative_area_residual': diagnostic.get('max_unblended_annular_area_closure_relative', diagnostic.get('max_area_closure_relative')),
        'other_recorded_bounds': {key: physical.get(key) for key in
            ('finite_primary_curves', 'fraction_bounds', 'nonnegative_flows_speeds_thickness_frequency')},
        'current_overall_physical_acceptance': 'not_reassessed; no physical-validation pass inferred'})
result = {'schema': 'openstream-annular-diagnostic-policy-v1',
    'authority': 'User instruction on2026-11-14: phase-volume closure is not an annular convergence/acceptance criterion; preserve OpenSTREAM governing equations and closure models. Mixture/TwoFluid checks remain.',
    'source_report_sha256': hashlib.sha256(original).hexdigest(),
    'policy_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'scope': 'Criterion-specific classification of existing evidence only; no solver execution, equations, numerical tolerances, saved arrays, comparison metrics or historical flags changed.',
    'counts': {'runs': len(rows), 'native_converged_unchanged': sum(r['native_converged'] for r in rows),
        'annular_area_rejections_now_informational': sum(r['recorded_area_rejection_superseded'] for r in rows),
        'twofluid_area_rejections_retained': sum(r['framework']=='TwoFluid' and r['recorded_area_diagnostic_rejected'] for r in rows),
        'mixture_original_assessment_unchanged': sum(r['framework']=='Mixture' for r in rows)},
    'runs': rows}
if path.read_bytes() != original:
    raise ValueError('Campaign report changed during policy review')
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n', encoding='utf-8')
print(json.dumps(result['counts']))
