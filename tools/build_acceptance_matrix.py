"""Build and check the evidence ledger; never execute or alter solver physics.

Source ledgers live in docs/acceptance/. Declaration annexes are inventories,
not evidence of branch correctness, complete operating ranges, or validation.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
IMPL = {'implemented', 'partial', 'missing', 'unsupported_source_defect', 'unsupported_port_gap'}
STATUS = {'passed_scoped', 'partial', 'failed', 'not_run', 'not_applicable'}
TRACKS = {'matlab_equivalence', 'numerical_verification', 'interface_parity',
          'reference_infrastructure', 'release', 'experimental_validation', 'literature_scope'}
REQUIRED = {'id', 'track', 'component', 'requirement', 'scope', 'upstream', 'python',
            'implementation', 'native_tests', 'matlab', 'physical', 'experimental',
            'evidence', 'gap', 'priority', 'acceptance_criteria', 'next_action'}


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def path_exists(ref):
    if ref.startswith(('https://', 'local-paper:')):
        return True  # Exact external identity/availability is recorded separately.
    path = re.sub(r':\d+(?:-\d+)?$', '', ref).split('#', 1)[0]
    return (ROOT/path).exists()


def validate(rows):
    ids = [r['id'] for r in rows]
    if len(ids) != len(set(ids)):
        raise ValueError('Duplicate requirement IDs')
    papers = {p['file_name'] for p in read_json(ROOT/'provenance/acceptance_sources.json')['literature']}
    for row in rows:
        if missing := REQUIRED - row.keys():
            raise ValueError(f"{row['id']}: missing {sorted(missing)}")
        if row['implementation'] not in IMPL or row['track'] not in TRACKS:
            raise ValueError(f"{row['id']}: invalid implementation/track")
        if row['priority'] not in {'P0', 'P1', 'P2'}:
            raise ValueError(f"{row['id']}: invalid priority")
        for name in ('upstream', 'python', 'evidence', 'acceptance_criteria', 'depends_on'):
            value = row.get(name, [])
            if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
                raise ValueError(f"{row['id']}: {name} must be a list of nonempty strings")
        for axis in ('native_tests', 'matlab', 'physical', 'experimental'):
            if row[axis] not in STATUS:
                raise ValueError(f"{row['id']}: invalid {axis}")
        for name in ('requirement', 'scope', 'gap', 'next_action'):
            if not isinstance(row[name], str) or not row[name].strip():
                raise ValueError(f"{row['id']}: empty {name}")
        if not row['acceptance_criteria'] or not row['evidence']:
            raise ValueError(f"{row['id']}: criteria/evidence required")
        for ref in row['upstream'] + row['python'] + row['evidence']:
            if not path_exists(ref):
                raise ValueError(f"{row['id']}: missing local reference {ref}")
            if ref.startswith('local-paper:') and ref.split(':', 1)[1].split('#', 1)[0] not in papers:
                raise ValueError(f"{row['id']}: unknown local paper {ref}")
        if unknown := set(row.get('depends_on', [])) - set(ids):
            raise ValueError(f"{row['id']}: unknown dependencies {unknown}")
    graph = {r['id']: r.get('depends_on', []) for r in rows}
    visited, active = set(), set()
    def visit(identity):
        if identity in active:
            raise ValueError(f'Cyclic acceptance dependency: {identity}')
        if identity in visited:
            return
        active.add(identity)
        for dependency in graph[identity]:
            visit(dependency)
        active.remove(identity)
        visited.add(identity)
    for identity in graph:
        visit(identity)


def table_cell(value):
    return str(value).replace('|', '\\|').replace('\n', ' ')


def csv_text(rows, columns):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore', lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({k: ('; '.join(map(str, v)) if isinstance(v, list) else v)
                         for k, v in row.items() if k in columns})
    return stream.getvalue()


def declaration_annexes(rows, inventory, methods):
    options = []
    actual_types = {p.stem for p in (ROOT/'upstream/+InputEnums').glob('*.m')}
    if actual_types != set(inventory['enumerations']):
        raise ValueError('Enum type inventory differs from preserved source files')
    for selector, choices in sorted(inventory['enumerations'].items()):
        source = f'upstream/+InputEnums/{selector}.m'
        if not (ROOT/source).is_file():
            raise ValueError(f'Missing enum source: {source}')
        text = (ROOT/source).read_text(encoding='utf-8-sig')
        body = re.search(r'^\s*enumeration\s*$([\s\S]*?)^\s*end\s*$', text, re.M)
        actual = re.findall(r'^\s*([A-Z][A-Z0-9_]*)\b', body.group(1), re.M) if body else []
        if set(actual) != set(choices):
            raise ValueError(f'Enum inventory differs from pinned source: {selector}')
        links = [r['id'] for r in rows if selector in r.get('selectors', []) + r.get('enum_names', [])]
        for choice in choices:
            caveat = ''
            if (selector, choice) == ('SPHTM', 'DITTUSBOELTERGEN'):
                caveat = 'Explicit rejection: unresolved upstream matrix/elementwise expression.'
            if (selector, choice) == ('LOCRELVEL', 'SIMPLE'):
                caveat = 'Declared upstream but no implemented source closure; explicit rejection.'
            if (selector, choice) == ('DROPDRAG', 'DISTORDED'):
                caveat = 'Framework-specific: TwoFluid branch exists; annular branch rejects undefined source objects.'
            if (selector, choice) == ('VAPORFRIC', 'SOLVER_DEPENDENT'):
                caveat = 'Resolve separately for each solver/precursor; not a standalone physical closure.'
            if (selector, choice) == ('BTHTM', 'DELORME'):
                caveat = 'One-wall path only; multiwall source dimensions unresolved.'
            options.append({'id': f'OPT-{selector}-{choice}', 'selector': selector, 'choice': choice,
                            'source': source, 'requirement_ids': links,
                            'declaration_status': 'declared_in_pinned_upstream',
                            'case_coverage': 'not_individually_certified_by_this_inventory',
                            'known_limit': caveat,
                            'required_case_axes': 'framework; regime; domain limits; geometry/walls; steady/transient; interacting selectors; inputs; reference/uncertainty'})
    for selector in ('AXIALINTERP', 'TIMEINTERP'):
        for choice in ('LINEAR', 'NEAREST', 'NEXT', 'PREVIOUS', 'PCHIP', 'SPLINE', 'MAKIMA', 'CUBIC'):
            options.append({'id': f'OPT-{selector}-{choice}', 'selector': selector, 'choice': choice,
                            'source': 'upstream/+Inputs/Options.m',
                            'requirement_ids': [r['id'] for r in rows if selector in r.get('selectors', [])],
                            'declaration_status': 'documented_interpolation_selection_not_InputEnums',
                            'case_coverage': 'not_individually_certified_by_this_inventory',
                            'known_limit': 'CUBIC is explicitly rejected: MATLAB release-dependent ambiguity.' if choice == 'CUBIC' else '',
                            'required_case_axes': 'knots; midpoint ties; endpoints; outside domain; axis/shape; short arrays; monotonicity; MATLAB release'})
    public = []
    for entry in methods['methods']:
        if entry['status'] == 'constructor_outside_numerical_method_count':
            continue
        s = entry['source']
        links = ['API-010'] + [r['id'] for r in rows
                 if (r.get('method_names') or r.get('class_prefixes'))
                 and (not r.get('method_names') or s['name'] in r['method_names'])
                 and (not r.get('class_prefixes') or
                      any(entry['upstream_class'].startswith(p) for p in r['class_prefixes']))]
        candidate = entry.get('native_candidate')
        public.append({'id': 'METHOD-' + entry['upstream_class'] + '.' + s['name'],
                       'upstream_class': entry['upstream_class'], 'method': s['name'],
                       'source': s['file'] + ':' + str(s['line']),
                       'native_candidate': (candidate['file'] + ':' + str(candidate['line'])) if candidate else '',
                       'declaration_classification': entry['status'], 'requirement_ids': links,
                       'semantic_acceptance': 'not_certified_by_declaration_match',
                       'review_note': json.dumps(entry.get('independent_review', entry.get('alternative_note', '')), ensure_ascii=False)})
    return options, public


def build():
    source_paths = [ROOT/'docs/acceptance'/f'{part}.json' for part in ('core', 'interfaces', 'experimental')]
    rows = []
    for source in source_paths:
        data = read_json(source)
        rows.extend(data if isinstance(data, list) else data['requirements'])
    plan = read_json(ROOT/'docs/acceptance/plan.json')
    ids = {r['id'] for r in rows}
    if set(plan.get('dependencies', {})) - ids:
        raise ValueError('Dependency plan contains unknown requirement IDs')
    for stage in plan['prioritized_work']:
        if set(stage['requirements']) - ids:
            raise ValueError(f"Unknown requirement in work stage {stage['id']}")
    for row in rows:
        row['depends_on'] = plan.get('dependencies', {}).get(row['id'], [])
    validate(rows)
    inventory = read_json(ROOT/'docs/upstream_inventory.json')
    methods = read_json(ROOT/'docs/METHOD_COVERAGE.json')
    for file, expected in {**methods['upstream_files'], **methods['native_files']}.items():
        if sha(ROOT/file) != expected:
            raise ValueError(f'Stale method inventory fingerprint: {file}')
    if sha(ROOT/'docs/FEATURE_MAP.md') != methods['feature_map_sha256']:
        raise ValueError('Regenerate method inventory after feature-map changes')
    options, public = declaration_annexes(rows, inventory, methods)
    for group in (options, public):
        if len({entry['id'] for entry in group}) != len(group):
            raise ValueError('Duplicate declaration annex IDs')
    for declaration in options + public:
        if set(declaration['requirement_ids']) - ids:
            raise ValueError(f"Unknown requirement link in {declaration['id']}")
    if any(not r['requirement_ids'] for r in options + public):
        missing = [r['id'] for r in options + public if not r['requirement_ids']]
        raise ValueError('Unlinked declaration entries: ' + ', '.join(missing))
    sources = read_json(ROOT/'provenance/acceptance_sources.json')
    result = {'schema': 'openstream-acceptance-matrix-v1', 'snapshot_date': sources['snapshot_date'],
              'fingerprint_policy': 'Ledger/source-text SHA256 normalizes CRLF to LF only. Supplied PDF SHA256 values are exact binary hashes.',
              'provenance': sources, 'scope_and_status_rules': plan['scope_and_status_rules'],
              'prioritized_work': plan['prioritized_work'],
              'counts_not_completion_scores': {
                  'requirements': len(rows), 'tracks': dict(Counter(r['track'] for r in rows)),
                  'priorities': dict(Counter(r['priority'] for r in rows)),
                  'implementation': dict(Counter(r['implementation'] for r in rows)),
                  'status_axes': {k: dict(Counter(r[k] for r in rows)) for k in ('native_tests', 'matlab', 'physical', 'experimental')},
                  'enum_types': len(inventory['enumerations']),
                  'enum_choices': sum(len(c) for c in inventory['enumerations'].values()),
                  'interpolation_choices': 16, 'public_method_entries_with_inheritance': len(public)},
              'source_ledger_sha256': {p.relative_to(ROOT).as_posix(): sha(p)
                                      for p in source_paths + [ROOT/'docs/acceptance/plan.json',
                                          ROOT/'docs/upstream_inventory.json', ROOT/'docs/METHOD_COVERAGE.json',
                                          ROOT/'provenance/acceptance_sources.json', Path(__file__)]},
              'requirements': rows}
    columns = ['id', 'priority', 'track', 'component', 'requirement', 'scope', 'implementation',
               'native_tests', 'matlab', 'physical', 'experimental', 'gap', 'acceptance_criteria',
               'next_action', 'depends_on', 'upstream', 'python', 'evidence']
    md = ['# Acceptance matrix', '', 'Generated from the reviewed ledgers in `docs/acceptance/`. '
          'This is a requirement/evidence inventory, not a percentage of full parity.', '',
          '[Prioritized work and acceptance rules](ACCEPTANCE_PLAN.md) | '
          '[Complete CSV](ACCEPTANCE_MATRIX.csv) | [Machine-readable JSON](ACCEPTANCE_MATRIX.json) | '
          '[Literature review](LITERATURE_ACCEPTANCE_REVIEW.md)', '',
          f"Scope: **{len(rows)} requirements**, **{len(inventory['enumerations'])} enum types / "
          f"{sum(len(c) for c in inventory['enumerations'].values())} choices**, 16 interpolation entries, "
          f"and **{len(public)} public method entries including inheritance**. "
          'These inventories overlap and are not additive. Combinations and operating-domain cases '
          'must be expanded before branch-complete acceptance can be claimed.', '',
          '`passed_scoped` means the cited evidence passed only its stated scope. `partial` means '
          'incomplete evidence or implementation; `failed` records an executed failed criterion; '
          '`not_run` means no qualifying executed check. `not_applicable` is only for an axis '
          'that does not apply. No status is inferred from a matching method name.', '',
          'P0: establish trustworthy inputs/references and investigate blocking inconsistencies. '
          'P1: execute the first reference/measurement acceptance campaigns. '
          'P2: complete remaining interfaces, domains, and release coverage; these remain required.', '']
    for track in sorted(TRACKS):
        subset = [r for r in rows if r['track'] == track]
        if not subset:
            continue
        md += ['## ' + track.replace('_', ' ').title(), '',
               '| ID / priority | Requirement | Implementation | Native checks | MATLAB | Physical | Experimental |',
               '|---|---|---|---|---|---|---|']
        for r in subset:
            md.append('| ' + ' | '.join(table_cell(v) for v in (r['id']+' / '+r['priority'],
                r['requirement'], r['implementation'], r['native_tests'], r['matlab'], r['physical'], r['experimental'])) + ' |')
        md.append('')
    md += ['## Requirement details', '']
    for r in rows:
        md += [f"### {r['id']}: {r['component']}", '', f"**Scope:** {r['scope']}", '',
               f"**Missing or unverified:** {r['gap']}", '', '**Acceptance evidence required:**', '']
        md += ['- ' + criterion for criterion in r['acceptance_criteria']]
        md += ['', '**Next action:** ' + r['next_action'], '',
               '**Evidence:** ' + '; '.join('`'+e+'`' for e in r['evidence']), '',
               '**Dependencies:** ' + (', '.join(r['depends_on']) or 'No additional matrix-row prerequisite.'), '']
    return {
        'docs/ACCEPTANCE_MATRIX.json': json.dumps(result, indent=2, ensure_ascii=False)+'\n',
        'docs/ACCEPTANCE_MATRIX.csv': '\ufeff'+csv_text(rows, columns),
        'docs/ACCEPTANCE_MATRIX.md': '\n'.join(md).rstrip('\n')+'\n',
        'docs/ACCEPTANCE_OPTIONS.csv': '\ufeff'+csv_text(options, list(options[0])),
        'docs/ACCEPTANCE_METHODS.csv': '\ufeff'+csv_text(public, list(public[0])),
    }, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate sources and fail if generated files are stale')
    args = parser.parse_args()
    artifacts, report = build()
    for name, text in artifacts.items():
        path = ROOT/name
        if args.check:
            if not path.exists() or path.read_bytes().replace(b'\r\n', b'\n') != text.encode('utf-8').replace(b'\r\n', b'\n'):
                raise ValueError(f'Generated file is missing/stale: {name}')
        else:
            path.write_bytes(text.encode('utf-8'))
    print(json.dumps(report['counts_not_completion_scores'], indent=2))
    print('Acceptance ledger integrity and generated files:', 'PASS' if args.check else 'WRITTEN')


if __name__ == '__main__':
    main()
