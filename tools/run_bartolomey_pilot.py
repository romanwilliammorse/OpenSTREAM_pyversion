"""Execute the preregistered Bartolomey pilot; no MATLAB or fitting required.

Every attempted run and measurement is accounted for. A completed comparison
is not an uncertainty-qualified validation pass. Existing output is never
overwritten. The default manifest was committed before prediction errors.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import traceback
import warnings

import numpy as np

from openstream import MixtureSolver
from openstream.database import load_bartolomey
from openstream.experimental_comparison import compare_void_profile
from openstream.output import balances, portable_json, save_result, source_hashes

ROOT = Path(__file__).resolve().parents[1]
XML_SHA256 = '93a16eced68d20b7d0b367abe5965d60311f18354c56c8991e3485bba8fca945'
MANIFEST_SHA256 = 'c193f988b5313329bbeac7408a46f02a618fff6daaa583337b296721abab4b55'


def write_json(path, data):
    def scalar(value):
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(type(value).__name__)
    path.write_text(json.dumps(portable_json(data), indent=2, ensure_ascii=False,
                               allow_nan=False, default=scalar)+'\n', encoding='utf-8')


def gui_input_document(inputs):
    """Represent this frozen pilot's default constant function for GUI import.

    InputSet.to_dict labels callables for provenance; the GUI requires a scalar.
    This campaign fixes CBTMULT to the upstream constant one, never a fitted or
    arbitrary callable. All other settings are copied without alteration.
    """
    if not np.all(np.asarray(inputs.model.CBTMULT(np.array([0., inputs.geometry.LENGTH]))) == 1):
        raise ValueError('Frozen Bartolomey pilot requires the default constant-one CBTMULT')
    data = {k: v for k, v in inputs.to_dict().items() if k != 'source_files'}
    data['model']['CBTMULT'] = 1.0
    return {'schema': 'openstream-gui-input-v1', 'framework': 'Mixture', 'inputs': data}


def physical_checks(solver, policy):
    """Steady source-equation and independent integrated balance checks, SI.

    Momentum is a source discrete-equation residual, not independent
    experimental evidence. Energy is transported enthalpy, not total energy.
    Phase occupied area is reconstructed from phase mass/density/velocity.
    """
    b = balances(solver)
    m, g = solver.mixture[-1], solver.inputSet.geometry
    bound = policy['fraction_bound_tolerance']
    liquid_area = m.liquid.W()/(m.fluid.RHOL(m.liquid.H())*m.liquid.U())
    vapor_area = m.vapor.W()/(m.fluid.RHOV(m.vapor.H())*m.vapor.U())
    occupied = liquid_area+vapor_area
    area_error = float(np.max(np.abs(occupied/g.AREA-1)))
    split_error = float(np.max(np.abs(m.liquid.W()+m.vapor.W()-m.W)))
    bc = solver.inputSet.bc[0]
    checks = {
        'solver_converged': bool(solver.converged),
        'finite_primary': all(np.isfinite(v).all() for v in (m.W, m.P, m.H, m.VF(), m.RHO(), m.U())),
        'positive_pressure_density': b['minimum_pressure_Pa'] > 0 and b['minimum_density_kg_m3'] > 0,
        'positive_forward_flow': bool(np.all(m.W > 0) and np.all(m.U() > 0)),
        'void_fraction_bounds': bool(np.all((m.VF() >= -bound) & (m.VF() <= 1+bound))),
        'vapor_quality_bounds': bool(np.all((m.X() >= -bound) & (m.X() <= 1+bound))),
        'mass': b['steady_mass_max_deviation_kg_s'] <= max(policy['mass_absolute_kg_s'], abs(bc.MFLOW)*policy['mass_relative']),
        'phase_mass_split': split_error <= max(policy['mass_absolute_kg_s'], abs(bc.MFLOW)*policy['mass_relative']),
        'enthalpy': b['steady_energy_relative_error'] <= policy['enthalpy_relative'],
        'momentum_source_residual': b['discrete_momentum_max_residual_Pa'] <= max(policy['momentum_absolute_Pa_floor'], solver.inputSet.options.ERRORP),
        'phase_occupied_area': area_error <= policy['area_closure_tolerance'],
        'inlet_mass': abs(m.W[0]-bc.MFLOW) <= 1e-12*max(1, abs(bc.MFLOW)),
        'inlet_enthalpy': abs(m.H[0]-bc.HIN) <= 1e-12*max(1, abs(bc.HIN)),
        'inlet_pressure': abs(m.P[0]-bc.PRESSURE) <= 1e-12*max(1, abs(bc.PRESSURE)),
        'prescribed_heating': abs(b['discrete_wall_power_W']-bc.POWER) <= 1e-12*max(1, abs(bc.POWER)),
    }
    return {'passed': bool(all(checks.values())), 'checks': checks, 'balances': b,
            'phase_area_max_relative_error': area_error, 'phase_mass_split_max_error_kg_s': split_error,
            'scope': 'Steady mass/enthalpy, source discrete momentum, bounds and reconstructed phase area. System-pressure property approximation retained.'}


def run_specs(manifest):
    for entry in manifest['entries']:
        for model in manifest['models']:
            for cells in manifest['mesh_cells']:
                yield entry, model, cells, 'base', dict(manifest['numerical_options'])
            cells = manifest['sensitivity_cells']
            tight = dict(manifest['numerical_options'])
            for key in ('ERRORW', 'ERRORP', 'ERRORH', 'SSCONVW', 'SSCONVP', 'SSCONVH'):
                tight[key] *= manifest['iteration_tightening_factor']
            yield entry, model, cells, 'tight', tight
            pseudo = dict(manifest['numerical_options'])
            pseudo.update(SSTSTEP=manifest['pseudo_time_step_s'], SSMAXITER=manifest['pseudo_time_max_iterations'])
            yield entry, model, cells, 'pseudo', pseudo


def sensitivity(left, right, tolerance):
    if not left or not right or left.get('execution') != 'completed' or right.get('execution') != 'completed':
        return {'status': 'unavailable', 'reason': 'One or both runs did not complete.'}
    # The same observation indices define the sensitivity population. Dropped
    # points must be reported, not counted as zero prediction changes.
    a = {p['index']: p['predicted'] for p in left['comparison']['points'] if p['status'] == 'compared'}
    b = {p['index']: p['predicted'] for p in right['comparison']['points'] if p['status'] == 'compared'}
    common = sorted(a.keys() & b.keys())
    max_change = max((abs(a[i]-b[i]) for i in common), default=None)
    eligible = left['converged'] and right['converged'] and a.keys() == b.keys()
    return {'status': 'passed' if eligible and max_change is not None and max_change <= tolerance else 'failed',
            'left': left['run_id'], 'right': right['run_id'], 'n_common_points': len(common),
            'unmatched_indices': sorted(a.keys() ^ b.keys()), 'max_void_change': max_change,
            'unit': '1', 'threshold': tolerance,
            'both_iteratively_converged': bool(left['converged'] and right['converged']),
            'same_compared_population': a.keys() == b.keys(),
            'interpretation': 'Sensitivity screening only; no observed order, asymptotic convergence or numerical uncertainty estimate.'}


def create_plots(output, manifest, runs, records):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    finest = max(manifest['mesh_cells'])
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout='constrained')
    for ax, record in zip(axes.flat, records):
        obs = record.observations()
        coord = np.array([np.nan if x is None else x for x in obs.coordinates])
        vf = np.array([np.nan if x is None else x for x in obs.void_fraction])
        ax.plot(coord, vf, 'ko', ms=4, label='Digitized measurement')
        for model, color in zip(manifest['models'], ('#2980b9', '#c44d34')):
            key = f'entry-{record.entry_id:02d}-{model}-n{finest}-base'
            run = runs[key]
            if run['execution'] != 'completed':
                ax.plot([], [], color=color, label=f'{model}: execution failed')
                continue
            with np.load(output/key/'numerical/results.npz') as values:
                x = values['XEQ'][-1] if obs.coordinate == 'Quality' else values['Z']
                ax.plot(x, values['VF'][-1], color=color, label=model.replace('_', ' '))
            if not run['converged'] or not run['physical']['passed']:
                ax.text(.02, .96, 'Numerical/physical check failed', color='#a32929', va='top', transform=ax.transAxes, fontsize=8)
        ax.set(title=f'Entry {record.entry_id} / TestID {record.test_id:g} — {record.test_name}',
               xlabel='Equilibrium quality [1]' if obs.coordinate == 'Quality' else 'Elevation [m]', ylabel='Void fraction [1]')
        ax.grid(alpha=.25); ax.legend(fontsize=8)
    fig.suptitle(f'Bartolomey pilot: fixed closures, {finest} cells\nDescriptive comparison; uncertainty-qualified validation not established', fontsize=12)
    fig.savefig(output/'pilot_comparison.png', dpi=170)
    fig.savefig(output/'pilot_comparison.pdf')
    plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT/'database')
    parser.add_argument('--manifest', type=Path, default=ROOT/'examples/bartolomey_pilot.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    manifest_bytes = args.manifest.read_bytes().replace(b'\r\n', b'\n')
    manifest = json.loads(manifest_bytes)
    if hashlib.sha256(manifest_bytes).hexdigest() != MANIFEST_SHA256:
        raise ValueError('Manifest differs from preregistered pilot; freeze a separate campaign before predicting errors.')
    if manifest.get('schema') != 'openstream-bartolomey-pilot-v1':
        raise ValueError('Unsupported pilot manifest schema')
    xml = args.database/'+Bartolomey/+src/Bartolomey.xml'
    if hashlib.sha256(xml.read_bytes().replace(b'\r\n', b'\n')).hexdigest() != XML_SHA256:
        raise ValueError('Database XML differs from the frozen pilot source; create a separately reviewed campaign.')
    dataset = load_bartolomey(args.database)
    records = [dataset.select(i) for i in manifest['entries']]
    if [r.test_id for r in records] != manifest['expected_test_ids'] or [r.observations().coordinate for r in records] != manifest['expected_coordinates']:
        raise ValueError('Selected record identity/coordinate differs from preregistration')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'frozen_manifest.json').write_bytes(manifest_bytes)
    report = {
        'schema': 'openstream-experimental-pilot-v1', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'manifest_sha256_lf': hashlib.sha256(manifest_bytes).hexdigest(), 'manifest_preregistration_commit': '4e76cc1b3d5751d4b2f02f7ff74c35124d31174c',
        'database_commit': manifest['database_commit'], 'xml_sha256_lf': XML_SHA256,
        'source_fingerprints': source_hashes(), 'python': platform.python_version(),
        'versions': {name: version(name) for name in ('openstream-python', 'numpy', 'scipy', 'CoolProp', 'matplotlib')},
        'experimental_status': 'Descriptive comparison only; combined uncertainty and independence not established.',
        'matlab_comparison': 'not_run', 'runs': {}, 'sensitivity': [],
    }
    registry = []
    for record in dataset.records:
        registry.append({'selected': record.entry_id in manifest['entries'],
                         'selection_reason': 'First record of source TestName group' if record.entry_id in manifest['entries'] else 'Outside metadata-only pilot selection; not rejected on prediction error',
                         'record': record.to_dict(), 'input_consistency': record.input_consistency()})
    write_json(args.output/'case_registry.json', registry)
    for entry, model, cells, variant, options in run_specs(manifest):
        run_id = f'entry-{entry:02d}-{model}-n{cells}-{variant}'
        directory = args.output/run_id
        directory.mkdir()
        record = dataset.select(entry)
        result = {'run_id': run_id, 'entry_id': entry, 'test_id': record.test_id, 'test_name': record.test_name,
                  'model': model, 'cells': cells, 'variant': variant, 'execution': 'failed', 'converged': False}
        caught = []
        try:
            inputs = record.to_input_set(model={**manifest['models'][model], 'ID': run_id, 'NNODES': cells}, options=options)
            write_json(directory/'submitted_inputs.json', inputs.to_dict())
            write_json(directory/'gui_inputs.json', gui_input_document(inputs))
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                solver = MixtureSolver(inputs).solve()
                result.update(converged=bool(solver.converged), elapsed_seconds=solver.elapsed_seconds)
                save_result(solver, directory/'numerical')
                m = solver.mixture[-1]
                obs = record.observations()
                comparison = compare_void_profile(obs, m.XEQ() if obs.coordinate == 'Quality' else solver.Z, m.VF())
                result.update(execution='completed', converged=bool(solver.converged), elapsed_seconds=solver.elapsed_seconds,
                              comparison=comparison, physical=physical_checks(solver, manifest['acceptance']))
            write_json(directory/'comparison.json', comparison)
            with (directory/'paired_measurements.csv').open('w', newline='', encoding='utf-8') as f:
                points = comparison['points']
                units = {'coordinate_unit': obs.unit, 'void_fraction_unit': '1', 'error_unit': '1'}
                writer = csv.DictWriter(f, fieldnames=(list(points[0]) if points else ['index'])+list(units))
                writer.writeheader(); writer.writerows({**point, **units} for point in points)
        except Exception as exc:
            # Completion includes required comparison artifacts. Preserve
            # numerical convergence if a later export fails, but do not admit
            # an incomplete run to the sensitivity acceptance population.
            result.update(execution='failed', error=f'{type(exc).__name__}: {exc}', traceback=traceback.format_exc())
        result['warnings'] = sorted(set(str(w.message) for w in caught))
        report['runs'][run_id] = result
        write_json(directory/'assessment.json', result)
        write_json(args.output/'report.json', report)
        print(f'{run_id}: {result["execution"]}; converged={result["converged"]}; physical={result.get("physical", {}).get("passed")}', flush=True)
    for record in records:
        for model in manifest['models']:
            def find(n, variant='base'):
                return report['runs'].get(f'entry-{record.entry_id:02d}-{model}-n{n}-{variant}')
            for a, b in zip(manifest['mesh_cells'], manifest['mesh_cells'][1:]):
                report['sensitivity'].append({'entry_id': record.entry_id, 'model': model, 'kind': f'mesh_{a}_{b}',
                    **sensitivity(find(a), find(b), manifest['acceptance']['mesh_max_void_change'])})
            for variant, policy in [('tight', 'iteration_max_void_change'), ('pseudo', 'pseudo_time_max_void_change')]:
                n = manifest['sensitivity_cells']
                report['sensitivity'].append({'entry_id': record.entry_id, 'model': model, 'kind': variant,
                    **sensitivity(find(n), find(n, variant), manifest['acceptance'][policy])})
    report['counts'] = {'attempted': len(report['runs']),
        'completed': sum(r['execution'] == 'completed' for r in report['runs'].values()),
        'converged': sum(r['converged'] for r in report['runs'].values()),
        'physical_passed': sum(r.get('physical', {}).get('passed', False) for r in report['runs'].values()),
        'sensitivity_passed': sum(s['status'] == 'passed' for s in report['sensitivity']),
        'sensitivity_total': len(report['sensitivity'])}
    write_json(args.output/'report.json', report)
    create_plots(args.output, manifest, report['runs'], records)
    print(json.dumps(report['counts']), flush=True)
    # Failed scientific criteria are retained and surfaced to batch callers.
    return 0 if report['counts']['completed'] == report['counts']['attempted'] and report['counts']['physical_passed'] == report['counts']['attempted'] and report['counts']['sensitivity_passed'] == report['counts']['sensitivity_total'] else 3


if __name__ == '__main__':
    raise SystemExit(main())
