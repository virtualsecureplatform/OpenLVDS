#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Pilot and qualify the single calculated 1/3/8-cap36 source candidate."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re

import driver_geometric_shape as recipe
import driver_source_campaign as campaign
import driver_stage0_balance as balance
import qualify_stronger_driver_shape as previous
from receiver_static_diagnosis import capture_manifest
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
sha = campaign.sha


def prepare_controls(controls):
    if not controls.is_relative_to(ROOT / 'build/diagnostics/driver_stage0_balance'):
        raise ValueError('Use the complete first-buffer tradeoff controls')
    cm = previous.pilot.bound(controls)
    receipt = json.loads((controls / 'summary.json').read_text())
    if (receipt.get('controls_passed') is not False or receipt.get('manifest_sha256') != sha(controls / 'manifest.json') or
            [t['id'] for t in cm['tasks']] != ['ss_25_negative_op', 'ff_40_negative_op']):
        raise ValueError('Require the measured SS/FF sizing tradeoff')
    paths = [controls / 'manifest.json', controls / 'summary.json']
    rows = []
    for task in cm['tasks']:
        folder = controls / task['id']
        row = json.loads((folder / 'summary.json').read_text())
        files = dict(task['files'], **row['files'])
        if (row.get('returncode') != 0 or row.get('manifest_sha256') != sha(controls / 'manifest.json') or
                any(sha(folder / n) != h for n, h in files.items()) or balance.measure(folder) != row['metrics']):
            raise ValueError('First-buffer tradeoff evidence changed')
        paths += [folder / n for n in set(files) | {'summary.json'}]
        rows.append(row)
    if rows != receipt['results'] or not rows[0]['metrics']['common_mode_pp_v'] <= .150 < rows[1]['metrics']['common_mode_pp_v']:
        raise ValueError('First-buffer tradeoff changed')
    parent = ROOT / cm['identity']['parent']
    previous.check_variant(parent)
    m = previous.pilot.bound(parent)
    report = json.loads((parent / 'summary.json').read_text())
    if (report.get('required_cases') != 30 or report.get('required_pvt') != 15 or
            report.get('manifest_sha256') != sha(parent / 'manifest.json')):
        raise ValueError('Complete the original stronger source matrix')
    paths += [parent / 'manifest.json', parent / 'summary.json']
    for process, temp in recipe.POINTS:
        for op in campaign.reference.shape.CASES:
            task = next(t for t in m['tasks'] if t['id'] == f'{process}_{temp}_{op}')
            _, files = previous.pilot.completed(parent, task, previous.pilot.VARIANT)
            paths += files
    inputs = dict(cm['identity']['inputs'], **m['identity']['inputs'])
    inputs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    code = dict(cm['identity']['code'], **m['identity']['code'])
    return parent, inputs, code


def write(parent, inputs, code, source, stage):
    req = json.loads((ROOT / 'requirements.json').read_text())
    points = recipe.POINTS if stage == 'pilot' else list(itertools.product(req['process_corners'], req['temperatures_c']))
    for name in [Path(__file__).name, 'driver_geometric_shape.py', 'driver_source_campaign.py']:
        code[name] = sha(ROOT / 'scripts' / name)
    inputs = dict(inputs, **{'requirements.json': sha(ROOT / 'requirements.json')})
    identity = dict(parent=str(parent.relative_to(ROOT)), inputs=inputs, code=code,
        simulator=campaign.provenance(), recipe=recipe.NEW, stage=stage,
        points=[list(p) for p in points], scope='Calculated 1/3/8 taper with uniform 36 um '
        'MIM output caps. First gate load remains the original one-unit load; later '
        'fanouts are 3 and 8/3. Fixed original bridge, 110:1 mirror, CMFB, rails, '
        'reference, 100 ohm/2 pF per pin and full 80 ns/1 ps alternating stimulus. '
        'Both initial polarities and fresh DC calibration at every declared PVT. '
        'Six-case TT25/SS25/FF40 pilot before all thirty full source cases. '
        'No physical, power/stress, native or PHY admission.')
    namespace = 'driver_source_pilot' if stage == 'pilot' else 'driver_shape_source'
    out = ROOT / 'build/diagnostics' / namespace / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    tasks = campaign.tasks(points)
    for task in tasks:
        old, folder = parent / ('tt_25_' + task['op']), out / task['id']
        folder.mkdir(exist_ok=True)
        deck = campaign.reference.fixture((old / 'bench.cir').read_text(), old, folder, task)
        probes = re.findall(r'V\(([^)]+)\)', re.search(r'(?im)^\.print tran[^\n]+', deck)[0])
        ProbeNetwork(source).validate(deck, probes)
        for name, body in [('source.spice', source), ('bench.cir', deck)]:
            p = folder / name
            if p.exists() and p.read_text() != body:
                raise ValueError('Prepared geometric candidate changed')
            if not p.exists():
                p.write_text(body)
        task['files'] = {n: sha(folder / n) for n in ['source.spice', 'bench.cir']}
    capture_manifest(out / 'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return out


def prepare_pilot(controls):
    parent, inputs, code = prepare_controls(controls)
    return write(parent, inputs, code, recipe.transform((parent / 'tt_25_negative_op/source.spice').read_text()), 'pilot')


def prepare_full(pilot):
    m, proofs = campaign.verified(pilot, recipe)
    if m['identity']['stage'] != 'pilot':
        raise ValueError('Use a complete passing six-case pilot')
    return write(pilot, dict(m['identity']['inputs'], **proofs), dict(m['identity']['code']),
                 (pilot / 'tt_25_negative_op/source.spice').read_text(), 'full')


def verify(out):
    m, proofs = campaign.verified(out, recipe)
    if m['identity']['stage'] != 'full' or len(m['tasks']) != 30:
        raise ValueError('Full fifteen-point source qualification required')
    proofs.update(m['identity']['inputs'])
    proofs.update({'scripts/' + n: h for n, h in m['identity']['code'].items()})
    report = dict(campaign=str(out.relative_to(ROOT)), proofs=proofs, source_waveform_ready=True,
        source_sha256=sha(out / 'tt_25_negative_op/source.spice'), required_cases=30, required_pvt=15,
        physical_admission=False, qualified_phy=False, scope=m['identity']['scope'])
    dest = ROOT / 'build/diagnostics/driver_shape_source_verification' / hashlib.sha256(json.dumps(report, sort_keys=True).encode()).hexdigest()[:16]
    dest.mkdir(parents=True, exist_ok=True)
    capture_manifest(dest / 'summary.json', report)
    return dest / 'summary.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare-pilot', 'prepare-full', 'run', 'verify'])
    parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    p = args.artifact.resolve()
    if args.action == 'prepare-pilot':
        print(prepare_pilot(p), flush=True)
    elif args.action == 'prepare-full':
        print(prepare_full(p), flush=True)
    elif args.action == 'run':
        campaign.run(p, recipe)
    else:
        print(verify(p), flush=True)
