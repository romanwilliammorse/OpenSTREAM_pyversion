"""Analytic checks for independent trace arithmetic; never execute a solver."""
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest


SPEC = importlib.util.spec_from_file_location(
    'independent_replay_audit', Path(__file__).resolve().parents[1]/'tools/audit_matched_replay.py')
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_mass_update_with_known_flux_storage_and_source():
    # u=2 m/s, up=3 kg/s, old=4 kg/s, old_u=4 m/s,
    # source=5 kg/(s m), dz=0.5 m, dt=1 s: 2*(3+0.5+2.5)/2.5.
    assert audit.mass_proposal(2, 3, 4, 4, 5, .5, 1) == 4.8


def test_advective_update_and_relaxation_known_values():
    # For velocity: all numerator terms are m^2/s^2, denominator m/s.
    assert audit.advective_proposal(2, 10, 8, 4, .5, 1) == 10.4
    assert audit.relaxed(4, 8, .25) == 5


@pytest.mark.parametrize('before,after', [((.5,-.25),(.25,0)), ((-.25,.5),(0,.5)), ((.5,.25),(.5,.25))])
def test_clipping_preserves_source_compensation_order(before, after):
    assert audit.clipped_mass(*before) == after


def test_arithmetic_check_detects_one_ulp_and_never_invents_tolerance():
    checks = audit.Checks()
    checks.add('velocity', 'm/s', 1., np.nextafter(1., 2.))
    result = checks.result()
    assert result['mismatches'] == 1
    assert result['groups']['velocity']['max_abs_difference'] == np.spacing(1.)
    assert not result['exact_arithmetic_match']


def test_nonfinite_arithmetic_is_explicitly_counted_not_a_finite_physical_claim():
    checks = audit.Checks()
    checks.add('mass', 'kg/s', 'NaN', 'NaN')
    checks.add('mass', 'kg/s', 'Infinity', '-Infinity')
    result = checks.result()
    assert result['groups']['mass']['nonfinite_pairs'] == 2
    assert result['mismatches'] == 1
    assert result['groups']['mass']['max_abs_difference'] == 0


def test_checks_refuse_unit_changes_and_implicit_multiwall_reduction():
    checks = audit.Checks()
    checks.add('field', 'kg/s', 1., 1.)
    with pytest.raises(ValueError, match='units'):
        checks.add('field', 'm/s', 1., 1.)
    with pytest.raises(ValueError, match='single-wall'):
        audit.one([1., 2.])


def test_organize_binds_only_returns_observed_before_each_stage():
    a = {'stage':'closure_return', 'method':'Liquid.MTOT', 'return_value':1.}
    b = {'stage':'closure_return', 'method':'Liquid.MTOT', 'return_value':2.}
    stages = audit.organize([a, {'stage':'first'}, b, {'stage':'second'}])
    assert stages['first'][1]['Liquid.MTOT']['return_value'] == 1.
    assert stages['second'][1]['Liquid.MTOT']['return_value'] == 2.
    with pytest.raises(ValueError, match='Duplicate stage'):
        audit.organize([{'stage':'first'}, {'stage':'first'}])


def test_final_audit_refuses_incomplete_replay(tmp_path):
    (tmp_path/'report.json').write_text(json.dumps({'execution_complete':False}))
    with pytest.raises(ValueError, match='incomplete'):
        audit.audit(tmp_path)


def test_final_audit_refuses_manifest_drift(tmp_path):
    (tmp_path/'report.json').write_text(json.dumps({'execution_complete':True, 'manifest_sha256':'wrong'}))
    (tmp_path/'frozen_manifest.json').write_text('{}')
    with pytest.raises(ValueError, match='manifest hash'):
        audit.audit(tmp_path)
