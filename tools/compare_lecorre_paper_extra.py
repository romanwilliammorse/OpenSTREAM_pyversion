"""Compare saved runs with separately identified Figure 6/7 paper readings.

Source marker identities never depend on agreement with the native calculation.
The callback propagates horizontal/vertical graphical bounds for Figure 7.
No solver execution, reference editing or extrapolation occurs here.
"""
from __future__ import annotations
import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET
import numpy as np
from openstream.properties import FluidProperties
from openstream.inputs import Model

ROOT=Path(__file__).resolve().parents[1]
REFERENCE=ROOT/'references/paper/lecorre2025/figures6_7'
FIELDS={'base':('BaseThickness','base.THICK'),'velocity':('WaveVelocity','wave.U'),'number_density':('WaveNumberDensity','wave.N')}
UNITS={'base.THICK':'m','wave.U':'m/s','wave.N':'1/m','wave.PERIOD':'s','mixture.vapor.U':'m/s'}
UNIT_ALIASES={'m^-1':'1/m'}
PINNED_XML_SHA256_LF={'Wurtz1978':'f45798013aa3516c5fa37700e76000d40742bc0b46b2b39a3d117c7f66740f8f',
    'Sawai1989':'9653bd5910e06c38bcd57b408274f24b2828fc28a12bd6731a46bf9273f598fa'}


def _unit(actual,expected,label):
    if UNIT_ALIASES.get(actual,actual)!=expected:
        raise ValueError(f'Unit mismatch for {label}: {actual!r} versus {expected!r}')


def _records(path):
    entries=[]
    for index,e in enumerate(ET.parse(path).getroot().findall('dataset'),1):
        values={}
        for item in e:
            if item.tag in values:continue
            raw=[x.text for x in e.findall(item.tag)]
            try:parsed=[float(x) if x else None for x in raw]
            except ValueError:parsed=raw
            values[item.tag]=parsed[0] if len(parsed)==1 else parsed
        entries.append((index,values))
    records={}
    for index,values in entries:
        test_id=int(values['TestID'])
        if test_id in records:
            raise ValueError(f'Ambiguous source TestID {test_id} in {path}')
        records[test_id]=(index,values)
    return records


def _scalar_point(prediction,value,bound):
    """Fixed case identity: horizontal measured uncertainty cannot tune a run."""
    if not all(np.isfinite(v) for v in (prediction,value,bound)) or bound<0:
        return {'status':'excluded','reason':'nonfinite_native_value_or_reading'}
    error=float(prediction-value)
    return {'status':'compared','reason':None,'predicted':float(prediction),'error':error,
            'native_min_over_x_reading_interval':float(prediction),
            'native_max_over_x_reading_interval':float(prediction),
            'reading_envelopes_intersect':bool(abs(error)<=bound),
            'distance_between_reading_envelopes':max(0.,abs(error)-bound)}


def _correlation(campaign,run_id,values):
    """Source eq.55 uses measured FilmFlow and the mixture vapor Reynolds number."""
    inputs=json.loads((campaign/run_id/'effective_inputs.json').read_text(encoding='utf-8'))
    model=inputs['model'];geom=inputs['geometry'];pressure=inputs['bc'][0]['PRESSURE']
    fluid=FluidProperties(pressure,SimpleNamespace(FLUID=model['FLUID'],PROPERTIES=model['PROPERTIES'],G=Model.G))
    perimeter=float(np.sum(geom['PERIM']));diameter=4*float(geom['AREA'])/perimeter
    with np.load(campaign/run_id/'numerical/mixture/results.npz') as raw:
        hv=float(raw['vapor.H'][-1,-1]);uv=float(raw['vapor.U'][-1,-1])
    raw_meta=json.loads((campaign/run_id/'numerical/mixture/metadata.json').read_text(encoding='utf-8'))
    _unit(raw_meta['units']['vapor.H'],'J/kg','saved vapor.H')
    _unit(raw_meta['units']['vapor.U'],'m/s','saved vapor.U')
    vapor_re=float(fluid.RHOV(hv)*uv*diameter/fluid.MUV(hv))
    film_re=4*values['FilmFlow']/(perimeter*fluid.MUF)
    prediction=5.37e-5*vapor_re**-.64*film_re**1.21*diameter
    return prediction,{'vapor_reynolds':vapor_re,'measured_film_reynolds':float(film_re),
        'measured_film_flow_kg_s':values['FilmFlow'],'hydraulic_diameter_m':diameter,
        'liquid_dynamic_viscosity_Pa_s':float(fluid.MUF),'vapor_enthalpy_J_kg':hv,
        'vapor_velocity_m_s':uv,'formula':'5.37e-5 * Re_v^(-0.64) * Re_f_measured^(1.21) * d_H',
        'source_method':'Re_v = rho_v(H_v) * U_v * d_H / mu_v(H_v); saved mixture vapor.H/U; effective run pressure and property model',
        'interpretation':'Correlation evaluated with measured film flow; not an independent native base-thickness prediction.'}


def _summaries(points):
    groups=[]
    for key in dict.fromkeys((p['figure'],p['panel'],p['series'],p['variant']) for p in points):
        group=[p for p in points if (p['figure'],p['panel'],p['series'],p['variant'])==key]
        valid=[p for p in group if p['status']=='compared'];error=np.asarray([p['error'] for p in valid])
        if len({UNIT_ALIASES.get(p['unit'],p['unit']) for p in group})!=1:
            raise ValueError(f'Mixed ordinate units in graphical series: {key}')
        groups.append({'figure':key[0],'panel':key[1],'series':key[2],'variant':key[3],'unit':group[0]['unit'],
            'n_total':len(group),'n_excluded':len(group)-len(valid),'n':len(valid),
            'bias':float(error.mean()) if error.size else None,'mae':float(abs(error).mean()) if error.size else None,
            'rmse':float(np.sqrt(np.mean(error**2))) if error.size else None,
            'max_absolute_error':float(abs(error).max()) if error.size else None,
            'reading_envelopes_intersect_count':sum(p['reading_envelopes_intersect'] for p in valid),
            'qualified_converged_pairs':sum(p.get('native_converged',False) for p in valid),
            'pairs_from_physical_failed_runs':sum(p.get('physical_status')=='failed' for p in valid),
            'qualification':'Graphical consistency only; not MATLAB equivalence, experimental acceptance or a numerical tolerance pass.'})
    return groups


def compare_extra(campaign:Path,report:dict,graphical_point)->dict:
    """Return points/series/reference hashes; callback matches main helper API."""
    campaign=Path(campaign);meta=json.loads((REFERENCE/'metadata.json').read_text())
    xml_paths={name:ROOT/'database'/f'+{name}/+src/{name}.xml' for name in ('Wurtz1978','Sawai1989')}
    pinned_xml={key.replace('\\','/'):value for key,value in meta['database_xml_sha256'].items()}
    # Preserve the original raw hashes; CRLF-only normalization independently
    # identifies content across clean Windows/Unix checkouts like the adapter.
    xml_identity={}
    for path in xml_paths.values():
        key=path.relative_to(ROOT/'database').as_posix()
        content=path.read_bytes();raw_hash=hashlib.sha256(content).hexdigest()
        canonical=hashlib.sha256(content.replace(b'\r\n',b'\n')).hexdigest()
        if canonical!=PINNED_XML_SHA256_LF[path.stem]:
            raise ValueError(f'Paper-marker case identity source has changed: {key}')
        xml_identity[key]={'sha256':raw_hash,'original_extraction_raw_sha256':pinned_xml[key],
            'raw_matches_extraction':raw_hash==pinned_xml[key],'sha256_lf':canonical,
            'text_hash_policy':'CRLF normalized to LF only','matches_pinned_content':True}
    wurtz=_records(xml_paths['Wurtz1978']);sawai=_records(xml_paths['Sawai1989'])
    cache={};correlations={};points=[]
    def profiles(run_id):
        if run_id not in cache:
            with np.load(campaign/run_id/'comparison_profiles.npz') as data:
                cache[run_id]={k:data[k].copy() for k in data.files}
            units=json.loads((campaign/run_id/'comparison_units.json').read_text(encoding='utf-8'))
            _unit(units['Z'],'m','native Z')
            for key,expected in UNITS.items():
                if key in cache[run_id]:_unit(units[key],expected,f'{run_id}/{key}')
        return cache[run_id]
    def qualify(record,run):
        record.update(native_converged=run.get('native_converged'),physical_status=run.get('physical',{}).get('status'),
            execution=run.get('execution'),native_source_state=run.get('source_state'))
    with (REFERENCE/'digitized_figure6.csv').open(newline='',encoding='utf-8') as handle:
        for item in csv.DictReader(handle):
            record={**item,'figure':6,'variant':'current_companion','source_kind':'paper_raster_not_MATLAB_arrays',
                'comparison_kind':'fixed_case_graphical_ordinate','status':'excluded','reason':'unmatched_source_case'}
            if not item['test_id']:
                points.append(record);continue
            entry,values=wurtz[int(item['test_id'])];field,key=FIELDS[item['panel']]
            _unit(item['unit'],UNITS[key],'paper Figure6 ordinate')
            _unit(item['coordinate_unit'],UNITS[key],'paper Figure6 measured coordinate')
            run_id=f'wurtz-{entry:02d}-n100-base';run=report['runs'].get(run_id)
            record.update(test_id=int(item['test_id']),entry_id=entry,run_id=run_id,quantity=key,
                calculation_kind='native_model_prediction' if item['series']=='prediction_dot' else 'correlation_with_measured_film_flow')
            source_x=values[field]
            coordinate=float(item['coordinate']);coordinate_bound=float(item['coordinate_reading_bound'])
            if source_x is not None and (not all(np.isfinite(v) for v in (source_x,coordinate,coordinate_bound)) or coordinate_bound<0):
                record.update(reason='invalid_source_coordinate_reading');points.append(record);continue
            if source_x is None or abs(source_x-coordinate)>coordinate_bound:
                record.update(reason='source_measured_coordinate_identity_mismatch');points.append(record);continue
            if values['MassFlux']!=float(item['mass_flux_kg_m2_s']) or values['Pressure']!=float(item['pressure_Pa']):
                record.update(reason='source_group_identity_mismatch');points.append(record);continue
            record['source_measured_coordinate']=source_x
            if not run or run.get('execution')!='completed':
                record.update(reason='native_run_unavailable')
                if run:qualify(record,run)
            else:
                qualify(record,run)
                try:
                    if item['series']=='prediction_dot':
                        native=float(profiles(run_id)[key][-1])
                    else:
                        if values.get('FilmFlow') is None:
                            record.update(reason='measured_film_flow_unavailable');points.append(record);continue
                        if run_id not in correlations:correlations[run_id]=_correlation(campaign,run_id,values)
                        native,details=correlations[run_id];record['correlation_details']=details
                        record['quantity']='LeCorre2022_eq55_base_thickness'
                    record.update(_scalar_point(native,float(item['value']),float(item['value_reading_bound'])))
                except (FileNotFoundError,KeyError) as exc:
                    record.update(reason='required_saved_quantity_unavailable',detail=str(exc))
            points.append(record)
    with (REFERENCE/'digitized_figure7.csv').open(newline='',encoding='utf-8') as handle:
        for item in csv.DictReader(handle):
            entry,values=sawai[int(item['test_id'])]
            diameter=values['Diameter'];mesh=np.asarray(values['WallMesh']);power=np.asarray(values['WallPower'])
            heated=float(np.sum((power>0)*mesh))
            for variant in ('paper-tw020','companion-tw010'):
                run_id=f'sawai-{entry:02d}-{variant}-n100-base';run=report['runs'].get(run_id)
                key='wave.U' if item['series']=='wave_velocity' else 'wave.PERIOD'
                _unit(item['unit'],UNITS[key],'paper Figure7 ordinate')
                _unit(item['coordinate_unit'],'1','paper Figure7 normalized coordinate')
                record={**item,'figure':7,'test_id':int(item['test_id']),'entry_id':entry,'variant':variant,'run_id':run_id,'quantity':key,
                    'source_kind':'paper_raster_not_MATLAB_arrays','comparison_kind':'bounded_axial_profile','calculation_kind':'native_model_prediction',
                    'status':'excluded','reason':'native_run_unavailable','heated_length_m':heated,'hydraulic_diameter_m':diameter}
                if not run or run.get('execution')!='completed':
                    if run:qualify(record,run)
                else:
                    qualify(record,run)
                    try:
                        p=profiles(run_id);start=run['onset']['annular_onset_index_zero_based']
                        record.update(graphical_point((p['Z'][start:]-heated)/diameter,p[key][start:],float(item['coordinate']),
                            float(item['value']),float(item['coordinate_reading_bound']),float(item['value_reading_bound'])))
                    except (FileNotFoundError,KeyError) as exc:
                        record.update(reason='required_saved_quantity_unavailable',detail=str(exc))
                points.append(record)
    hashes={path.relative_to(ROOT).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
        for path in [REFERENCE/'digitized_figure6.csv',REFERENCE/'digitized_figure7.csv',REFERENCE/'metadata.json',*xml_paths.values()]}
    return {'points':points,'series':_summaries(points),'reference_sha256':hashes,'paper_sha256':meta['paper_sha256'],'xml_identity':xml_identity,
        'extraction_exclusions':meta['exclusions'],'policy':'Figure6 uses fixed source case identity; compare only ordinate reading bounds, never interpolate predictions against measured x. Correlation stars use source eq55 and measured film flow separately from model dots. Figure7 propagates both coordinate and ordinate reading bounds. Failed/nonconverged native statuses remain explicit; no tolerance or experimental acceptance claim.'}
