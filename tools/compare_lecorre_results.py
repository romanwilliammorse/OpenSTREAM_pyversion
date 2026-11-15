"""Summarize saved NURETH reconstruction outputs and bounded paper readings.

No solver execution, coefficient adjustment, extrapolation or reference rewrite.
Graphical reading envelopes are distinct from experimental/MATLAB tolerances.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import numpy as np

from openstream.output import portable_json
from openstream.inputs import Model
from openstream.properties import FluidProperties
from openstream.database import load_wurtz,load_sawai
from compare_lecorre_paper_extra import compare_extra

ROOT=Path(__file__).resolve().parents[1]
PAPER_MAP={
 'wall_heat_flux':('mixture','HFLUX'),
 'mixture_liquid_mass_flow':('mixture','mixture.liquid.W'),
 'twofluid_liquid_mass_flow':('twofluid','liquid.W'),
 'mixture_void_fraction':('mixture','mixture.VF'),
 'twofluid_void_fraction':('twofluid','vapor.VF'),
 'mixture_vapor_quality':('mixture','mixture.X'),
 'twofluid_vapor_quality':('twofluid','vapor.X'),
 'threefield_film_mass_flow':('threefield','film.W'),
 'threefield_drop_mass_flow':('threefield','drop.W'),
 'fourfield_base_mass_flow':('fourfield','base.W'),
 'fourfield_wave_mass_flow':('fourfield','wave.W'),
 'threefield_film_thickness':('threefield','film.THICK'),
 'fourfield_base_thickness':('fourfield','base.THICK'),
 'fourfield_wave_amplitude':('fourfield','wave.AMPLITUDE'),
 'mixture_vapor_velocity':('mixture','mixture.vapor.U'),
 'twofluid_liquid_velocity':('twofluid','liquid.U'),
 'threefield_film_velocity':('threefield','film.U'),
 'threefield_drop_velocity':('threefield','drop.U'),
 'fourfield_base_velocity':('fourfield','base.U'),
 'fourfield_wave_velocity':('fourfield','wave.U'),
 'fourfield_wave_frequency':('fourfield','wave.FREQUENCY'),
 'fourfield_equilibrium_wave_frequency':('fourfield','wave.EQFREQUENCY'),
}

def dump(path,value):
    path.write_text(json.dumps(portable_json(value),ensure_ascii=False,indent=2,allow_nan=False,
        default=lambda v:v.item() if isinstance(v,np.generic) else str(v))+'\n',encoding='utf-8')

def profiles(campaign,run_id):
    with np.load(campaign/run_id/'comparison_profiles.npz') as data:return {k:data[k].copy() for k in data.files}

def statistics(errors):
    a=np.asarray(errors,dtype=float)
    return {'n':len(a),'bias':float(a.mean()) if a.size else None,'mae':float(np.abs(a).mean()) if a.size else None,
            'rmse':float(np.sqrt(np.mean(a*a))) if a.size else None,'max_absolute_error':float(np.max(np.abs(a))) if a.size else None}

def graphical_point(x,y,coordinate,value,x_bound,y_bound):
    """Compare a linearly interpolated profile to a bounded graphical reading.

    The ordinate envelope includes all piecewise-linear extrema in the x-reading
    interval, including grid vertices. It does not assume a local derivative at
    discontinuities. Bounds describe reading resolution, not confidence limits.
    """
    x,y=np.asarray(x,float),np.asarray(y,float)
    if x.ndim!=1 or y.ndim!=1 or len(x)!=len(y) or len(x)<2 or not np.all(np.diff(x)>0) or not np.isfinite(x).all():
        raise ValueError('Invalid graphical-comparison profile')
    if not all(np.isfinite(v) for v in (coordinate,value,x_bound,y_bound)) or x_bound<0 or y_bound<0:
        raise ValueError('Invalid graphical reading or bound')
    if not x[0]<=coordinate<=x[-1]:return {'status':'excluded','reason':'outside_native_domain'}
    lo=max(x[0],coordinate-x_bound);hi=min(x[-1],coordinate+x_bound)
    at=np.r_[lo,x[(x>lo)&(x<hi)],hi,coordinate]
    sampled=np.interp(at,x,y)
    if not np.isfinite(sampled).all():return {'status':'excluded','reason':'nonfinite_native_profile'}
    lower,upper=float(sampled.min()),float(sampled.max())
    prediction=float(np.interp(coordinate,x,y))
    return {'status':'compared','reason':None,'predicted':prediction,'error':prediction-value,
            'native_min_over_x_reading_interval':lower,'native_max_over_x_reading_interval':upper,
            'reading_envelopes_intersect':bool(lower<=value+y_bound and upper>=value-y_bound),
            'distance_between_reading_envelopes':max(0.,lower-(value+y_bound),(value-y_bound)-upper)}

def paper_comparison(campaign,report,reference):
    cache={};unit_cache={};points=[]
    with reference.open(newline='',encoding='utf-8') as f:raw=list(csv.DictReader(f))
    for item in raw:
        frame,key=PAPER_MAP[item['series']]
        if item['coordinate_unit']!='m':raise ValueError('Paper profile coordinate must be in metres')
        run_id=f'demo-{frame}-n100-base';run=report['runs'].get(run_id)
        record={**item,'run_id':run_id,'quantity':key,'source_kind':'paper_raster_not_MATLAB_arrays'}
        if not run or run['execution']!='completed':
            record.update(status='excluded',reason='native_run_unavailable')
        else:
            if run_id not in cache:
                cache[run_id]=profiles(campaign,run_id)
                unit_cache[run_id]=json.loads((campaign/run_id/'comparison_units.json').read_text())
            if item['unit']!=unit_cache[run_id][key]:raise ValueError(f'Paper/native unit mismatch for {key}')
            p=cache[run_id];start=run['onset']['annular_onset_index_zero_based'] if frame in ('threefield','fourfield') else 0
            record.update(graphical_point(p['Z'][start:],p[key][start:],float(item['coordinate']),float(item['value']),
                float(item['coordinate_reading_bound']),float(item['value_reading_bound'])))
            record['native_converged']=run['native_converged']
            record['physical_status']=run['physical']['status']
        points.append(record)
    summaries=[]
    for series in dict.fromkeys(x['series'] for x in points):
        group=[x for x in points if x['series']==series];compared=[x for x in group if x['status']=='compared']
        summaries.append({'series':series,'unit':group[0]['unit'],'n_total':len(group),
            'n_excluded':len(group)-len(compared),**statistics([x['error'] for x in compared]),
            'reading_envelopes_intersect_count':sum(x['reading_envelopes_intersect'] for x in compared),
            'qualification':'Graphical reconstruction only; not numerical equivalence or experimental acceptance.'})
    return {'points':points,'series':summaries,'policy':'Propagate both horizontal and vertical image-reading bounds. Envelopes are not confidence intervals, solver tolerances, or an acceptance pass.'}

def refinement(campaign,report,manifest):
    results=[]
    for sentinel in manifest['study']['sentinels']:
        case=sentinel['case_id']
        for left,right,label in [(f'{case}-n100-base',f'{case}-n200-mesh','100_to_200'),
            (f'{case}-n200-mesh',f'{case}-n400-mesh','200_to_400'),(f'{case}-n100-base',f'{case}-n100-tight','tighter_iterations')]:
            a,b=report['runs'].get(left),report['runs'].get(right)
            entry={'case_id':case,'study':label,'left':left,'right':right}
            if not a or not b or a['execution']!='completed' or b['execution']!='completed':
                entry.update(status='unavailable',reason='one_or_both_runs_incomplete')
            elif not (a['native_converged'] and b['native_converged']):
                entry.update(status='unavailable',reason='one_or_both_runs_not_natively_converged')
            else:
                pa,pb=profiles(campaign,left),profiles(campaign,right);items={}
                units=json.loads((campaign/left/'comparison_units.json').read_text())
                other_units=json.loads((campaign/right/'comparison_units.json').read_text())
                for key in pa:
                    if key in ('Z','AFFNC'):continue
                    if units[key]!=other_units[key]:raise ValueError(f'Refinement unit mismatch for {key}')
                    annular=key.startswith(('film.','base.','wave.','drop.'))
                    mask=np.isfinite(pa[key]) & (pa['Z']>=pb['Z'][0]) & (pa['Z']<=pb['Z'][-1])
                    if annular:mask &= pa['AFFNC']>=1-1e-12
                    # An interpolation interval must remain inside the eligible
                    # domain on both grids; no bridging inactive annular nodes.
                    j=np.searchsorted(pb['Z'],pa['Z'],side='left').clip(0,len(pb['Z'])-1)
                    left_j=np.where(pb['Z'][j]==pa['Z'],j,np.maximum(0,j-1))
                    mask &= np.isfinite(pb[key][j]) & np.isfinite(pb[key][left_j])
                    if annular:mask &= (pb['AFFNC'][j]>=1-1e-12)&(pb['AFFNC'][left_j]>=1-1e-12)
                    delta=np.interp(pa['Z'][mask],pb['Z'],pb[key])-pa[key][mask]
                    items[key]={'unit':units[key],'n_compared':int(mask.sum()),'n_excluded':int((~mask).sum()),**statistics(delta)}
                entry.update(status='descriptive_sensitivity',quantities=items,
                    physical_status_left=a['physical']['status'],physical_status_right=b['physical']['status'])
            results.append(entry)
    return results

def experimental_summary(report):
    values=[];unavailable=[]
    for run in report['runs'].values():
        if run['numerics']!='base':continue
        if run['family']!='demo' and not run.get('comparisons'):
            unavailable.append({'run_id':run['run_id'],'family':run['family'],'entry_id':run['entry_id'],
                'execution':run['execution'],'reason':'measurement_pairs_unavailable',
                'interpretation':'Observation population is not included in the metric denominator; inspect source registry and failed run.'})
        for quantity,comparison in run.get('comparisons',{}).items():
            for point in comparison['points']:
                values.append({'run_id':run['run_id'],'family':run['family'],'entry_id':run['entry_id'],
                    'variant_id':run.get('variant_id','companion'),'quantity':quantity,
                    'native_converged':run['native_converged'],'physical_status':run['physical']['status'],**point})
    summaries=[]
    for family,variant,quantity in dict.fromkeys((v['family'],v['variant_id'],v['quantity']) for v in values):
        group=[v for v in values if (v['family'],v['variant_id'],v['quantity'])==(family,variant,quantity)]
        if len({v['unit'] for v in group})!=1:raise ValueError(f'Mixed units for {family}/{variant}/{quantity}')
        valid=[v for v in group if v['status']=='compared']
        summaries.append({'family':family,'variant':variant,'quantity':quantity,'unit':group[0]['unit'],
            'n_total':len(group),'n_excluded':len(group)-len(valid),**statistics([v['error'] for v in valid]),
            'qualified_converged_pairs':sum(v['native_converged'] for v in valid),
            'pairs_from_physical_failed_runs':sum(v['physical_status']=='failed' for v in valid)})
    return {'points':values,'groups':summaries,'unavailable_runs':unavailable,'observation_accounting_complete':not unavailable,
        'status':'descriptive only; missing comparisons are listed explicitly; calibration association and physical failures prevent independent validation claims'}

def csv_output(path,rows):
    fields=list(dict.fromkeys(key for row in rows for key in row))
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def make_plots(campaign,output,report,paper,experimental,extra):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    colors={'mixture':'#0072bd','twofluid':'#d95319','threefield':'#b59a00','fourfield':'#7e2f8e'}
    figures={
      3:[('HFLUX','Heat flux [W/m²]',1),('mass','Liquid-field flow [kg/s]',1),('void','Void fraction / quality [1]',1)],
      4:[('thickness','Film dimension [mm]',1000),('velocity','Velocity [m/s]',1),('frequency','Wave frequency [Hz]',1)]}
    category={
      'HFLUX':['wall_heat_flux'],
      'mass':['mixture_liquid_mass_flow','twofluid_liquid_mass_flow','threefield_film_mass_flow','threefield_drop_mass_flow','fourfield_base_mass_flow','fourfield_wave_mass_flow'],
      'void':['mixture_void_fraction','twofluid_void_fraction','mixture_vapor_quality','twofluid_vapor_quality'],
      'thickness':['threefield_film_thickness','fourfield_base_thickness','fourfield_wave_amplitude'],
      'velocity':['mixture_vapor_velocity','twofluid_liquid_velocity','threefield_film_velocity','threefield_drop_velocity','fourfield_base_velocity','fourfield_wave_velocity'],
      'frequency':['fourfield_wave_frequency','fourfield_equilibrium_wave_frequency']}
    for figure,panels in figures.items():
        fig,axes=plt.subplots(1,3,figsize=(15,4.9),layout='constrained')
        for ax,(panel,label,scale) in zip(axes,panels):
            for series in category[panel]:
                frame,key=PAPER_MAP[series];run_id=f'demo-{frame}-n100-base';run=report['runs'].get(run_id)
                if not run or run['execution']!='completed':continue
                p=profiles(campaign,run_id);start=run['onset']['annular_onset_index_zero_based'] if frame in ('threefield','fourfield') else 0
                dash='--' if any(word in series for word in ('drop','wave_mass','wave_amplitude','vapor_quality')) else '-'
                color='#c82727' if 'equilibrium_wave' in series else colors[frame]
                ax.plot(p['Z'][start:],p[key][start:]*scale,dash,color=color,label=series.replace('_',' '),lw=1.6)
                points=[q for q in paper['points'] if q['series']==series and q['status']=='compared']
                if points:ax.scatter([float(q['coordinate']) for q in points],[float(q['value'])*scale for q in points],
                    s=14,facecolors='none',edgecolors=color,linewidths=.65)
            ax.set(xlabel='Elevation [m]',ylabel=label);ax.grid(alpha=.2);ax.legend(fontsize=6.5)
        fig.suptitle(f'Le Corre Figure {figure}: Python companion reconstruction\nLines: native 100-cell results; open markers: digitized paper. Physical checks remain failed.',fontsize=11)
        fig.savefig(output/f'figure{figure}_paper_comparison.png',dpi=190);plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(13,4.6),layout='constrained')
    wurtz=load_wurtz(ROOT/'database');markers={500:'o',750:'s',1000:'^',2000:'D'}
    corr=[]
    for ax,quantity,label,scale in zip(axes,['BaseThickness','WaveVelocity','WaveNumberDensity'],['Base thickness [mm]','Wave velocity [m/s]','Wave number density [m⁻¹]'],[1000,1,1]):
        points=[p for p in experimental['points'] if p['family']=='wurtz' and p['quantity']==quantity and p['status']=='compared']
        for flux in markers:
            group=[p for p in points if wurtz.select(p['entry_id']).values['MassFlux']==flux]
            if group:ax.scatter([p['measured']*scale for p in group],[p['predicted']*scale for p in group],marker=markers[flux],s=30,label=f'G={flux:g} kg/(m² s)')
        if quantity=='BaseThickness':
            for point in points:
                record=wurtz.select(point['entry_id']);v=record.values
                if v.get('FilmFlow') is None:continue
                p=profiles(campaign,point['run_id']);inputs=record.to_input_set()
                fluid=FluidProperties(inputs.bc[0].PRESSURE,inputs.model)
                dh=float(inputs.geometry.HDIAM());perim=float(inputs.geometry.PERIM[0])
                with np.load(campaign/point['run_id']/'numerical/mixture/results.npz') as raw:
                    hv=float(raw['vapor.H'][-1,-1])
                rev=float(fluid.RHOV(hv)*p['mixture.vapor.U'][-1]*dh/fluid.MUV(hv))
                ref=4*v['FilmFlow']/(perim*fluid.MUF)
                value=5.37e-5*rev**-.64*ref**1.21*dh
                corr.append({'entry_id':point['entry_id'],'measured_base_thickness_m':point['measured'],
                    'correlation_base_thickness_m':value,'measured_film_flow_kg_s':v['FilmFlow'],'vapor_Re':rev,'measured_film_Re':ref,
                    'note':'Le Corre2022 eq55 correlation with measured film flow; not an independent native solver prediction.'})
            ax.scatter([p['measured_base_thickness_m']*1000 for p in corr],[p['correlation_base_thickness_m']*1000 for p in corr],
                       marker='*',s=30,color='#555',alpha=.65,label='Eq.55; measured film flow')
        bound=max([p['measured']*scale for p in points]+[p['predicted']*scale for p in points]+[1e-9])*1.1
        ax.plot([0,bound],[0,bound],'k-',lw=.8)
        ax.plot([0,bound],[0,1.2*bound],'k:',lw=.7);ax.plot([0,bound],[0,bound/1.2],'k:',lw=.7)
        ax.set(xlabel='Measured '+label,ylabel='Calculated '+label,xlim=(0,bound),ylim=(0,bound));ax.grid(alpha=.2);ax.legend(fontsize=7)
    fig.suptitle('Le Corre Figure 6 targets: all 21 TS20 cases\nDescriptive comparisons; dotted factor-1.2 guides are not acceptance limits.',fontsize=11)
    fig.savefig(output/'figure6_measurement_comparison.png',dpi=190);plt.close(fig)
    dump(output/'figure6_measured_film_correlation.json',corr)
    fig,axes=plt.subplots(1,3,figsize=(13,4.5),layout='constrained')
    for ax,panel,label,scale in zip(axes,['base','velocity','number_density'],
            ['Base thickness [mm]','Wave velocity [m/s]','Wave number density [m⁻¹]'],[1000,1,1]):
        rows=[p for p in extra['points'] if p['figure']==6 and p['panel']==panel and p['status']=='compared']
        for series,marker,title in [('prediction_dot','o','Native model'),
                ('measured_film_flow_correlation_star','*','Eq.55; measured film flow')]:
            selected=[p for p in rows if p['series']==series]
            if selected:ax.errorbar([float(p['source_measured_coordinate'])*scale for p in selected],
                [p['error']*scale for p in selected],yerr=[float(p['value_reading_bound'])*scale for p in selected],
                fmt=marker,ms=5,capsize=2,lw=.8,label=title)
        ax.axhline(0,color='black',lw=.8);ax.set(xlabel='Measured '+label,ylabel='Python − paper '+label)
        ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Figure 6: difference from identifiable published markers\nBars: estimated ±3-pixel ordinate-reading bounds; not experimental uncertainty.',fontsize=11)
    fig.savefig(output/'figure6_paper_comparison.png',dpi=190);plt.close(fig)
    sawai=load_sawai(ROOT/'database')
    fig,axes=plt.subplots(2,2,figsize=(12,9),layout='constrained')
    for col,entries in enumerate(([1,2],[5,6])):
        axes[0,col].set_title(f"Outlet quality {sawai.select(entries[0]).values['Xout']:g}; source entries {entries[0]}, {entries[1]}",fontsize=10)
        for entry,color in zip(entries,('#0072bd','#388d39')):
            record=sawai.select(entry);v=record.values;dh=v['Diameter']
            heated=sum(length for length,power in zip(v['WallMesh'],v['WallPower']) if power>0)
            for row,(quantity,key,factor,label) in enumerate([('WaveVelocity','wave.U',1,'Wave velocity [m/s]'),('WaveTimePeriod','wave.PERIOD',1000,'Wave period [ms]')]):
                ax=axes[row,col];obs=record.observations(quantity)
                x=[(z-heated)/dh for z in obs.coordinates];inside=np.asarray(obs.coordinates)<=v['Length']
                y=np.asarray(obs.values)*factor
                ax.scatter(np.asarray(x)[inside],y[inside],color=color,s=32,label=f'Entry{entry} measured')
                ax.scatter(np.asarray(x)[~inside],y[~inside],facecolors='none',edgecolors=color,marker='s',s=42,label=f'Entry{entry} outside stored channel')
                key_series='wave_velocity' if row==0 else 'wave_period'
                readings=[p for p in extra['points'] if p['figure']==7 and p['test_id']==entry
                    and p['series']==key_series and p['variant']=='paper-tw020']
                if readings:ax.scatter([float(p['coordinate']) for p in readings],
                    [float(p['value'])*factor for p in readings],marker='v',facecolors='none',edgecolors=color,s=35,
                    label=f'Entry{entry} paper curve')
                for variant,style in [('paper-tw020','-'),('companion-tw010','--')]:
                    run_id=f'sawai-{entry:02d}-{variant}-n100-base';run=report['runs'].get(run_id)
                    if not run or run['execution']!='completed':continue
                    p=profiles(campaign,run_id);start=run['onset']['annular_onset_index_zero_based']
                    ax.plot((p['Z'][start:]-heated)/dh,p[key][start:]*factor,style,color=color,lw=1.5,label=f'Entry{entry} τ={.2 if variant=="paper-tw020" else .1:g}s')
                    if row==1 and variant=='paper-tw020':
                        ax.plot((p['Z'][start:]-heated)/dh,1000/p['wave.EQFREQUENCY'][start:],':',color=color,lw=.8)
                ax.axvline(0,color='#aaa',lw=.7);ax.set(xlabel='(z - heated length) / hydraulic diameter [1]',ylabel=label);ax.grid(alpha=.2)
    handles=[Line2D([],[],color=color,label=f'G={flux} kg/(m² s)')
        for color,flux in [('#0072bd',300),('#388d39',500)]]
    handles.extend([Line2D([],[],color='black',ls=style,label=label) for style,label in
        [('-','Python τ=0.2 s'),('--','Python τ=0.1 s'),(':','Equilibrium period')]])
    handles.extend([Line2D([],[],color='black',ls='none',marker=marker,markerfacecolor=face,label=label)
        for marker,face,label in [('o','black','Measurement'),('s','none','Measurement outside channel'),('v','none','Digitized paper curve')]])
    fig.legend(handles=handles,loc='outside lower center',ncols=4,fontsize=8)
    fig.suptitle('Le Corre Figure 7: paper τ=0.2 s and companion τ=0.1 s\nOpen squares: out-of-domain measurements. Open triangles: digitized paper curves.\nPhysical failures and some point nonconvergence remain; comparisons are descriptive.',fontsize=11)
    fig.savefig(output/'figure7_measurement_comparison.png',dpi=190);plt.close(fig)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--allow-incomplete',action='store_true')
    args=p.parse_args(argv)
    report=json.loads((args.campaign/'report.json').read_text(encoding='utf-8'))
    manifest=json.loads((args.campaign/'frozen_manifest.json').read_text(encoding='utf-8'))
    if len(report['runs'])!=manifest['expected_attempts']['total'] and not args.allow_incomplete:
        raise ValueError('Campaign incomplete; final analysis requires every planned attempt')
    args.output.mkdir(parents=True,exist_ok=False)
    scripts=[Path(__file__),ROOT/'tools/compare_lecorre_paper_extra.py']
    fingerprints={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest() for path in scripts}
    for path in scripts:(args.output/('executed_'+path.name)).write_bytes(path.read_bytes())
    reference=ROOT/'references/paper/lecorre2025/digitized_curves.csv'
    paper=paper_comparison(args.campaign,report,reference)
    extra=compare_extra(args.campaign,report,graphical_point)
    experiments=experimental_summary(report)
    study=refinement(args.campaign,report,manifest)
    analysis={'schema':'openstream-lecorre-analysis-v1','counts':report['counts'],'incomplete_preview':len(report['runs'])!=69,
        'comparison_source_sha256_lf':fingerprints,
        'postprocessing_versions':{key:version(key) for key in ('numpy','CoolProp','matplotlib')},
        'report_sha256':hashlib.sha256((args.campaign/'report.json').read_bytes()).hexdigest(),
        'paper_reference_sha256':hashlib.sha256(reference.read_bytes()).hexdigest(),'paper_comparison':paper,
        'paper_figures6_7_comparison':extra,
        'experimental_comparison':experiments,'numerical_sensitivity':study,'matlab_equivalence':'unverified',
        'experimental_acceptance':'not_established','figure5_status':'unavailable_TRACE_reference'}
    dump(args.output/'analysis.json',analysis)
    csv_output(args.output/'paper_comparison.csv',paper['points'])
    csv_output(args.output/'paired_measurements.csv',experiments['points'])
    csv_output(args.output/'measurement_metrics.csv',experiments['groups'])
    csv_output(args.output/'paper_metrics.csv',paper['series'])
    csv_output(args.output/'paper_figures6_7_comparison.csv',extra['points'])
    csv_output(args.output/'paper_figures6_7_metrics.csv',extra['series'])
    make_plots(args.campaign,args.output,report,paper,experiments,extra)
    print(json.dumps({'counts':report['counts'],'graphical_points':len(paper['points']),
        'experimental_groups':experiments['groups'],'eligible_sensitivity_pairs':sum(s['status']=='descriptive_sensitivity' for s in study)},indent=2))

if __name__=='__main__':main()
