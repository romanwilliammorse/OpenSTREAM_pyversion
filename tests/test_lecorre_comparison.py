"""Independent analytic checks of saved-output and graphical comparisons."""
import csv
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys

import numpy as np
import pytest


ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
SPEC=importlib.util.spec_from_file_location('lecorre_saved_comparison_tests',ROOT/'tools/compare_lecorre_results.py')
COMPARISON=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPARISON)
EXTRA=sys.modules['compare_lecorre_paper_extra']


def test_common_domain_receipt_is_optional_and_binds_exact_report_and_manifest(tmp_path):
    assert COMPARISON.common_domain_receipt(tmp_path)=={'status':'not_run'}
    report=b'{"runs": {}}\n';manifest=b'{"study": {}}\r\n'
    (tmp_path/'report.json').write_bytes(report)
    (tmp_path/'frozen_manifest.json').write_bytes(manifest)
    receipt={'schema':'openstream-lecorre-common-domain-diagnostic-v1',
        'report_sha256':hashlib.sha256(report).hexdigest(),
        'manifest_sha256_lf':hashlib.sha256(manifest.replace(b'\r\n',b'\n')).hexdigest(),
        'summary':{'eligible_sentinels':1}}
    path=tmp_path/'common_domain_diagnostic.json';path.write_text(json.dumps(receipt),encoding='utf-8')
    result=COMPARISON.common_domain_receipt(tmp_path)
    assert result['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert result['status']=='posthoc_descriptive_diagnostic'
    (tmp_path/'report.json').write_bytes(report+b' ')
    with pytest.raises(ValueError,match='different campaign report'):COMPARISON.common_domain_receipt(tmp_path)
    (tmp_path/'report.json').write_bytes(report)
    (tmp_path/'frozen_manifest.json').write_bytes(manifest+b' ')
    with pytest.raises(ValueError,match='different frozen manifest'):COMPARISON.common_domain_receipt(tmp_path)


def saved_profile(tmp_path,run_id,z,values,aff=None,units=None):
    directory=tmp_path/run_id;directory.mkdir()
    arrays={'Z':np.asarray(z,dtype=float),'AFFNC':np.ones(len(z)) if aff is None else np.asarray(aff,dtype=float)}
    arrays.update({k:np.asarray(v,dtype=float) for k,v in values.items()})
    np.savez_compressed(directory/'comparison_profiles.npz',**arrays)
    mapped={'Z':'m','AFFNC':'1',**{key:'m/s' if key.endswith('.U') else 'kg/s' for key in values}}
    if units:mapped.update(units)
    (directory/'comparison_units.json').write_text(json.dumps(mapped),encoding='utf-8')


def run(*,converged=True,status='completed',physical='not_fully_assessed'):
    return {'execution':status,'native_converged':converged,'physical':{'status':physical},
            'onset':{'annular_onset_index_zero_based':0}}


def first_refinement(tmp_path,left,right):
    manifest={'study':{'sentinels':[{'case_id':'sentinel'}]}}
    report={'runs':{'sentinel-n100-base':left,'sentinel-n200-mesh':right}}
    return COMPARISON.refinement(tmp_path,report,manifest)[0]


def test_graphical_envelope_includes_interior_grid_extrema():
    # Endpoints of the interval have y=0; at x=1 the value is8. The interior
    # vertex x=.75 has y=10 and must not be missed by endpoint/derivative logic.
    result=COMPARISON.graphical_point([0.,.75,2.],[0.,10.,0.],1.,10.5,1.,.5)
    assert result['predicted']==8.
    assert result['error']==-2.5
    assert result['native_min_over_x_reading_interval']==0.
    assert result['native_max_over_x_reading_interval']==10.
    assert result['reading_envelopes_intersect'] is True
    assert result['distance_between_reading_envelopes']==0.


def test_both_x_and_y_bounds_matter_and_tangent_envelopes_intersect():
    # y=2x: x=.5+/- .1 gives [.8,1.2]; observed1.4+/- .2 touches at1.2.
    result=COMPARISON.graphical_point([0.,1.],[0.,2.],.5,1.4,.1,.2)
    assert result['predicted']==1.
    assert result['native_min_over_x_reading_interval']==pytest.approx(.8)
    assert result['native_max_over_x_reading_interval']==pytest.approx(1.2)
    assert result['reading_envelopes_intersect'] is True
    outside=COMPARISON.graphical_point([0.,1.],[0.,2.],.5,1.5,.1,.2)
    assert outside['reading_envelopes_intersect'] is False
    assert outside['distance_between_reading_envelopes']==pytest.approx(.1,abs=1e-15)
    assert outside['error']==-.5


def test_zero_reading_bounds_compare_exact_point_not_neighbouring_extrema():
    result=COMPARISON.graphical_point([0.,.75,2.],[0.,10.,0.],1.,8.,0.,0.)
    assert result['native_min_over_x_reading_interval']==result['native_max_over_x_reading_interval']==8.
    assert result['reading_envelopes_intersect'] is True
    assert result['error']==0.


@pytest.mark.parametrize('coordinate',[np.nextafter(0.,-np.inf),np.nextafter(2.,np.inf),-1.,3.])
def test_graphical_reading_centres_outside_native_domain_are_never_extrapolated(coordinate):
    result=COMPARISON.graphical_point([0.,1.,2.],[2.,4.,6.],coordinate,4.,10.,1.)
    assert result=={'status':'excluded','reason':'outside_native_domain'}


def test_in_domain_bound_interval_is_limited_to_available_native_domain():
    result=COMPARISON.graphical_point([0.,1.],[0.,2.],0.,.2,.5,0.)
    assert result['native_min_over_x_reading_interval']==0.
    assert result['native_max_over_x_reading_interval']==1.
    assert result['predicted']==0.


def test_nonfinite_local_profile_is_excluded_but_distant_invalid_vertex_not_sampled():
    result=COMPARISON.graphical_point([0.,1.,2.],[0.,float('nan'),2.],1.,1.,.1,.1)
    assert result=={'status':'excluded','reason':'nonfinite_native_profile'}
    isolated=COMPARISON.graphical_point([0.,1.,2.],[0.,1.,float('nan')],.25,.25,.1,0.)
    assert isolated['status']=='compared' and isolated['error']==0.


@pytest.mark.parametrize('x,y,coordinate,value,xb,yb',[
    ([[0.,1.]],[0.,1.],.5,.5,0.,0.),([0.,1.],[[0.,1.]],.5,.5,0.,0.),
    ([0.],[0.],0.,0.,0.,0.),([0.,1.],[0.],.5,.5,0.,0.),
    ([0.,0.,1.],[0.,0.,1.],.5,.5,0.,0.),([0.,2.,1.],[0.,2.,1.],.5,.5,0.,0.),
    ([0.,float('nan')],[0.,1.],.5,.5,0.,0.),
    ([0.,1.],[0.,1.],.5,.5,-.1,0.),([0.,1.],[0.,1.],.5,.5,0.,-.1),
    ([0.,1.],[0.,1.],float('inf'),.5,0.,0.),([0.,1.],[0.,1.],.5,float('nan'),0.,0.),
])
def test_invalid_graphical_profiles_or_reading_bounds_rejected(x,y,coordinate,value,xb,yb):
    with pytest.raises(ValueError):COMPARISON.graphical_point(x,y,coordinate,value,xb,yb)


def test_error_statistics_signed_bias_absolute_errors_and_empty_case():
    result=COMPARISON.statistics([-1.,1.,2.])
    assert result=={'n':3,'bias':2/3,'mae':4/3,'rmse':math.sqrt(2.),'max_absolute_error':2.}
    assert COMPARISON.statistics([])=={'n':0,'bias':None,'mae':None,'rmse':None,'max_absolute_error':None}


@pytest.mark.parametrize('left,right,reason',[
    (None,run(),'one_or_both_runs_incomplete'),
    (run(status='failed'),run(),'one_or_both_runs_incomplete'),
    (run(),run(status='failed'),'one_or_both_runs_incomplete'),
    (run(converged=False),run(),'one_or_both_runs_not_natively_converged'),
    (run(),run(converged=False),'one_or_both_runs_not_natively_converged'),
])
def test_refinement_needs_both_completed_and_converged_runs(tmp_path,monkeypatch,left,right,reason):
    monkeypatch.setattr(COMPARISON,'profiles',lambda *_:pytest.fail('Ineligible refinement must not load profiles'))
    result=first_refinement(tmp_path,left,right)
    assert result['status']=='unavailable' and result['reason']==reason
    assert 'quantities' not in result


def test_refinement_does_not_clamp_to_shorter_comparison_grid(tmp_path):
    saved_profile(tmp_path,'sentinel-n100-base',[0.,1.,2.,3.],{'mixture.W':[0.,2.,4.,6.]})
    saved_profile(tmp_path,'sentinel-n200-mesh',[.5,1.,2.,2.5],{'mixture.W':[1.,2.,4.,5.]})
    result=first_refinement(tmp_path,run(),run())
    q=result['quantities']['mixture.W']
    assert (q['n_compared'],q['n_excluded'])==(2,2)
    assert q['rmse']==q['max_absolute_error']==0.
    assert q['unit']=='kg/s'


def test_refinement_requires_annular_eligibility_on_both_bracketing_nodes(tmp_path):
    left=[0.,.5,1.,1.5,2.,2.5,3.]
    saved_profile(tmp_path,'sentinel-n100-base',left,
        {'wave.U':np.asarray(left)*2,'mixture.W':np.asarray(left)*3},aff=[0.,0.,0.,1.,1.,1.,1.])
    saved_profile(tmp_path,'sentinel-n200-mesh',[0.,1.,2.,3.],
        {'wave.U':[0.,2.,4.,6.],'mixture.W':[0.,3.,6.,9.]},aff=[0.,0.,1.,1.])
    result=first_refinement(tmp_path,run(physical='failed'),run(physical='failed'))
    wave=result['quantities']['wave.U'];mixture=result['quantities']['mixture.W']
    assert (wave['n_compared'],wave['n_excluded'])==(3,4)
    assert wave['max_absolute_error']==0.
    assert mixture['n_compared']==7 and mixture['n_excluded']==0
    assert result['status']=='descriptive_sensitivity'
    assert result['physical_status_left']==result['physical_status_right']=='failed'


def test_refinement_excludes_nonfinite_values_without_claiming_zero_data_agreement(tmp_path):
    saved_profile(tmp_path,'sentinel-n100-base',[0.,1.,2.],{'wave.U':[1.,2.,3.]})
    saved_profile(tmp_path,'sentinel-n200-mesh',[0.,1.,2.],{'wave.U':[float('nan')]*3})
    result=first_refinement(tmp_path,run(),run())
    q=result['quantities']['wave.U']
    assert q['n']==q['n_compared']==0 and q['n_excluded']==3
    assert q['mae'] is None and q['rmse'] is None and q['max_absolute_error'] is None


def measured_run(run_id,points,*,family='wurtz',variant=None,converged=True,physical='failed',numerics='base'):
    result={'run_id':run_id,'family':family,'entry_id':1,'numerics':numerics,'native_converged':converged,
            'physical':{'status':physical},'comparisons':{'WaveVelocity':{'points':points}}}
    if variant is not None:result['variant_id']=variant
    return result


def measured_point(index,error=None,reason=None,unit='m/s'):
    return {'index':index,'unit':unit,'measured':2.,'predicted':None if reason else 2+error,
            'error':None if reason else error,'status':'excluded' if reason else 'compared',
            'reason':reason,'source_flags':[]}


def test_experimental_aggregate_preserves_unconverged_errors_and_exclusion_population():
    runs=[measured_run('w1',[measured_point(0,1.),measured_point(1,reason='missing_observation')],converged=False),
          measured_run('w2',[measured_point(0,-.5)],physical='not_fully_assessed'),
          measured_run('w2-mesh',[measured_point(0,100.)],numerics='mesh')]
    result=COMPARISON.experimental_summary({'runs':{r['run_id']:r for r in runs}})
    assert len(result['points'])==3
    summary=result['groups'][0]
    assert summary['n_total']==3 and summary['n']==2 and summary['n_excluded']==1
    assert summary['bias']==.25 and summary['mae']==.75
    assert summary['rmse']==math.sqrt(.625) and summary['max_absolute_error']==1.
    assert summary['qualified_converged_pairs']==1
    assert summary['pairs_from_physical_failed_runs']==1
    assert summary['unit']=='m/s'
    assert result['points'][0]['native_converged'] is False


def test_sawai_paper_and_companion_variants_are_not_pooled():
    runs=[measured_run('paper',[measured_point(0,1.)],family='sawai',variant='paper-tw020'),
          measured_run('companion',[measured_point(0,-1.)],family='sawai',variant='companion-tw010')]
    result=COMPARISON.experimental_summary({'runs':{r['run_id']:r for r in runs}})
    assert [(g['variant'],g['bias']) for g in result['groups']]==[('paper-tw020',1.),('companion-tw010',-1.)]


def test_all_missing_measurements_retained_with_null_metrics():
    result=COMPARISON.experimental_summary({'runs':{'w':measured_run('w',[measured_point(0,reason='missing_observation')])}})
    group=result['groups'][0]
    assert group['n_total']==group['n_excluded']==1
    assert group['n']==0 and group['rmse'] is None
    assert group['qualified_converged_pairs']==group['pairs_from_physical_failed_runs']==0


def test_missing_base_comparison_reports_unavailable_population_without_invented_denominator():
    complete=measured_run('complete',[measured_point(0,.25)])
    failed={'run_id':'failed','family':'wurtz','entry_id':2,'numerics':'base','execution':'failed'}
    # A demonstration has no experimental pairs; mesh cases are accounted in
    # the numerical study, rather than counted again as observation populations.
    demo={**failed,'run_id':'demo','family':'demo','entry_id':None}
    mesh={**failed,'run_id':'mesh','numerics':'mesh'}
    runs={r['run_id']:r for r in (complete,failed,demo,mesh)}
    summary=COMPARISON.experimental_summary({'runs':runs})
    assert summary['observation_accounting_complete'] is False
    assert len(summary['unavailable_runs'])==1
    unavailable=summary['unavailable_runs'][0]
    assert unavailable['run_id']=='failed' and unavailable['execution']=='failed'
    assert unavailable['reason']=='measurement_pairs_unavailable'
    assert 'not included in the metric denominator' in unavailable['interpretation']
    assert len(summary['points'])==1 and summary['groups'][0]['n_total']==1
    assert summary['groups'][0]['rmse']==.25
    del runs['failed']
    available=COMPARISON.experimental_summary({'runs':runs})
    assert available['observation_accounting_complete'] is True and available['unavailable_runs']==[]


def test_paper_comparison_keeps_graphical_errors_and_native_status_separate(tmp_path):
    run_id='demo-mixture-n100-base'
    saved_profile(tmp_path,run_id,[0.,1.,2.],{'mixture.VF':[0.,.5,1.]},units={'mixture.VF':'1'})
    path=tmp_path/'readings.csv'
    fields=['series','coordinate','value','coordinate_reading_bound','value_reading_bound','unit','coordinate_unit']
    rows=[dict(zip(fields,['mixture_void_fraction',1.,.4,0.,.01,'1','m'])),
          dict(zip(fields,['mixture_void_fraction',3.,.8,0.,.01,'1','m'])),
          dict(zip(fields,['twofluid_void_fraction',1.,.4,0.,.01,'1','m']))]
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    result=COMPARISON.paper_comparison(tmp_path,{'runs':{run_id:run(converged=False,physical='failed')}},path)
    p,q,unavailable=result['points']
    assert p['error']==pytest.approx(.1) and not p['native_converged']
    assert p['physical_status']=='failed'
    assert not p['reading_envelopes_intersect']
    assert q['reason']=='outside_native_domain'
    assert unavailable['reason']=='native_run_unavailable'
    assert result['series'][0]['n_total']==2 and result['series'][0]['n_excluded']==1
    assert result['series'][1]['n']==0 and result['series'][1]['rmse'] is None


@pytest.mark.parametrize('coordinate_unit,quantity_unit,message',[
    ('mm','1','coordinate must be in metres'),('m','%','Paper/native unit mismatch'),
])
def test_paper_comparison_rejects_unconverted_units(tmp_path,coordinate_unit,quantity_unit,message):
    run_id='demo-mixture-n100-base'
    saved_profile(tmp_path,run_id,[0.,1.],{'mixture.VF':[0.,.5]},units={'mixture.VF':'1'})
    path=tmp_path/'readings.csv'
    row={'series':'mixture_void_fraction','coordinate':.5,'value':.25,
         'coordinate_reading_bound':0.,'value_reading_bound':0.,
         'unit':quantity_unit,'coordinate_unit':coordinate_unit}
    with path.open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=list(row));writer.writeheader();writer.writerow(row)
    with pytest.raises(ValueError,match=message):
        COMPARISON.paper_comparison(tmp_path,{'runs':{run_id:run()}},path)


def test_refinement_rejects_mixed_units(tmp_path):
    saved_profile(tmp_path,'sentinel-n100-base',[0.,1.],{'wave.U':[0.,1.]})
    saved_profile(tmp_path,'sentinel-n200-mesh',[0.,1.],{'wave.U':[0.,1.]},units={'wave.U':'cm/s'})
    with pytest.raises(ValueError,match='Refinement unit mismatch'):
        first_refinement(tmp_path,run(),run())


def test_experimental_summary_rejects_mixed_units_in_same_population():
    runs=[measured_run('w1',[measured_point(0,1.,unit='m/s')]),
          measured_run('w2',[measured_point(0,1.,unit='cm/s')])]
    with pytest.raises(ValueError,match='Mixed units'):
        COMPARISON.experimental_summary({'runs':{r['run_id']:r for r in runs}})


def figure67_reference(tmp_path,monkeypatch,figure6=(),figure7=()):
    """Tiny pinned source fixture: source identity is independent of predictions."""
    root=tmp_path/'fixture';reference=root/'references';reference.mkdir(parents=True)
    database=root/'database';hashes={};canonical_hashes={}
    bodies={
        'Wurtz1978':'<TestID>101</TestID><BaseThickness>0.001</BaseThickness>'
            '<MassFlux>500</MassFlux><Pressure>7000000</Pressure><FilmFlow>0.01</FilmFlow>',
        'Sawai1989':'<TestID>1</TestID><Diameter>0.004</Diameter>'
            '<WallMesh>0.4</WallMesh><WallMesh>0.4</WallMesh><WallMesh>0.424</WallMesh><WallMesh>0.424</WallMesh>'
            '<WallPower>1</WallPower><WallPower>1</WallPower><WallPower>0</WallPower><WallPower>0</WallPower>',
    }
    for family,body in bodies.items():
        path=database/f'+{family}/+src/{family}.xml';path.parent.mkdir(parents=True)
        path.write_text(f'<datasets><dataset>{body}</dataset></datasets>',encoding='utf-8')
        hashes[path.relative_to(database).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
        canonical_hashes[family]=hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()
    (reference/'metadata.json').write_text(json.dumps({'database_xml_sha256':hashes,
        'paper_sha256':'test-paper-digest','exclusions':[]}),encoding='utf-8')
    for number,rows in ((6,figure6),(7,figure7)):
        with (reference/f'digitized_figure{number}.csv').open('w',newline='',encoding='utf-8') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['series'])
            writer.writeheader();writer.writerows(rows)
    monkeypatch.setattr(EXTRA,'ROOT',root);monkeypatch.setattr(EXTRA,'REFERENCE',reference)
    monkeypatch.setattr(EXTRA,'PINNED_XML_SHA256_LF',canonical_hashes)
    campaign=root/'campaign';campaign.mkdir()
    return campaign


def fig6_point(**changes):
    return {'figure':6,'panel':'base','series':'prediction_dot','test_id':101,
            'mass_flux_kg_m2_s':500,'pressure_Pa':7000000,'coordinate':.001,
            'coordinate_unit':'m','value':.0008,'unit':'m',
            'coordinate_reading_bound':1e-5,'value_reading_bound':1e-6,**changes}


def fig7_point(**changes):
    return {'figure':7,'panel':'velocity_048','series':'wave_velocity','test_id':1,
            'coordinate':1.,'coordinate_unit':'1','value':4.,'unit':'m/s',
            'coordinate_reading_bound':.1,'value_reading_bound':.01,**changes}


def test_figure6_fixed_identity_and_ordinate_error_do_not_tune_against_measured_x(tmp_path,monkeypatch):
    campaign=figure67_reference(tmp_path,monkeypatch,figure6=[fig6_point(),
        fig6_point(coordinate=.002),fig6_point(test_id=''),fig6_point(mass_flux_kg_m2_s=750)])
    native_id='wurtz-01-n100-base'
    saved_profile(campaign,native_id,[0.,1.],{'base.THICK':[.0006,.00081]},units={'base.THICK':'m'})
    result=EXTRA.compare_extra(campaign,{'runs':{native_id:run(converged=False,physical='failed')}},COMPARISON.graphical_point)
    compared,wrong_coordinate,unmatched,wrong_group=result['points']
    assert compared['entry_id']==1 and compared['test_id']==101
    assert compared['source_measured_coordinate']==.001
    assert compared['predicted']==.00081 and compared['error']==pytest.approx(1e-5)
    # A large measured-x reading bound cannot excuse disagreement in the ordinate.
    assert compared['reading_envelopes_intersect'] is False
    assert compared['native_converged'] is False and compared['physical_status']=='failed'
    assert wrong_coordinate['reason']=='source_measured_coordinate_identity_mismatch'
    assert unmatched['reason']=='unmatched_source_case'
    assert wrong_group['reason']=='source_group_identity_mismatch'
    summary=result['series'][0]
    assert (summary['n_total'],summary['n'],summary['n_excluded'])==(4,1,3)
    assert summary['qualified_converged_pairs']==0 and summary['pairs_from_physical_failed_runs']==1


def test_figure7_nondimensional_coordinate_and_period_units_with_both_variants(tmp_path,monkeypatch):
    campaign=figure67_reference(tmp_path,monkeypatch,figure7=[fig7_point(),fig7_point(coordinate=3.),
        fig7_point(panel='period_048',series='wave_period',value=.02,unit='s')])
    native_id='sawai-01-paper-tw020-n100-base'
    saved_profile(campaign,native_id,[.8,.804,.808],{'wave.U':[2.,4.,6.],'wave.PERIOD':[.01,.02,.03]},
                  units={'wave.PERIOD':'s'})
    result=EXTRA.compare_extra(campaign,{'runs':{native_id:run(converged=False,physical='failed')}},COMPARISON.graphical_point)
    velocity,companion,outside,_,period,_=result['points']
    assert velocity['heated_length_m']==.8 and velocity['hydraulic_diameter_m']==.004
    assert velocity['predicted']==pytest.approx(4.) and velocity['error']==pytest.approx(0.,abs=1e-14)
    assert velocity['native_min_over_x_reading_interval']==pytest.approx(3.8)
    assert velocity['native_max_over_x_reading_interval']==pytest.approx(4.2)
    assert velocity['native_converged'] is False
    assert companion['reason']=='native_run_unavailable'
    assert outside['reason']=='outside_native_domain'
    assert period['predicted']==pytest.approx(.02) and period['unit']=='s'
    assert period['error']==pytest.approx(0.,abs=1e-15)


def test_figure67_source_identity_revision_is_checked(tmp_path,monkeypatch):
    campaign=figure67_reference(tmp_path,monkeypatch)
    path=EXTRA.ROOT/'database/+Wurtz1978/+src/Wurtz1978.xml'
    path.write_text(path.read_text()+'\n',encoding='utf-8')
    with pytest.raises(ValueError,match='identity source has changed'):
        EXTRA.compare_extra(campaign,{'runs':{}},COMPARISON.graphical_point)


@pytest.mark.parametrize('prediction,value,bound',[(float('nan'),1.,.1),(1.,float('inf'),.1),(1.,1.,-.1)])
def test_figure6_nonfinite_scalar_or_invalid_reading_bound_excluded(prediction,value,bound):
    result=EXTRA._scalar_point(prediction,value,bound)
    assert result['status']=='excluded' and 'error' not in result


@pytest.mark.parametrize('figure,changes',[(6,{'unit':'mm'}),(6,{'coordinate_unit':'mm'}),
                                         (7,{'unit':'cm/s'}),(7,{'coordinate_unit':'m'})])
def test_figure67_rejects_unconverted_reference_units(tmp_path,monkeypatch,figure,changes):
    kwargs={f'figure{figure}':[(fig6_point if figure==6 else fig7_point)(**changes)]}
    campaign=figure67_reference(tmp_path,monkeypatch,**kwargs)
    with pytest.raises(ValueError,match='Unit mismatch'):
        EXTRA.compare_extra(campaign,{'runs':{}},COMPARISON.graphical_point)


def test_figure67_rejects_incompatible_saved_quantity_units(tmp_path,monkeypatch):
    campaign=figure67_reference(tmp_path,monkeypatch,figure7=[fig7_point()])
    native_id='sawai-01-paper-tw020-n100-base'
    saved_profile(campaign,native_id,[.8,.804],{'wave.U':[2.,4.]},units={'wave.U':'cm/s'})
    with pytest.raises(ValueError,match='Unit mismatch'):
        EXTRA.compare_extra(campaign,{'runs':{native_id:run()}},COMPARISON.graphical_point)


def test_figure67_accepts_crlf_only_xml_difference_and_records_raw_provenance(tmp_path,monkeypatch):
    campaign=figure67_reference(tmp_path,monkeypatch)
    path=EXTRA.ROOT/'database/+Wurtz1978/+src/Wurtz1978.xml'
    # Introduce a line break first and update the synthetic pinned source. Then
    # alter only its representation, as happens in clean Windows checkouts.
    content=path.read_bytes().replace(b'<dataset>',b'<dataset>\n')
    path.write_bytes(content)
    EXTRA.PINNED_XML_SHA256_LF['Wurtz1978']=hashlib.sha256(content).hexdigest()
    path.write_bytes(content.replace(b'\n',b'\r\n'))
    result=EXTRA.compare_extra(campaign,{'runs':{}},COMPARISON.graphical_point)
    identity=result['xml_identity']['+Wurtz1978/+src/Wurtz1978.xml']
    assert identity['matches_pinned_content'] is True
    assert identity['raw_matches_extraction'] is False


def test_figure67_summary_rejects_mixed_units_within_series():
    base={'figure':6,'panel':'base','series':'prediction_dot','variant':'current_companion',
          'status':'compared','error':.1,'reading_envelopes_intersect':False,'native_converged':True}
    with pytest.raises(ValueError,match='Mixed ordinate units'):
        EXTRA._summaries([{**base,'unit':'m'},{**base,'unit':'mm'}])


def test_figure67_rejects_ambiguous_source_test_ids(tmp_path):
    path=tmp_path/'duplicate.xml'
    path.write_text('<datasets><dataset><TestID>7</TestID><BaseThickness>0.1</BaseThickness></dataset>'
                    '<dataset><TestID>7</TestID><BaseThickness>0.2</BaseThickness></dataset></datasets>',encoding='utf-8')
    with pytest.raises(ValueError,match='Ambiguous source TestID 7'):
        EXTRA._records(path)


@pytest.mark.parametrize('changes',[
    {'coordinate':float('nan')},{'coordinate':float('inf')},
    {'coordinate_reading_bound':float('nan')},{'coordinate_reading_bound':float('inf')},
    {'coordinate_reading_bound':-.1},
])
def test_figure6_invalid_horizontal_identity_reading_never_compared(tmp_path,monkeypatch,changes):
    campaign=figure67_reference(tmp_path,monkeypatch,figure6=[fig6_point(**changes)])
    result=EXTRA.compare_extra(campaign,{'runs':{'wurtz-01-n100-base':run()}},COMPARISON.graphical_point)
    point=result['points'][0]
    assert point['status']=='excluded' and point['reason']=='invalid_source_coordinate_reading'
    assert result['series'][0]['n']==0 and result['series'][0]['n_excluded']==1
