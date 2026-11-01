#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare two bounded passive frontend-bias corrections in matched DC fixtures."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import receiver_lvt_pair_experiment as baseline
import receiver_architecture_observations as observed
from diagnose_architecture_rate import measure, observed_devices
from dll_campaign import atomic, text_block
from dll_measurements import read_wave
from layout import circuits
from receiver_decision_load_static import measured
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, engine, provenance
from spice_library import replace
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
TOP = 'openlvds_receiver_core'
RES = 'sky130_fd_pr__res_high_po_0p35'
VARIANTS = ['control', 'reference_return', 'rail_pullup']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(source, variant):
    if variant not in VARIANTS:
        raise ValueError('Unknown bounded common-mode correction')
    rows = {r[0]: r for r in circuits(source)[TOP][1]}
    for stem, prefix, upper, lower in [('PP', 'XRLPP', 'PPRT', 'PPRB'), ('PN', 'XRLPN', 'PNRT', 'PNRB')]:
        connections = [[stem, 'VREF', 'VSS'], [stem, upper, 'VSS'], [upper, 'VREF', 'VSS'],
                       [stem, lower, 'VSS'], [lower, 'VSS', 'VSS']]
        for suffix, nodes in zip('ABCDE', connections, strict=True):
            name = prefix+suffix
            if rows.get(name) != (name, nodes, RES, dict(w='0.35', l='1.25')):
                raise ValueError('Original frontend resistor topology/dimensions changed')
    if any(n.startswith('XRBC') for n in rows):
        raise ValueError('Common-mode correction already exists')
    if variant == 'control':
        return source
    block = text_block(source, TOP)
    if variant == 'reference_return':
        # Original load: R || 2R to VREF || 2R to ground, centered at
        # 0.75*VREF. Returning the last leg to VREF keeps R/2 and gain.
        for name, node in [('XRLPPE', 'PPRB'), ('XRLPNE', 'PNRB')]:
            block, count = re.subn(r'(?m)^('+name+' '+node+r') VSS VSS ', r'\1 VREF VSS ', block)
            if count != 1:
                raise ValueError('Ambiguous frontend return resistor')
    else:
        # Add R to VDDD: nominal center becomes 0.5*VREF+VDDD/3=1.2 V,
        # with R/3 load instead of R/2. This trades gain for bandwidth.
        added = '\n'.join(f'XRBC{n} {n} VDDD VSS {RES} w=0.35 l=1.25' for n in ['PP', 'PN'])+'\n'
        at = block.lower().rfind('.ends'); block = block[:at]+added+block[at:]
    return replace(source, TOP, block)


def instrument(source):
    # Same ideal zero-volt/one-ohm observation convention as the existing
    # architecture observer. Physical candidate bytes remain uninstrumented.
    block = text_block(source, TOP)
    if 'OBS_' in block:
        raise ValueError('Source already contains observation meters')
    for device, (drain, label) in observed.METERS.items():
        block, count = re.subn(r'(?m)^'+device+' '+drain+r'(?= )', device+' OBS_'+label+'_D', block)
        if count != 1:
            raise ValueError('Unexpected current-meter device')
        lines = f'VOBS_{label} {drain} OBS_{label}_D 0\nHOBS_{label} OBS_I{label} VSS VOBS_{label} 1\n'
        block = block.replace('.ends '+TOP, lines+'.ends '+TOP)
    return replace(source, TOP, block)


def probe_view(text):
    # The frozen generic probe checker does not know CCVS output nodes.
    # Expose their two terminals in a parser-only resistor view. This text
    # is never written as a scientific source or passed to the simulator.
    return re.sub(r'(?m)^HOBS_(\S+) (\S+) (\S+) (\S+) 1$',
                  r'ROBS_\1 \2 \3 1', text)


def prepare(parent):
    if engine() != 'ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/receiver_lvt_pair_static'):
        raise ValueError('Use a completed matched LVT source-static control')
    if not (parent/'summary.json').is_file():
        raise ValueError('Complete the original static control first')
    r = baseline.run(parent)
    if not r['lvt_decision_pair']['metrics']['passed']:
        raise ValueError('Original LVT source-static control failed')
    original = (parent/'source.spice').read_text()
    if original != baseline.source_variant((ROOT/'analog/openlvds.spice').read_text(), True):
        raise ValueError('Static baseline is not the unchanged LVT source factory')
    pm = json.loads((parent/'manifest.json').read_text())
    paths = [parent/n for n in ['manifest.json', 'summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn']]
    paths.extend([ROOT/'requirements.json', ROOT/'analog/openlvds.spice'])
    names = set(pm['identity']['code']) | {NAME, 'receiver_architecture_observations.py',
        'diagnose_architecture_rate.py', 'receiver_architecture_rate.py', 'spice_dispatch.py'}
    identity = dict(parent=str(parent.relative_to(ROOT)), variants=VARIANTS,
        inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
        code={n: sha(ROOT/'scripts'/n) for n in sorted(names)}, simulator_provenance=provenance(),
        scope='Three matched full 144 ns/12-point source DC/current pilots. Fixed supplies and original stimuli/numerical policy. Only the declared passive frontend loads change; no native, rate, full-PVT or PHY admission.')
    root = ROOT/'build/diagnostics/receiver_common_mode'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True); tasks = []
    for variant in VARIANTS:
        folder = root/variant; folder.mkdir(exist_ok=True)
        candidate = transform(original, variant); source = instrument(candidate)
        deck = observed.observe_deck((parent/'bench.cir').read_text(), parent, folder)
        prints = re.findall(r'(?im)^\.print tran[^\n]*$', deck)
        ProbeNetwork(probe_view(source)).validate(probe_view(deck), re.findall(r'V\(([^)]+)\)', prints[0], re.I))
        for name, text in [('candidate.spice', candidate), ('source.spice', source), ('bench.cir', deck)]:
            p = folder/name
            if p.exists() and p.read_text() != text:
                raise ValueError('Prepared common-mode pilot changed')
            if not p.exists():
                p.write_text(text)
        tasks.append(dict(id=variant, files={n: sha(folder/n) for n in ['candidate.spice', 'source.spice', 'bench.cir']}))
    capture_manifest(root/'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_common_mode'):
        raise ValueError('Use a prepared passive common-mode pilot')
    m = json.loads((root/'manifest.json').read_text()); i = m['identity']; stamp = sha(root/'manifest.json')
    def unchanged():
        if (sha(root/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                [t['id'] for t in m['tasks']] != VARIANTS or
                any(sha(ROOT/'scripts'/n) != h for n, h in i['code'].items()) or
                any(sha(ROOT/n) != h for n, h in i['inputs'].items()) or
                any(sha(root/t['id']/n) != h for t in m['tasks'] for n, h in t['files'].items())):
            raise ValueError('Common-mode pilot context changed')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged(); results = []
        for task in m['tasks']:
            folder = root/task['id']; cached = json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else None
            if cached is None:
                if any((folder/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
                    raise ValueError('Partial common-mode pilot retained; use a fresh context')
                atomic(root/'execution.json', dict(status='waiting_for_slot', task=task['id'], qualified_phy=False))
                with lease(ROOT, priority=0, label='receiver-common-mode-static'):
                    unchanged(); atomic(root/'execution.json', dict(status='running', task=task['id'], qualified_phy=False))
                    p = subprocess.run(command(folder/'ngspice.log', folder/'bench.cir'), cwd=folder, capture_output=True, text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr); p.check_returncode()
            elif sha(folder/'bench.cir.prn') != cached['waveform_sha256']:
                raise ValueError('Completed common-mode pilot waveform changed')
            unchanged(); w, h = read_wave(folder/'bench.cir.prn'); metrics = measured(w, h, True)
            rows = {r[0]: r for r in circuits((folder/'candidate.spice').read_text())[TOP][1]}
            six = observed.observations(w, h, rows)
            twelve = measure(w, h, observed_devices((folder/'source.spice').read_text()))
            twelve['scope'] = 'Full original 144 ns trace; twelve decision/bias/restoration devices. 1.95 V project screen, not foundry absolute ratings. Remaining frontend/bias stress and native/rate qualification remain open.'
            result = dict(task=task['id'], metrics=metrics, current_and_headroom=six,
                twelve_device_observations=twelve, qualified_phy=False,
                passed=bool(metrics['metrics']['passed'] and twelve['observed_thin_guard_passed']),
                manifest_sha256=stamp, waveform_sha256=sha(folder/'bench.cir.prn'))
            unchanged()
            if cached is not None and cached != result:
                raise ValueError('Common-mode pilot remeasurement changed')
            capture_manifest(folder/'summary.json', result); results.append(result)
            if task['id'] == 'control' and not metrics['metrics']['passed']:
                atomic(root/'execution.json', dict(status='held_for_diagnosis', qualified_phy=False,
                    reason='Instrumented control does not reproduce original DC decisions'))
                raise ValueError('Common-mode pilot control failed original DC calibration')
        report = dict(diagnostic_complete=True, qualified_phy=False, manifest_sha256=stamp, results=results, scope=i['scope'])
        capture_manifest(root/'summary.json', report)
        atomic(root/'execution.json', dict(status='completed', qualified_phy=False))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.artifact.resolve()), flush=True)
    else:
        run(a.artifact.resolve()); print(a.artifact.resolve()/'summary.json', flush=True)
