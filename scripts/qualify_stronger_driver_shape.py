#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Full source PVT for the stronger taper, gated by complete TT25/FF0 pilots."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path

import probe_stronger_driver_shape as pilot
import qualify_driver_output_shape_source as matrix
import verify_driver_shape_source as verification
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = matrix.sha


def pilot_ready(parent):
    if not parent.is_relative_to(ROOT / 'build/diagnostics/stronger_driver_shape'):
        raise ValueError('Use the completed stronger-driver pilot')
    m = pilot.bound(parent)
    if [{k: v for k, v in t.items() if k != 'files'} for t in m['tasks']] != pilot.tasks():
        raise ValueError('Require both polarities at TT25 and FF0')
    paths = [parent / 'summary.json'] + [parent / t['id'] / 'summary.json' for t in m['tasks']]
    if any(not p.is_file() for p in paths):
        raise ValueError('Complete all four stronger-driver pilot cases before source PVT')
    report = json.loads((parent / 'summary.json').read_text())
    if report.get('source_pilot_passed') is not True or report.get('manifest_sha256') != sha(parent / 'manifest.json'):
        raise ValueError('Both stronger-driver pilot PVT points must pass')
    proofs = {str(p.relative_to(ROOT)): sha(p) for p in paths + [parent / 'manifest.json']}
    rows = []
    source = None
    for task in m['tasks']:
        row, files = pilot.completed(parent, task, pilot.VARIANT)
        folder = parent / task['id']
        wave, headers = matrix.shape.read_wave(folder / 'bench.cir.prn')
        if matrix.shape.initial_dc(wave, headers) != row['initial_dc']:
            raise ValueError('Stronger-driver DC remeasurement changed')
        model = (folder / 'source.spice').read_bytes()
        if source is not None and model != source:
            raise ValueError('Stronger pilot circuits differ')
        source = model
        rows.append(row)
        proofs.update({str(p.relative_to(ROOT)): sha(p) for p in files})
    points = []
    req = json.loads((ROOT / 'requirements.json').read_text())
    for process, temp in [('tt', 25), ('ff', 0)]:
        pair = [r for r in rows if r['case'].startswith(f'{process}_{temp}_')]
        low, high = [r['initial_dc']['differential_v'] for r in pair]
        waveforms = {r['task']: matrix.shape.transitions(
            *matrix.shape.read_wave(parent / r['case'] / 'bench.cir.prn'), low, high) for r in pair}
        points.append(dict(process=process, temperature=temp,
            passed=matrix.pair_checks(pair, waveforms, req), calibrated_transitions=waveforms))
    if rows != report['results'] or points != report['pvt'] or not all(p['passed'] for p in points):
        raise ValueError('Stronger pilot waveform remeasurement changed or failed')
    if any(sha(ROOT / n) != h for n, h in proofs.items()):
        raise ValueError('Stronger pilot changed during remeasurement')
    return m, proofs


@contextmanager
def stronger_measurements():
    # The frozen matrix asks its measurement helper for the first taper's
    # metadata. Route that single call to the declared 1/4/8 unit counts in
    # this process only. Devices, traces, reference checks and limits stay
    # unchanged. The adapter is bound in each new campaign's code identity.
    original = matrix.shape.pilot.measure

    def measure(folder, variant):
        if variant != 'taper_16_32_64':
            raise ValueError('Unexpected frozen matrix measurement variant')
        return original(folder, pilot.VARIANT)

    matrix.shape.pilot.measure = measure
    try:
        yield
    finally:
        matrix.shape.pilot.measure = original


def prepare(parent):
    m, proofs = pilot_ready(parent)
    previous = m['identity']
    inputs = dict(previous['inputs'], **proofs)
    inputs['requirements.json'] = sha(ROOT / 'requirements.json')
    code = dict(previous['code'])
    for name in [Path(__file__).name, 'qualify_driver_output_shape_source.py', 'verify_driver_shape_source.py']:
        code[name] = sha(ROOT / 'scripts' / name)
    identity = dict(parent=str(parent.relative_to(ROOT)), inputs=inputs, code=code,
        simulator=matrix.provenance(), variant=pilot.VARIANT,
        scope='All thirty stronger-taper source cases: five processes x 0/25/40 C x '
              'two initial logic polarities, after complete passing TT25/FF0 pilots. '
              'Same 30x30 um output caps, 110:1 mirror, bridge, CMFB, fixed rails, '
              'reference, 100 ohm/2 pF per pin, 80 ns/1 ps fixture and original waveform '
              'limits. This bound adapter measures the actual 1/4/8 parallel-unit '
              'counts using the frozen common analyzers. Source waveform qualification '
              'only; no stress/power, physical/native or PHY admission.')
    out = ROOT / 'build/diagnostics/driver_shape_source' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    tasks = matrix.cases(json.loads((ROOT / 'requirements.json').read_text()))
    source = (parent / 'tt_25_negative_op/source.spice').read_text()
    for task in tasks:
        old, folder = parent / ('tt_25_' + task['op']), out / task['id']
        folder.mkdir(exist_ok=True)
        deck = matrix.fixture((old / 'bench.cir').read_text(), old, folder, task)
        for name, body in [('source.spice', source), ('bench.cir', deck)]:
            p = folder / name
            if p.exists() and p.read_text() != body:
                raise ValueError('Prepared stronger source matrix changed')
            if not p.exists():
                p.write_text(body)
        task['files'] = {n: sha(folder / n) for n in ['source.spice', 'bench.cir']}
    capture_manifest(out / 'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return out


def check_variant(campaign):
    m = pilot.bound(campaign)
    if m['identity'].get('variant') != pilot.VARIANT:
        raise ValueError('Require the declared stronger source matrix')


def run(campaign):
    check_variant(campaign)
    with stronger_measurements():
        matrix.run(campaign, jobs=2)


def verify(campaign):
    check_variant(campaign)
    with stronger_measurements():
        report = verification.verify(campaign)
    report.update(variant=pilot.VARIANT, analysis_adapter_sha256=sha(Path(__file__)))
    out = ROOT / 'build/diagnostics/driver_shape_source_verification' / hashlib.sha256(
        json.dumps(report, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'summary.json', report)
    return out / 'summary.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'verify'])
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.artifact.resolve()), flush=True)
    elif args.action == 'run':
        run(args.artifact.resolve())
    else:
        print(verify(args.artifact.resolve()), flush=True)
