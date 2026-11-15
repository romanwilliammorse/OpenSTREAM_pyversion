"""Verify this policy revision changed no numerical solver or closure code."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
BASE = '039afe6a723e542927dd7cc11610d610ded27c3e'

def previous(path):
    return subprocess.run(['git', '-C', str(ROOT), 'show', f'{BASE}:{path}'],
                          check=True, capture_output=True).stdout.decode('utf-8-sig')

def dump(node):
    return ast.dump(node, include_attributes=False)

def functions(tree):
    return {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

files = []
for file in sorted((ROOT/'src/openstream').glob('*.py')):
    name = file.relative_to(ROOT).as_posix()
    old, new = ast.parse(previous(name)), ast.parse(file.read_text(encoding='utf-8-sig'))
    if name not in ('src/openstream/threefield.py', 'src/openstream/gui_worker.py'):
        assert dump(old) == dump(new), f'Unexpected numerical/module change: {name}'
    elif name.endswith('threefield.py'):
        old_functions, new_functions = functions(old), functions(new)
        assert old_functions.keys() == new_functions.keys()
        for key in old_functions:
            if key != '_physical_inventory_diagnostics':
                assert dump(old_functions[key]) == dump(new_functions[key]), key
        left, right = old_functions['_physical_inventory_diagnostics'], new_functions['_physical_inventory_diagnostics']
        # Ignore the changed docstring. Every original arithmetic statement up
        # to the final return is retained exactly; only an information flag is added.
        assert [dump(n) for n in left.body[1:-1]] == [dump(n) for n in right.body[1:-2]]
        before = {key.value: value for key, value in zip(left.body[-1].value.keys, left.body[-1].value.values)}
        after = {key.value: value for key, value in zip(right.body[-1].value.keys, right.body[-1].value.values)}
        for key in before.keys() - {'physical_consistency', 'area_closure_relative_tolerance', 'inventory_interpretation'}:
            assert dump(before[key]) == dump(after[key]), key
    else:
        before, after = functions(old), functions(new)
        for name_ in before.keys() - {'write_json', '_run_job_locked'}:
            assert dump(before[name_]) == dump(after[name_]), name_
        for method in ('solve', 'save'):
            calls = lambda tree: [dump(n) for n in ast.walk(tree) if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute) and n.func.attr == method]
            assert calls(old) == calls(new), f'GUI numerical {method} calls changed'
    files.append({'file': name, 'current_sha256': hashlib.sha256(file.read_bytes()).hexdigest(),
                  'ast_identical': dump(old) == dump(new)})

name = 'tools/recover_annular_reference.py'
old, new = ast.parse(previous(name)), ast.parse((ROOT/name).read_text(encoding='utf-8-sig'))
before, after = functions(old), functions(new)
assert before.keys() == after.keys()
for key in before.keys() - {'physical_checks'}:
    assert dump(before[key]) == dump(after[key]), key
left, right = before['physical_checks'], after['physical_checks']
# The archive calculations/loops are unchanged; only the final result metadata differs.
assert [dump(n) for n in left.body[:-1]] == [dump(n) for n in right.body[:-1]]

receipt = {'schema': 'openstream-annular-source-scope-audit-v1', 'baseline_commit': BASE,
    'numerical_and_closure_module_ast_unchanged_except_diagnostic_metadata': True,
    'all_solver_convergence_methods_ast_unchanged': True,
    'annular_diagnostic_arithmetic_ast_unchanged': True,
    'archive_recovery_array_functions_and_area_arithmetic_ast_unchanged': True,
    'gui_solver_calls_ast_unchanged': True, 'files': files,
    'permitted_changes': ['annular diagnostic classification, explanatory text and indeterminate flag',
        'GUI report status/presentation', 'bounded PermissionError retry for Windows progress JSON replacement',
        'archive diagnostic metadata'],
    'scope': 'Compared current source with the recorded pre-revision commit. This verifies change scope, not original MATLAB numerical equivalence or model validation.'}
output = Path(__file__).with_name('source_scope_audit.json')
with output.open('x', encoding='utf-8') as stream:
    json.dump(receipt, stream, indent=2)
    stream.write('\n')
print(f'{len(files)} native Python modules audited; numerical equations and stopping logic unchanged.')
