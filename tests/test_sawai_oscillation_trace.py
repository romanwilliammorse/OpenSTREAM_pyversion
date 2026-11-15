"""Focused observer guards; numerical invariance is checked by full replay."""
from __future__ import annotations

import importlib.util
import gzip
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('sawai_cycle_trace_tool', ROOT/'tools/trace_sawai_oscillation.py')
tool = importlib.util.module_from_spec(SPEC)
oldpath = sys.path[:]
try:
    sys.path.insert(0, str(ROOT/'tools'))
    SPEC.loader.exec_module(tool)
finally:
    sys.path[:] = oldpath


def observer(tmp_path):
    solver = object.__new__(tool.FourFieldSolver)
    return tool.CycleTrace(solver, range(20,29), tmp_path,
                           {'time_s':8.0,'nodes_zero_based':[24,25,26],
                            'iteration_min':90,'iteration_max':100})


@pytest.mark.parametrize('time,node,iteration,expected', [
    (8,24,90,True),(8,26,100,True),(7,24,95,False),
    (8,23,95,False),(8,24,89,False),(8,24,101,False)])
def test_deep_window_is_exact_and_bounded(tmp_path,time,node,iteration,expected):
    trace = observer(tmp_path)
    trace.active = SimpleNamespace(f_locals={'film':SimpleNamespace(TIME=time),
                                             'j':node,'iteration':iteration})
    assert trace.in_window() is expected


def test_trace_guard_does_not_create_or_replace_active_tracer(tmp_path):
    trace = observer(tmp_path)
    original = sys.gettrace()
    def existing(frame,event,arg):
        return existing
    try:
        sys.settrace(existing)
        with pytest.raises(RuntimeError, match='existing Python tracer'):
            trace.__enter__()
        assert sys.gettrace() is existing
        assert not (tmp_path/'closure_trace.jsonl.gz').exists()
    finally:
        sys.settrace(original)


def test_manifest_fixes_current_case_and_complete_numeric_reference():
    manifest = json.loads((ROOT/'examples/sawai_oscillation_diagnostic.json').read_text())
    assert manifest['settings'] == {'RELAXTW':0.2,'NNODES':100}
    assert len(manifest['numeric_files']) == 5
    assert len(manifest['native_source_sha256']) == 25
    assert all((ROOT/path).is_file() and tool.digest(ROOT/path)==sha
               for path,sha in manifest['corrected_reference_sha256'].items())
    assert {'CONC','MDEP','MWAVE','MBASE','FTOT','_secant'} <= tool.METHODS


def test_current_numerical_source_bytes_match_registered_replay():
    """Keep the traced numerical bytes frozen while the results GUI evolves.

    The historical manifest and replay command retain their strict full-source
    guard. Only these explicitly named presentation files are outside this
    current-release comparison; new or removed numerical files still fail.
    """
    manifest = json.loads((ROOT/'examples/sawai_oscillation_diagnostic.json').read_text())
    current = tool.source_hashes()
    frozen = manifest['native_source_sha256']
    assert current.keys() - frozen.keys() == {'gui_exports.py'}
    assert not frozen.keys() - current.keys()
    assert {name: digest for name, digest in current.items()
            if name not in {'gui.py', 'gui_exports.py'}} == {
                name: digest for name, digest in frozen.items() if name != 'gui.py'}


def provenance_fixture(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location('sawai_trace_provenance_tool', ROOT/'tools/audit_sawai_trace_provenance.py')
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    monkeypatch.setattr(audit, 'source_hashes', lambda: {'module.py':'frozen'})
    monkeypatch.setattr(audit.subprocess, 'check_output', lambda *a,**kw: b'helper\n')
    directory = tmp_path/'trace'
    directory.mkdir()
    for name in ('tools','examples','reference'):
        (tmp_path/name).mkdir()
    for name in ('replay_matched_diagnostics.py','run_lecorre_reproduction.py'):
        (tmp_path/'tools'/name).write_bytes(b'helper\r\n')
    (tmp_path/'tools/trace_sawai_oscillation.py').write_bytes(b'executed')
    (directory/'executed_trace.py').write_bytes(b'executed')
    for name in ('update_trace.jsonl','point_trace.csv','temporal_trace.json'):
        (directory/name).write_bytes(b'same')
        (tmp_path/'reference'/name).write_bytes(b'same')
    manifest = {'native_source_sha256':{'module.py':'frozen'},
                'baseline_commit':'frozen-commit','corrected_reference_directory':'reference',
                'deep_window':{'time_s':8.0,'nodes_zero_based':[24],
                               'iteration_min':90,'iteration_max':90}}
    for path in (directory/'frozen_manifest.json',tmp_path/'examples/sawai_oscillation_diagnostic.json'):
        path.write_text(json.dumps(manifest))
    names = ('Base.MTOT','Wave.MTOT','Base.UEQUIL','Base._secant','Wave.FTOT',
             'Drop.CONC','Drop.MDEP','Base.MWAVE','Wave.MBASE')
    rows = [{'time_s':8.0,'node_zero_based':24,'iteration':90,'event_index':k,
             'stage':'closure_return','receiver_class':name.split('.')[0],'method':name}
            for k,name in enumerate(names)]
    rows.append({'time_s':8.0,'node_zero_based':24,'iteration':90,
                 'event_index':len(rows),'stage':'secant_trial'})
    with gzip.open(directory/'closure_trace.jsonl.gz','wt') as stream:
        for row in rows:
            stream.write(json.dumps(row)+'\n')
    (directory/'deep_trace_schema.json').write_text(json.dumps({'records':len(rows)}))
    assessment = {'observer_exact_numeric_equality':True,
                  'native_source_sha256':manifest['native_source_sha256'],
                  'manifest_sha256':tool.digest(directory/'frozen_manifest.json'),
                  'artifact_sha256':{p.name:tool.digest(p) for p in directory.iterdir()}}
    (directory/'assessment.json').write_text(json.dumps(assessment))
    return audit, directory


def test_provenance_binds_complete_window_and_sources(tmp_path, monkeypatch):
    audit, directory = provenance_fixture(tmp_path,monkeypatch)
    result = audit.audit(directory)
    assert result['all_required_points_and_closures_observed']
    assert result['expected_points']==result['observed_points']==1


def test_provenance_rejects_artifact_tampering(tmp_path, monkeypatch):
    audit, directory = provenance_fixture(tmp_path,monkeypatch)
    (directory/'point_trace.csv').write_bytes(b'changed')
    with pytest.raises(ValueError,match='Artifact differs'):
        audit.audit(directory)


def test_provenance_rejects_missing_window_point(tmp_path, monkeypatch):
    audit, directory = provenance_fixture(tmp_path,monkeypatch)
    with gzip.open(directory/'closure_trace.jsonl.gz','wt') as stream:
        stream.write('')
    assessment = json.loads((directory/'assessment.json').read_text())
    assessment['artifact_sha256']['closure_trace.jsonl.gz']=tool.digest(directory/'closure_trace.jsonl.gz')
    (directory/'assessment.json').write_text(json.dumps(assessment))
    with pytest.raises(ValueError,match='Missing points'):
        audit.audit(directory)
