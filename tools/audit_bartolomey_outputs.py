"""Independently recompute pilot CSV errors, geometry and energy from saved arrays."""
import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    args = parser.parse_args(argv)
    report = json.loads((args.campaign/'report.json').read_text())
    checked, point_count = [], 0
    for name, result in report['runs'].items():
        directory = args.campaign/name
        if result['execution'] != 'completed':
            continue  # Preserved explicitly in the independent audit counts.
        with (directory/'paired_measurements.csv').open(encoding='utf-8', newline='') as f:
            points = list(csv.DictReader(f))
        valid = [p for p in points if p['status'] == 'compared']
        errors = np.asarray([float(p['predicted'])-float(p['measured']) for p in valid])
        assert all(p['error_unit'] == '1' and p['void_fraction_unit'] == '1' for p in points)
        assert all(p['coordinate_unit'] == result['comparison']['coordinate_unit'] for p in points)
        np.testing.assert_allclose(errors, [float(p['error']) for p in valid], rtol=0, atol=1e-15)
        if len(errors):
            actual = result['comparison']['summary']
            np.testing.assert_allclose([np.mean(errors), np.mean(np.abs(errors)), np.sqrt(np.mean(errors**2))],
                                       [actual['bias'], actual['mae'], actual['rmse']], rtol=1e-14, atol=1e-15)
        inputs = json.loads((directory/'submitted_inputs.json').read_text())
        bc, geometry = inputs['bc'][0], inputs['geometry']
        with np.load(directory/'numerical/results.npz') as arrays:
            z, w, h, heat = arrays['Z'], arrays['W'][-1], arrays['H'][-1], arrays['HFLUX'][-1]
            np.testing.assert_allclose([z[0], z[-1]], [0, geometry['LENGTH']], rtol=0, atol=1e-14)
            wall_power = float(np.sum(heat[1:] @ np.asarray(geometry['PERIM']))*(z[1]-z[0]))
            gain = float(w[0]*(h[-1]-h[0]))
            np.testing.assert_allclose(wall_power, bc['POWER'], rtol=1e-12, atol=1e-8)
            np.testing.assert_allclose(gain, result['physical']['balances']['steady_enthalpy_gain_W'], rtol=1e-14, atol=1e-8)
            assert abs(gain-wall_power)/max(abs(wall_power), 1) <= 1e-6
        checked.append(name); point_count += len(valid)
    receipt = {'status': 'passed', 'completed_runs_checked': len(checked), 'paired_measurements_checked': point_count,
               'failed_execution_runs_not_audited': [k for k, v in report['runs'].items() if v['execution'] != 'completed'],
               'checks': ['CSV signed errors and units', 'independent NumPy bias/MAE/RMSE', 'saved axial endpoints',
                          'integrated saved heat flux equals prescribed power', 'saved steady transported-enthalpy balance'],
               'source_report_sha256': hashlib.sha256((args.campaign/'report.json').read_bytes()).hexdigest(),
               'scope': 'Artifact arithmetic and dimensional consistency, not experimental validation or MATLAB equivalence.'}
    target = args.campaign/'independent_output_audit.json'
    with target.open('x', encoding='utf-8') as f:
        json.dump(receipt, f, indent=2); f.write('\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
