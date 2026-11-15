"""Run the frozen NURETH-21 reconstruction without altering solver physics.

Source-default cases precede separately labeled diagnostic refinements. Every
attempt, warning, excluded measurement and physical failure is retained.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import time
import traceback
import warnings

import numpy as np

from openstream import MixtureSolver, TwoFluidSolver, ThreeFieldSolver, FourFieldSolver
from openstream.inputs import InputSet, Model, Options, Geometry, BoundaryConditions
from openstream.database import load_wurtz, load_sawai, _generated_input, _file_number
from openstream.output import portable_json, source_hashes, save_result, balances
from openstream.multifield_output import save_multifield

ROOT=Path(__file__).resolve().parents[1]
MANIFEST_SHA='1a2ad36cfedd15998eb85612987329e22b456fb2a0b9f17ea69ce31536c42172'
PREREGISTRATION='03fb5eaebc7b020f441c1b47544cd836978f8469'
SOLVERS={'Mixture':MixtureSolver,'TwoFluid':TwoFluidSolver,'ThreeField':ThreeFieldSolver,'FourField':FourFieldSolver}


def write_json(path,data):
    path.write_text(json.dumps(portable_json(data),indent=2,ensure_ascii=False,allow_nan=False,
        default=lambda value:value.item() if isinstance(value,np.generic) else str(value))+'\n',encoding='utf-8')


def base_specs(manifest):
    for case in manifest['demo']['frameworks']:
        yield {**deepcopy(case),'family':'demo','entry_id':None}
    for entry in manifest['wurtz']['entry_ids']:
        yield {'case_id':f'wurtz-{entry:02d}','family':'wurtz','entry_id':entry,'framework':'FourField','model':deepcopy(manifest['wurtz']['model'])}
    for entry in manifest['sawai']['entry_ids']:
        for variant in manifest['sawai']['variants']:
            yield {'case_id':f'sawai-{entry:02d}-{variant["variant_id"]}','family':'sawai','entry_id':entry,'framework':'FourField',
                   'variant_id':variant['variant_id'],'model':{**deepcopy(manifest['sawai']['model']),'RELAXTW':variant['RELAXTW']}}


def run_specs(manifest):
    cases=list(base_specs(manifest)); by_id={s['case_id']:s for s in cases}
    for spec in cases:
        yield {**spec,'cells':manifest['base']['nnodes'],'numerics':'base'}
    for sentinel in manifest['study']['sentinels']:
        for cells in manifest['study']['meshes']:
            yield {**deepcopy(by_id[sentinel['case_id']]),'cells':cells,'numerics':'mesh'}
        yield {**deepcopy(by_id[sentinel['case_id']]),'cells':manifest['study']['tightening']['nnodes'],'numerics':'tight'}


def construct_inputs(manifest,spec,datasets):
    options=deepcopy(manifest['base']['options'])
    if spec['family']=='demo':options.update(manifest['demo']['options'])
    if spec['numerics']=='tight':
        controls=Options(options); policy=manifest['study']['tightening']
        options.update({key:getattr(controls,key)*policy['factor'] for key in controls._schema
                        if any(key.startswith(prefix) for prefix in policy['prefixes'])})
        options.update(MAXITER=policy['MAXITER'],SSMAXITER=policy['SSMAXITER'])
    model={**spec['model'],'NNODES':spec['cells']}
    if spec['family']!='demo':
        return datasets[spec['family']].select(spec['entry_id']).to_input_set(model=model,options=options)
    entry=manifest['demo']['entry']
    g=_generated_input(Geometry,{'ID':'GENERICDATASET','LENGTH':entry['Length'],'AREA':entry['Area'],'PERIM':entry['Perimeter']})
    m=_generated_input(Model,{'ID':'DEFAULT','FLUID':entry['Fluid'],**model})
    o=_generated_input(Options,options)
    bc={k:_file_number(v) for k,v in {'TIME':0,'PRESSURE':entry['Pressure'],'MFLOW':entry['MassFlow'],
        'HIN':entry['InletEnthalpy'],'POWER':entry['Power'],'WMESH':entry['WallMesh'],'WPOWER':entry['WallPower']}.items()}
    return InputSet(m,o,g,[BoundaryConditions(bc,g)],[str(ROOT/manifest['sources']['companion']['path'])])


def vector(value):
    a=np.asarray(value,dtype=float)
    if a.ndim==2 and a.shape[1]==1:return a[:,0]
    if a.ndim!=1:raise ValueError(f'Expected one axial/single-wall profile, got {a.shape}')
    return a


def collect_curves(solver,framework):
    precursor=solver if framework=='Mixture' else solver.mixSolver
    mix=precursor.mixture[-1]
    curves={'Z':vector(solver.Z),'HFLUX':vector(mix.HFLUX),'mixture.W':vector(mix.W),
        'mixture.liquid.W':vector(mix.liquid.W()),'mixture.VF':vector(mix.VF()),'mixture.X':vector(mix.X()),
        'mixture.XEQ':vector(mix.XEQ()),'mixture.vapor.U':vector(mix.vapor.U()),'AFFNC':vector(mix.AFFNC())}
    units={'Z':'m','HFLUX':'W/m^2','mixture.W':'kg/s','mixture.liquid.W':'kg/s','mixture.VF':'1',
           'mixture.X':'1','mixture.XEQ':'1','mixture.vapor.U':'m/s','AFFNC':'1'}
    if framework=='TwoFluid':
        liq,vap=solver.liquid[-1],solver.vapor[-1]
        for key,value,unit in [('liquid.W',liq.W,'kg/s'),('liquid.U',liq.U,'m/s'),('vapor.VF',vap.VF(liq),'1'),('vapor.X',vap.X(),'1')]:
            curves[key]=vector(value);units[key]=unit
    if framework in ('ThreeField','FourField'):
        film,drop=solver.film[-1],solver.drop[-1]
        for key,value,unit in [('film.W',film.W,'kg/s'),('film.U',film.U,'m/s'),('film.THICK',film.THICK(),'m'),('drop.W',drop.W,'kg/s'),('drop.U',drop.U,'m/s')]:
            curves[key]=vector(value);units[key]=unit
        if framework=='FourField':
            for key,value,unit in [('base.W',film.base.W,'kg/s'),('base.U',film.base.U,'m/s'),('base.THICK',film.base.THICK(),'m'),
                ('wave.W',film.wave.W,'kg/s'),('wave.U',film.wave.U,'m/s'),('wave.AMPLITUDE',film.wave.AMPLITUDE(),'m'),
                ('wave.FREQUENCY',film.wave.FREQUENCY,'Hz'),('wave.EQFREQUENCY',film.wave.EQFREQUENCY(),'Hz'),
                ('wave.PERIOD',film.wave.PERIOD(),'s'),('wave.N',film.wave.N(),'m^-1')]:
                curves[key]=vector(value);units[key]=unit
    return curves,units,{'annular_onset_index_zero_based':int(mix.OAFIDX()),'annular_onset_z_m':float(mix.OAFZ())}


TARGETS={'BaseThickness':('base.THICK','m'),'WaveVelocity':('wave.U','m/s'),
         'WaveNumberDensity':('wave.N','m^-1'),'WaveTimePeriod':('wave.PERIOD','s')}


def compare_measurements(observations,curves,quantity):
    key,unit=TARGETS[quantity]
    if observations.quantity!=quantity or observations.quantity_unit!=unit or observations.unit!='m':
        raise ValueError('Observation quantity/unit mismatch')
    x,y=curves['Z'],curves[key]; mask=curves['AFFNC']>=1-1e-12
    if x.ndim!=1 or len(x)!=len(y) or not np.all(np.isfinite(x)) or not np.all(np.diff(x)>0):
        raise ValueError('Ambiguous axial profile')
    points=[];errors=[]
    for i,(position,measured) in enumerate(zip(observations.coordinates,observations.values)):
        reason=None;prediction=None
        if position is None or measured is None:reason='missing_coordinate_or_measurement'
        elif not math.isfinite(position) or not math.isfinite(measured):reason='nonfinite_observation'
        elif not x[0]<=position<=x[-1]:reason='outside_stored_channel'
        else:
            right=int(np.searchsorted(x,position,side='left'))
            indices=[right] if x[right]==position else [right-1,right]
            if not np.all(mask[indices]):reason='outside_fully_annular_domain'
            elif not np.all(np.isfinite(y[indices])):reason='nonfinite_prediction'
            else:prediction=float(np.interp(position,x,y))
        error=None if prediction is None else prediction-measured
        if error is not None:errors.append(error)
        points.append({'index':i,'elevation_m':position,'measured':measured,'predicted':prediction,'error':error,
                       'unit':unit,'status':'excluded' if reason else 'compared','reason':reason,
                       'source_flags':list(observations.point_flags[i])})
    return {'quantity':quantity,'unit':unit,'error_definition':'predicted minus measured','kind':'descriptive',
            'observations':observations.to_dict(),'points':points,
            'summary':{'n_total':len(points),'n_compared':len(errors),'n_excluded':len(points)-len(errors),
                       'bias':math.fsum(errors)/len(errors) if errors else None,
                       'mae':math.fsum(abs(e) for e in errors)/len(errors) if errors else None,
                       'rmse':math.sqrt(math.fsum(e*e for e in errors)/len(errors)) if errors else None},
            'scope':'No extrapolation, coordinate adjustment, or uncertainty-qualified acceptance. Inlet/onset initialization outside unblended annular domain excluded.'}


def physical_assessment(solver,framework,curves):
    precursor=solver if framework=='Mixture' else solver.mixSolver
    balance=balances(precursor)
    diag=solver.diagnostics() if hasattr(solver,'diagnostics') else {}
    # Report scoped facts rather than promote absent tests into a physical pass.
    finite=all(np.isfinite(v).all() for k,v in curves.items() if k not in ('wave.PERIOD','wave.N'))
    bound_checks={k:bool(np.all((curves[k]>=-1e-12)&(curves[k]<=1+1e-12))) for k in
        ('mixture.VF','mixture.X','vapor.VF','vapor.X') if k in curves}
    nonnegative={k:bool(np.all(v>=-1e-12)) for k,v in curves.items()
                 if k.endswith(('.W','.U','.THICK','.AMPLITUDE','.FREQUENCY'))}
    failed=diag.get('physical_consistency') is False or not finite or not all(bound_checks.values()) or not all(nonnegative.values())
    return {'status':'failed' if failed else 'not_fully_assessed','precursor_balances':balance,
            'source_field_diagnostics':diag,'finite_primary_curves':finite,'fraction_bounds':bound_checks,
            'nonnegative_flows_speeds_thickness_frequency':nonnegative,
            'interpretation':'Passing listed bounds or absence of area rejection is not complete physical acceptance. Original diagnostic tolerances and applicable annular-domain masks retained.'}


def execute_case(manifest,spec,datasets,output):
    run_id=f"{spec['case_id']}-n{spec['cells']}-{spec['numerics']}"
    directory=output/run_id;directory.mkdir(exist_ok=False)
    result={**spec,'run_id':run_id,'execution':'failed','native_converged':False,'source_state':None}
    started=time.perf_counter();caught=[]
    try:
        inputs=construct_inputs(manifest,spec,datasets)
        write_json(directory/'submitted_inputs.json',inputs.to_dict())
        effective=inputs.for_solver(spec['framework'])
        write_json(directory/'effective_inputs.json',effective.to_dict())
        gui={k:v for k,v in inputs.to_dict().items() if k!='source_files'}
        if not np.all(inputs.model.CBTMULT(np.array([0.,inputs.geometry.LENGTH]))==1):
            raise ValueError('This frozen campaign requires constant-one CBTMULT')
        gui['model']['CBTMULT']=1.0
        write_json(directory/'gui_inputs.json',{'schema':'openstream-gui-input-v1','framework':spec['framework'],'inputs':gui})
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            solver=SOLVERS[spec['framework']](inputs).solve()
            result.update(native_converged=bool(solver.converged),source_state=solver.STATE.name,
                          precursor_converged=bool(solver.converged if spec['framework']=='Mixture' else solver.mixSolver.converged),
                          wave_frequency_converged=getattr(solver,'wave_frequency_converged',None))
            curves,units,onset=collect_curves(solver,spec['framework'])
            np.savez_compressed(directory/'comparison_profiles.npz',**curves)
            write_json(directory/'comparison_units.json',units)
            if spec['framework']=='Mixture':save_result(solver,directory/'numerical')
            else:save_multifield(solver,directory/'numerical')
            result.update(onset=onset,physical=physical_assessment(solver,spec['framework'],curves),comparisons={})
            if spec['family']!='demo':
                record=datasets[spec['family']].select(spec['entry_id'])
                for target in manifest[spec['family']]['targets']:
                    result['comparisons'][target]=compare_measurements(record.observations(target),curves,target)
            write_json(directory/'comparisons.json',result['comparisons'])
            with (directory/'paired_measurements.csv').open('w',newline='',encoding='utf-8') as f:
                fields=['quantity','index','elevation_m','measured','predicted','error','unit','status','reason','source_flags']
                writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
                for quantity,comparison in result['comparisons'].items():
                    writer.writerows({'quantity':quantity,**point} for point in comparison['points'])
            result['execution']='completed'
    except Exception as exc:
        result.update(execution='failed',error=f'{type(exc).__name__}: {exc}',traceback=traceback.format_exc())
    result['warnings']=sorted(set(str(item.message) for item in caught))
    result['elapsed_seconds_including_precursor']=time.perf_counter()-started
    write_json(directory/'assessment.json',result)
    print(f'{run_id}: {result["execution"]}; native_converged={result["native_converged"]}; physical={result.get("physical",{}).get("status")}; {result["elapsed_seconds_including_precursor"]:.1f}s',flush=True)
    return result


def validate_sources(manifest,path):
    content=path.read_bytes().replace(b'\r\n',b'\n')
    if hashlib.sha256(content).hexdigest()!=MANIFEST_SHA:raise ValueError('Frozen manifest changed; use a separately preregistered campaign')
    for item in manifest['sources']['xml'].values():
        if hashlib.sha256((ROOT/item['path']).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=item['sha256_lf']:
            raise ValueError('Pinned database XML changed')
    item=manifest['sources']['companion']
    if hashlib.sha256((ROOT/item['path']).read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Pinned companion changed')
    return content


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=ROOT/'examples/lecorre_reproduction.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    manifest=json.loads(args.manifest.read_text(encoding='utf-8-sig'))
    frozen=validate_sources(manifest,args.manifest)
    specs=list(run_specs(manifest))
    if len(specs)!=manifest['expected_attempts']['total']:raise ValueError('Frozen case accounting mismatch')
    datasets={'wurtz':load_wurtz(ROOT/'database'),'sawai':load_sawai(ROOT/'database')}
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'frozen_manifest.json').write_bytes(frozen)
    (args.output/'executed_runner.py').write_bytes(Path(__file__).read_bytes())
    report={'schema':'openstream-lecorre-reconstruction-results-v1','created_utc':datetime.now(timezone.utc).isoformat(),
        'manifest_sha256_lf':MANIFEST_SHA,'preregistration_commit':PREREGISTRATION,'sources':manifest['sources'],
        'source_fingerprints':source_hashes(),'python':platform.python_version(),
        'versions':{k:version(k) for k in ('openstream-python','numpy','scipy','CoolProp','matplotlib')},
        'scope':manifest['scope'],'matlab_equivalence':'not_run','experimental_acceptance':'not_established',
        'blocked_figures':manifest['blocked_figures'],'runs':{},'literal_companion_checks':{}}
    for family in ('wurtz','sawai'):
        try:
            datasets[family].select(1).to_input_set(model={**manifest[family]['model'],'VAPORFRIC':'CONST'})
        except Exception as exc:
            report['literal_companion_checks'][family]={'status':'rejected_as_expected','error':str(exc)}
        else:raise RuntimeError('Literal invalid CONST unexpectedly accepted')
        write_json(args.output/f'{family}_registry.json',[{'record':r.to_dict(),'input_consistency':r.input_consistency(),
            'selected':r.entry_id in manifest[family]['entry_ids']} for r in datasets[family].records])
    for spec in specs:
        result=execute_case(manifest,spec,datasets,args.output)
        report['runs'][result['run_id']]=result
        report['counts']={'attempted':len(report['runs']),'planned':len(specs),
            'completed':sum(r['execution']=='completed' for r in report['runs'].values()),
            'native_converged':sum(r['native_converged'] for r in report['runs'].values()),
            'physical_failed':sum(r.get('physical',{}).get('status')=='failed' for r in report['runs'].values())}
        write_json(args.output/'report.json',report)
    print(json.dumps(report['counts']),flush=True)
    return 0 if all(r['execution']=='completed' and r['native_converged'] and r.get('physical',{}).get('status')!='failed' for r in report['runs'].values()) else 3


if __name__=='__main__':raise SystemExit(main())
