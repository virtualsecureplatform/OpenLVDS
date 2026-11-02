#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure a complete shaped-driver source matrix before a physical handoff."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

import qualify_driver_output_shape_source as source
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = source.sha


def verify(campaign):
    if not campaign.is_relative_to(ROOT / 'build/diagnostics/driver_shape_source'):
        raise ValueError('Use the complete shaped-driver source matrix')
    manifest = json.loads((campaign / 'manifest.json').read_text())
    identity = manifest['identity']
    stamp = sha(campaign / 'manifest.json')
    req = json.loads((ROOT / 'requirements.json').read_text())
    tasks = manifest['tasks']
    if (campaign.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or source.provenance() != identity['simulator']):
        raise ValueError('Source matrix identity/runtime changed')
    if [{k: v for k, v in t.items() if k != 'files'} for t in tasks] != source.cases(req):
        raise ValueError('Require all thirty source cases in original order')
    proofs = dict(identity['inputs'])
    proofs.update({'scripts/' + name: value for name, value in identity['code'].items()})
    proofs[str((campaign / 'manifest.json').relative_to(ROOT))] = stamp
    if any(sha(ROOT / name) != value for name, value in proofs.items()):
        raise ValueError('Source matrix context changed')
    paths = [campaign / 'summary.json'] + [campaign / t['id'] / 'summary.json' for t in tasks]
    if any(not p.is_file() for p in paths):
        raise ValueError('Complete all thirty source cases before physical handoff')
    proofs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    aggregate = json.loads(paths[0].read_text())
    if (aggregate.get('source_waveform_matrix_passed') is not True or
            aggregate.get('required_cases') != 30 or aggregate.get('required_pvt') != 15 or
            aggregate.get('passed_pvt') != 15 or aggregate.get('manifest_sha256') != stamp):
        raise ValueError('All fifteen source waveform PVT points must pass')
    results = []
    reference_source = None
    for task in tasks:
        folder = campaign / task['id']
        row = json.loads((folder / 'summary.json').read_text())
        if (row.get('case') != task['id'] or row.get('task') != task['op'] or
                row.get('returncode') != 0 or row.get('error') is not None or
                row.get('manifest_sha256') != stamp or row.get('metrics') is None or
                row.get('initial_dc') is None):
            raise ValueError('Source case incomplete or failed: ' + task['id'])
        if (set(task['files']) != {'source.spice', 'bench.cir'} or
                set(row['files']) != {'bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log'}):
            raise ValueError('Source case evidence missing: ' + task['id'])
        files = dict(task['files'])
        files.update(row['files'])
        if any(sha(folder / name) != value for name, value in files.items()):
            raise ValueError('Source case evidence changed: ' + task['id'])
        proofs.update({str((folder / name).relative_to(ROOT)): value for name, value in files.items()})
        model = (folder / 'source.spice').read_bytes()
        if reference_source is None:
            reference_source = model
        if model != reference_source:
            raise ValueError('Source circuit differs across PVT cases')
        wave, headers = source.shape.read_wave(folder / 'bench.cir.prn')
        if (source.shape.pilot.measure(folder, 'taper_16_32_64') != row['metrics'] or
                source.shape.initial_dc(wave, headers) != row['initial_dc']):
            raise ValueError('Source case remeasurement changed: ' + task['id'])
        results.append(row)
    points = []
    for process, temp in itertools.product(req['process_corners'], req['temperatures_c']):
        rows = [r for r in results if r['case'] in
                [f'{process}_{temp}_{op}' for op in source.shape.CASES]]
        low, high = [r['initial_dc']['differential_v'] for r in rows]
        waveforms = {r['task']: source.shape.transitions(
            *source.shape.read_wave(campaign / r['case'] / 'bench.cir.prn'), low, high)
            for r in rows}
        points.append(dict(process=process, temperature=temp,
                           passed=source.pair_checks(rows, waveforms, req),
                           calibrated_transitions=waveforms, error=None))
    if (results != aggregate['results'] or points != aggregate['pvt'] or
            not all(p['passed'] for p in points)):
        raise ValueError('Source aggregate differs from complete waveform remeasurement')
    if any(sha(ROOT / name) != value for name, value in proofs.items()):
        raise ValueError('Source evidence changed during verification')
    powers = {rail: [r['metrics']['mean_supply_power_w'][rail] for r in results]
              for rail in ['io', 'digital']}
    stress = [device[key] for r in results for device in r['metrics']['added_mos_stress']
              for key in ['max_abs_vgs', 'max_abs_vgd', 'max_abs_vds', 'max_abs_vbs']]
    return dict(campaign=str(campaign.relative_to(ROOT)), proofs=proofs,
        source_sha256=hashlib.sha256(reference_source).hexdigest(),
        source_waveform_ready=True, required_cases=30, required_pvt=15,
        mean_supply_power_range_w={rail: dict(min=min(v), max=max(v)) for rail, v in powers.items()},
        maximum_added_device_terminal_difference_v=max(stress),
        qualified_phy=False, physical_admission=False,
        scope='Read-only full source waveform verification. All thirty complete cases '
              'are remeasured, including both DC calibration polarities at every PVT. '
              'Power and added-MOS voltages are observations without a new acceptance '
              'limit. Device-stress review, compact layout, DRC/LVS, native PVT, '
              'channel/capture and complete PHY qualification remain required.')


def record(campaign):
    report = verify(campaign)
    report['producer_sha256'] = sha(Path(__file__))
    fingerprint = hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()[:16]
    out = ROOT / 'build/diagnostics/driver_shape_source_verification' / fingerprint
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'summary.json', report)
    return out / 'summary.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    args = parser.parse_args()
    print(record(args.campaign.resolve()), flush=True)
