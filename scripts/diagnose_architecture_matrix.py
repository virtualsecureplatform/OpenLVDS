#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extend completed architecture DC observations to all three restoration stages."""
import argparse
import hashlib
import json
from pathlib import Path

from diagnose_architecture_rate import measure, observed_devices
from dll_measurements import read_wave
from receiver_static_diagnosis import capture_manifest
import receiver_architecture_matrix as matrix

ROOT = Path(__file__).resolve().parents[1]


def diagnose(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_architecture_matrix'):
        raise ValueError('Use a completed receiver architecture DC matrix')
    manifest = json.loads((root/'manifest.json').read_text()); children = manifest['identity']['children']
    if (len(children) != 15 or not (root/'summary.json').is_file() or
        any(not (ROOT/c['root']/'summary.json').is_file() for c in children)):
        raise ValueError('Complete all fifteen DC cases before expanded observations')
    report = matrix.run(root)  # Completed scientific remeasurement only.
    if report.get('required') != 15 or report.get('dc_all_passed') is not True:
        raise ValueError('The original DC/current/six-device screen must pass first')
    results = []; paths = [root/'manifest.json', root/'summary.json']
    for child in children:
        folder = ROOT/child['root']; wave, headers = read_wave(folder/'bench.cir.prn')
        # Every original point and every transition is retained, including
        # startup. No interpolation, time mask or new simulation is used.
        observations = measure(wave, headers, observed_devices((folder/'source.spice').read_text()))
        observations['scope'] = ('Full original 144 ns DC-point transient; six decision/bias MOS and six downshift/restoration MOS. '
            'The 1.95 V guard is a project screen, not a foundry rating. Remaining frontend/bias stress and dynamic/native qualification remain open.')
        results.append(dict(case=child['case'], process=child['process'], temperature=child['temperature'], observations=observations))
        paths.extend(folder/n for n in ['manifest.json', 'summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn'])
    paths.extend([Path(__file__), ROOT/'scripts/diagnose_architecture_rate.py',
                  ROOT/'scripts/receiver_architecture_observations.py', ROOT/'scripts/layout.py'])
    identity = dict(matrix=str(root.relative_to(ROOT)), inputs={str(p.relative_to(ROOT)): matrix.sha(p) for p in paths})
    out = root/'completed_observations'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    result = dict(identity=identity, qualified_phy=False, required=15,
        observed_twelve_device_guard_all_passed=all(r['observations']['observed_thin_guard_passed'] for r in results), results=results)
    capture_manifest(out/'summary.json', result)
    return out, result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('matrix', type=Path); a = p.parse_args()
    out, result = diagnose(a.matrix.resolve())
    print(out/'summary.json', flush=True)
    for r in result['results']:
        o = r['observations']; tail = o['devices']['XCT']
        print(json.dumps(dict(case=r['case'], observed_thin_guard_passed=o['observed_thin_guard_passed'],
            tail_current=o['currents']['tail'], minimum_tail_absolute_vds_v=tail['minimum_absolute_vds_v'],
            maximum_observed_thin_terminal_v=max(d['maximum_terminal_difference']['voltage_v'] for d in o['devices'].values() if d['thin_guard_applies']))), flush=True)
