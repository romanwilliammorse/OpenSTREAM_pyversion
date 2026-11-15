"""Run the preregistered longer-budget variant without changing source physics."""
from __future__ import annotations
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import warnings
import numpy as np
from openstream import TwoFluidSolver
from openstream.inputs import InputSet, Options
from openstream.database import load_wurtz, load_sawai
from openstream.output import portable_json, source_hashes
from openstream.multifield_output import save_multifield
from replay_matched_diagnostics import ROOT, write_json, digest, check_frozen, compare_npz
from run_lecorre_reproduction import construct_inputs, run_specs, validate_sources


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args=parser.parse_args(argv)
    policy_path=ROOT/'examples/twofluid_initialization_budget.json'
    policy=json.loads(policy_path.read_text())
    manifest=json.loads((ROOT/policy['matched_manifest']).read_text())
    case=next(c for c in manifest['cases'] if c['run_id']==policy['original_run_id'])
    check_frozen(case)
    campaign_path=ROOT/'examples/lecorre_reproduction.json'
    campaign=json.loads(campaign_path.read_text());validate_sources(campaign,campaign_path)
    spec=next(s for s in run_specs(campaign) if s['case_id']=='demo-twofluid' and s['cells']==400 and s['numerics']=='mesh')
    original=ROOT/policy['original_case']
    inputs=construct_inputs(campaign,spec,{'sawai':load_sawai(ROOT/'database'),'wurtz':load_wurtz(ROOT/'database')})
    before=portable_json(inputs.for_solver('TwoFluid').to_dict())
    assert before==json.loads((original/'effective_inputs.json').read_text())
    options=inputs.options.to_dict();assert options['SSMAXITER']==30;options['SSMAXITER']=60
    inputs=InputSet(inputs.model,Options(options),inputs.geometry,inputs.bc,inputs.source_files)
    after=portable_json(inputs.for_solver('TwoFluid').to_dict())
    expected=deepcopy(before);expected['options']['SSMAXITER']=60
    if after != expected:raise ValueError('Unexpected additional input change')
    source_before=source_hashes()
    args.output.mkdir(parents=True,exist_ok=False)
    shutil.copy2(policy_path,args.output/'frozen_policy.json');shutil.copy2(__file__,args.output/'executed_budget_diagnostic.py')
    write_json(args.output/'effective_inputs.json',after)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        solver=TwoFluidSolver(inputs).solve(progress=lambda r:print(f"t={r['time_s']:g}s max dHl={r['time_dHL_J_kg']:.9g} J/kg point={r['point_converged']}",flush=True))
        save_multifield(solver,args.output/'numerical')
    checks=[]
    with np.load(original/'numerical/initialization.npz') as a,np.load(args.output/'numerical/initialization.npz') as b:
        assert set(a.files)==set(b.files)
        for key in a.files:
            actual=b[key] if key=='Z' else b[key][:a[key].shape[0]]
            checks.append({'key':key,'original_shape':list(a[key].shape),'compared_shape':list(actual.shape),
                'exact_prefix_equal':a[key].dtype==actual.dtype and a[key].shape==actual.shape and np.array_equal(a[key],actual,equal_nan=True)})
    precursor=[compare_npz(original/f'numerical/mixture/{name}.npz',args.output/f'numerical/mixture/{name}.npz') for name in ['results','initialization']]
    report={'schema':policy['schema'],'policy_sha256':digest(policy_path),'only_input_change':policy['only_input_change'],
        'source_state':solver.STATE.name,'native_converged':bool(solver.converged),
        'last_initialization_time_s':float(solver.liquidInit[-1].TIME),'stored_states':len(solver.liquidInit),
        'last_history':solver.history[-1],'original_initialization_prefix':checks,
        'original_initialization_prefix_exact':all(c['exact_prefix_equal'] for c in checks),
        'precursor_comparisons':precursor,'precursor_exact':all(c['passed'] for c in precursor),
        'physical_diagnostics':solver.diagnostics(),'warnings':sorted(set(str(w.message) for w in caught)),
        'original_result':'retained failed 30-state attempt; this separate variant does not replace it',
        'matlab_equivalence':'not_run','experimental_validation':'not_established',
        'native_source_sha256':source_before,'source_unchanged':source_hashes()==source_before}
    check_frozen(case)
    write_json(args.output/'report.json',report)
    print(json.dumps({k:report[k] for k in ['native_converged','last_initialization_time_s','stored_states','original_initialization_prefix_exact','precursor_exact','source_unchanged']}))
    if not report['original_initialization_prefix_exact'] or not report['precursor_exact'] or not report['source_unchanged']:
        raise RuntimeError('Budget diagnostic changed evidence before the original stopping limit')
    return 0


if __name__=='__main__':raise SystemExit(main())
