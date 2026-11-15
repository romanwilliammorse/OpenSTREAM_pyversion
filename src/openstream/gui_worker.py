"""Isolated GUI job runner. Calls the unchanged native numerical API."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import traceback
import zipfile

import numpy as np


class JobCancelled(Exception):
    pass


def write_json(path, value):
    from .output import portable_json
    path = Path(path)
    tmp = path.with_suffix(path.suffix + '.tmp')
    def scalar(obj):
        if isinstance(obj, np.generic): return obj.item()
        raise TypeError(f'Cannot serialize {type(obj).__name__}')
    tmp.write_text(json.dumps(portable_json(value), indent=2, allow_nan=False, default=scalar) + '\n', encoding='utf-8')
    # A Windows reader can briefly hold the destination open during polling.
    # Retry only that replace failure, preserving the final error if it persists.
    for attempt in range(10):
        try:
            os.replace(tmp, path)
            break
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(.02)


def mixture_checks(solver):
    """Integrated steady checks, with explicit engineering acceptance thresholds.

    Energy uses the upstream enthalpy equation (not total energy). Momentum
    reports the solver's discrete equation residual; it is not experiment.
    """
    from .output import balances
    b = balances(solver)
    s = solver.mixture[-1]
    checks = {
        'finite_primary_arrays': all(np.isfinite(v).all() for v in (s.W, s.P, s.H, s.U())),
        'positive_pressure_density': b['minimum_pressure_Pa'] > 0 and b['minimum_density_kg_m3'] > 0,
        'void_fraction_bounds': bool(np.all((s.VF() >= -1e-12) & (s.VF() <= 1+1e-12))),
        'mass_balance': b['steady_mass_max_deviation_kg_s'] <= max(1e-10, abs(s.W[0])*1e-6),
        'enthalpy_balance': b['steady_energy_relative_error'] <= 1e-6,
        'discrete_momentum_balance': b['discrete_momentum_max_residual_Pa'] <= max(1e-6, solver.inputSet.options.ERRORP),
    }
    return {**b, 'checks': checks, 'physical_consistency': all(checks.values()),
            'acceptance': {'mass': 'max(1e-10 kg/s, 1e-6 * inlet mass flow)',
                           'enthalpy': 'relative error <= 1e-6 (denominator max(abs(Q),1 W))',
                           'momentum': 'max(1e-6 Pa, input ERRORP)', 'void_fraction': '[-1e-12, 1+1e-12]'},
            'scope': 'Steady integral enthalpy/mass balance, discrete momentum and basic bounds; not experimental validation.'}


def physical_report(diagnostics):
    """Display descriptive annular closure without a physical-pass claim."""
    ok = diagnostics.get('physical_consistency')
    informational = diagnostics.get('phase_volume_closure_role') == 'informational'
    if ok is False:
        message = 'Physical consistency checks failed. Inspect diagnostics; numerical agreement does not establish physical validity.'
    elif ok is True:
        message = 'Implemented consistency checks passed; experimental validation not performed.'
    elif informational:
        message = ('Phase-volume closure is informational for this annular framework and does not change solver acceptance. '
                   'Residual values remain available; physical validation is not established.')
    else:
        message = 'Consistency cannot be assessed on an applicable physical domain; inspect diagnostics.'
    return {'status': ('informational' if informational else 'not_checked') if ok is None else 'passed' if ok else 'failed',
            'diagnostics': diagnostics, 'message': message}


def run_job(directory):
    from .gui_lock import FileLock
    directory = Path(directory).resolve()
    with FileLock(directory/'worker.lock'):
        return _run_job_locked(directory)


def _run_job_locked(directory):
    from . import MixtureSolver, TwoFluidSolver, ThreeFieldSolver, FourFieldSolver
    from .gui_schema import validate_payload, assess_payload, framework_name
    from .gui_reference import compare_reference
    directory = Path(directory).resolve()
    state_path = directory/'status.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    if state['status'] in ('completed', 'failed', 'cancelled'): return 1
    def update(**kw):
        state.update(kw)
        write_json(state_path, state)
    try:
        def check_cancel():
            if (directory/'cancel.request').exists(): raise JobCancelled()
        check_cancel()
        payload = json.loads((directory/'submitted_inputs.json').read_text(encoding='utf-8'))
        inputs = validate_payload(payload)
        # The actual submitted config is the run input source. Original baseline
        # files are preserved separately by the schema/baseline provenance.
        inputs.source_files = [str(directory/'submitted_inputs.json')]
        framework = framework_name(payload['framework'])
        update(status='running', phase='Preparing thermophysical properties')
        def progress(record):
            check_cancel()
            state['progress'].append(record)
            update(phase=f"{record.get('framework', framework)}: {record.get('phase', 'solving')}")
        constructors = {'Mixture': MixtureSolver, 'TwoFluid': TwoFluidSolver,
                        'ThreeField': ThreeFieldSolver, 'FourField': FourFieldSolver}
        if framework == 'Mixture':
            solver = MixtureSolver(inputs).solve(lambda r: progress({**r, 'framework': 'Mixture'}))
        else:
            precursor = MixtureSolver(inputs).solve(lambda r: progress({**r, 'framework': 'Mixture precursor'}))
            solver = constructors[framework](inputs, mix_solver=precursor).solve(progress)
        update(phase='Saving numerical arrays and plots', converged=bool(solver.converged))
        check_cancel()
        output = directory/'output'
        solver.save(output)
        check_cancel()
        reference = (compare_reference(framework, output) if assess_payload(payload)['is_reference'] else
                     {'status': 'not_compared', 'message': 'Custom inputs differ from the archived baseline; no equivalence claim.'})
        diagnostics = mixture_checks(solver) if framework == 'Mixture' else solver.diagnostics()
        physical = physical_report(diagnostics)
        report = {'reference': reference, 'physical': physical, 'converged': bool(solver.converged),
                  'baseline': assess_payload(payload), 'experimental_validation': 'not performed',
                  'framework': framework, 'submitted_inputs': payload}
        write_json(output/'gui_verification.json', report)
        # Supplement the generic output metadata with this run's actual checks.
        metadata_path = output/'metadata.json'
        metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
        metadata['gui_verification'] = report
        metadata['verification'] = {'archived_baseline': reference, 'experimental_validation': 'not performed'}
        write_json(metadata_path, metadata)
        with zipfile.ZipFile(directory/'results.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(directory/'submitted_inputs.json', 'submitted_inputs.json')
            for p in sorted(output.rglob('*')):
                if p.is_file(): archive.write(p, str(p.relative_to(directory)))
        names = ['submitted_inputs.json', 'results.zip'] + [p.relative_to(directory).as_posix() for p in sorted(output.rglob('*')) if p.is_file()]
        update(status='completed', phase='Completed', reference=reference, physical=physical,
               files=[{'name': n, 'url': f"/files/{state['id']}/{n}"} for n in names],
               finished_at=datetime.now(timezone.utc).isoformat())
        return 0
    except JobCancelled:
        update(status='cancelled', phase='Cancelled', error=None,
               finished_at=datetime.now(timezone.utc).isoformat())
        return 0
    except Exception as exc:
        traceback.print_exc()
        update(status='failed', phase='Failed', error=f'{type(exc).__name__}: {exc}',
               finished_at=datetime.now(timezone.utc).isoformat(),
               files=[{'name': n, 'url': f"/files/{state['id']}/{n}"} for n in ('submitted_inputs.json', 'worker.log')])
        return 1


if __name__ == '__main__':
    raise SystemExit(run_job(sys.argv[1]))
