"""Independent saved-array accounting for the preregistered Sawai control study.

No solver imports or executions. Native convergence, a reference-scaled
mass-defect screen, signed-flow bounds and experimental evidence stay separate.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import hashlib
import itertools
import json
from pathlib import Path
import subprocess

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
POINT_FIELDS = {
    'base_mass': ('film.base.ITR.DWL', 'ERRORWF', 'kg/(s m)'),
    'base_velocity': ('film.base.ITR.DU', 'ERRORUF', 'm/s'),
    'wave_mass': ('film.wave.ITR.DWL', 'ERRORWF', 'kg/(s m)'),
    'wave_velocity': ('film.wave.ITR.DU', 'ERRORUF', 'm/s'),
    'wave_frequency': ('film.wave.ITR.DF', 'ERRORFW', 'Hz'),
    'drop_velocity': ('drop.ITR.DU', 'ERRORUD', 'm/s'),
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def scalar(value):
    a = np.asarray(value)
    if a.size != 1:
        raise ValueError(f'Expected scalar; found shape {a.shape}')
    return float(a.ravel()[0])


def verify_hashes(directory, mapping):
    directory = Path(directory).resolve()
    for name, expected in mapping.items():
        path = (directory/name).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or digest(path) != expected:
            raise ValueError(f'Artifact changed or escaped its directory: {name}')


def mass_defect(w, u, old_w, old_u, source, perimeter, dz, dt, error_wf):
    """Same-state backward-Euler residual R, unrelaxed D, baseline-scaled q.

    R and D are kg/s; q=0.5*abs(D)/(P*ERRORWF) is dimensionless. Node zero
    is an inlet boundary, excluded with NaN rather than reported as a zero.
    """
    vectors = [np.asarray(a, dtype=float) for a in (w, u, old_w, old_u, source)]
    if any(a.ndim != 1 for a in vectors) or len({a.shape for a in vectors}) != 1 or len(vectors[0]) < 2:
        raise ValueError('Mass-defect inputs must be equal one-dimensional node vectors')
    if not all(np.isfinite(x) and x > 0 for x in (perimeter, dz, dt, error_wf)):
        raise ValueError('Perimeter, mesh spacing, step and fixed tolerance must be positive finite SI values')
    w, u, old_w, old_u, source = vectors
    residual, defect, ratio, steady = [np.full(w.shape, np.nan) for _ in range(4)]
    with np.errstate(divide='ignore', invalid='ignore'):
        steady[1:] = w[1:]-w[:-1]-perimeter*source[1:]*dz
        residual[1:] = w[1:]-w[:-1]+dz/dt*(w[1:]/u[1:]-old_w[1:]/old_u[1:])-perimeter*source[1:]*dz
        defect[1:] = -u[1:]/(u[1:]+dz/dt)*residual[1:]
        ratio[1:] = .5*np.abs(defect[1:])/perimeter/error_wf
    return {'residual_kg_s': residual, 'unrelaxed_defect_kg_s': defect,
            'reference_scaled_ratio': ratio, 'steady_residual_kg_s': steady}


def extrema(values, mask, z):
    values, mask, z = np.asarray(values), np.asarray(mask, dtype=bool), np.asarray(z)
    if values.shape != mask.shape or values.shape != z.shape or values.ndim != 1:
        raise ValueError('Values, mask and coordinates must have identical vector shapes')
    nodes = np.flatnonzero(mask)
    finite = nodes[np.isfinite(values[nodes])]
    worst = int(finite[np.argmax(np.abs(values[finite]))]) if len(finite) else None
    return {'selected_nodes': int(len(nodes)), 'excluded_nodes': int(len(values)-len(nodes)),
            'nonfinite_nodes': [int(i) for i in nodes if not np.isfinite(values[i])],
            'max_abs_finite': float(abs(values[worst])) if worst is not None else None,
            'signed_value_at_max': float(values[worst]) if worst is not None else None,
            'node_zero_based_at_max': worst, 'z_m_at_max': float(z[worst]) if worst is not None else None}


def screen_ratio(values, mask, z):
    result = extrema(values, mask, z)
    result['strictly_below_one'] = bool(result['selected_nodes'] and not result['nonfinite_nodes']
                                      and result['max_abs_finite'] < 1)
    return result


def exact_snapshot_match(snapshot, initialization):
    if not np.array_equal(snapshot['Z'], initialization['Z']):
        raise ValueError('Snapshot and saved initialization meshes differ')
    if len(initialization['TIME']) < 2:
        raise ValueError('Final and previous initialization states are required')
    checked = 0
    for prefix, state_index in (('current', -1), ('previous', -2)):
        for field in ('base', 'wave', 'drop'):
            for quantity in ('W', 'U', 'H') + (('FREQUENCY',) if field == 'wave' else ()):
                snapshot_key = f'{prefix}.{field}.{quantity}'
                stored_key = f'{"film." if field != "drop" else ""}{field}.{quantity}'
                actual = snapshot[snapshot_key]
                expected = initialization[stored_key][state_index].reshape(-1)
                if actual.dtype != expected.dtype or not np.array_equal(actual, expected, equal_nan=True):
                    raise ValueError(f'Frozen diagnostic state differs from saved solver arrays: {snapshot_key}')
                checked += 1
    return checked


def profile_metrics(a, b):
    a, b = np.asarray(a), np.asarray(b)
    if a.shape != b.shape:
        raise ValueError('Profile shapes differ')
    finite = np.isfinite(a) & np.isfinite(b)
    if not np.all(finite):
        return {'finite': False, 'max_absolute': None, 'relative_linf_to_second': None,
                'nonfinite_pairs': int(np.sum(~finite))}
    difference = float(np.max(np.abs(a-b)))
    denominator = float(np.max(np.abs(b)))
    return {'finite': True, 'max_absolute': difference,
            'relative_linf_to_second': difference/denominator if denominator else (0.0 if difference == 0 else None),
            'second_profile_linf': denominator, 'exact_equal': bool(np.array_equal(a, b))}


def point_metrics(initialization, options):
    z = initialization['Z']; mask = np.arange(len(z)) >= 1
    result = {}
    for label, (name, threshold_name, unit) in POINT_FIELDS.items():
        values = initialization[name][-1].reshape(-1)
        threshold = float(options[threshold_name])
        result[label] = {'unit': unit, 'threshold': threshold,
                         **extrema(values, mask, z), 'normalized': screen_ratio(values/threshold, mask, z)}
    return result


def signed_bounds(snapshot, z, fixed_mask):
    masks = {'all_nodes': np.ones(len(z), dtype=bool), 'fixed_annular_mask': fixed_mask}
    result = {}
    keys = [f'current.{field}.{quantity}' for field in ('base', 'wave', 'drop') for quantity in ('W', 'U')]
    keys += ['current.wave.FREQUENCY']
    for key in keys:
        result[key] = {}
        values = snapshot[key]
        for label, mask in masks.items():
            finite = np.isfinite(values) & mask
            negative = np.flatnonzero(mask & (values < 0))
            result[key][label] = {'minimum_finite': float(np.min(values[finite])) if np.any(finite) else None,
                'negative_node_indices': negative.tolist(), 'negative_node_z_m': z[negative].tolist(),
                'nonfinite_node_indices': np.flatnonzero(mask & ~np.isfinite(values)).tolist()}
    return result


def save_json(path, value):
    def portable(x):
        if isinstance(x, np.generic): return portable(x.item())
        if isinstance(x, np.ndarray): return portable(x.tolist())
        if isinstance(x, dict): return {k: portable(v) for k, v in x.items()}
        if isinstance(x, (tuple, list)): return [portable(v) for v in x]
        if isinstance(x, float) and not np.isfinite(x): return None
        return x
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(portable(value), stream, indent=2, allow_nan=False); stream.write('\n')


def compare_npz_files(left, right):
    with np.load(left, allow_pickle=False) as a, np.load(right, allow_pickle=False) as b:
        if set(a.files) != set(b.files):
            return {'exact': False, 'arrays': 0, 'different': ['array inventory']}
        different = [name for name in a.files if a[name].shape != b[name].shape or a[name].dtype != b[name].dtype
                     or not np.array_equal(a[name], b[name], equal_nan=True)]
        return {'exact': not different, 'arrays': len(a.files), 'different': different,
                'reference_sha256': digest(left), 'candidate_sha256': digest(right)}


def mask_applicability(snapshot, mask):
    invalid = np.zeros(mask.shape, dtype=bool)
    for field in ('base', 'wave'):
        for key in ('W', 'U'):
            values = snapshot[f'current.{field}.{key}']
            invalid |= mask & (~np.isfinite(values) | (values <= 0))
    return {'nonempty': bool(np.any(mask)), 'inapplicable_nodes': np.flatnonzero(invalid).tolist(),
            'applicable': bool(np.any(mask) and not np.any(invalid))}


def verify_execution_sources(study, assessment, manifest_path):
    sources = assessment['executed_sources']
    if digest(study/'executed_runner.py') != sources['executed_runner_sha256'] or sources['runner_sha256'] != sources['executed_runner_sha256']:
        raise ValueError('Executed runner binding differs')
    registration = assessment['preregistration_commit']
    committed_manifest = subprocess.check_output(['git', 'show', registration+':examples/sawai_control_study.json'], cwd=ROOT)
    if committed_manifest != manifest_path.read_bytes():
        raise ValueError('Frozen manifest differs from recorded preregistration commit')
    if set(sources['helpers']) != {'tools/replay_matched_diagnostics.py', 'tools/run_lecorre_reproduction.py'}:
        raise ValueError('Imported helper inventory differs')
    for name, binding in sources['helpers'].items():
        current = ROOT/name
        if digest(current) != binding['sha256']:
            raise ValueError(f'Imported helper hash differs: {name}')
        committed = subprocess.check_output(['git', 'show', registration+':'+name], cwd=ROOT)
        if current.read_bytes().replace(b'\r\n', b'\n') != committed.replace(b'\r\n', b'\n'):
            raise ValueError(f'Imported helper differs from registered version: {name}')


def status_consistency(assessment, final_point_arrays_pass):
    temporal_stopped = assessment['source_state'] in ('INITIALSTEPCONVERGED', 'SOLVEDCONVERGED')
    point_consistent = (not temporal_stopped or bool(assessment['point_converged']) == final_point_arrays_pass)
    native_consistent = assessment['native_converged_after_output'] == assessment['native_converged']
    claimed_pass_has_point_evidence = not assessment['native_converged'] or final_point_arrays_pass
    return {'temporal_stop_point_flag_matches_arrays': bool(point_consistent),
            'native_flag_unchanged_by_output': bool(native_consistent),
            'claimed_native_pass_has_point_evidence': bool(claimed_pass_has_point_evidence),
            'consistent': bool(point_consistent and native_consistent and claimed_pass_has_point_evidence),
            'note': 'At temporal-budget exhaustion, the retained source point flag may remain false even if final point arrays pass. Output-induced status changes preclude a qualified evidence claim; original flags are not rewritten.'}


def analyze_case(directory, spec, manifest, reference_inputs, fixed_mask, reference_z):
    assessment_path = directory/'assessment.json'
    assessment = read_json(assessment_path)
    if assessment['case_id'] != spec['case_id']:
        raise ValueError('Case identity differs from registered manifest')
    if assessment['execution'] not in ('completed', 'failed'):
        raise ValueError(f'Attempt is unfinished: {spec["case_id"]}')
    verify_hashes(directory, assessment['artifact_sha256'])
    if 'executed_sources' in assessment:
        verify_execution_sources(directory.parent, assessment, directory.parent/'frozen_manifest.json')
    elif assessment['execution'] == 'completed':
        raise ValueError('Completed attempt has no executable-source binding')
    row = {'case_id': spec['case_id'], 'registered_options': spec['option_overrides'],
           'execution': assessment['execution'], 'native_converged': assessment.get('native_converged'),
           'qualified_numerical_candidate': False,
           'runtime_s': assessment.get('runtime_s', assessment.get('elapsed_seconds_including_precursor_output')),
           'warnings': assessment.get('warnings', []), 'assessment_sha256': digest(assessment_path)}
    if assessment['execution'] != 'completed':
        row.update(error=assessment.get('error', assessment.get('integrity_error')),
                   qualification_failures=['execution did not complete'])
        return row, {}, None
    inputs = read_json(directory/'effective_inputs.json')
    expected = deepcopy(reference_inputs)
    expected['options'].update(spec['option_overrides'])
    if inputs != expected:
        raise ValueError(f'Inputs changed outside preregistered controls: {spec["case_id"]}')
    if assessment['native_source_sha256'] != manifest['native_source_sha256'] or not assessment['source_and_reference_evidence_unchanged']:
        raise ValueError('Source/reference integrity was not preserved')
    frozen_meta = read_json(directory/'frozen_state.json')
    if digest(directory/'frozen_state.npz') != frozen_meta['data_sha256']:
        raise ValueError('Frozen source-array hash changed')
    if not all(frozen_meta[key] for key in ('original_stored_arrays_caches_scalars_unchanged',
                                          'detached_primary_arrays_unchanged', 'precursor_handle_graph_preserved')):
        raise ValueError('Diagnostic-state independence was not established')
    with np.load(directory/'frozen_state.npz', allow_pickle=False) as file:
        snapshot = {name: file[name] for name in file.files}
    with np.load(directory/'numerical/initialization.npz', allow_pickle=False) as file:
        init = {name: file[name] for name in file.files}
    if not np.array_equal(snapshot['Z'], reference_z):
        raise ValueError('Candidate mesh differs from frozen case')
    snapshot_checks = exact_snapshot_match(snapshot, init)
    constants = frozen_meta['constants']; z = snapshot['Z']
    perimeter = scalar(inputs['geometry']['PERIM'])
    if constants['PERIM_m'] != perimeter or constants['time_s'] != float(init['TIME'][-1]):
        raise ValueError('Snapshot constants differ from saved state or input')
    if not np.allclose(np.diff(z), constants['DZ_m'], rtol=0, atol=2*np.spacing(float(z[-1]))):
        raise ValueError('Recorded mesh spacing is inconsistent with coordinates')
    if constants['DT_s'] != float(init['TIME'][-1]-init['TIME'][-2]):
        raise ValueError('Recorded step differs from final saved initialization interval')
    comparisons = {name: compare_npz_files(ROOT/manifest['corrected_reference_directory']/name, directory/name)
                   for name in manifest['numeric_files']}
    precursor_exact = all(comparisons[name]['exact'] for name in ('numerical/mixture/results.npz', 'numerical/mixture/initialization.npz'))
    all_reference_exact = all(c['exact'] for c in comparisons.values())
    if spec['case_id'] == 'ww50-it100' and (not all_reference_exact or sum(c['arrays'] for c in comparisons.values()) != 215):
        raise ValueError('Fresh unchanged control does not reproduce all 215 reference arrays')
    all_interior = np.arange(len(z)) >= 1
    actual_mask = all_interior & (np.arange(len(z)) >= constants['onset_node_zero_based'])
    actual_mask &= (snapshot['current.base.W'] > 0) & (snapshot['current.wave.W'] > 0)
    applicability = mask_applicability(snapshot, fixed_mask)
    diagnostics, residual_arrays = {}, {}
    for field in ('base', 'wave'):
        values = mass_defect(snapshot[f'current.{field}.W'], snapshot[f'current.{field}.U'],
            snapshot[f'previous.{field}.W'], snapshot[f'previous.{field}.U'], snapshot[f'{field}.MTOT'],
            perimeter, constants['DZ_m'], constants['DT_s'], inputs['options']['ERRORWF'])
        residual_arrays.update({field+'.'+name: value for name, value in values.items()})
        diagnostics[field] = {}
        for label, mask in (('all_interior', all_interior), ('frozen_reference_mask', fixed_mask), ('actual_case_mask', actual_mask)):
            diagnostics[field][label] = {'reference_scaled_ratio': screen_ratio(values['reference_scaled_ratio'], mask, z),
                'same_state_mass_residual_kg_s': extrema(values['residual_kg_s'], mask, z),
                'steady_mass_residual_kg_s': extrema(values['steady_residual_kg_s'], mask, z)}
    metadata = read_json(directory/'numerical/metadata.json')
    physical = metadata['physical_diagnostics']
    primary_keys = [name for name in init if name.endswith(('.W', '.U', '.H', '.FREQUENCY'))]
    nonfinite_primary = {name: int(np.sum(~np.isfinite(init[name]))) for name in primary_keys}
    point = point_metrics(init, inputs['options'])
    point_pass = all(p['normalized']['strictly_below_one'] for p in point.values())
    consistency = status_consistency(assessment, point_pass)
    conditions = {
        'native_converged': assessment['native_converged'] is True,
        'onset_checks_pass': bool(assessment.get('onset')) and all(item['converged'] for item in assessment['onset']),
        'nested_checks_pass': not physical['nested_closure_failures'],
        'precursor_exact': precursor_exact,
        'finite_primary_states': not any(nonfinite_primary.values()),
        'frozen_reference_mask_applicable': applicability['applicable'],
        'base_fixed_mask_mass_defect': diagnostics['base']['frozen_reference_mask']['reference_scaled_ratio']['strictly_below_one'],
        'wave_fixed_mask_mass_defect': diagnostics['wave']['frozen_reference_mask']['reference_scaled_ratio']['strictly_below_one'],
    }
    row.update(source_state=assessment['source_state'], precursor_exact=precursor_exact,
        all_215_reference_arrays_exact=all_reference_exact, comparisons_to_reference=comparisons,
        qualified_numerical_candidate=all(conditions.values()) and consistency['consistent'], qualification_conditions=conditions,
        qualification_failures=[key for key, value in conditions.items() if not value] + ([] if consistency['consistent'] else ['evidence_status_inconsistent']),
        evidence_status_consistency=consistency,
        last_initialization_time_s=float(init['TIME'][-1]), saved_initialization_states=len(init['TIME']),
        point_metrics=point, final_point_arrays_pass=point_pass,
        mass_defects=diagnostics, frozen_mask_applicability=applicability,
        actual_case_mask_nodes=np.flatnonzero(actual_mask).tolist(), nonfinite_primary_counts=nonfinite_primary,
        signed_bounds=signed_bounds(snapshot, z, fixed_mask), original_physical_diagnostics=physical,
        recomputed_source_warnings=frozen_meta['warnings'], snapshot_primary_arrays_exactly_checked=snapshot_checks,
        native_converged_after_output=assessment.get('native_converged_after_output'),
        force_values_descriptive={field: extrema(snapshot[field+'.FTOT'], all_interior, z) for field in ('base', 'wave')},
        interpretation='Qualified is only the preregistered native numerical-control screen; signed bounds and area diagnostics are retained separately. No MATLAB or experimental validation claim.')
    residual_arrays.update(Z=z, fixed_reference_mask=fixed_mask, actual_case_mask=actual_mask)
    return row, residual_arrays, snapshot


def profile_comparisons(rows, snapshots):
    completed = {r['case_id']: r for r in rows if r['execution'] == 'completed'}
    pairs = []
    for a, b in itertools.combinations(completed, 2):
        ra, rb = completed[a], completed[b]
        same_relax = ra['registered_options']['RELAXWW'] == rb['registered_options']['RELAXWW']
        both_native = ra['native_converged'] and rb['native_converged']
        if not same_relax and not both_native:
            continue
        metrics = {}
        for field in ('base', 'wave', 'drop'):
            for quantity, unit in (('W', 'kg/s'), ('U', 'm/s')):
                key = f'current.{field}.{quantity}'
                metrics[field+'.'+quantity] = {'unit': unit, **profile_metrics(snapshots[a][key], snapshots[b][key])}
        for quantity, unit in (('FREQUENCY', 'Hz'), ('PERIOD', 's')):
            av, bv = snapshots[a]['current.wave.FREQUENCY'], snapshots[b]['current.wave.FREQUENCY']
            if quantity == 'PERIOD':
                av, bv = 1/av, 1/bv
            metrics['wave.'+quantity] = {'unit': unit, **profile_metrics(av, bv)}
        pairs.append({'first': a, 'second': b, 'same_relaxation_budget_comparison': same_relax,
                      'both_native_converged': bool(both_native),
                      'both_qualified_numerical_candidates': bool(ra['qualified_numerical_candidate'] and rb['qualified_numerical_candidate']),
                      'metrics': metrics, 'acceptance_gate': None,
                      'interpretation': 'Descriptive profile sensitivity; iteration tolerances are not an accuracy or experimental-validation tolerance.'})
    return pairs


def plot_study(rows, snapshots, output):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.ticker import NullLocator
    plt.rcParams.update({'font.size': 11})
    palette = {.5: '#0072B2', .25: '#009E73', .1: '#D55E00', .05: '#CC79A7'}
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout='constrained')
    def finite_max(values):
        values = [v for v in values if v is not None and np.isfinite(v)]
        return max(values) if values else np.nan
    for budget in (100, 250):
        selected = sorted([r for r in rows if r['registered_options']['MAXITER'] == budget and r['execution'] == 'completed'],
                          key=lambda r: r['registered_options']['RELAXWW'])
        xs = [r['registered_options']['RELAXWW'] for r in selected]
        data = [[finite_max(p['normalized']['max_abs_finite'] for p in r['point_metrics'].values()) for r in selected],
                [finite_max(r['mass_defects'][f]['frozen_reference_mask']['reference_scaled_ratio']['max_abs_finite'] for f in ('base', 'wave')) for r in selected]]
        for axis, ys in zip(axes[0], data):
            axis.plot(xs, ys, '-' if budget == 250 else '--', color='0.45', linewidth=1)
            for x, y, row in zip(xs, ys, selected):
                axis.plot(x, y, 'o' if budget == 100 else 's', color=palette[x], markerfacecolor=palette[x] if row['native_converged'] else 'white', markersize=7)
            axis.set_xscale('log'); axis.set_xticks([.05, .1, .25, .5], labels=['0.05', '0.1', '0.25', '0.5'])
            axis.xaxis.set_minor_locator(NullLocator())
            axis.set_xlabel('RELAXWW: wave mass-flow relaxation [1]'); axis.grid(alpha=.2)
    axes[0, 0].set_ylabel('Maximum point increment / tolerance [1]')
    axes[0, 1].set_ylabel('Maximum reference-scaled mass-defect ratio [1]')
    for axis in axes[0]:
        axis.set_yscale('log'); axis.axhline(1, color='0.35', linestyle='--', linewidth=1)
    from matplotlib.lines import Line2D
    for row in rows:
        if row['execution'] != 'completed': continue
        a = snapshots[row['case_id']]; option = row['registered_options']; color = palette[option['RELAXWW']]
        style = '-' if option['MAXITER'] == 250 else '--'
        for axis, values in zip(axes[1], (a['current.wave.U'], 1000/a['current.wave.FREQUENCY'])):
            axis.plot(a['Z'], values, color=color, linestyle=style, linewidth=1.3)
    for axis, label in zip(axes[1], ('Wave velocity [m/s]', 'Wave period [ms]')):
        axis.set(xlabel='Axial position [m]', ylabel=label); axis.grid(alpha=.2)
    handles = [Line2D([], [], color=color, label=f'RELAXWW = {relax:g}') for relax, color in palette.items()]
    handles += [Line2D([], [], color='0.25', marker=marker, linestyle=style, label=f'MAXITER = {n}') for n, style, marker in ((100, '--', 'o'), (250, '-', 's'))]
    handles += [Line2D([], [], color='0.25', marker='o', linestyle='None', label='Native convergence'),
                Line2D([], [], color='0.25', marker='o', markerfacecolor='white', linestyle='None', label='Native failure')]
    fig.legend(handles=handles, loc='outside lower center', ncol=4, fontsize=9)
    fig.savefig(output/'control_study.png', dpi=180); plt.close(fig)


def analyze(study, output):
    manifest_path = study/'frozen_manifest.json'; manifest = read_json(manifest_path)
    if manifest != read_json(ROOT/'examples/sawai_control_study.json'):
        raise ValueError('Executed and preregistered manifests differ')
    for name, expected in manifest['corrected_reference_sha256'].items():
        if digest(ROOT/name) != expected:
            raise ValueError(f'Corrected reference changed: {name}')
    for name, expected in manifest['native_source_sha256'].items():
        if digest(ROOT/'src/openstream'/name) != expected:
            raise ValueError(f'Native source changed: {name}')
    reference = ROOT/manifest['corrected_reference_directory']
    reference_inputs = read_json(reference/'effective_inputs.json')
    with np.load(reference/'numerical/initialization.npz', allow_pickle=False) as a:
        z = a['Z']; expected_mask = (np.arange(len(z)) >= 1) & (np.arange(len(z)) >= manifest['frozen_reference_mask']['onset_node_zero_based'])
        expected_mask &= (a['film.base.W'][-1].reshape(-1) > 0) & (a['film.wave.W'][-1].reshape(-1) > 0)
    fixed_mask = np.zeros(len(z), dtype=bool); fixed_mask[manifest['frozen_reference_mask']['nodes_zero_based']] = True
    if not np.array_equal(fixed_mask, expected_mask) or not np.any(fixed_mask):
        raise ValueError('Frozen reference mask is missing or differs from its recorded definition')
    rows, all_arrays, snapshots = [], {}, {}
    for spec in manifest['cases']:
        directory = study/spec['case_id']
        if not (directory/'assessment.json').exists():
            raise ValueError(f'Registered attempt is missing: {spec["case_id"]}')
        if read_json(directory/'assessment.json')['manifest_sha256'] != digest(manifest_path):
            raise ValueError('Case did not execute this frozen manifest')
        row, arrays, snapshot = analyze_case(directory, spec, manifest, reference_inputs, fixed_mask, z)
        rows.append(row)
        all_arrays.update({spec['case_id']+'.'+name: value for name, value in arrays.items()})
        if snapshot is not None: snapshots[spec['case_id']] = snapshot
    result = {'schema': 'openstream-sawai-control-analysis-v1', 'manifest_sha256': digest(manifest_path),
              'analysis_tool_sha256': digest(__file__), 'solver_executed_by_analysis': False,
              'governing_equations_changed': False, 'registered_attempts': len(manifest['cases']),
              'completed_attempts': sum(r['execution'] == 'completed' for r in rows),
              'native_converged_attempts': sum(r['native_converged'] is True for r in rows),
              'qualified_numerical_candidates': sum(r['qualified_numerical_candidate'] for r in rows),
              'fixed_reference_mask': manifest['frozen_reference_mask'], 'cases': rows,
              'profile_comparisons': profile_comparisons(rows, snapshots),
              'limitations': ['Qualification is a preregistered numerical-control screen, not a new solver criterion or governing equation.',
                 'Same-state source returns are recomputed on a copied graph, not observed sequential point proposals.',
                 'All-node residuals and signed bounds remain visible even where frozen-mask qualification passes.',
                 'Iteration budgets and mass-flow relaxation differ; physical case, closures, mesh and convergence tolerances do not.',
                 'Runtime includes output generation and may reflect concurrently executing independent cases.',
                 'No matched MATLAB equivalence, full-software parity, mesh independence or experimental validation is established.']}
    output.mkdir(parents=True, exist_ok=False)
    np.savez_compressed(output/'mass_defects.npz', **all_arrays)
    fields = ['case_id', 'RELAXWW', 'MAXITER', 'execution', 'native_converged', 'qualified_numerical_candidate',
              'precursor_exact', 'last_initialization_time_s', 'runtime_s', 'base_fixed_ratio', 'wave_fixed_ratio', 'base_all_ratio', 'wave_all_ratio']
    with (output/'summary.csv').open('x', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields); writer.writeheader()
        for row in rows:
            small = {k: row.get(k) for k in fields if k in row}; small.update(row['registered_options'])
            if row['execution'] == 'completed':
                for field in ('base', 'wave'):
                    for suffix, mask in (('fixed', 'frozen_reference_mask'), ('all', 'all_interior')):
                        small[f'{field}_{suffix}_ratio'] = row['mass_defects'][field][mask]['reference_scaled_ratio']['max_abs_finite']
            writer.writerow(small)
    plot_study(rows, snapshots, output)
    result['output_sha256'] = {p.name: digest(p) for p in output.iterdir() if p.is_file()}
    save_json(output/'analysis.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, default=ROOT/'outputs/verification/sawai-control-study-01')
    parser.add_argument('--output', type=Path, default=ROOT/'outputs/verification/sawai-control-study-01/analysis')
    args = parser.parse_args()
    result = analyze(args.study.resolve(), args.output.resolve())
    print(json.dumps({key: result[key] for key in ('registered_attempts', 'completed_attempts', 'native_converged_attempts', 'qualified_numerical_candidates')}, indent=2))


if __name__ == '__main__':
    main()
