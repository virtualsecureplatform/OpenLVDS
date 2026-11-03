#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify the actual lead-compensated schematic after its ideal-wire diagnostic."""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import re
import sys

import driver_geometric_shape as geometric
import driver_source_campaign as campaign
import probe_driver_cmfb_lead as lead
from receiver_static_diagnosis import capture_manifest
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
NEW = lead.NEW + '_actual_schematic'
POINTS = lead.POINTS
sha = campaign.sha


def measure(folder):
    result = geometric.measure(folder)
    result['scope'] = ('Actual 1/3/8-cap36 schematic with one direct and five '
        'series-resistor compensation MIMs; source waveform and observed '
        'supply/MOS voltages only, no native or PHY admission.')
    return result


def require_stage(manifest, stage):
    if manifest['identity']['stage'] != stage:
        raise ValueError('Require the ' + stage + ' campaign, independently verified')


def design_model(manifest, original):
    proposal = ROOT / manifest['identity']['design_proposal']
    relative = str(proposal.relative_to(ROOT))
    if manifest['identity']['inputs'].get(relative) != sha(proposal):
        raise ValueError('Actual schematic proposal is not bound to the diagnostic')
    source = lead.transform(original, 'lvds_cmfb')
    if proposal.read_text() != source:
        raise ValueError('Actual schematic differs from the single calculated proposal')
    return source


def write(parent, inputs, code, source, stage):
    if stage not in ['pilot', 'full']:
        raise ValueError('Unknown source qualification stage')
    req = json.loads((ROOT / 'requirements.json').read_text())
    points = POINTS if stage == 'pilot' else list(itertools.product(
        req['process_corners'], req['temperatures_c']))
    code = dict(code)
    for name in [Path(__file__).name, 'driver_source_campaign.py',
                 'driver_geometric_shape.py', 'probe_driver_cmfb_lead.py']:
        code[name] = sha(ROOT / 'scripts' / name)
    inputs = dict(inputs, **{'requirements.json': sha(ROOT / 'requirements.json')})
    identity = dict(parent=str(parent.relative_to(ROOT)), recipe=NEW,
        stage=stage, points=[list(p) for p in points], inputs=inputs,
        code=code, simulator=campaign.provenance(), scope=
        'Actual original-design device geometry with one direct and five '
        'series-resistor CMFB MIMs, W=.35/L=1.25 PDK poly resistor. '
        'The ideal-wire matched-device diagnostic must pass before this '
        'six-case source pilot, then all thirty source PVT/polarity cases. '
        'Fixed 3.3/1.8 V, 1.2 V reference, 35 uA source bias, 100 ohm '
        'and 2 pF/pin, original complete 80 ns/1 ps fixtures and fresh '
        'DC calibration. Source waveform readiness only; fresh physical, '
        'native, long-component and coupled PHY gates remain required.')
    namespace = 'driver_source_pilot' if stage == 'pilot' else 'driver_shape_source'
    out = ROOT / 'build/diagnostics' / namespace / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    tasks = campaign.tasks(points)
    for task in tasks:
        old = parent / ('tt_25_' + task['op'])
        folder = out / task['id']
        folder.mkdir(exist_ok=True)
        deck = campaign.reference.fixture((old / 'bench.cir').read_text(), old, folder, task)
        prints = re.findall(r'(?im)^\.print tran[^\n]+', deck)
        if len(prints) != 1:
            raise ValueError('Require the original source observations')
        probes = re.findall(r'V\(([^)]+)\)', prints[0])
        ProbeNetwork(source).validate(deck, probes)
        for name, body in [('source.spice', source), ('bench.cir', deck)]:
            path = folder / name
            if path.exists() and path.read_text() != body:
                raise ValueError('Prepared lead source fixture changed')
            if not path.exists():
                path.write_text(body)
        task['files'] = {n: sha(folder / n) for n in ['source.spice', 'bench.cir']}
    capture_manifest(out / 'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return out


def prepare_pilot(diagnostic, original):
    dm, diagnostic_proofs = campaign.verified(diagnostic, lead)
    require_stage(dm, 'pilot')
    sm, source_proofs = campaign.verified(original, geometric)
    require_stage(sm, 'full')
    source = design_model(dm, (original / 'tt_25_negative_op/source.spice').read_text())
    return write(original, {**dm['identity']['inputs'], **sm['identity']['inputs'],
        **diagnostic_proofs, **source_proofs},
        dict(dm['identity']['code'], **sm['identity']['code']), source, 'pilot')


def prepare_full(pilot):
    m, proofs = campaign.verified(pilot, sys.modules[__name__])
    require_stage(m, 'pilot')
    return write(pilot, dict(m['identity']['inputs'], **proofs), m['identity']['code'],
        (pilot / 'tt_25_negative_op/source.spice').read_text(), 'full')


def verify(out):
    m, proofs = campaign.verified(out, sys.modules[__name__])
    require_stage(m, 'full')
    if len(m['tasks']) != 30 or len(m['identity']['points']) != 15:
        raise ValueError('Require all thirty actual schematic cases')
    proofs.update(m['identity']['inputs'])
    proofs.update({'scripts/' + n: h for n, h in m['identity']['code'].items()})
    report = dict(campaign=str(out.relative_to(ROOT)), proofs=proofs,
        recipe=NEW, source_waveform_ready=True,
        source_sha256=sha(out / 'tt_25_negative_op/source.spice'),
        required_cases=30, required_pvt=15, physical_admission=False,
        qualified_phy=False, scope=m['identity']['scope'])
    dest = ROOT / 'build/diagnostics/driver_cmfb_lead_source_verification' / hashlib.sha256(
        json.dumps(report, sort_keys=True).encode()).hexdigest()[:16]
    dest.mkdir(parents=True, exist_ok=True)
    capture_manifest(dest / 'summary.json', report)
    return dest / 'summary.json'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare-pilot', 'prepare-full', 'run', 'verify'])
    p.add_argument('artifact', type=Path)
    p.add_argument('--original', type=Path)
    args = p.parse_args()
    out = args.artifact.resolve()
    if args.action == 'prepare-pilot':
        if args.original is None:
            p.error('--original passing full geometric source campaign required')
        print(prepare_pilot(out, args.original.resolve()), flush=True)
    elif args.action == 'prepare-full':
        print(prepare_full(out), flush=True)
    elif args.action == 'run':
        campaign.run(out, sys.modules[__name__])
    else:
        print(verify(out), flush=True)
