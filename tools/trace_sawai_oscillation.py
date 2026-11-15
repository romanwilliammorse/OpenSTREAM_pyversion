"""Observe the unchanged Sawai point cycle; never evaluate extra closures.

Full selected-node stage/point observations reuse the matched-replay observer.
Additional actual closure returns and secant trials are confined to the frozen
late-cycle window. A separate gzip JSONL stream keeps this evidence compact.
"""
from __future__ import annotations

import argparse
import gzip
import inspect
import json
from pathlib import Path
import shutil
import sys
import time
import warnings

import numpy as np

from replay_matched_diagnostics import (
    ROOT, IterationTrace, FourFieldSolver, load_sawai, load_wurtz,
    construct_inputs, run_specs, collect_curves, validate_sources,
    portable_json, source_hashes, save_multifield, check_frozen,
    compare_npz, digest, trace_json, write_json,
)
from openstream.annular import AnnularField

METHODS = {
    'MTOT', 'MEVAP', 'MENT', 'MDEP', 'MTURB', 'MWAVE', 'MBASE',
    'FTOT', 'FWALL', 'FWAVE', 'FWAVEMASS', 'FBASEVAPOR', 'FDEP',
    'FVAPOR', 'FBUOY', 'FGRAV', 'FBASE', 'FBASEMASS', 'FDRAG',
    'FSHEAR', 'THICK', 'AMPLITUDE', 'WIDTH', 'BETA', 'BETAP', 'ETA',
    'EPSILON', 'EQTHICK', 'ENTNUM', 'OKAWAMENT', 'CONC', 'KENH',
    'DELTAFREQ', 'EQFREQUENCY', 'EQSTROUHAL', 'SPACING', 'SHAPEFACTOR',
    'UEQUIL', 'USLIP', '_secant', 'CW', 'CV', 'DRAGCOEF', 'REV',
}


class CycleTrace(IterationTrace):
    def __init__(self, solver, nodes, directory, window):
        super().__init__(solver, nodes, directory)
        self.window = window
        self.deep = None
        self.deep_count = 0
        self.secant_code = AnnularField._secant.__code__
        lines, first = inspect.getsourcelines(AnnularField._secant)
        found = [first+k for k, line in enumerate(lines)
                 if line.strip().startswith('if error < tolerance:')]
        if len(found) != 1:
            raise ValueError(f'Ambiguous secant residual anchor: {found}')
        self.secant_line = found[0]

    def in_window(self):
        if not self.selected():
            return False
        local = self.active.f_locals
        return (float(local['film'].TIME) == self.window['time_s']
                and int(local['j']) in self.window['nodes_zero_based']
                and self.window['iteration_min'] <= int(local['iteration'])
                <= self.window['iteration_max'])

    def __enter__(self):
        if sys.gettrace() is not None:
            raise RuntimeError('An existing Python tracer is active; do not replace it')
        self.deep = gzip.open(self.directory/'closure_trace.jsonl.gz', 'xt', encoding='utf-8')
        try:
            return super().__enter__()
        except BaseException:
            self.deep.close()
            raise

    def __exit__(self, *args):
        try:
            super().__exit__(*args)
        finally:
            self.deep.close()
        write_json(self.directory/'deep_trace_schema.json', {
            'schema': 'openstream-sawai-closure-trace-v1',
            'window': self.window, 'methods': sorted(METHODS),
            'records': self.deep_count,
            'secant_anchor': self.secant_line,
            'stage_semantics': 'secant_trial occurs after f2 and error evaluation, before strict tolerance test; closure_return is the actual function return.',
            'state_semantics': 'Stored base/wave/drop primary arrays at event time; no derived getter is evaluated by this observer.',
            'call_context': 'method is defining function; receiver_class identifies actual self; callers are nearest-first up to the outer advance.',
            'units': {'W': 'kg/s', 'U': 'm/s', 'H': 'J/kg', 'F': 'Hz',
                      'mass_exchange': 'kg/(m^2 s)', 'force': 'N/m^2',
                      'thickness_width_amplitude_spacing': 'm',
                      'CONC': 'kg/m^3', 'DELTAFREQ': 'Hz/m',
                      'secant_f0_f1_f2_error': 'N/m^2'},
            'mixed_return': 'Base.MWAVE with return_net=True returns (blended directional exchange, unblended net source); both kg/(m^2 s).',
            'matlab_equivalence': 'not established',
        })

    def dispatch(self, frame, event, arg):
        if (event == 'call' and self.in_window()
                and frame.f_code.co_name in METHODS
                and 'src/openstream/' in frame.f_code.co_filename.replace('\\', '/')):
            frame.f_trace_lines = frame.f_code is self.secant_code
            return self.deep_observe
        return super().dispatch(frame, event, arg)

    def deep_observe(self, frame, event, arg):
        if not self.in_window():
            return self.deep_observe
        if event != 'return' and not (event == 'line' and frame.f_code is self.secant_code
                                      and frame.f_lineno == self.secant_line):
            return self.deep_observe
        callers = []
        parent = frame.f_back
        while parent is not None:
            callers.append({'method': parent.f_code.co_qualname, 'line': parent.f_lineno,
                            'receiver_class': type(parent.f_locals['self']).__name__
                            if 'self' in parent.f_locals else None})
            if parent is self.active:
                break
            parent = parent.f_back
        data = {**self.identity(self.active.f_locals), **self.state(self.active.f_locals),
                'event_index': self.deep_count, 'stage': 'closure_return' if event == 'return' else 'secant_trial',
                'method': frame.f_code.co_qualname,
                'receiver_class': type(frame.f_locals['self']).__name__ if 'self' in frame.f_locals else None,
                'source_file': Path(frame.f_code.co_filename).name,
                'source_line': frame.f_lineno, 'outer_source_line': self.active.f_lineno,
                'callers': callers, 'locals': self.numeric_locals(frame.f_locals)}
        if event == 'return':
            data['return_value'] = arg
        self.deep.write(json.dumps(trace_json(data), separators=(',', ':'), allow_nan=False)+'\n')
        self.deep_count += 1
        # Retain the inherited coarse closure records for the independent
        # arithmetic auditor, without another evaluation of the closure.
        if event == 'return' and frame.f_code.co_name in {'MTOT','FTOT','DELTAFREQ','UEQUIL','USLIP','_secant'}:
            self.closure_return(frame, event, arg)
        return self.deep_observe


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT/'examples/sawai_oscillation_diagnostic.json')
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/verification/sawai-oscillation-01/deep-trace')
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    frozen = json.loads((ROOT/'examples/matched_diagnostic_replay.json').read_text())
    case = next(c for c in frozen['cases'] if c['run_id'] == manifest['run_id'])
    check_frozen(case)
    for path, sha in manifest['corrected_reference_sha256'].items():
        if digest(ROOT/path) != sha:
            raise ValueError(f'Corrected reference changed: {path}')
    source_before = source_hashes()
    if source_before != manifest['native_source_sha256']:
        raise ValueError('Source changed after diagnostic registration')
    campaign_path = ROOT/'examples/lecorre_reproduction.json'
    campaign = json.loads(campaign_path.read_text())
    validate_sources(campaign, campaign_path)
    specs = {f"{s['case_id']}-n{s['cells']}-{s['numerics']}": s for s in run_specs(campaign)}
    datasets = {'sawai': load_sawai(ROOT/'database'), 'wurtz': load_wurtz(ROOT/'database')}
    inputs = construct_inputs(campaign, specs[manifest['run_id']], datasets)
    reference = ROOT/manifest['corrected_reference_directory']
    effective = portable_json(inputs.for_solver('FourField').to_dict())
    if effective != json.loads((reference/'effective_inputs.json').read_text()):
        raise ValueError('Inputs differ from corrected reference')
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(args.manifest, args.output/'frozen_manifest.json')
    shutil.copy2(__file__, args.output/'executed_trace.py')
    write_json(args.output/'effective_inputs.json', effective)
    started = time.perf_counter()
    print('Sawai 1: constructing unchanged precursor, then observing existing operations', flush=True)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        solver = FourFieldSolver(inputs)
        with CycleTrace(solver, manifest['stage_nodes_zero_based'], args.output, manifest['deep_window']):
            solver.solve(progress=lambda r: print(f"t={r['time_s']:g}s; point={r['point_converged']}; maxiter={r['max_iterations']}", flush=True))
        curves, units, onset = collect_curves(solver, 'FourField')
        np.savez_compressed(args.output/'comparison_profiles.npz', **curves)
        save_multifield(solver, args.output/'numerical')
    comparisons = [compare_npz(reference/path, args.output/path) for path in manifest['numeric_files']]
    check_frozen(case)
    for path, sha in manifest['corrected_reference_sha256'].items():
        if digest(ROOT/path) != sha:
            raise ValueError(f'Corrected reference changed during replay: {path}')
    if source_hashes() != source_before:
        raise ValueError('Numerical source changed during tracing')
    result = {
        'schema': 'openstream-sawai-oscillation-assessment-v1',
        'manifest_sha256': digest(args.manifest), 'run_id': manifest['run_id'],
        'source_state': solver.STATE.name, 'native_converged': bool(solver.converged),
        'elapsed_seconds': time.perf_counter()-started, 'onset': onset,
        'warnings': sorted(set(str(w.message) for w in caught)),
        'numeric_arrays_compared': sum(len(c['arrays']) for c in comparisons),
        'observer_exact_numeric_equality': all(c['passed'] for c in comparisons),
        'comparisons': comparisons, 'native_source_sha256': source_before,
        'source_and_original_evidence_unchanged': True,
        'matlab_equivalence': 'not_run',
        'artifact_sha256': {str(p.relative_to(args.output)).replace('\\','/'): digest(p)
                            for p in args.output.rglob('*') if p.is_file()},
    }
    write_json(args.output/'assessment.json', result)
    print(f"Exact numeric equality={result['observer_exact_numeric_equality']}; arrays={result['numeric_arrays_compared']}; native converged={solver.converged}", flush=True)
    if not result['observer_exact_numeric_equality']:
        raise RuntimeError('Trace changed results or reference differs; do not infer read-only invariance')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
