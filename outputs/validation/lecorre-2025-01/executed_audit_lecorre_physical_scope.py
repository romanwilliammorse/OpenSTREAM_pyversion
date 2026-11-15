"""Read-only source-state audit; imports no OpenSTREAM solver or adapter."""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--campaign',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args();campaign=args.campaign
if args.output.exists(): raise FileExistsError(args.output)
report_path=campaign/'report.json';report_bytes=report_path.read_bytes();report=json.loads(report_bytes);out=[];hashes={}
for run_id,run in report['runs'].items():
    if run.get('execution')!='completed' or run.get('numerics')!='base':continue
    profile_path=campaign/run_id/'comparison_profiles.npz'
    hashes[run_id]={'comparison_profiles.npz':hashlib.sha256(profile_path.read_bytes()).hexdigest()}
    with np.load(profile_path) as data:
        if 'AFFNC' not in data:continue
        z=data['Z'];aff=data['AFFNC'];negative=[]
        for key in ['film.W','base.W','wave.W','drop.W','film.U','base.U','wave.U','drop.U','film.THICK','base.THICK','wave.AMPLITUDE','wave.FREQUENCY']:
            if key not in data:continue
            a=data[key];mask=a<0
            if not np.any(mask):continue
            j=int(np.nanargmin(a));negative.append({'quantity':key,'count':int(mask.sum()),'minimum':float(a[j]),'minimum_z_m':float(z[j]),'minimum_AFFNC':float(aff[j]),'min_z_m':float(z[mask].min()),'max_z_m':float(z[mask].max()),'minimum_AFFNC_over_negative_nodes':float(aff[mask].min()),'maximum_AFFNC_over_negative_nodes':float(aff[mask].max()),'negative_fully_annular_count':int((mask&(aff>=1-1e-12)).sum())})
        agg_error=None;independent_area=None;difference=None
        if 'base.W' in data:
            lhs=data['film.W']/data['film.U'];rhs=data['base.W']/data['base.U']+data['wave.W']/data['wave.U']
            agg_error=float(np.nanmax(abs(lhs-rhs)))
        if 'film.W' in data:
            effective=json.loads((campaign/run_id/'effective_inputs.json').read_text())
            if effective['model']['PROPERTIES']!='SATURATED':
                raise ValueError('Independent density cancellation requires the audited saturated property assumption')
            for file in ['effective_inputs.json','numerical/mixture/results.npz']:
                hashes[run_id][file]=hashlib.sha256((campaign/run_id/file).read_bytes()).hexdigest()
            with np.load(campaign/run_id/'numerical/mixture/results.npz') as raw:
                # Portable numerical arrays are (time,node), unlike original
                # MATLAB state properties; the comparison profiles are (node,).
                precursor_liquid_inventory=raw['liquid.W'][-1,:]/raw['liquid.U'][-1,:]
                assert precursor_liquid_inventory.shape==z.shape
                annular=aff>=1-1e-12
                # Recover rhoF*A from precursor liquid W/U and its volume
                # fraction; source vapor occupies the unchanged precursor VF.
                liquid_inventory=data['film.W']/data['film.U']+data['drop.W']/data['drop.U']
                independent=(liquid_inventory/precursor_liquid_inventory-1)*(1-data['mixture.VF'])
                independent_area=float(np.max(abs(independent[annular]))) if np.any(annular) else None
    diag=run['physical'].get('source_field_diagnostics',{})
    out.append({'run_id':run_id,'native_converged':run['native_converged'],'physical_status':run['physical']['status'],
        'annular_area_relative':diag.get('max_unblended_annular_area_closure_relative'),
        'all_region_area_relative':diag.get('max_area_closure_relative'),'film_W_over_U_additivity_abs_kg_m':agg_error,
        'independent_annular_area_relative':independent_area,
        'independent_area_difference':independent_area-diag['max_unblended_annular_area_closure_relative'] if independent_area is not None else None,
        'negative_quantities':negative})
result={'schema':'openstream-lecorre-physical-scope-audit-v1','report_sha256':hashlib.sha256(report_bytes).hexdigest(),
    'audit_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'source_sha256':hashes,'runs':out,'annular_mask':'AFFNC >= 1-1e-12',
    'independent_area_formula':'((Wfilm/Ufilm + Wdrop/Udrop)/(Wliquid_precursor/Uliquid_precursor) - 1)*(1-VF_precursor)',
    'assumptions':'Saturated liquid density cancels between precursor and annular liquid. Precursor vapor occupies VF*A and is not updated by annular velocities. Film aggregate W/U includes base and wave inventories. Only completed base runs examined.',
    'unmodified':'No solver inputs, equations, acceptance tolerances or frozen diagnostic flags are changed.'}
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps({'base_runs_audited':len(out),'negative_runs':[x for x in out if x['negative_quantities']],'demo':[x for x in out if x['run_id'].startswith('demo')]},indent=2))
