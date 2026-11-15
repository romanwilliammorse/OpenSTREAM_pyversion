"""Independent safeguards for control-study arithmetic and evidence accounting."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sawai_control_analysis', ROOT/'tools/analyze_sawai_control_study.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def test_same_state_mass_balance_and_inlet_exclusion():
    w = np.full(3, .001); u = np.ones(3)
    result = tool.mass_defect(w, u, w, u, np.zeros(3), .02, .1, 1., .0001)
    assert np.isnan(result['residual_kg_s'][0])
    assert np.array_equal(result['residual_kg_s'][1:], np.zeros(2))
    assert np.array_equal(result['reference_scaled_ratio'][1:], np.zeros(2))


def test_mass_residual_matches_independent_source_proposal():
    w = np.array([.001, .0012]); u = np.array([1., 2.])
    old = np.array([.001, .0011]); source = np.array([0., .001])
    result = tool.mass_defect(w, u, old, u, source, .02, .1, .5, .0001)
    # Flow difference0.0002 + storage0.00001 - source0.000002, all kg/s.
    assert result['residual_kg_s'][1] == pytest.approx(.000208, abs=1e-18)
    direct_proposal = 2*(.001 + .0011/2*.1/.5 + .02*.001*.1)/(2+.1/.5)
    assert result['unrelaxed_defect_kg_s'][1] == pytest.approx(direct_proposal-.0012, abs=1e-18)


def test_lower_relaxation_cannot_manufacture_supplementary_pass():
    w = np.full(2, .001); u = np.ones(2)
    result = tool.mass_defect(w, u, w, u, np.array([0., .0033]), .02, .1, 1., .0001)
    actual_small_relaxation_increment_ratio = .05*abs(result['unrelaxed_defect_kg_s'][1])/.02/.0001
    assert actual_small_relaxation_increment_ratio < 1
    assert result['reference_scaled_ratio'][1] == pytest.approx(1.5)
    assert not tool.screen_ratio(result['reference_scaled_ratio'], np.array([False, True]), np.array([0., .1]))['strictly_below_one']


def test_strict_limit_and_nonfinite_values_do_not_pass():
    z = np.array([0., .1, .2]); mask = np.array([False, True, True])
    assert not tool.screen_ratio(np.array([np.nan, .5, 1.]), mask, z)['strictly_below_one']
    r = tool.screen_ratio(np.array([np.nan, .5, np.nan]), mask, z)
    assert r['nonfinite_nodes'] == [2] and not r['strictly_below_one']
    assert not tool.screen_ratio(np.zeros(3), np.zeros(3, dtype=bool), z)['strictly_below_one']


def test_fixed_mask_cannot_drop_newly_nonpositive_nodes():
    state = {f'current.{field}.{quantity}': np.ones(3) for field in ('base', 'wave') for quantity in ('W', 'U')}
    state['current.base.W'][2] = 0.
    frozen = np.array([False, True, True])
    assert tool.mask_applicability(state, frozen) == {'nonempty': True, 'inapplicable_nodes': [2], 'applicable': False}
    assert np.array_equal(frozen, [False, True, True])


def test_snapshot_identity_requires_original_saved_state():
    z = np.array([0., .1]); init = {'Z': z, 'TIME': np.array([0., 1.])}; snap = {'Z': z}
    for field in ('base', 'wave', 'drop'):
        for quantity in ('W', 'U', 'H') + (('FREQUENCY',) if field == 'wave' else ()):
            name = f'{"film." if field != "drop" else ""}{field}.{quantity}'
            init[name] = np.arange(4, dtype=float).reshape(2, 2, 1)
            for prefix, index in (('previous', 0), ('current', 1)):
                snap[f'{prefix}.{field}.{quantity}'] = init[name][index].ravel().copy()
    assert tool.exact_snapshot_match(snap, init) == 20
    snap['current.wave.W'][1] += 1e-9
    with pytest.raises(ValueError, match='differs from saved'):
        tool.exact_snapshot_match(snap, init)


def test_profile_nonfinite_or_shape_mismatch_is_visible():
    assert not tool.profile_metrics(np.array([1., np.nan]), np.ones(2))['finite']
    assert tool.profile_metrics(np.zeros(2), np.zeros(2))['relative_linf_to_second'] == 0
    with pytest.raises(ValueError, match='shapes'):
        tool.profile_metrics(np.ones(2), np.ones(3))


def test_tampered_or_external_artifacts_rejected(tmp_path):
    f = tmp_path/'array.bin'; f.write_bytes(b'original')
    expected = {'array.bin': tool.digest(f)}; tool.verify_hashes(tmp_path, expected)
    f.write_bytes(b'changed')
    with pytest.raises(ValueError, match='Artifact changed'):
        tool.verify_hashes(tmp_path, expected)
    with pytest.raises(ValueError, match='escaped'):
        tool.verify_hashes(tmp_path, {'../outside.bin': 'no hash'})


def test_temporal_budget_exhaustion_is_not_false_status_mismatch():
    assessment = {'source_state': 'INITIALSTEPNOTCONVERGED', 'point_converged': False,
                  'native_converged': False, 'native_converged_after_output': False}
    assert tool.status_consistency(assessment, True)['consistent']
    assessment['source_state'] = 'INITIALSTEPCONVERGED'
    assert not tool.status_consistency(assessment, True)['consistent']


def test_output_mutated_native_flag_precludes_consistency_claim():
    assessment = {'source_state': 'INITIALSTEPCONVERGED', 'point_converged': True,
                  'native_converged': True, 'native_converged_after_output': False}
    assert not tool.status_consistency(assessment, True)['consistent']
    assessment['native_converged_after_output'] = True
    assert tool.status_consistency(assessment, True)['consistent']
