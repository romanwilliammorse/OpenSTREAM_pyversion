"""Execute preregistered numerical-control cases without changing solver physics.

This driver changes only explicitly registered Options values. It preserves
failed attempts and saves source returns evaluated on a detached final state
for independent residual analysis; these are not observed point iterations.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import traceback
import uuid
import warnings

import numpy as np

from openstream import FourFieldSolver
from openstream.inputs import InputSet, Options
from openstream.output import portable_json, source_hashes
from openstream.multifield_output import save_multifield
from openstream.database import load_sawai, load_wurtz
from replay_matched_diagnostics import ROOT, digest, write_json, trace_json, compare_npz, check_frozen
from run_lecorre_reproduction import construct_inputs, run_specs, validate_sources, collect_curves

ALLOWED_OPTIONS = {'RELAXWW', 'RELAXWB', 'MAXITER', 'SSMAXITER'}
NUMERIC_FILES = ['comparison_profiles.npz', 'numerical/results.npz',
                 'numerical/initialization.npz', 'numerical/mixture/results.npz',
                 'numerical/mixture/initialization.npz']
POINT_FIELDS = {'dWLb': ('base', 'DWL', 'ERRORWF', 'kg/(s m)'),
                'dUb': ('base', 'DU', 'ERRORUF', 'm/s'),
                'dWLw': ('wave', 'DWL', 'ERRORWF', 'kg/(s m)'),
                'dUw': ('wave', 'DU', 'ERRORUF', 'm/s'),
                'dFw': ('wave', 'DF', 'ERRORFW', 'Hz'),
                'dUd': ('drop', 'DU', 'ERRORUD', 'm/s')}


def number(value):
    array = np.asarray(value)
    if array.size != 1:
        raise ValueError(f'Single-wall scalar required, got {array.shape}')
    return float(array.reshape(-1)[0])


def write_once_same(path, content):
    """Atomically publish complete shared bytes without replacing any file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with temporary.open('xb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.read_bytes() != content:
                raise ValueError(f'Existing study provenance differs: {path}')
    finally:
        temporary.unlink(missing_ok=True)


def apply_registered_options(inputs, overrides, expected_original):
    if set(overrides)-ALLOWED_OPTIONS:
        raise ValueError(f'Unapproved option changes: {set(overrides)-ALLOWED_OPTIONS}')
    before = portable_json(inputs.for_solver('FourField').to_dict())
    if before != expected_original:
        raise ValueError('Constructed baseline inputs differ from retained reference')
    values = inputs.options.to_dict()
    values.update(overrides)
    candidate = InputSet(inputs.model, Options(values), inputs.geometry, inputs.bc, inputs.source_files)
    effective = portable_json(candidate.for_solver('FourField').to_dict())
    expected = deepcopy(before)
    expected['options'].update(overrides)
    if effective != expected:
        raise ValueError('Effective input change exceeds registered Options overrides')
    if effective['model']['NNODES'] != 100 or effective['model']['RELAXTW'] != .2:
        raise ValueError('The registered physical case must remain 100 cells, tau=0.2 s')
    return candidate, effective


def check_registered(manifest, path):
    """Require committed preregistration and exact source/reference bytes."""
    rel = Path(path).resolve().relative_to(ROOT).as_posix()
    committed = subprocess.check_output(['git', 'show', 'HEAD:'+rel], cwd=ROOT)
    if committed != Path(path).read_bytes():
        raise ValueError('Study manifest must be committed byte-for-byte before execution')
    if source_hashes() != manifest['native_source_sha256']:
        raise ValueError('Native source differs from preregistered study')
    for name, expected in manifest['corrected_reference_sha256'].items():
        if digest(ROOT/name) != expected:
            raise ValueError(f'Corrected reference changed: {name}')
    matched = json.loads((ROOT/'examples/matched_diagnostic_replay.json').read_text())
    for case in matched['cases']:
        check_frozen(case)
    ids = [c['case_id'] for c in manifest['cases']]
    if len(ids) != len(set(ids)):
        raise ValueError('Repeated preregistered case ID')
    for case in manifest['cases']:
        if not case['case_id'] or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-_' for c in case['case_id']):
            raise ValueError('Case ID must be a safe lowercase directory name')
        if set(case['option_overrides'])-ALLOWED_OPTIONS:
            raise ValueError('Manifest includes changes beyond numerical controls')


def graph_fingerprint(root):
    """Read stored numeric data and alias topology without property evaluation.

    Opaque backend/lock internals are excluded. FluidProperties deliberately
    shares its immutable property wrapper during deepcopy; stored properties
    and all reachable arrays, cache dictionaries and scalar values are checked.
    """
    seen, entries = {}, {}
    def visit(value, path):
        if isinstance(value, np.ndarray):
            if id(value) in seen:
                entries[path] = {'alias': seen[id(value)]}
                return
            seen[id(value)] = path
            entries[path] = {'shape': list(value.shape), 'dtype': str(value.dtype),
                             'sha256': hashlib.sha256(value.tobytes(order='C')).hexdigest()}
            return
        if value is None or isinstance(value, (str, bool, int, float, np.number)):
            entries[path] = trace_json(value)
            return
        if id(value) in seen:
            entries[path] = {'alias': seen[id(value)]}
            return
        seen[id(value)] = path
        if isinstance(value, dict):
            for key in sorted(value, key=repr):
                visit(value[key], path+'['+repr(key)+']')
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                visit(item, f'{path}[{index}]')
        elif hasattr(value, '__dict__'):
            entries[path+'.__class__'] = type(value).__module__+'.'+type(value).__qualname__
            for name, item in sorted(vars(value).items()):
                visit(item, path+'.'+name)
        else:
            entries[path] = {'opaque_type': type(value).__module__+'.'+type(value).__qualname__}
    visit(root, 'solver')
    raw = json.dumps(entries, sort_keys=True, allow_nan=False).encode('utf-8')
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'entries': entries,
            'array_count': sum(isinstance(v, dict) and 'dtype' in v for v in entries.values())}


def execution_sources(output, registration_commit):
    """Bind executable observer helpers without permitting source drift."""
    current, executed = Path(__file__).resolve(), Path(output)/'executed_runner.py'
    if current.read_bytes() != executed.read_bytes():
        raise ValueError('Shared executed runner differs from current executable source')
    result = {'runner_sha256': digest(current), 'executed_runner_sha256': digest(executed), 'helpers': {}}
    for name in ('tools/replay_matched_diagnostics.py', 'tools/run_lecorre_reproduction.py'):
        content = (ROOT/name).read_bytes()
        committed = subprocess.check_output(['git', 'show', registration_commit+':'+name], cwd=ROOT)
        if content.replace(b'\r\n', b'\n') != committed.replace(b'\r\n', b'\n'):
            raise ValueError(f'Imported helper differs from preregistration: {name}')
        result['helpers'][name] = {'sha256': digest(ROOT/name),
                                  'registration_equal_after_line_ending_normalization': True}
    return result


def primary_arrays(solver):
    arrays = {'Z': solver.Z.copy()}
    for group in ('film', 'filmInit', 'drop', 'dropInit'):
        for index, state in enumerate(getattr(solver, group, [])):
            fields = {'': state}
            if hasattr(state, 'base'):
                fields.update({'.base': state.base, '.wave': state.wave})
            for suffix, field in fields.items():
                for name in ('W', 'U', 'H', 'FREQUENCY'):
                    if hasattr(field, name):
                        arrays[f'{group}[{index}]{suffix}.{name}'] = np.asarray(getattr(field, name)).copy()
    for group in ('mixture', 'mixtureInit'):
        for index, state in enumerate(getattr(solver.mixSolver, group, [])):
            for name in ('W', 'P', 'H'):
                arrays[f'{group}[{index}].{name}'] = np.asarray(getattr(state, name)).copy()
    return arrays


def arrays_equal(a, b):
    return (a.keys() == b.keys() and all(a[k].shape == b[k].shape and a[k].dtype == b[k].dtype
            and np.array_equal(a[k], b[k], equal_nan=True) for k in a))


def point_summary(solver, path):
    film, drop = solver.filmInit[-1], solver.dropInit[-1]
    fields = {'base': film.base, 'wave': film.wave, 'drop': drop}
    rows = []
    for node, z in enumerate(solver.Z):
        row = {'node_zero_based': node, 'node_one_based': node+1, 'z_m': float(z),
               'time_s': float(film.TIME), 'evaluated_point': node > 0,
               'iterations': int(number(film.wave.ITR['N'][node]))}
        for label, (field, key, option, unit) in POINT_FIELDS.items():
            row[label] = number(fields[field].ITR[key][node])
            row['threshold_'+label] = float(getattr(solver.inputSet.options, option))
        row['all_point_criteria_pass'] = (all(row[k] < row['threshold_'+k] for k in POINT_FIELDS)
                                         if node > 0 else None)
        rows.append(row)
    with Path(path).open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)
    return {'time_s': float(film.TIME), 'nodes': len(rows), 'evaluated_nodes': len(rows)-1,
            'failed_nodes_zero_based': [r['node_zero_based'] for r in rows if r['all_point_criteria_pass'] is False],
            'criteria_maxima': {k: {'value': max(r[k] for r in rows[1:]),
                                  'threshold': rows[0]['threshold_'+k], 'unit': v[3]}
                                for k, v in POINT_FIELDS.items()},
            'units': {k: v[3] for k, v in POINT_FIELDS.items()}}


def frozen_state_diagnostics(solver, directory):
    before = graph_fingerprint(solver)
    detached = deepcopy(solver)
    original_after_copy = graph_fingerprint(solver)
    if before != original_after_copy:
        raise ValueError('Deepcopy mutated original stored solver state')
    current, previous = detached.filmInit[-1], detached.filmInit[-2]
    drop, old_drop = detached.dropInit[-1], detached.dropInit[-2]
    mix = detached.mixSolver.mixture[0]
    if not (current.base.film is current and current.wave.film is current
            and current.base.mix is mix and current.wave.mix is mix and current.mix is drop.mix):
        raise ValueError('Detached graph does not preserve source precursor handles')
    arrays = {'Z': detached.Z.copy()}
    for prefix, film, drops in [('current', current, drop), ('previous', previous, old_drop)]:
        for field, state in [('base', film.base), ('wave', film.wave), ('drop', drops)]:
            for name in ('W', 'U', 'H', 'FREQUENCY'):
                if hasattr(state, name):
                    arrays[f'{prefix}.{field}.{name}'] = np.asarray(getattr(state, name)).reshape(-1).copy()
    clone_primary_before = primary_arrays(detached)
    sources = {key: [] for key in ('base.MTOT', 'wave.MTOT', 'base.FTOT', 'wave.FTOT',
                                  'base.THICK', 'wave.THICK', 'wave.DELTAFREQ',
                                  'sweep.liquid.U', 'sweep.vapor.U', 'sweep.liquid.W',
                                  'sweep.vapor.W', 'sweep.AFFNC', 'aggregate.AFFNC',
                                  'base.AFFNC', 'wave.AFFNC', 'drop.AFFNC')}
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        for node in range(detached.NZ):
            values = {'base.MTOT': current.base.MTOT(drop, node), 'wave.MTOT': current.wave.MTOT(drop, node),
                      'base.FTOT': current.base.FTOT(drop, node), 'wave.FTOT': current.wave.FTOT(drop, node),
                      'base.THICK': current.base.THICK(node), 'wave.THICK': current.wave.THICK(node),
                      'wave.DELTAFREQ': current.wave.DELTAFREQ(node),
                      'sweep.liquid.U': mix.liquid.U(node), 'sweep.vapor.U': mix.vapor.U(node),
                      'sweep.liquid.W': mix.liquid.W(node), 'sweep.vapor.W': mix.vapor.W(node),
                      'sweep.AFFNC': mix.AFFNC(node), 'aggregate.AFFNC': current.mix.AFFNC(node),
                      'base.AFFNC': current.base.mix.AFFNC(node), 'wave.AFFNC': current.wave.mix.AFFNC(node),
                      'drop.AFFNC': drop.mix.AFFNC(node)}
            for name, value in values.items():
                sources[name].append(number(value))
    arrays.update({name: np.array(values) for name, values in sources.items()})
    after = graph_fingerprint(solver)
    if before != after or not arrays_equal(clone_primary_before, primary_arrays(detached)):
        raise ValueError('Diagnostic evaluation mutated original graph or detached primary state')
    np.savez_compressed(directory/'frozen_state.npz', **arrays)
    metadata = {'schema': 'openstream-sawai-frozen-state-diagnostics-v1',
        'interpretation': 'Recomputed source returns at saved final initialization states on a deepcopy of the entire solver. These are not observed point-iteration proposals or new solver convergence gates.',
        'constants': {'PERIM_m': number(detached.inputSet.geometry.PERIM), 'DZ_m': float(detached.DZ),
                      'DT_s': float(current.DT), 'RHOF_kg_m3': float(current.fluid.RHOF),
                      'time_s': float(current.TIME), 'onset_node_zero_based': int(mix.OAFIDX())},
        'units': {'W': 'kg/s', 'U': 'm/s', 'H': 'J/kg', 'FREQUENCY': 'Hz', 'Z': 'm',
                  'MTOT': 'kg/(m^2 s)', 'FTOT': 'Pa', 'THICK': 'm', 'DELTAFREQ': 'Hz/m', 'AFFNC': '1'},
        'original_graph_before': {k: v for k, v in before.items() if k != 'entries'},
        'original_graph_after': {k: v for k, v in after.items() if k != 'entries'},
        'original_stored_arrays_caches_scalars_unchanged': True,
        'detached_primary_arrays_unchanged': True,
        'precursor_handle_graph_preserved': True,
        'opaque_backend_note': 'The immutable FluidProperties wrapper deliberately shares its locked CoolProp backend; opaque backend/lock internals are excluded from the stored-state fingerprint.',
        'warnings': sorted(set(str(w.message) for w in caught)),
        'data_sha256': digest(directory/'frozen_state.npz')}
    write_json(directory/'frozen_state.json', metadata)
    return metadata


def run_case(manifest, manifest_path, case, output):
    check_registered(manifest, manifest_path)
    directory = Path(output)/case['case_id']
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory/'registered_case.json', case)
    started, solver = time.perf_counter(), None
    result = {'schema': 'openstream-sawai-control-case-v1', 'case_id': case['case_id'],
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'preregistration_commit': subprocess.check_output(
                  ['git', 'log', '-1', '--format=%H', '--', Path(manifest_path).resolve().relative_to(ROOT).as_posix()],
                  cwd=ROOT, text=True).strip(),
              'registered_options': case['option_overrides'], 'role': case.get('role', 'numerical_control'),
              'manifest_sha256': digest(manifest_path), 'execution': 'started', 'native_converged': None,
              'matlab_equivalence': 'not_run', 'experimental_validation': 'not_established'}
    write_json(directory/'assessment.json', result)
    caught = []
    try:
        result['executed_sources'] = execution_sources(output, result['preregistration_commit'])
        campaign_path = ROOT/'examples/lecorre_reproduction.json'
        campaign = json.loads(campaign_path.read_text()); validate_sources(campaign, campaign_path)
        spec = next(s for s in run_specs(campaign)
                    if f"{s['case_id']}-n{s['cells']}-{s['numerics']}" == manifest['original_run_id'])
        baseline = construct_inputs(campaign, spec, {'sawai': load_sawai(ROOT/'database'), 'wurtz': load_wurtz(ROOT/'database')})
        reference = ROOT/manifest['corrected_reference_directory']
        expected = json.loads((reference/'effective_inputs.json').read_text())
        inputs, effective = apply_registered_options(baseline, case['option_overrides'], expected)
        result['is_unchanged_reference_control'] = effective == expected
        write_json(directory/'effective_inputs.json', effective)
        print(f"{case['case_id']}: constructing source-equivalent precursor and executing registered controls", flush=True)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            solver = FourFieldSolver(inputs)
            solver.solve(progress=lambda r: print(f"{case['case_id']}: t={r['time_s']:g}s; point={r['point_converged']}; maxiter={r['max_iterations']}", flush=True))
            result.update(source_state=solver.STATE.name, native_converged=bool(solver.converged),
                          point_converged=bool(solver.point_converged),
                          frequency_temporally_converged=bool(solver.wave_frequency_converged),
                          transient_converged=bool(solver.transient_converged),
                          history=deepcopy(solver.history), onset=deepcopy(solver.onset_diagnostics),
                          last_init_time_s=float(solver.filmInit[-1].TIME),
                          final_point=point_summary(solver, directory/'final_point_criteria.csv'))
            primary_before = primary_arrays(solver)
            curves, units, onset = collect_curves(solver, 'FourField')
            np.savez_compressed(directory/'comparison_profiles.npz', **curves)
            write_json(directory/'comparison_units.json', units)
            save_multifield(solver, directory/'numerical')
            if not arrays_equal(primary_before, primary_arrays(solver)):
                raise ValueError('Output generation changed primary numerical arrays')
        metadata = json.loads((directory/'numerical/metadata.json').read_text())
        result['physical_diagnostics'] = metadata['physical_diagnostics']
        result['output_primary_arrays_unchanged'] = True
        result['native_converged_after_output'] = bool(solver.converged)
        result['comparisons_to_corrected_reference'] = [compare_npz(reference/name, directory/name) for name in NUMERIC_FILES]
        comparisons = result['comparisons_to_corrected_reference']
        result['precursor_exact'] = all(c['passed'] for c in comparisons[-2:])
        result['all_215_reference_arrays_exact'] = all(c['passed'] for c in comparisons)
        result['baseline_array_exact'] = result['all_215_reference_arrays_exact']
        result['numeric_arrays_compared'] = sum(len(c['arrays']) for c in comparisons)
        result['frozen_state_diagnostics'] = frozen_state_diagnostics(solver, directory)
        if result['is_unchanged_reference_control'] and not result['all_215_reference_arrays_exact']:
            raise ValueError('Unchanged baseline does not reproduce every corrected reference array')
        result['execution'] = 'completed'
    except Exception as exc:
        result.update(execution='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        if solver is not None:
            try:
                np.savez_compressed(directory/'partial_primary_state.npz', **primary_arrays(solver))
                result['partial_state_note'] = 'Stored state retained after exception; may include unadvanced allocated states and is not a completed solution.'
            except Exception as secondary:
                result['partial_state_error'] = f'{type(secondary).__name__}: {secondary}'
    result['warnings'] = sorted(set(str(w.message) for w in caught))
    result['elapsed_seconds_including_precursor_output'] = time.perf_counter()-started
    result['runtime_s'] = result['elapsed_seconds_including_precursor_output']
    result['native_source_sha256'] = source_hashes()
    result['source_unchanged'] = result['native_source_sha256'] == manifest['native_source_sha256']
    try:
        check_registered(manifest, manifest_path)
        if 'executed_sources' in result and execution_sources(output, result['preregistration_commit']) != result['executed_sources']:
            raise ValueError('Runner or imported helper source changed during this attempt')
        result['source_and_reference_evidence_unchanged'] = True
    except Exception as exc:
        result.update(execution='failed', integrity_error=f'{type(exc).__name__}: {exc}', source_and_reference_evidence_unchanged=False)
    result['artifact_sha256'] = {p.relative_to(directory).as_posix(): digest(p)
                                for p in directory.rglob('*') if p.is_file() and p.name != 'assessment.json'}
    write_json(directory/'assessment.json', result)
    print(f"{case['case_id']}: {result['execution']}; native_converged={result['native_converged']}; {result['elapsed_seconds_including_precursor_output']:.1f}s", flush=True)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=ROOT/'examples/sawai_control_study.json')
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/verification/sawai-control-study-01')
    parser.add_argument('--case', help='Execute one registered case ID; omit for all registered cases in order')
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text())
    check_registered(manifest, args.manifest)
    cases = [c for c in manifest['cases'] if args.case is None or c['case_id'] == args.case]
    if not cases:
        raise ValueError(f'Unknown registered case: {args.case}')
    args.output.mkdir(parents=True, exist_ok=True)
    write_once_same(args.output/'frozen_manifest.json', args.manifest.read_bytes())
    write_once_same(args.output/'executed_runner.py', Path(__file__).read_bytes())
    outcomes = [run_case(manifest, args.manifest, case, args.output) for case in cases]
    return 0 if all(r['execution'] == 'completed' for r in outcomes) else 2


if __name__ == '__main__':
    raise SystemExit(main())
