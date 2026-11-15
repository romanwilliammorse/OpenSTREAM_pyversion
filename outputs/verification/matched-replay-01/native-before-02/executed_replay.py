"""Read-only line tracing of the two frozen diagnostic replay cases.

No solver source or state is changed. Traces observe existing locals/arrays;
property methods are never re-evaluated by the observer. Original numeric
arrays are compared exactly, separately from unavailable MATLAB references.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import inspect
import json
from pathlib import Path
import shutil
import sys
import time
import warnings

import numpy as np

from openstream import FourFieldSolver, TwoFluidSolver
from openstream.database import load_sawai, load_wurtz
from openstream.output import portable_json, source_hashes
from openstream.multifield_output import save_multifield
from run_lecorre_reproduction import construct_inputs, run_specs, collect_curves, validate_sources

ROOT = Path(__file__).resolve().parents[1]
POINT_NAMES = {
    'FourField': ['dWLb', 'dUb', 'dWLw', 'dUw', 'dFw', 'dUd'],
    'TwoFluid': ['dWl', 'dWv', 'dUl', 'dUv', 'dHl', 'dHv'],
}
POINT_UNITS = {
    'FourField': ['kg/(s m)', 'm/s', 'kg/(s m)', 'm/s', 'Hz', 'm/s'],
    'TwoFluid': ['kg/s', 'kg/s', 'm/s', 'm/s', 'J/kg', 'J/kg'],
}
THRESHOLDS = {
    'FourField': ['ERRORWF', 'ERRORUF', 'ERRORWF', 'ERRORUF', 'ERRORFW', 'ERRORUD'],
    'TwoFluid': ['ERRORW', 'ERRORW', 'ERRORU', 'ERRORU', 'ERRORH', 'ERRORH'],
}
STAGES = {
    'FourField': {
        'base_mass_proposal': 'base.W[j] = (1-o.RELAXWB)',
        'base_mass_applied': 'ww_new = uw*',
        'wave_mass_proposal': 'wave.W[j] = (1-o.RELAXWW)',
        'before_clipping': 'if m.POSFILM:',
        'after_clipping': 'drop.W[j] = mix.liquid.W(j)',
        'after_droplet_mass': 'if m.WAVEFREQUENCY==',
        'after_frequency': 'if m.MOMENTBASE==',
        'after_base_momentum': 'if m.MOMENTWAVE==',
        'after_wave_momentum': 'if m.MOMENTDROP==',
        'point': 'if all(np.all(error<threshold)',
    },
    'TwoFluid': {
        'liquid_mass_proposal': 'l.W[j] = (1-o.RELAXWL)',
        'vapor_mass_proposal': 'v.W[j] = (1-o.RELAXWV)',
        'liquid_momentum_proposal': 'l.U[j] = (1-o.RELAXUL)',
        'vapor_momentum_proposal': 'v.U[j] = (1-o.RELAXUV)',
        'liquid_enthalpy_proposal': 'l.H[j] = (1-o.RELAXHL)',
        'vapor_enthalpy_proposal': 'v.H[j] = (1-o.RELAXHV)',
        'point': 'if np.all(delta<[o.ERRORW',
    },
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    Path(path).write_text(json.dumps(trace_json(data), indent=2, allow_nan=False)+'\n', encoding='utf-8')


def trace_json(value):
    if isinstance(value, np.ndarray):
        return trace_json(value.tolist())
    if isinstance(value, np.generic):
        return trace_json(value.item())
    if isinstance(value, dict):
        return {key: trace_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [trace_json(item) for item in value]
    return portable_json(value)


def check_frozen(case):
    for path, expected in case['original_file_sha256'].items():
        if digest(ROOT/path) != expected:
            raise ValueError(f'Frozen evidence changed: {path}')


def compare_npz(original, replay):
    with np.load(original, allow_pickle=False) as a, np.load(replay, allow_pickle=False) as b:
        if set(a.files) != set(b.files):
            raise ValueError(f'Array names differ: {original}')
        rows = []
        for key in a.files:
            x, y = a[key], b[key]
            equal = x.shape == y.shape and np.array_equal(x, y, equal_nan=True)
            row = {'key': key, 'shape': list(x.shape), 'exact_equal': bool(equal)}
            if x.shape == y.shape:
                finite = np.isfinite(x) & np.isfinite(y)
                row['max_abs_difference'] = float(np.max(np.abs(x[finite]-y[finite]))) if np.any(finite) else None
            rows.append(row)
        return {'original': str(original), 'replay': str(replay), 'passed': all(r['exact_equal'] for r in rows), 'arrays': rows}


def scalar(value):
    a = np.asarray(value)
    if a.size != 1:
        raise ValueError(f'Trace requires single-wall scalar, found {a.shape}')
    return float(a.ravel()[0])


class IterationTrace:
    """Observe actual updates with CPython tracing, without monkeypatching methods."""

    def __init__(self, solver, nodes, directory):
        self.solver, self.framework = solver, solver.framework
        self.nodes, self.directory = set(nodes), Path(directory)
        self.code = solver._advance.__func__.__code__
        lines, first = inspect.getsourcelines(solver._advance)
        self.lines = {}
        for stage, prefix in STAGES[self.framework].items():
            found = [first+i for i, line in enumerate(lines) if line.strip().startswith(prefix)]
            if len(found) != 1:
                raise ValueError(f'Ambiguous/missing source trace anchor: {stage}: {found}')
            self.lines[found[0]] = stage
        self.active = None
        self.rows, self.temporal, self.counts = [], [], {}
        self.raw = None

    def __enter__(self):
        if sys.gettrace() is not None:
            raise RuntimeError('An existing Python tracer is active; do not replace it')
        self.raw = (self.directory/'update_trace.jsonl').open('x', encoding='utf-8', newline='\n')
        sys.settrace(self.dispatch)
        return self

    def __exit__(self, *args):
        sys.settrace(None)
        self.raw.close()
        if self.rows:
            with (self.directory/'point_trace.csv').open('x', encoding='utf-8', newline='') as out:
                writer = csv.DictWriter(out, fieldnames=list(self.rows[0]))
                writer.writeheader(); writer.writerows(self.rows)
        write_json(self.directory/'temporal_trace.json', self.temporal)
        units = dict(zip(POINT_NAMES[self.framework], POINT_UNITS[self.framework]))
        for name, unit in list(units.items()):
            units['threshold_'+name] = unit
        units.update(time_s='s', dt_s='s', z_m='m', node_zero_based='1', node_one_based='1', iteration='1')
        for field in ('base', 'wave', 'drop', 'liquid', 'vapor'):
            for key, unit in [('W','kg/s'), ('U','m/s'), ('H','J/kg'), ('F','Hz')]:
                units[field+'_'+key] = unit
        write_json(self.directory/'trace_schema.json', {
            'schema': 'openstream-matched-native-trace-v1', 'framework': self.framework,
            'source_file': inspect.getsourcefile(self.solver._advance),
            'source_sha256': digest(inspect.getsourcefile(self.solver._advance)),
            'line_anchors': self.lines, 'point_units': units,
            'trace_nodes_zero_based': sorted(self.nodes), 'event_counts': self.counts,
            'observation': 'Line events occur BEFORE the anchored statement; point event is after residual calculation. No property recomputation.',
            'extra_locals': 'Snapshot of available numeric locals, including potentially stale temporaries; use stage and source line. These are not all independent outputs.',
            'closure_returns': 'Actual MTOT/FTOT/DELTAFREQ/UEQUIL/USLIP returns at selected nodes; units follow the corresponding source method and source audit, not a uniform force-unit assumption.',
            'matlab_equivalence': 'not established by this native trace',
        })

    def selected(self):
        return self.active is not None and self.active.f_locals.get('j') in self.nodes and 'iteration' in self.active.f_locals

    def dispatch(self, frame, event, arg):
        if event != 'call':
            return None
        if frame.f_code is self.code:
            self.active = frame
            return self.observe
        if self.selected() and frame.f_code.co_name in {'MTOT','FTOT','DELTAFREQ','UEQUIL','USLIP','_secant'} and 'src/openstream/' in frame.f_code.co_filename.replace('\\','/'):
            frame.f_trace_lines = False
            return self.closure_return
        return None

    def emit(self, data):
        self.counts[data['stage']] = self.counts.get(data['stage'], 0)+1
        self.raw.write(json.dumps(trace_json(data), separators=(',', ':'), allow_nan=False)+'\n')

    def identity(self, local):
        field = local['film'] if self.framework == 'FourField' else local['l']
        j = int(local['j'])
        return {'time_s': float(field.TIME), 'dt_s': float(field.DT), 'node_zero_based': j,
                'node_one_based': j+1, 'z_m': float(self.solver.Z[j]), 'iteration': int(local['iteration'])}

    def state(self, local):
        names = ('base','wave','drop') if self.framework == 'FourField' else ('l','v')
        labels = names if self.framework == 'FourField' else ('liquid','vapor')
        j = local['j']; state = {}
        for name, label in zip(names, labels):
            field = local[name]
            for key in ('W','U','H'):
                state[label+'_'+key] = scalar(getattr(field, key)[j])
            if label == 'wave':
                state['wave_F'] = scalar(field.FREQUENCY[j])
        return state

    @staticmethod
    def numeric_locals(local):
        result = {}
        for key, value in local.items():
            if isinstance(value, (int,float,bool,np.number)):
                result[key] = value
            elif isinstance(value, np.ndarray) and value.size <= 16:
                result[key] = value.copy()
        return result

    def closure_return(self, frame, event, arg):
        if event == 'return' and self.selected():
            self.emit({**self.identity(self.active.f_locals), 'stage': 'closure_return',
                'method': frame.f_code.co_qualname, 'source_line': frame.f_code.co_firstlineno,
                'return_value': arg, 'locals': self.numeric_locals(frame.f_locals)})
        return self.closure_return

    def observe(self, frame, event, arg):
        if event == 'return':
            if arg is not None:
                field = frame.f_locals['film'] if self.framework == 'FourField' else frame.f_locals['l']
                okay, changes = arg
                self.temporal.append({'time_s': float(field.TIME), 'point_converged': bool(okay),
                    **{'time_'+key: scalar(value) for key,value in zip(POINT_NAMES[self.framework],changes)}})
            self.active = None
        elif event == 'line' and frame.f_lineno in self.lines and self.selected():
            local = frame.f_locals; stage = self.lines[frame.f_lineno]
            record = {**self.identity(local), **self.state(local), 'stage': stage, 'source_line': frame.f_lineno}
            self.emit({**record, 'locals': self.numeric_locals(local)})
            if stage == 'point':
                errors = local['errors'] if self.framework == 'FourField' else local['delta']
                row = {key:value for key,value in record.items() if key not in ('stage','source_line')}
                for key, value, threshold in zip(POINT_NAMES[self.framework], errors, THRESHOLDS[self.framework]):
                    row[key] = scalar(value); row['threshold_'+key] = float(getattr(self.solver.inputSet.options,threshold))
                row['all_point_criteria_pass'] = all(row[key] < row['threshold_'+key] for key in POINT_NAMES[self.framework])
                self.rows.append(row)
        return self.observe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT/'examples/matched_diagnostic_replay.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    for case in manifest['cases']:
        check_frozen(case)
    source_before = source_hashes()
    campaign_path = ROOT/'examples/lecorre_reproduction.json'
    campaign = json.loads(campaign_path.read_text())
    validate_sources(campaign, campaign_path)
    specs = {f"{s['case_id']}-n{s['cells']}-{s['numerics']}": s for s in run_specs(campaign)}
    datasets = {'sawai': load_sawai(ROOT/'database'), 'wurtz': load_wurtz(ROOT/'database')}
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.manifest, args.output/'frozen_manifest.json')
    shutil.copy2(__file__, args.output/'executed_replay.py')
    report = {'schema': 'openstream-matched-native-replay-v1', 'manifest_sha256': digest(args.manifest),
              'native_source_sha256_before': source_before, 'matlab_equivalence': 'not_run', 'cases': []}
    for case in manifest['cases']:
        started = time.perf_counter(); name = case['run_id']
        directory = args.output/name; directory.mkdir()
        inputs = construct_inputs(campaign, specs[name], datasets)
        expected = json.loads((ROOT/case['original_directory']/'effective_inputs.json').read_text())
        effective = portable_json(inputs.for_solver(case['framework']).to_dict())
        if effective != expected:
            raise ValueError(f'Effective inputs differ from frozen case: {name}')
        write_json(directory/'effective_inputs.json', effective)
        print(f'{name}: constructing identical precursor and tracing selected nodes', flush=True)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            solver = {'FourField': FourFieldSolver, 'TwoFluid': TwoFluidSolver}[case['framework']](inputs)
            with IterationTrace(solver, case['trace_nodes_zero_based'], directory):
                solver.solve(progress=lambda r: print(f"  t={r['time_s']:g}s point={r['point_converged']} maxiter={r['max_iterations']}", flush=True))
            curves, units, onset = collect_curves(solver, case['framework'])
            np.savez_compressed(directory/'comparison_profiles.npz', **curves)
            save_multifield(solver, directory/'numerical')
        comparisons = []
        original = ROOT/case['original_directory']
        for path in ['comparison_profiles.npz', 'numerical/results.npz', 'numerical/initialization.npz', 'numerical/mixture/results.npz', 'numerical/mixture/initialization.npz']:
            comparisons.append(compare_npz(original/path, directory/path))
        result = {'run_id': name, 'source_state': solver.STATE.name, 'native_converged': bool(solver.converged),
                  'elapsed_seconds': time.perf_counter()-started, 'onset': onset,
                  'warnings': sorted(set(str(w.message) for w in caught)),
                  'native_exact_reproducibility': all(c['passed'] for c in comparisons), 'comparisons': comparisons,
                  'matlab_equivalence': 'not_run; native reproducibility is not a MATLAB comparison'}
        write_json(directory/'replay_assessment.json', result); report['cases'].append(result)
        write_json(args.output/'report.json', report)
        check_frozen(case)
        print(f"{name}: native exact equality={result['native_exact_reproducibility']}; convergence={solver.converged}", flush=True)
        if not result['native_exact_reproducibility']:
            raise RuntimeError('Native replay differs; inspect before continuing to the second case')
    if source_hashes() != source_before:
        raise ValueError('Numerical source changed during tracing')
    for case in manifest['cases']:
        check_frozen(case)
    report['source_and_original_evidence_unchanged'] = True
    report['execution_complete'] = True
    write_json(args.output/'report.json', report)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
