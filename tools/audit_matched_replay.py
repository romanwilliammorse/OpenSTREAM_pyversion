"""Independently recompute recorded scalar updates; never import/run a solver.

This audits arithmetic and trace integrity, not MATLAB equivalence, convergence,
or experimental validity. Exact numeric equality is used; no physical acceptance
tolerance is introduced. Inputs are completed replay receipts and saved arrays.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def one(value):
    a = np.asarray(value, dtype=float)
    if a.size != 1:
        raise ValueError(f'Only the recorded single-wall replay is supported: {a.shape}')
    return float(a.ravel()[0])


def mass_proposal(u, upstream, old, old_u, source, dz, dt):
    """kg/s: source is linear mass rate kg/(s m)."""
    return u*(upstream+old/old_u*dz/dt+source*dz)/(u+dz/dt)


def advective_proposal(u, upstream, old, source, dz, dt):
    """m/s or J/kg: source is acceleration or specific heating rate."""
    return (upstream*u+old*dz/dt+source*dz)/(u+dz/dt)


def relaxed(old, proposal, factor):
    return (1-factor)*old+factor*proposal


def clipped_mass(base, wave):
    """Source POSFILM order: preserve total, clip wave, compensate/clip base."""
    total = base+wave
    wave_after = max(wave, 0.0)
    return max(total-wave_after, 0.0), wave_after


def equal_numeric(a, b):
    return a == b or (math.isnan(a) and math.isnan(b))


class Checks:
    def __init__(self):
        self.groups = {}
        self.context = None
        self.examples = []

    def add(self, name, unit, actual, expected):
        actual, expected = one(actual), one(expected)
        row = self.groups.setdefault(name, {'unit': unit, 'checks': 0, 'mismatches': 0,
                                            'nonfinite_pairs': 0, 'max_abs_difference': 0.0})
        if row['unit'] != unit:
            raise ValueError('Inconsistent units for arithmetic check')
        row['checks'] += 1
        if math.isfinite(actual) and math.isfinite(expected):
            row['max_abs_difference'] = max(row['max_abs_difference'], abs(actual-expected))
        else:
            row['nonfinite_pairs'] += 1
        if not equal_numeric(actual, expected):
            row['mismatches'] += 1
            if len(self.examples) < 30:
                self.examples.append({'check': name, 'where': self.context,
                                      'observed': str(actual), 'recomputed': str(expected)})

    def result(self):
        count = sum(v['checks'] for v in self.groups.values())
        failed = sum(v['mismatches'] for v in self.groups.values())
        return {'checks': count, 'mismatches': failed, 'exact_arithmetic_match': count > 0 and failed == 0,
                'groups': self.groups, 'first_mismatches': self.examples}


def identity(row):
    return row['time_s'], row['node_zero_based'], row['iteration']


def iteration_groups(path):
    """Consecutive event groups; line-stage locals are interpreted only there."""
    key, rows = None, []
    with Path(path).open(encoding='utf-8') as stream:
        for line in stream:
            row = json.loads(line)
            current = identity(row)
            if key is not None and current != key:
                yield key, rows
                rows = []
            key = current
            rows.append(row)
    if rows:
        yield key, rows


def organize(rows):
    stages = {}
    returns = {}
    for row in rows:
        if row['stage'] == 'closure_return':
            returns[row['method']] = row
        else:
            stage = row['stage']
            if stage in stages:
                raise ValueError(f'Duplicate stage in one point iteration: {stage}')
            stages[stage] = (row, dict(returns))
    return stages


def audit_twofluid(stages, options, model, precursor, node, checks):
    order = ['liquid_mass_proposal', 'vapor_mass_proposal', 'liquid_momentum_proposal',
             'vapor_momentum_proposal', 'liquid_enthalpy_proposal', 'vapor_enthalpy_proposal', 'point']
    if set(stages) != set(order):
        raise ValueError(f'Incomplete TwoFluid stages: {sorted(stages)}')
    for number, (label, short, phase) in enumerate((('liquid', 'l', 'Liquid'), ('vapor', 'v', 'Vapor'))):
        row, returned = stages[label+'_mass_proposal']; loc = row['locals']
        get = lambda key: one(loc[key])
        source = one(returned[phase+'.MTOT']['return_value'])
        checks.add(label+'.mass_source_snapshot', 'kg/(s m)', get('mtot'), source)
        value = mass_proposal(get('u'+short+'i'), get('w'+short+'up'), get('w'+short+'old'),
                              get('u'+short+'old'), source, get('dz'), get('dt'))
        checks.add(label+'.mass_proposal', 'kg/s', get('w'+short+'new'), value)
        after = stages[order[number+1]][0]
        checks.add(label+'.mass_relaxation', 'kg/s', after[label+'_W'],
                   relaxed(get('w'+short+'i'), get('w'+short+'new'), options['RELAXW'+short.upper()]))

        row, returned = stages[label+'_momentum_proposal']; loc = row['locals']
        get = lambda key: one(loc[key])
        if model['MOMENTLIQUID' if label == 'liquid' else 'MOMENTGAS'] != 'FULL':
            raise ValueError('This audit is scoped to the frozen FULL-momentum TwoFluid case')
        wi, ui = get('w'+short+'i'), get('u'+short+'i')
        force = one(returned[phase+'.FTOT']['return_value'])/(wi/ui) if wi > 1e-3 else 0.0
        checks.add(label+'.force_normalization', 'm/s^2', get('ftot'), force)
        trial = advective_proposal(ui, get('u'+short+'up'), get('u'+short+'old'), force, get('dz'), get('dt'))
        value = min(1.5*float(precursor[label+'.U'][0, node]), max(0.0, trial)) if wi > 1e-3 else ui
        checks.add(label+'.momentum_proposal', 'm/s', get('u'+short+'new'), value)
        after = stages[order[number+3]][0]
        checks.add(label+'.momentum_relaxation', 'm/s', after[label+'_U'],
                   relaxed(ui, get('u'+short+'new'), options['RELAXU'+short.upper()]))

        row, _ = stages[label+'_enthalpy_proposal']; loc = row['locals']
        get = lambda key: one(loc[key])
        value = advective_proposal(get('u'+short+'i'), get('h'+short+'up'), get('h'+short+'old'),
                                   get('htot'), get('dz'), get('dt'))
        checks.add(label+'.enthalpy_proposal', 'J/kg', get('h'+short+'new'), value)
        after = stages[order[number+5]][0]
        checks.add(label+'.enthalpy_relaxation', 'J/kg', after[label+'_H'],
                   relaxed(get('h'+short+'i'), get('h'+short+'new'), options['RELAXH'+short.upper()]))
    point = stages['point'][0]
    for index, (label, key, oldkey, unit) in enumerate([
        ('liquid','W','wli','kg/s'), ('vapor','W','wvi','kg/s'),
        ('liquid','U','uli','m/s'), ('vapor','U','uvi','m/s'),
        ('liquid','H','hli','J/kg'), ('vapor','H','hvi','J/kg')]):
        checks.add(label+'.point_d'+key, unit, point['locals']['delta'][index],
                   abs(point[label+'_'+key]-one(point['locals'][oldkey])))


def audit_fourfield(stages, options, model, perimeter, checks):
    for label, short, method in [('base','b','Base.MTOT'), ('wave','w','Wave.MTOT')]:
        row, returned = stages[label+'_mass_proposal']; loc = row['locals']
        get = lambda key: one(loc[key])
        source = perimeter*one(returned[method]['return_value'])
        value = mass_proposal(get('u'+short), get('w'+short+'_up'), get('w'+short+'_old'),
                              get('u'+short+'_old'), source, get('dz'), get('dt'))
        checks.add(label+'.mass_proposal', 'kg/s', get('w'+short+'_new'), value)
        after = stages['base_mass_applied' if label == 'base' else 'before_clipping'][0]
        checks.add(label+'.mass_relaxation', 'kg/s', after[label+'_W'],
                   relaxed(get('w'+short), get('w'+short+'_new'), options['RELAXW'+short.upper()]))
    before, after = stages['before_clipping'][0], stages['after_clipping'][0]
    expected = clipped_mass(before['base_W'], before['wave_W']) if model['POSFILM'] else (before['base_W'], before['wave_W'])
    for label, value in zip(('base','wave'), expected):
        checks.add(label+'.source_clipping', 'kg/s', after[label+'_W'], value)


def audit_temporal(directory, framework, perimeter, checks):
    trace = json.loads((directory/'temporal_trace.json').read_text())
    with np.load(directory/'numerical/initialization.npz', allow_pickle=False) as a:
        if len(trace) != len(a['TIME'])-1:
            raise ValueError('Temporal trace does not cover every saved advance')
        if framework == 'TwoFluid':
            fields = [('dWl','liquid.W','kg/s'), ('dWv','vapor.W','kg/s'),
                      ('dUl','liquid.U','m/s'), ('dUv','vapor.U','m/s'),
                      ('dHl','liquid.H','J/kg'), ('dHv','vapor.H','J/kg')]
        else:
            fields = [('dWLb','film.base.W','kg/(s m)'), ('dUb','film.base.U','m/s'),
                      ('dWLw','film.wave.W','kg/(s m)'), ('dUw','film.wave.U','m/s'),
                      ('dFw','film.wave.FREQUENCY','Hz'), ('dUd','drop.U','m/s')]
        for k, row in enumerate(trace, 1):
            if row['time_s'] != float(a['TIME'][k]):
                raise ValueError('Temporal trace time differs from saved array axis')
            checks.context = {'time_s': row['time_s'], 'stage': 'temporal'}
            for key, field, unit in fields:
                new, old = a[field][k], a[field][k-1]
                if key in {'dWLb','dWLw'}:
                    new, old = new/perimeter, old/perimeter
                checks.add('temporal.'+key, unit, row['time_'+key], np.max(np.abs(new-old)))


def audit(campaign):
    campaign = Path(campaign)
    report = json.loads((campaign/'report.json').read_text())
    if not report.get('execution_complete'):
        raise ValueError('Replay is incomplete; refuse a final arithmetic receipt')
    if sha(campaign/'frozen_manifest.json') != report['manifest_sha256']:
        raise ValueError('Frozen replay manifest hash differs from completed report')
    frozen = json.loads((campaign/'frozen_manifest.json').read_text())
    result = {'schema': 'openstream-independent-replay-arithmetic-v1', 'report_sha256': sha(campaign/'report.json'),
              'audit_script_sha256': sha(__file__), 'frozen_manifest_sha256': sha(campaign/'frozen_manifest.json'),
              'comparison_rule': 'Exact numeric equality, including matching NaN locations; no acceptance tolerance.',
              'scope': 'Recorded scalar-update arithmetic and saved temporal differences only; no solver or property recomputation, MATLAB execution, or physical-validation claim.',
              'limitations': ['Closure-return values are observed inputs, not independent closure validation.',
                             'Raw HTOT and force constituents were not captured in this trace; source-order force addition is not resolved.',
                             'Only selected axial nodes are traced; temporal maxima use all saved nodes.'], 'cases': []}
    root = Path(__file__).resolve().parents[1]
    for case in frozen['cases']:
        directory = campaign/case['run_id']
        inp = json.loads((directory/'effective_inputs.json').read_text())
        perimeter = one(inp['geometry']['PERIM']); checks = Checks(); count = 0
        schema = json.loads((directory/'trace_schema.json').read_text())
        identities, covered = set(), set()
        with np.load(directory/'numerical/mixture/results.npz', allow_pickle=False) as precursor:
            for key, rows in iteration_groups(directory/'update_trace.jsonl'):
                if key in identities:
                    raise ValueError('Repeated point-iteration identity in nonconsecutive trace groups')
                identities.add(key); covered.add(key[:2])
                checks.context = {'time_s': key[0], 'node_zero_based': key[1], 'iteration': key[2]}
                stages = organize(rows)
                if case['framework'] == 'TwoFluid':
                    audit_twofluid(stages, inp['options'], inp['model'], precursor, key[1], checks)
                else:
                    audit_fourfield(stages, inp['options'], inp['model'], perimeter, checks)
                count += 1
        temporal = json.loads((directory/'temporal_trace.json').read_text())
        expected = {(row['time_s'], node) for row in temporal for node in schema['trace_nodes_zero_based']}
        if covered != expected or count != schema['event_counts']['point']:
            raise ValueError('Trace coverage differs from declared selected nodes, times, or event counts')
        audit_temporal(directory, case['framework'], perimeter, checks)
        dtype_checks = 0
        dtype_sources = {}
        for name in ['comparison_profiles.npz','numerical/results.npz','numerical/initialization.npz',
                     'numerical/mixture/results.npz','numerical/mixture/initialization.npz']:
            with np.load(root/case['original_directory']/name, allow_pickle=False) as a, np.load(directory/name, allow_pickle=False) as b:
                if set(a.files) != set(b.files):
                    raise ValueError('Dtype audit array inventory differs')
                for field in a.files:
                    if a[field].dtype != b[field].dtype:
                        raise ValueError(f'Dtype changed in {case["run_id"]}/{name}/{field}')
                    dtype_checks += 1
            dtype_sources[name] = {'original_sha256': sha(root/case['original_directory']/name),
                                   'replay_sha256': sha(directory/name)}
        sources = ['update_trace.jsonl','temporal_trace.json','trace_schema.json','effective_inputs.json',
                   'numerical/initialization.npz','numerical/mixture/results.npz']
        result['cases'].append({'run_id': case['run_id'], 'point_iterations_audited': count,
                                'selected_node_time_pairs_complete': len(covered),
                                'dtype_pairs_identical': dtype_checks,
                                'dtype_read_files_sha256': dtype_sources,
                                'read_file_sha256': {p: sha(directory/p) for p in sources}, **checks.result()})
    result['all_exact_arithmetic_checks_passed'] = all(x['exact_arithmetic_match'] for x in result['cases'])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    result = audit(args.campaign)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, allow_nan=False); stream.write('\n')
    print(json.dumps({'exact_arithmetic': result['all_exact_arithmetic_checks_passed'],
                      'counts': {x['run_id']: x['checks'] for x in result['cases']}}))
    return 0 if result['all_exact_arithmetic_checks_passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
