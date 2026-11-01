#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Screen one bounded architecture in a completed captured source-clock fixture."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import receiver_architecture_observations as observed
import receiver_clamp_experiment as clock
from dll_measurements import read_wave
from layout import circuits, flatten, schematic_text
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_probes import ProbeNetwork
from stage_phy_candidate import overlay

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
sha = observed.experiment.digest
TOP = 'openlvds_receiver_core'


def pvt(deck):
    process = re.findall(r'(?im)^\.lib\s+\S+\s+(\S+)\s*$', deck)
    temp = re.findall(r'(?im)^\.options device temp=(\S+)\s*$', deck)
    if len(process) != 1 or len(temp) != 1:
        raise ValueError('Expected one original process and temperature')
    return process[0], float(temp[0])


def fixture(deck, old, new, nodes):
    include = f'.include "{old}/library.spice"'
    if deck.count(include) != 1 or '.tran 5p 80n 0 1p' not in deck:
        raise ValueError('Require the original full 80 ns, 1 ps captured source fixture')
    deck = deck.replace(include, f'.include "{new}/library.spice"')
    matches = list(re.finditer(r'(?im)^\.print tran[^\n]*$', deck))
    if len(matches) != 1:
        raise ValueError('Expected one original print statement')
    at = matches[0].end()
    return deck[:at]+' '+' '.join('V('+n+')' for n in nodes)+deck[at:]


def prepare(parent, sanity):
    if (not parent.is_relative_to(ROOT/'build/diagnostics/receiver_clamp') or
        not sanity.is_relative_to(ROOT/'build/diagnostics/receiver_architecture_static')):
        raise ValueError('Use completed captured source-clock and architecture static evidence')
    old = parent/'clamped_captured'
    if not (old/'summary.json').is_file() or not (sanity/'summary.json').is_file():
        raise ValueError('Complete the captured source case and matched static screen first')
    prior = json.loads((parent/'manifest.json').read_text()); task = next(t for t in prior['tasks'] if t['id'] == 'clamped_captured')
    if any(sha(old/n) != h for n, h in task['files'].items()):
        raise ValueError('Original captured fixture changed')
    report = json.loads((old/'summary.json').read_text())
    if report['manifest_sha256'] != sha(parent/'manifest.json') or report['waveform_sha256'] != sha(old/'bench.cir.prn'):
        raise ValueError('Original captured completion evidence changed')
    source_report = observed.run(sanity)
    if not (source_report['architecture']['metrics']['passed'] and source_report['architecture']['observations']['observed_thin_guard_passed']):
        raise ValueError('Matched DC/current/observed-stress screen failed')
    if pvt((sanity/'bench.cir').read_text()) != pvt((old/'bench.cir').read_text()):
        raise ValueError('Static and captured-clock process/temperature must match')
    sm = json.loads((sanity/'manifest.json').read_text()); variant = sm['identity']['architecture_variant']
    source = observed.experiment.source_variant((ROOT/'analog/openlvds.spice').read_text(), True, variant)
    ports, devices = flatten(circuits(source), TOP); model = schematic_text(TOP, ports, devices)
    library = overlay((old/'library.spice').read_text(), model, TOP, ('lvds_bias', 'openlvds_ddr_rx'))
    files = [parent/'manifest.json']+[old/n for n in ['candidate.spice', 'library.spice', 'bench.cir', 'summary.json', 'bench.cir.prn']]
    files += [sanity/n for n in ['manifest.json', 'summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn']]+[ROOT/'requirements.json']
    names = set(prior['identity']['code']) | set(sm['identity']['code']) | {NAME, 'stage_phy_candidate.py', 'spice_dispatch.py'}
    identity = dict(parent=str(parent.relative_to(ROOT)), sanity=str(sanity.relative_to(ROOT)), architecture_variant=variant,
        inputs={str(p.relative_to(ROOT)): sha(p) for p in files}, code={n: sha(ROOT/'scripts'/n) for n in sorted(names)},
        simulator_provenance=clock.provenance(), scope='One matched-PVT captured source-clock width pilot; unchanged pin stimuli, native bias/RX load and 80 ns/1 ps fixture. No full fifteen-case, native analog or PHY admission.')
    root = ROOT/'build/diagnostics/receiver_clamp'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    folder = root/'clamped_captured'; folder.mkdir(parents=True, exist_ok=True)
    aliases = {n: 'XRC:'+TOP+'__'+n for n in ['CT', 'CL', 'RESTORE0', 'RESTORE1']}
    deck = fixture((old/'bench.cir').read_text(), old, folder, list(aliases.values()))
    ProbeNetwork(library).validate(deck, aliases.values())
    for name, text in [('candidate.spice', source), ('library.spice', library), ('bench.cir', deck)]:
        path = folder/name
        if path.exists() and path.read_text() != text:
            raise ValueError('Prepared source-clock pilot changed')
        if not path.exists():
            path.write_text(text)
    actual_aliases = dict(task['aliases'], **aliases)
    capture_manifest(root/'manifest.json', dict(identity=identity, qualified_phy=False, tasks=[dict(
        id='clamped_captured', clamped=True, mode='captured', aliases=actual_aliases,
        files={n: sha(folder/n) for n in ['candidate.spice', 'library.spice', 'bench.cir']})]))
    return root


def scheduling(root, priority):
    policy = dict(producer_sha256=sha(Path(__file__)), dispatcher_sha256=sha(ROOT/'scripts/spice_dispatch.py'),
        priority=priority, global_slot_budget=6, no_outer_lease=True)
    out = root/'pilot_scheduling'/hashlib.sha256(json.dumps(policy, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True); capture_manifest(out/'manifest.json', policy)


def run_static(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_architecture_static'):
        raise ValueError('Use a prepared bounded architecture static screen')
    scheduling(root, 0); previous = observed.experiment.lease
    try:
        observed.experiment.lease = lambda wait_slot=None: lease(ROOT, priority=0, label='architecture_clock_pilot_dc')
        return observed.run(root)
    finally:
        observed.experiment.lease = previous


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_clamp'):
        raise ValueError('Use a prepared source-clock pilot')
    manifest = json.loads((root/'manifest.json').read_text())
    if manifest['identity']['code'].get(NAME) != sha(Path(__file__)) or len(manifest['tasks']) != 1:
        raise ValueError('Source-clock pilot producer or coverage changed')
    folder = root/'clamped_captured'
    if not (folder/'summary.json').is_file() and any((folder/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
        raise ValueError('Partial source-clock pilot retained; prepare a fresh context')
    scheduling(root, 1); previous = clock.slot
    try:
        clock.slot = lambda: lease(ROOT, priority=1, label='architecture_clock_pilot')
        clock.run(root)
    finally:
        clock.slot = previous
    wave, _ = read_wave(folder/'bench.cir.prn'); t = wave[:, 1]
    if t[0] > 1e-15 or t[-1] < 80e-9-1e-12 or not np.isfinite(wave).all() or np.any(np.diff(t) <= 0):
        raise ValueError('Incomplete full source-clock pilot waveform')
    summary = json.loads((folder/'summary.json').read_text()); pulses = summary['receiver_transport']
    passed = len(pulses['pulses']) == 47 and not pulses['missing_output_edges'] and all(p['output_edges_in_next_input_period'] == 1 for p in pulses['pulses'])
    capture_manifest(root/'clock_pilot_result.json', dict(pilot_passed=bool(passed), qualified_phy=False,
        manifest_sha256=sha(root/'manifest.json'), summary_sha256=sha(folder/'summary.json'),
        scope='Single original captured-clock diagnostic only; full PVT, source controls and native qualification remain required'))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run', 'run-static'])
    p.add_argument('artifact', type=Path); p.add_argument('--sanity', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        if a.sanity is None:
            p.error('--sanity is required')
        print(prepare(a.artifact.resolve(), a.sanity.resolve()), flush=True)
    elif a.action == 'run-static':
        run_static(a.artifact.resolve())
    else:
        run(a.artifact.resolve())
