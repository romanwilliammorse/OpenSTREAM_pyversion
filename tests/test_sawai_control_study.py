"""Guard registered controls, immutable evidence and detached-state diagnostics."""
from __future__ import annotations

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sawai_control_study_tool', ROOT/'tools/run_sawai_control_study.py')
tool = importlib.util.module_from_spec(spec)
original_path = sys.path[:]
try:
    sys.path.insert(0, str(ROOT/'tools'))
    spec.loader.exec_module(tool)
finally:
    sys.path[:] = original_path


def inputs():
    value = tool.InputSet.official_sample()
    value.model.RELAXTW = .2
    return value


def test_only_registered_options_change_and_original_inputs_are_retained():
    before = inputs()
    expected = tool.portable_json(before.for_solver('FourField').to_dict())
    candidate, effective = tool.apply_registered_options(before, {'RELAXWW': .1, 'MAXITER': 250}, expected)
    wanted = deepcopy(expected)
    wanted['options'].update(RELAXWW=.1, MAXITER=250)
    assert effective == wanted
    assert tool.portable_json(before.for_solver('FourField').to_dict()) == expected
    assert candidate.options is not before.options


@pytest.mark.parametrize('change', [{'ERRORWF': .1}, {'RELAXTW': .1}, {'POSFILM': False}])
def test_unregistered_equation_or_tolerance_changes_are_rejected(change):
    before = inputs()
    expected = tool.portable_json(before.for_solver('FourField').to_dict())
    with pytest.raises(ValueError, match='Unapproved option changes'):
        tool.apply_registered_options(before, change, expected)


def test_source_uint8_iteration_limit_is_not_silently_extended():
    before = inputs()
    expected = tool.portable_json(before.for_solver('FourField').to_dict())
    with pytest.raises(ValueError):
        tool.apply_registered_options(before, {'MAXITER': 400}, expected)


def test_registered_reference_identity_is_checked_before_changes():
    before = inputs()
    expected = tool.portable_json(before.for_solver('FourField').to_dict())
    expected['geometry']['LENGTH'] *= 2
    with pytest.raises(ValueError, match='baseline inputs differ'):
        tool.apply_registered_options(before, {'MAXITER': 250}, expected)


def test_shared_provenance_can_be_reused_but_never_replaced(tmp_path):
    path = tmp_path/'frozen.json'
    tool.write_once_same(path, b'frozen\r\n')
    tool.write_once_same(path, b'frozen\r\n')
    with pytest.raises(ValueError, match='provenance differs'):
        tool.write_once_same(path, b'changed\n')
    assert path.read_bytes() == b'frozen\r\n'
    assert list(tmp_path.iterdir()) == [path]


def test_graph_fingerprint_detects_cache_and_alias_changes_without_getters():
    class Holder:
        def __init__(self):
            self.array = np.array([1., 2.])
            self.cache = {'x': np.array([3.])}
            self.shared = self.cache
        @property
        def forbidden(self):
            raise RuntimeError('A property must not be read')
    value = Holder()
    original = tool.graph_fingerprint(value)
    assert tool.graph_fingerprint(deepcopy(value)) == original
    value.cache['x'][0] = 4
    assert tool.graph_fingerprint(value) != original
    value.cache['x'][0] = 3
    value.shared = deepcopy(value.cache)
    assert tool.graph_fingerprint(value) != original


def test_graph_fingerprint_tracks_array_object_aliases():
    array = np.array([1., 2.])
    value = SimpleNamespace(first=array, second=array)
    original = tool.graph_fingerprint(value)
    assert tool.graph_fingerprint(deepcopy(value)) == original
    value.second = array.copy()
    assert tool.graph_fingerprint(value) != original


def test_executable_and_helper_provenance_rejects_drift(tmp_path, monkeypatch):
    directory = tmp_path/'tools'
    directory.mkdir()
    runner = directory/'runner.py'
    runner.write_bytes(b'runner\n')
    output = tmp_path/'run'
    output.mkdir()
    (output/'executed_runner.py').write_bytes(b'runner\n')
    for name in ('replay_matched_diagnostics.py', 'run_lecorre_reproduction.py'):
        (directory/name).write_bytes(b'helper\r\n')
    monkeypatch.setattr(tool, 'ROOT', tmp_path)
    monkeypatch.setattr(tool, '__file__', str(runner))
    monkeypatch.setattr(tool.subprocess, 'check_output', lambda *a, **kw: b'helper\n')
    assert len(tool.execution_sources(output, 'registered')['helpers']) == 2
    runner.write_bytes(b'changed\n')
    with pytest.raises(ValueError, match='Shared executed runner differs'):
        tool.execution_sources(output, 'registered')
    runner.write_bytes(b'runner\n')
    (directory/'run_lecorre_reproduction.py').write_bytes(b'changed helper\n')
    with pytest.raises(ValueError, match='Imported helper differs'):
        tool.execution_sources(output, 'registered')


def test_point_criteria_are_strict_and_inlet_is_not_a_solved_point(tmp_path):
    def field(error):
        return SimpleNamespace(ITR={'N': np.array([0, 2, 100]),
                                    'DWL': np.array([[0.], [0.], [error]]),
                                    'DU': np.zeros((3, 1)), 'DF': np.zeros((3, 1))})
    base, wave, drop = field(0), field(.0001), field(0)
    solver = SimpleNamespace(Z=np.array([0., .1, .2]), filmInit=[SimpleNamespace(base=base, wave=wave, TIME=8.)],
                             dropInit=[drop], inputSet=SimpleNamespace(options=SimpleNamespace(ERRORWF=.0001, ERRORUF=.01, ERRORFW=.1, ERRORUD=.01)))
    result = tool.point_summary(solver, tmp_path/'point.csv')
    assert result['failed_nodes_zero_based'] == [2]
    assert result['evaluated_nodes'] == 2
    assert result['criteria_maxima']['dWLw']['value'] == .0001


def test_case_failure_is_retained_without_erasing_existing_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(tool, 'check_registered', lambda *a: None)
    monkeypatch.setattr(tool, 'source_hashes', lambda: {'x': 'hash'})
    monkeypatch.setattr(tool.subprocess, 'check_output', lambda *a, **kw: 'registered-commit')
    monkeypatch.setattr(tool, 'validate_sources', lambda *a: None)
    monkeypatch.setattr(tool, 'run_specs', lambda *a: iter([]))
    manifest = {'original_run_id': 'absent', 'native_source_sha256': {'x': 'hash'}}
    monkeypatch.setattr(tool, 'ROOT', tmp_path)
    (tmp_path/'examples').mkdir()
    (tmp_path/'examples/lecorre_reproduction.json').write_text('{}')
    manifest_file = tmp_path/'manifest.json'
    manifest_file.write_text('{}')
    case = {'case_id': 'failure', 'option_overrides': {'MAXITER': 250}}
    result = tool.run_case(manifest, manifest_file, case, tmp_path/'runs')
    path = tmp_path/'runs/failure/assessment.json'
    assert result['execution'] == 'failed'
    assert json.loads(path.read_text())['execution'] == 'failed'
    preserved = path.read_bytes()
    with pytest.raises(FileExistsError):
        tool.run_case(manifest, manifest_file, case, tmp_path/'runs')
    assert path.read_bytes() == preserved
