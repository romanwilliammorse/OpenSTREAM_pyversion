"""Summarize saved replay arrays and draw diagnostic plots; never run a solver."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import shutil
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    parser.add_argument('--stem',default='comparison')
    args=parser.parse_args(argv); root=args.directory
    if Path(args.stem).name != args.stem: raise ValueError('Stem must be a filename, not a path')
    target=root/(args.stem+'.json');figure=root/(args.stem+'.png')
    if target.exists() or figure.exists(): raise FileExistsError('Choose an unused analysis destination')
    before=read(root/'native-before-02/report.json');after=read(root/'native-after/report.json')
    assert before['execution_complete'] and after['execution_complete']
    assert before['source_and_original_evidence_unchanged'] and after['source_and_original_evidence_unchanged']
    result={'schema':'openstream-matched-replay-comparison-v1','cases':[],
        'comparison_scope':'Native before/after correction with identical case inputs. Not a matched MATLAB execution.',
        'sources':{str(p.relative_to(root)):sha(p) for p in [root/'native-before-02/report.json',root/'native-after/report.json',root/'twofluid-budget-60/report.json']},
        'postprocessor_sha256':sha(Path(__file__))}
    for old,new in zip(before['cases'],after['cases']):
        assert old['run_id']==new['run_id'];name=old['run_id']
        a=root/'native-before-02'/name;b=root/'native-after'/name
        units_path=Path(__file__).resolve().parents[1]/'outputs/validation/lecorre-2025-01'/name/'comparison_units.json'
        units=read(units_path);result['sources'][str(units_path)]=sha(units_path)
        assert read(a/'effective_inputs.json')==read(b/'effective_inputs.json')
        rows=[]
        with np.load(a/'comparison_profiles.npz') as x,np.load(b/'comparison_profiles.npz') as y:
            assert set(x.files)==set(y.files)
            for key in x.files:
                assert x[key].shape==y[key].shape
                finite=np.isfinite(x[key]) & np.isfinite(y[key]);diff=np.abs(y[key]-x[key])
                idx=int(np.argmax(np.where(finite,diff,-1)))
                rows.append({'quantity':key,'unit':units[key],'exact_equal':bool(np.array_equal(x[key],y[key],equal_nan=True)),
                    'max_absolute_change':float(diff[idx]) if finite.any() else None,'maximum_node_zero_based':idx,
                    'z_m':float(x['Z'][idx]),'before_value':float(x[key][idx]),'after_value':float(y[key][idx])})
        result['cases'].append({'run_id':name,'before_source_state':old['source_state'],'after_source_state':new['source_state'],
            'before_native_converged':old['native_converged'],'after_native_converged':new['native_converged'],
            'all_frozen_inputs_identical':True,'profile_changes':rows})
    name=before['cases'][0]['run_id'];a=root/'native-before-02'/name;b=root/'native-after'/name
    with (b/'point_trace.csv').open() as f:
        point=list(csv.DictReader(f))
    time=max(float(r['time_s']) for r in point)
    rows=[r for r in point if float(r['time_s'])==time and int(r['node_zero_based'])==24]
    result['sawai_final_node24']={'time_s':time,'z_m':float(rows[-1]['z_m']),
        'point_limit_kg_s_m':float(rows[-1]['threshold_dWLw']),
        'last_six_iterations':[{k:float(r[k]) for k in ['iteration','wave_W','wave_U','dWLw','base_W','base_U']} for r in rows[-6:]],
        'interpretation':'Alternating late iterates persist after the source-object correction. Their MATLAB values remain unverified.'}
    with np.load(a/'numerical/initialization.npz') as x,np.load(b/'numerical/initialization.npz') as y:
        z=y['Z']; old_inc=x['film.wave.ITR.DWL'][-1].ravel();new_inc=y['film.wave.ITR.DWL'][-1].ravel()
        bad=np.flatnonzero(new_inc>=float(rows[-1]['threshold_dWLw']))
        result['sawai_final_failed_wave_nodes']=[{'node_zero_based':int(j),'z_m':float(z[j]),'before_increment_kg_s_m':float(old_inc[j]),'after_increment_kg_s_m':float(new_inc[j])} for j in bad]
    budget=read(root/'twofluid-budget-60/report.json')
    result['twofluid_budget']={k:budget[k] for k in ['only_input_change','source_state','native_converged','last_initialization_time_s','stored_states','last_history','original_initialization_prefix_exact','precursor_exact','source_unchanged']}
    with (root/'twofluid-budget-60/numerical/convergence.csv').open() as f:
        history=list(csv.DictReader(f))
    t=np.array([float(r['time_s']) for r in history]);h=np.array([float(r['time_dHL_J_kg']) for r in history])
    plt.rcParams.update({'font.size':11,'axes.labelsize':11})
    fig,axes=plt.subplots(1,3,figsize=(16,4.8),layout='constrained')
    tail=rows[-21:]
    axes[0].plot([float(r['iteration']) for r in tail],[1000*float(r['wave_W']) for r in tail],'-o',ms=3,color='#2980b9',label='Corrected Sawai, node 24')
    axes[0].set(xlabel='Point iteration [1]',ylabel='Wave mass flow [g/s]')
    axes[1].plot(z,old_inc,color='#777777',linestyle='--',label='Before correction')
    axes[1].plot(z,new_inc,color='#2980b9',label='After correction')
    axes[1].axhline(float(rows[-1]['threshold_dWLw']),color='#c0392b',linestyle=':',label='Original point limit')
    axes[1].set(xlim=(.3,.6),xlabel='Axial position [m]',ylabel='Wave-flow iteration change [kg/(s m)]')
    mask=t>=20
    axes[2].plot(t[mask],h[mask],'-o',ms=3,color='#2980b9',label='Longer initialization budget')
    axes[2].axhline(1,color='#c0392b',linestyle=':',label='Unchanged 1 J/kg limit')
    axes[2].axvline(29,color='#777777',linestyle='--',label='Original 29 s stop')
    axes[2].set(xlabel='Initialization pseudo-time [s]',ylabel='Maximum liquid enthalpy change [J/kg]')
    for ax in axes:
        ax.grid(alpha=.2);ax.legend(fontsize=8,loc='upper center',bbox_to_anchor=(.5,-.18))
    fig.savefig(figure,dpi=180);plt.close(fig)
    result['figure_sha256']=sha(figure)
    target.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    shutil.copy2(__file__,root/(args.stem+'_executed_summary.py'))
    print(json.dumps({'case_count':len(result['cases']),'failed_sawai_nodes':len(result['sawai_final_failed_wave_nodes']),
        'twofluid_budget_stop_s':budget['last_initialization_time_s'],'matlab_equivalence':'not_run'}))


if __name__=='__main__':main()
