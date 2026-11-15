"""Source-derived annular database/input/observable contracts, without MATLAB."""
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest

from openstream.database import (
    DATABASE_COMMIT, DatasetError, load_wurtz, load_sawai,
    PINNED_WURTZ_XML_SHA256_LF, PINNED_SAWAI_XML_SHA256_LF,
)
from openstream.inputs import InputError


ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def wurtz():
    return load_wurtz(ROOT/'database')


@pytest.fixture(scope='module')
def sawai():
    return load_sawai(ROOT/'database')


def xml_path(family):
    return ROOT/'database'/('+'+family)/'+src'/(family+'.xml')


def changed_xml(tmp_path,family,change):
    root=ET.parse(xml_path(family)).getroot()
    change(root)
    path=tmp_path/(family+'.xml')
    ET.ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    return path


def test_source_identity_and_paper_case_selection(wurtz,sawai):
    assert len(wurtz)==50 and len(sawai)==8
    assert wurtz.select_test_name('TS 20')==tuple(range(1,22))
    assert wurtz.select_test_name('TS 1726L')==tuple(range(22,51))
    assert wurtz.select_test_name('TS20')==()
    assert [sawai.select(i).test_name for i in (1,2,5,6)]==['A_G300','A_G500','C_G300','C_G500']
    for data,family,canonical in ((wurtz,'Wurtz1978',PINNED_WURTZ_XML_SHA256_LF),
                                  (sawai,'Sawai1989',PINNED_SAWAI_XML_SHA256_LF)):
        content=xml_path(family).read_bytes()
        assert data.source['sha256']==hashlib.sha256(content).hexdigest()
        assert data.source['sha256_lf']==canonical
        assert data.source['database_commit']==DATABASE_COMMIT
        assert data.source['matches_pinned_xml'] is True
        assert 'input_adapter_sha256_lf' in data.source
        assert 'plot_mapping_sha256_lf' in data.source


@pytest.mark.parametrize('family,index', [('Wurtz1978',i) for i in range(1,51)]+[('Sawai1989',i) for i in range(1,9)])
def test_every_original_record_input_matches_independent_xml_read(family,index,wurtz,sawai):
    dataset=wurtz if family=='Wurtz1978' else sawai
    row=ET.parse(xml_path(family)).getroot()[index-1]
    inputs=dataset.select(index).to_input_set()
    get=lambda key:[float(x.text) for x in row.findall(key)]
    assert inputs.geometry.ID==family.upper()
    assert inputs.geometry.LENGTH==get('Length')[0]
    assert inputs.geometry.AREA==get('Area')[0]
    assert inputs.geometry.PERIM.tolist()==get('Perimeter')
    assert inputs.model.ID==inputs.options.ID=='DEFAULT'
    assert inputs.model.NNODES==100
    assert inputs.model.FLUID==row.findtext('Fluid').upper()
    assert inputs.model.RELAXCONDCOEF[1]==.33333333333  # Writer, not Python binary1/3.
    bc=inputs.bc[0]
    assert bc.TIME==0
    assert bc.PRESSURE==get('Pressure')[0]
    assert bc.HIN==get('InletEnthalpy')[0]
    assert bc.MFLOW==get('MassFlow')[0]
    assert bc.POWER==get('Power')[0]
    np.testing.assert_array_equal(bc.WMESH,get('WallMesh'))
    expected=np.array(get('WallPower')).reshape((len(get('WallMesh')),len(get('Perimeter'))),order='F')
    np.testing.assert_array_equal(bc.WPOWER,expected)
    assert sum(bc.WMESH)==pytest.approx(inputs.geometry.LENGTH,rel=0,abs=1e-14)


def test_sawai_period_units_raw_values_and_out_of_domain_are_explicit(sawai):
    for record in sawai.records:
        period=record.observations('WaveTimePeriod')
        velocity=record.observations('WaveVelocity')
        assert period.quantity_unit=='s' and period.raw_quantity_unit=='ms'
        assert period.raw_values==record.values['WaveTimePeriod']
        np.testing.assert_allclose(period.values,np.array(period.raw_values)/1000,rtol=2e-16,atol=0)
        assert period.coordinates==record.values['Elevation']==velocity.coordinates
        assert period.unit==velocity.unit=='m'
        assert velocity.quantity_unit=='m/s'
        assert period.coordinates[-1]>record.values['Length']
        assert period.point_flags[-1]==('coordinate_outside_stored_channel',)
        assert all(not flags for flags in period.point_flags[:-1])
        assert period.measurement_uncertainty is None and period.digitization_uncertainty is None
    assert sawai.select(1).values['WaveTimePeriod'][0]==64.3567
    assert sawai.select(1).observations('WaveTimePeriod').values[0]==.0643567


def test_wurtz_outlet_observables_and_derived_period(wurtz):
    r=wurtz.select(1)
    for quantity,value,unit in [('BaseThickness',.00025,'m'),('WaveVelocity',1.8,'m/s'),
        ('WaveNumberDensity',3.8889,'m^-1'),('FilmFlow',.062989,'kg/s')]:
        series=r.observations(quantity)
        assert series.values==(value,) and series.quantity_unit==unit
        assert series.coordinates==(9.,) and series.coordinate=='Elevation'
        assert series.raw_values==series.values
        assert 'outlet_location_from_stored_Length' in series.point_flags[0]
    period=r.observations('WaveTimePeriod')
    assert period.values==(1/7,)
    assert period.raw_quantity=='WaveFrequency' and period.raw_quantity_unit=='Hz'
    assert period.raw_values==(7.,)
    assert 'derived_from_stored_frequency' in period.point_flags[0]
    assert 'imposed_input_not_independent_validation_target' in r.observations('Xout').point_flags[0]


def test_missing_annular_data_are_none_not_zero_and_raw_empty_tags_retained(wurtz):
    missing=next(r for r in wurtz.records if r.values['WaveVelocity'] is None)
    assert any(key=='WaveVelocity' and not text for key,text in missing.raw_fields)
    series=missing.observations('WaveVelocity')
    assert series.values==(None,) and 'missing_observation' in series.point_flags[0]
    missing_frequency=next(r for r in wurtz.records if r.values['WaveFrequency'] is None)
    assert missing_frequency.observations('WaveTimePeriod').values==(None,)
    assert len(json.loads(json.dumps(missing.to_dict(),allow_nan=False))['raw_fields'])==len(missing.raw_fields)


def test_multiwall_records_are_preserved_without_assigning_measurements_to_a_wall(wurtz):
    record=wurtz.select(22)
    assert record.values['Perimeter']==(.053407,.081681)
    inputs=record.to_input_set()
    assert inputs.geometry.PERIM.shape==(2,)
    assert inputs.bc[0].WPOWER.shape==(2,2)
    assert 'multiwall_measurement_wall_unassigned' in record.observations('WaveVelocity').point_flags[0]
    assert record.input_consistency()['checks']['heat_flux_times_heated_area']['status']=='not_assessed_multiwall_metadata'


def test_override_precedence_input_roundtrip_and_independent_mutability(wurtz,sawai):
    given={'ID':'paper','VOID':'BESTION','NNODES':200}
    weights=np.array([[2.],[3.],[0.],[0.]])
    a=sawai.select(1).to_input_set(model=given,geometry={'ID':[]},options={'SSTSTEP':.125},
        boundary_conditions={'MFLOW':.004,'WPOWER':weights})
    b=sawai.select(1).to_input_set()
    assert a.model.ID=='PAPER' and a.model.VOID=='BESTION' and a.model.NNODES==200
    assert a.geometry.ID=='SAWAI1989' and a.options.SSTSTEP==.125
    assert a.bc[0].MFLOW==.004
    weights[:]=9;given['NNODES']=3;a.bc[0].WPOWER[:]=7
    assert b.model.NNODES==100 and b.bc[0].WPOWER[:,0].tolist()==[1,1,0,0]
    assert sawai.select(1).values['WallPower']==(1,1,0,0)
    with pytest.raises(InputError):
        wurtz.select(1).to_input_set(model={'VAPORFRIC':'CONST'})


def test_nonuniform_wall_overrides_preserve_matlab_column_major_order(wurtz):
    # Nonuniform values make an accidental row-major reshape detectable.
    inputs=wurtz.select(22).to_input_set(boundary_conditions={'WPOWER':[1,2,3,4]})
    np.testing.assert_array_equal(inputs.bc[0].WPOWER,[[1,3],[2,4]])


def test_selection_identity_inclusive_ranges_and_no_shared_records(wurtz,sawai):
    assert wurtz.by_test_id(601).entry_id==1
    assert wurtz.matching_test_id(601)==(wurtz.select(1),)
    assert sawai.filter_runs(MassFlux=(300,300))==(1,3,5,7)
    assert wurtz.filter_runs(Pressure=(7e6,7e6),MassFlux=(500,500))[0]==1
    for invalid in (0,51,True,1.0):
        with pytest.raises(DatasetError):wurtz.select(invalid)
    with pytest.raises(DatasetError):wurtz.by_test_id(-1)
    with pytest.raises(DatasetError):sawai.filter_runs(WaveVelocity=(0,5))
    with pytest.raises(DatasetError):wurtz.filter_runs(Perimeter=(0,.1))
    with pytest.raises(DatasetError):wurtz.select_test_name(1)
    with pytest.raises(TypeError):wurtz.select(1).values['Power']=3
    with pytest.raises(FrozenInstanceError):sawai.select(1).observations('WaveVelocity').quantity='VoidFraction'


def test_independent_geometry_energy_and_wave_dimension_checks(wurtz,sawai):
    # Wurtz source cases are adiabatic, with equal stored inlet/outlet enthalpy.
    for record in wurtz.records:
        checks=record.input_consistency()['checks']
        assert checks['enthalpy_gain_times_flow']['stored']==0
        assert checks['enthalpy_gain_times_flow']['calculated']==0
        assert abs(checks['mass_flux_times_area']['signed_difference'])<2e-5
    for record in sawai.records:
        checks=record.input_consistency()['checks']
        assert checks['heat_flux_times_heated_area']['positive_wall_weight_length_m']==.8
        assert abs(checks['heat_flux_times_heated_area']['signed_difference'])/record.values['Power']<1e-4
        assert abs(checks['enthalpy_gain_times_flow']['signed_difference'])/record.values['Power']<1e-4
        assert abs(checks['mass_flux_times_area']['signed_difference'])/record.values['MassFlow']<1e-4
    check=wurtz.select(1).input_consistency()['checks']['wave_frequency_divided_by_velocity']
    assert check['calculated']==pytest.approx(7/1.8)
    assert check['unit']=='m^-1'
    # These dimensional checks are arithmetic checks, not uncertainty bounds.


@pytest.mark.parametrize('mutation,match',[
    (lambda r:ET.SubElement(r[0],'Transient'),'unsupported'),
    (lambda r:ET.SubElement(r[0],'Unknown').__setattr__('text','1'),'unsupported'),
    (lambda r:ET.SubElement(r[0],'Pressure').__setattr__('text','1'),'duplicate scalar'),
    (lambda r:r[0].find('Pressure').__setattr__('text','nan'),'nonfinite'),
    (lambda r:r[0].find('TestID').__setattr__('text','1.5'),'invalid TestID'),
    (lambda r:r[0].remove(r[0].find('Length')),'mandatory input'),
])
def test_malformed_or_unsupported_source_records_fail_explicitly(tmp_path,mutation,match):
    with pytest.raises(DatasetError,match=match):
        load_sawai(changed_xml(tmp_path,'Sawai1989',mutation))


def test_modified_source_cannot_claim_pinned_identity_and_duplicate_ids_stay_ambiguous(tmp_path):
    data=load_wurtz(changed_xml(tmp_path,'Wurtz1978',lambda r:r[1].find('TestID').__setattr__('text','601')))
    assert data.source['database_commit'] is None and not data.source['matches_pinned_xml']
    assert [r.entry_id for r in data.matching_test_id(601)]==[1,2]
    with pytest.raises(DatasetError,match='matches entries'):data.by_test_id(601)


def test_coordinate_count_or_invalid_reciprocal_period_rejected(tmp_path):
    s=load_sawai(changed_xml(tmp_path,'Sawai1989',lambda r:r[0].remove(r[0].find('Elevation'))))
    with pytest.raises(DatasetError,match='counts differ'):s.select(1).observations('WaveVelocity')
    w=load_wurtz(changed_xml(tmp_path,'Wurtz1978',lambda r:r[0].find('WaveFrequency').__setattr__('text','0')))
    with pytest.raises(DatasetError,match='positive stored frequency'):w.select(1).observations('WaveTimePeriod')
    with pytest.raises(DatasetError,match='unsupported observation'):w.select(1).observations('VoidFraction')


def test_raw_xml_line_endings_do_not_change_canonical_identity(tmp_path):
    original=xml_path('Sawai1989').read_bytes().replace(b'\r\n',b'\n')
    lf=tmp_path/'lf.xml';crlf=tmp_path/'crlf.xml'
    lf.write_bytes(original);crlf.write_bytes(original.replace(b'\n',b'\r\n'))
    a,b=load_sawai(lf),load_sawai(crlf)
    assert a.source['sha256']!=b.source['sha256']
    assert a.source['sha256_lf']==b.source['sha256_lf']==PINNED_SAWAI_XML_SHA256_LF
    assert a.source['database_commit']==b.source['database_commit']==DATABASE_COMMIT


def test_missing_redundant_metadata_does_not_replace_authoritative_inputs(tmp_path):
    def remove_metadata(root):
        for field in ('MassFlux','HeatFlux','OutletEnthalpy'):
            root[0].remove(root[0].find(field))
    record=load_sawai(changed_xml(tmp_path,'Sawai1989',remove_metadata)).select(1)
    inputs=record.to_input_set()
    assert inputs.bc[0].MFLOW==.0037699 and inputs.bc[0].POWER==5127.0792
    checks=record.input_consistency()['checks']
    for key in ('mass_flux_times_area','heat_flux_times_heated_area','enthalpy_gain_times_flow'):
        assert checks[key]['status']=='missing_metadata'
