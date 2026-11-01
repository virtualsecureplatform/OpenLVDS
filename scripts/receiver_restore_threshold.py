#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test lower-threshold first restoration stages with the qualified two-unit frontend bias."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import receiver_lvt_pair_experiment as baseline
import receiver_soft_common_mode as bias
from receiver_lvt_restore_experiment import lower_first_nfet, HELPER
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
VARIANTS = ['control', 'restore_lvt_n4', 'restore_lvt_n8']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(source, variant):
    if variant not in VARIANTS:
        raise ValueError('Unknown bounded first-restorer intervention')
    # The exact qualified two-unit frontend is the matched control.
    source = bias.transform(source, 'rail_pullup_2r')
    if variant == 'control':
        return source
    source = lower_first_nfet(source)
    if variant == 'restore_lvt_n8':
        block = text_block(source, HELPER)
        block, count = re.subn(r'(?m)^(XN Y A VSS VSS sky130_fd_pr__nfet_01v8_lvt w=)4( l=0\.15\s*)$',
            lambda m: m[1]+'8'+m[2], block)
        if count != 1:
            raise ValueError('Unexpected first-restorer low-threshold device dimensions')
        source = replace(source, HELPER, block)
    return source


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


def prepare(parent, bias_matrix):
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
    if not bias_matrix.is_relative_to(ROOT/'build/diagnostics/receiver_soft_common_mode_matrix'):
        raise ValueError('Use the completed two-unit bias source matrix')
    bm = json.loads((bias_matrix/'manifest.json').read_text())
    gate = json.loads((bias_matrix/'source_dc_admission/rail_pullup_2r.json').read_text())
    if (gate.get('source_dc_passed') is not True or gate.get('required') != 15 or
            gate.get('manifest_sha256') != sha(bias_matrix/'manifest.json') or gate.get('completed') != 15 or
            gate.get('passed_cases') != 15 or gate.get('report_sha256') != sha(bias_matrix/'summary.json')):
        raise ValueError('The matched two-unit frontend must pass all fifteen DC cases')
    matches = [c for c in bm['identity']['children'] if c['control'] == str(parent.relative_to(ROOT))]
    if len(matches) != 1:
        raise ValueError('Bias matrix does not bind this exact original PVT control')
    prior = ROOT/matches[0]['root']
    if any(not (prior/v/'summary.json').is_file() for v in bias.VARIANTS):
        raise ValueError('Complete all original matched bias pilots before restoration tests')
    calibrated = bias.run(prior)
    if not next(r for r in calibrated['results'] if r['task']=='rail_pullup_2r')['passed']:
        raise ValueError('Matched two-unit bias control failed')
    if (prior/'rail_pullup_2r/candidate.spice').read_text() != transform(original,'control'):
        raise ValueError('Restoration control differs from the admitted two-unit source')
    pm = json.loads((parent/'manifest.json').read_text())
    paths = [parent/n for n in ['manifest.json', 'summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn']]
    paths.extend([ROOT/'requirements.json', ROOT/'analog/openlvds.spice'])
    paths.extend(bias_matrix/n for n in ['manifest.json','summary.json','source_dc_admission/rail_pullup_2r.json'])
    paths.extend(prior/n for n in ['manifest.json','summary.json'])
    paths.extend(prior/'rail_pullup_2r'/n for n in ['candidate.spice','source.spice','bench.cir','bench.cir.prn','summary.json'])
    names = set(pm['identity']['code']) | {NAME, 'receiver_architecture_observations.py',
        'diagnose_architecture_rate.py', 'receiver_architecture_rate.py', 'spice_dispatch.py',
        'receiver_soft_common_mode.py', 'receiver_lvt_restore_experiment.py'}
    identity = dict(parent=str(parent.relative_to(ROOT)), variants=VARIANTS,
        inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
        code={n: sha(ROOT/'scripts'/n) for n in sorted(names)}, simulator_provenance=provenance(),
        scope='Three matched full 144 ns/12-point source DC/current pilots. Qualified two-unit bias is control; only the first restoration NFET changes to low-threshold N4/N8. Fixed supplies, all decision/frontend/later-restorer devices and original stimuli/numerics remain. No native, rate, full-PVT or PHY admission.')
    root = ROOT/'build/diagnostics/receiver_restore_threshold'/hashlib.sha256(
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
                raise ValueError('Prepared first-restorer pilot changed')
            if not p.exists():
                p.write_text(text)
        tasks.append(dict(id=variant, files={n: sha(folder/n) for n in ['candidate.spice', 'source.spice', 'bench.cir']}))
    capture_manifest(root/'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_restore_threshold'):
        raise ValueError('Use a prepared first-restorer pilot')
    m = json.loads((root/'manifest.json').read_text()); i = m['identity']; stamp = sha(root/'manifest.json')
    def unchanged():
        if (sha(root/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                [t['id'] for t in m['tasks']] != VARIANTS or
                any(sha(ROOT/'scripts'/n) != h for n, h in i['code'].items()) or
                any(sha(ROOT/n) != h for n, h in i['inputs'].items()) or
                any(sha(root/t['id']/n) != h for t in m['tasks'] for n, h in t['files'].items())):
            raise ValueError('First-restorer pilot context changed')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged(); results = []
        for task in m['tasks']:
            folder = root/task['id']; cached = json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else None
            if cached is None:
                if any((folder/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
                    raise ValueError('Partial first-restorer pilot retained; use a fresh context')
                atomic(root/'execution.json', dict(status='waiting_for_slot', task=task['id'], qualified_phy=False))
                with lease(ROOT, priority=0, label='receiver-restore-threshold-static'):
                    unchanged(); atomic(root/'execution.json', dict(status='running', task=task['id'], qualified_phy=False))
                    p = subprocess.run(command(folder/'ngspice.log', folder/'bench.cir'), cwd=folder, capture_output=True, text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr); p.check_returncode()
            elif sha(folder/'bench.cir.prn') != cached['waveform_sha256']:
                raise ValueError('Completed first-restorer pilot waveform changed')
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
                raise ValueError('First-restorer pilot remeasurement changed')
            capture_manifest(folder/'summary.json', result); results.append(result)
            if task['id'] == 'control' and not metrics['metrics']['passed']:
                atomic(root/'execution.json', dict(status='held_for_diagnosis', qualified_phy=False,
                    reason='Instrumented control does not reproduce original DC decisions'))
                raise ValueError('First-restorer pilot control failed original DC calibration')
        report = dict(diagnostic_complete=True, qualified_phy=False, manifest_sha256=stamp, results=results, scope=i['scope'])
        capture_manifest(root/'summary.json', report)
        atomic(root/'execution.json', dict(status='completed', qualified_phy=False))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path); p.add_argument('--bias-matrix', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        if a.bias_matrix is None:
            p.error('--bias-matrix is required for preparation')
        print(prepare(a.artifact.resolve(), a.bias_matrix.resolve()), flush=True)
    else:
        run(a.artifact.resolve()); print(a.artifact.resolve()/'summary.json', flush=True)
