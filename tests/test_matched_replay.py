"""Trace integrity and frozen-array comparison; no numerical case execution."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'matched_replay_test_tool', ROOT/'tools/replay_matched_diagnostics.py')
replay = importlib.util.module_from_spec(SPEC)
_original_path = sys.path[:]
try:
    sys.path.insert(0, str(ROOT/'tools'))
    SPEC.loader.exec_module(replay)
finally:
    sys.path[:] = _original_path


def empty_solver():
    # The trace constructor only inspects the bound method and framework.
    # Do not initialize a precursor or execute any numerical calculation.
    return object.__new__(replay.TwoFluidSolver)


def save_pair(tmp_path, original, changed):
    a, b = tmp_path/'original.npz', tmp_path/'replay.npz'
    np.savez(a, field=original)
    np.savez(b, field=changed)
    return replay.compare_npz(a, b)


def reject_nonstandard_constant(value):
    raise AssertionError(f'Nonstandard JSON constant {value}')


def test_trace_json_preserves_nested_numpy_shapes_and_nonfinite_sentinels(tmp_path):
    values = np.array([[np.nan, np.inf], [-np.inf, 2.5]])
    before = values.copy()
    source = {'array': values, 'zero_dim': np.array(np.nan),
              'nested': (np.int64(3), {'flag': np.bool_(True), 'x': np.float32(0.5)})}
    path = tmp_path/'trace.json'
    replay.write_json(path, source)
    decoded = json.loads(path.read_text(), parse_constant=reject_nonstandard_constant)
    assert decoded == {'array': [['NaN', 'Infinity'], ['-Infinity', 2.5]],
                       'zero_dim': 'NaN', 'nested': [3, {'flag': True, 'x': 0.5}]}
    np.testing.assert_array_equal(values, before)
    assert source['array'] is values and isinstance(source['nested'], tuple)


def test_numeric_local_snapshot_is_read_only_and_does_not_evaluate_objects():
    class Unevaluated:
        def __float__(self):
            raise AssertionError('Observer must not evaluate solver objects')

    values = np.array([1.0, np.nan])
    snapshot = replay.IterationTrace.numeric_locals(
        {'small': values, 'large': np.ones(17), 'object': Unevaluated(), 'iteration': 3})
    assert set(snapshot) == {'small', 'iteration'}
    assert not np.shares_memory(snapshot['small'], values)
    values[0] = 9
    assert snapshot['small'][0] == 1
    assert np.isnan(snapshot['small'][1])


def test_exact_numeric_comparison_accepts_matching_nonfinite_locations(tmp_path):
    values = np.array([[1.0, np.nan], [np.inf, -np.inf]])
    result = save_pair(tmp_path, values, values.copy())
    assert result['passed']
    assert result['arrays'][0]['dtype_equal']
    assert result['arrays'][0]['max_abs_difference'] == 0


def test_exact_comparison_does_not_invent_error_for_no_finite_pairs(tmp_path):
    result = save_pair(tmp_path, np.array([np.nan, np.inf]), np.array([np.nan, np.inf]))
    assert result['passed']
    assert result['arrays'][0]['max_abs_difference'] is None


@pytest.mark.parametrize('changed', [
    np.array([np.nextafter(1.0, np.inf), np.nan, np.inf]),
    np.array([1.0, 0.0, np.inf]),
    np.array([np.nan, 1.0, np.inf]),
    np.array([1.0, np.nan, -np.inf]),
    np.array([[1.0, np.nan, np.inf]]),
])
def test_exact_comparison_detects_small_value_nan_sign_and_shape_errors(tmp_path, changed):
    result = save_pair(tmp_path, np.array([1.0, np.nan, np.inf]), changed)
    assert not result['passed']
    assert not result['arrays'][0]['exact_equal']


def test_exact_comparison_requires_same_storage_dtype(tmp_path):
    result = save_pair(tmp_path, np.array([1, 2], dtype=np.float64),
                       np.array([1, 2], dtype=np.float32))
    assert not result['passed']
    assert not result['arrays'][0]['dtype_equal']
    assert result['arrays'][0]['dtype'] == 'float64'
    assert result['arrays'][0]['replay_dtype'] == 'float32'
    assert result['arrays'][0]['max_abs_difference'] == 0


def test_comparison_contract_is_numeric_equality_not_bitwise_signed_zero(tmp_path):
    result = save_pair(tmp_path, np.array([0.0, -0.0]), np.array([-0.0, 0.0]))
    assert result['passed']


def test_comparison_rejects_changed_array_inventory(tmp_path):
    a, b = tmp_path/'original.npz', tmp_path/'replay.npz'
    np.savez(a, field=np.array([1.0]))
    np.savez(b, field=np.array([1.0]), unexpected=np.array([2.0]))
    with pytest.raises(ValueError, match='Array names differ'):
        replay.compare_npz(a, b)


def test_comparison_never_unpickles_object_arrays(tmp_path):
    with pytest.raises(ValueError, match='allow_pickle=False'):
        save_pair(tmp_path, np.array([{'x': 1}], dtype=object),
                  np.array([{'x': 1}], dtype=object))


def test_trace_refuses_active_existing_tracer_without_replacing_it(monkeypatch, tmp_path):
    current = lambda *args: None
    changes = []
    monkeypatch.setattr(replay.sys, 'gettrace', lambda: current)
    monkeypatch.setattr(replay.sys, 'settrace', changes.append)
    observer = replay.IterationTrace(empty_solver(), [1], tmp_path)
    with pytest.raises(RuntimeError, match='existing Python tracer'):
        observer.__enter__()
    assert changes == []
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('lines', [
    ['    unrelated = 1\n'],
    ['    l.W[j] = (1-o.RELAXWL)*wli\n',
     '    l.W[j] = (1-o.RELAXWL)*other\n'],
])
def test_trace_refuses_missing_or_ambiguous_source_anchor(monkeypatch, tmp_path, lines):
    monkeypatch.setattr(replay.inspect, 'getsourcelines', lambda method: (lines, 100))
    with pytest.raises(ValueError, match='Ambiguous/missing source trace anchor'):
        replay.IterationTrace(empty_solver(), [1], tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_trace_refuses_existing_output_before_enabling_tracing(monkeypatch, tmp_path):
    existing = tmp_path/'update_trace.jsonl'
    existing.write_text('immutable evidence\n')
    changes = []
    monkeypatch.setattr(replay.sys, 'gettrace', lambda: None)
    monkeypatch.setattr(replay.sys, 'settrace', changes.append)
    observer = replay.IterationTrace(empty_solver(), [1], tmp_path)
    with pytest.raises(FileExistsError):
        observer.__enter__()
    assert changes == []
    assert existing.read_text() == 'immutable evidence\n'


def test_trace_cleans_up_and_writes_schema_when_observed_code_raises(monkeypatch, tmp_path):
    changes = []
    monkeypatch.setattr(replay.sys, 'gettrace', lambda: None)
    monkeypatch.setattr(replay.sys, 'settrace', changes.append)
    observer = replay.IterationTrace(empty_solver(), [1], tmp_path)
    with pytest.raises(RuntimeError, match='observed failure'):
        with observer:
            raise RuntimeError('observed failure')
    assert changes == [observer.dispatch, None]
    assert observer.raw.closed
    assert json.loads((tmp_path/'temporal_trace.json').read_text()) == []
    schema = json.loads((tmp_path/'trace_schema.json').read_text())
    assert schema['trace_nodes_zero_based'] == [1]
    assert schema['point_units']['dHl'] == 'J/kg'
    assert schema['source_sha256'] == replay.digest(ROOT/'src/openstream/twofluid.py')


def test_scalar_refuses_silent_multiwall_reduction():
    assert replay.scalar(np.array([[3.0]])) == 3.0
    with pytest.raises(ValueError, match='single-wall scalar'):
        replay.scalar(np.array([3.0, 4.0]))
