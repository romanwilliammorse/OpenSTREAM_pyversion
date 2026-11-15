"""Frozen publication-case accounting and quantity/domain acceptance contracts."""
from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from openstream.database import MeasurementSeries, load_wurtz, load_sawai
from openstream.ff_fields import Wave
from openstream.inputs import Model, Options, InputError


ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('lecorre_reproduction_test_runner',ROOT/'tools/run_lecorre_reproduction.py')
RUNNER=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


@pytest.fixture(scope='module')
def manifest():
    return json.loads((ROOT/'examples/lecorre_reproduction.json').read_text(encoding='utf-8'))


@pytest.fixture(scope='module')
def datasets():
    return {'wurtz':load_wurtz(ROOT/'database'),'sawai':load_sawai(ROOT/'database')}


def observation(x,y,quantity='WaveVelocity',unit='m/s',coordinate='Elevation',coordinate_unit='m',flags=None):
    return MeasurementSeries(coordinate,coordinate_unit,tuple(x),quantity,unit,tuple(y),quantity,unit,
                             tuple(y),'test analytic observations',tuple(flags) if flags is not None else tuple(() for _ in x))


def profile(x=(0.,1.,2.),y=(2.,4.,6.),aff=(1.,1.,1.),key='wave.U'):
    return {'Z':np.asarray(x,dtype=float),key:np.asarray(y,dtype=float),'AFFNC':np.asarray(aff,dtype=float)}


def equal_value(actual,expected):
    if callable(actual):
        np.testing.assert_array_equal(actual(np.array([0.,.5,2.])),expected(np.array([0.,.5,2.])))
    elif isinstance(actual,(list,tuple,np.ndarray)) or isinstance(expected,(list,tuple,np.ndarray)):
        np.testing.assert_array_equal(actual,expected)
    else:
        assert actual==expected or (isinstance(actual,float) and isinstance(expected,float) and math.isnan(actual) and math.isnan(expected))


def test_frozen_manifest_source_identity_and_69_unique_attempts(manifest):
    path=ROOT/'examples/lecorre_reproduction.json'
    assert hashlib.sha256(path.read_bytes().replace(b'\r\n',b'\n')).hexdigest()==RUNNER.MANIFEST_SHA
    RUNNER.validate_sources(manifest,path)
    specs=list(RUNNER.run_specs(manifest))
    assert len(specs)==69
    assert Counter(s['numerics'] for s in specs)=={'base':33,'mesh':24,'tight':12}
    assert len({(s['case_id'],s['cells'],s['numerics']) for s in specs})==69
    bases=[s for s in specs if s['numerics']=='base']
    assert Counter(s['family'] for s in bases)=={'demo':4,'wurtz':21,'sawai':8}
    assert all(s['cells']==100 for s in bases)
    assert Counter(s['cells'] for s in specs if s['numerics']=='mesh')=={200:12,400:12}


def test_frozen_selected_ids_and_sawai_variants_are_not_interchanged(manifest,datasets):
    specs=list(RUNNER.base_specs(manifest))
    wurtz=[s for s in specs if s['family']=='wurtz']
    assert [s['entry_id'] for s in wurtz]==list(datasets['wurtz'].select_test_name('TS 20'))==list(range(1,22))
    sawai=[s for s in specs if s['family']=='sawai']
    assert [s['entry_id'] for s in sawai]==[1,1,2,2,5,5,6,6]
    for s in sawai:
        expected=.2 if s['variant_id']=='paper-tw020' else .1
        assert s['model']['RELAXTW']==expected
    assert [datasets['sawai'].select(i).test_name for i in [1,2,5,6]]==['A_G300','A_G500','C_G300','C_G500']


def test_demo_cumulative_inheritance_and_explicit_physics(manifest,datasets):
    specs=[s for s in RUNNER.run_specs(manifest) if s['family']=='demo' and s['numerics']=='base']
    mix,two,three,four=[RUNNER.construct_inputs(manifest,s,datasets) for s in specs]
    assert [s['framework'] for s in specs]==['Mixture','TwoFluid','ThreeField','FourField']
    assert mix.model.INTNU==Model().INTNU
    for inputs in (two,three,four):
        assert inputs.model.INTNU=='RELAXATION'
        np.testing.assert_array_equal(inputs.model.RELAXX,[-.5,1.])
        np.testing.assert_array_equal(inputs.model.RELAXCONDT,[.5,.5,.01])
        assert inputs.model.MOMENTLIQUID==inputs.model.MOMENTGAS=='FULL'
        assert inputs.model.DROPDRAG=='VISCOUS'
    for inputs in (three,four):
        assert inputs.model.MOMENTFILM==inputs.model.MOMENTDROP=='FULL'
        assert inputs.model.DROPDIAM==.001
    assert four.model.MOMENTBASE=='FULLNOP' and four.model.MOMENTWAVE=='FULL'
    assert four.model.WAVEBASEINT=='VAPORSHEARDROPMASS'
    assert four.model.OAFFILMSPLIT=='RATIO' and four.model.OAFBASERATIO==.3
    assert four.model.BASEEQTHICK=='YPLUS'
    # Inheritance is a configuration copy, not shared mutable input state.
    two.model.RELAXX[0]=-99
    assert three.model.RELAXX[0]==four.model.RELAXX[0]==-.5
    assert manifest['demo']['frameworks'][1]['model']['RELAXX']==[-.5,1.]


def test_demo_mandatory_inputs_and_writer_roundtrip_preserved(manifest,datasets):
    spec=next(s for s in RUNNER.run_specs(manifest) if s['case_id']=='demo-mixture')
    inputs=RUNNER.construct_inputs(manifest,spec,datasets)
    g,bc=inputs.geometry,inputs.bc[0]
    assert (g.LENGTH,g.AREA)==(5.5,6.0821e-5)
    np.testing.assert_array_equal(g.PERIM,[.0276])
    assert (bc.PRESSURE,bc.MFLOW,bc.HIN,bc.POWER)==(6e6,.07,1.1394e6,87500.)
    np.testing.assert_array_equal(bc.WMESH,[1.75,1.75,2.])
    np.testing.assert_array_equal(bc.WPOWER,[[1.],[1.],[0.]])
    assert inputs.options.AXIALINTERP=='NEXT'
    assert inputs.model.RELAXCONDCOEF[1]==.33333333333
    assert inputs.model.RELAXCONDCOEF[1]!=1/3
    for key in Options()._schema:
        expected='NEXT' if key=='AXIALINTERP' else getattr(Options(),key)
        if isinstance(expected,float):expected=float(format(expected,'.11f'))
        equal_value(getattr(inputs.options,key),expected)


def test_tighter_controls_change_only_declared_numerics(manifest,datasets):
    specs=list(RUNNER.run_specs(manifest))
    bases={s['case_id']:s for s in specs if s['numerics']=='base'}
    for tight in (s for s in specs if s['numerics']=='tight'):
        a=RUNNER.construct_inputs(manifest,bases[tight['case_id']],datasets)
        b=RUNNER.construct_inputs(manifest,tight,datasets)
        for name in ('model','geometry'):
            left,right=getattr(a,name),getattr(b,name)
            for key in left._schema:equal_value(getattr(left,key),getattr(right,key))
        for key in a.bc[0].to_dict():equal_value(getattr(a.bc[0],key),getattr(b.bc[0],key))
        for key in a.options._schema:
            old,new=getattr(a.options,key),getattr(b.options,key)
            if key=='MAXITER':assert new==200
            elif key=='SSMAXITER':assert new==60
            elif key.startswith(('ERROR','SSCONV')):
                assert new==pytest.approx(float(format(old*.1,'.11f')),rel=0,abs=1e-15)
            else:equal_value(old,new)


def test_mesh_variants_change_only_node_count(manifest,datasets):
    specs=list(RUNNER.run_specs(manifest));bases={s['case_id']:s for s in specs if s['numerics']=='base'}
    for mesh in (s for s in specs if s['numerics']=='mesh'):
        a=RUNNER.construct_inputs(manifest,bases[mesh['case_id']],datasets)
        b=RUNNER.construct_inputs(manifest,mesh,datasets)
        for key in a.model._schema:
            if key=='NNODES':assert b.model.NNODES==mesh['cells']
            else:equal_value(getattr(a.model,key),getattr(b.model,key))
        for left,right in [(a.options,b.options),(a.geometry,b.geometry),(a.bc[0],b.bc[0])]:
            for key in left.to_dict():equal_value(getattr(left,key),getattr(right,key))


@pytest.mark.parametrize('family',['wurtz','sawai'])
def test_literal_companion_const_spelling_is_rejected(manifest,datasets,family):
    with pytest.raises(InputError):
        datasets[family].select(1).to_input_set(model={**manifest[family]['model'],'VAPORFRIC':'CONST'})


def test_exact_linear_profile_signed_errors_and_source_flags():
    obs=observation([.5,2.],[2.5,5.],flags=[('source_marker',),()])
    result=RUNNER.compare_measurements(obs,profile(),'WaveVelocity')
    assert [p['predicted'] for p in result['points']]==[3.,6.]
    assert [p['error'] for p in result['points']]==[.5,1.]
    assert result['points'][0]['source_flags']==['source_marker']
    assert result['summary']=={'n_total':2,'n_compared':2,'n_excluded':0,'bias':.75,'mae':.75,'rmse':math.sqrt(.625)}
    assert result['unit']=='m/s' and result['kind']=='descriptive'


def test_endpoints_included_and_next_float_outside_not_extrapolated():
    obs=observation([0.,2.,np.nextafter(0.,-np.inf),np.nextafter(2.,np.inf)],[2.,6.,2.,6.])
    result=RUNNER.compare_measurements(obs,profile(),'WaveVelocity')
    assert [p['predicted'] for p in result['points']]==[2.,6.,None,None]
    assert [p['reason'] for p in result['points']]==[None,None,'outside_stored_channel','outside_stored_channel']
    assert result['summary']['n_compared']==result['summary']['n_excluded']==2


def test_annular_mask_applies_to_both_interpolation_nodes():
    result=RUNNER.compare_measurements(observation([.5,1.,1.5],[3.,4.,5.]),profile(aff=(0.,1.,1.)),'WaveVelocity')
    assert [p['predicted'] for p in result['points']]==[None,4.,5.]
    assert result['points'][0]['reason']=='outside_fully_annular_domain'


def test_missing_nonfinite_measurements_and_predictions_remain_explicit():
    obs=observation([None,.5,1.,1.5,2.,0.],[3.,None,4.,5.,float('nan'),2.])
    result=RUNNER.compare_measurements(obs,profile(y=(2.,float('nan'),6.)),'WaveVelocity')
    reasons=[p['reason'] for p in result['points']]
    assert reasons==['missing_coordinate_or_measurement','missing_coordinate_or_measurement',
                     'nonfinite_prediction','nonfinite_prediction','nonfinite_observation',None]
    assert result['summary']=={'n_total':6,'n_compared':1,'n_excluded':5,'bias':0.,'mae':0.,'rmse':0.}
    assert all(p['predicted'] is None and p['error'] is None for p in result['points'][:-1])


@pytest.mark.parametrize('quantity,unit,coordinate_unit',[
    ('WaveVelocity','cm/s','m'),('WaveTimePeriod','ms','m'),('WaveNumberDensity','Hz','m'),
    ('WaveVelocity','m/s','mm'),('BaseThickness','m','m'),
])
def test_quantity_and_unit_mismatch_is_rejected(quantity,unit,coordinate_unit):
    with pytest.raises(ValueError,match='quantity/unit mismatch'):
        RUNNER.compare_measurements(observation([1.],[4.],quantity,unit,coordinate_unit=coordinate_unit),profile(),'WaveVelocity')


def test_coordinate_semantics_must_be_elevation_not_only_metres():
    with pytest.raises(ValueError):
        RUNNER.compare_measurements(observation([1.],[4.],coordinate='Time'),profile(),'WaveVelocity')


@pytest.mark.parametrize('coords,values,flags',[
    ((0.,1.),(2.,),((),())),((0.,),(2.,4.),((),)),((0.,),(2.,),()),
    ((0.,),(2.,),((),())),
])
def test_observation_population_cannot_be_silently_truncated(coords,values,flags):
    with pytest.raises(ValueError):
        RUNNER.compare_measurements(observation(coords,values,flags=flags),profile(),'WaveVelocity')


@pytest.mark.parametrize('bad',[
    profile(x=(0.,0.,2.)),profile(x=(0.,2.,1.)),profile(x=(0.,float('nan'),2.)),
    profile(x=((0.,1.,2.),)),profile(y=((2.,4.,6.),)),
    profile(aff=((1.,),(1.,),(1.,))),profile(aff=(1.,1.)),
])
def test_profile_dimensions_and_axial_order_are_explicit(bad):
    with pytest.raises(ValueError):
        RUNNER.compare_measurements(observation([1.],[4.]),bad,'WaveVelocity')


def test_wave_number_density_is_frequency_over_velocity():
    wave=Wave.__new__(Wave)
    wave.U=np.array([[2.],[4.],[10.]])
    wave.FREQUENCY=np.array([[6.],[20.],[30.]])
    np.testing.assert_allclose(wave.N()[:,0],[3.,5.,3.],atol=0,rtol=0)
    np.testing.assert_allclose(wave.PERIOD()[:,0],[1/6,1/20,1/30],atol=0,rtol=0)
    assert RUNNER.TARGETS['WaveNumberDensity']==('wave.N','m^-1')
    assert RUNNER.TARGETS['WaveTimePeriod']==('wave.PERIOD','s')


@pytest.mark.parametrize('diagnostic',[{}, {'physical_consistency':None}, {'physical_consistency':True}])
def test_absent_or_scoped_physical_diagnostics_never_become_full_pass(monkeypatch,diagnostic):
    solver=SimpleNamespace(diagnostics=lambda:diagnostic)
    monkeypatch.setattr(RUNNER,'balances',lambda _: {'steady_energy_relative_error':0.})
    curves={'mixture.W':np.ones(3),'mixture.VF':np.zeros(3),'mixture.X':np.zeros(3)}
    result=RUNNER.physical_assessment(solver,'Mixture',curves)
    assert result['status']=='not_fully_assessed'
    assert result['source_field_diagnostics']==diagnostic


@pytest.mark.parametrize('diagnostic,curves',[
    ({'physical_consistency':False},{'mixture.W':np.ones(3)}),
    ({},{'mixture.W':np.array([1.,-1.,1.])}),
    ({},{'mixture.VF':np.array([0.,1.01,.5])}),
    ({},{'wave.FREQUENCY':np.array([1.,float('nan'),1.])}),
])
def test_executed_physical_failures_remain_failures(monkeypatch,diagnostic,curves):
    solver=SimpleNamespace(diagnostics=lambda:diagnostic)
    monkeypatch.setattr(RUNNER,'balances',lambda _: {})
    assert RUNNER.physical_assessment(solver,'Mixture',curves)['status']=='failed'


def test_changed_manifest_rejected_before_output_creation(tmp_path,manifest):
    changed=deepcopy(manifest);changed['base']['nnodes']=101
    source=tmp_path/'changed.json';source.write_text(json.dumps(changed),encoding='utf-8')
    dest=tmp_path/'must-not-exist'
    with pytest.raises(ValueError,match='Frozen manifest changed'):
        RUNNER.main(['--manifest',str(source),'--output',str(dest)])
    assert not dest.exists()
