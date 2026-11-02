#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare restorer balance and decision-pair gain against the source-qualified P8/N8 receiver."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import receiver_lvt_pair_experiment as baseline
import receiver_restore_threshold as control
from receiver_lvt_restore_experiment import HELPER
from retry_receiver_restore_static import tighten
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
VARIANTS = ['control', 'restore_p4_n8', 'decision_pair_w32']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(source, variant):
    if variant not in VARIANTS:
        raise ValueError('Unknown bounded receiver gain/balance intervention')
    source = control.transform(source, 'restore_lvt_n8')
    if variant == 'control':
        return source
    if variant == 'restore_p4_n8':
        block = text_block(source, HELPER)
        block, count = re.subn(r'(?m)^(XP Y A VDD VDD sky130_fd_pr__pfet_01v8 w=)8( l=0\.15\s*)$',
            lambda m: m[1]+'4'+m[2], block)
        if count != 1:
            raise ValueError('Unexpected first-restorer PMOS dimensions')
        return replace(source, HELPER, block)
    block = text_block(source, TOP)
    block, count = re.subn(r'(?m)^(XC[01] [^\n]*sky130_fd_pr__nfet_01v8_lvt w=)8( l=0\.15\s*)$',
        lambda m: m[1]+'32'+m[2], block)
    if count != 2:
        raise ValueError('Unexpected low-threshold decision pair dimensions')
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


def prepare(parent, control_matrix):
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
    if not control_matrix.is_relative_to(ROOT/'build/diagnostics/receiver_restore_threshold_matrix'):
        raise ValueError('Use the completed P8/N8 LVT source matrix')
    bm = json.loads((control_matrix/'manifest.json').read_text())
    gate = json.loads((control_matrix/'source_dc_admission/restore_lvt_n8.json').read_text())
    if (gate.get('source_dc_passed') is not True or gate.get('required') != 15 or
            gate.get('manifest_sha256') != sha(control_matrix/'manifest.json') or gate.get('completed') != 15 or
            gate.get('passed_cases') != 15 or gate.get('report_sha256') != sha(control_matrix/'summary.json')):
        raise ValueError('The matched P8/N8 LVT control must pass all fifteen DC cases')
    matches = [c for c in bm['identity']['children'] if c['control'] == str(parent.relative_to(ROOT))]
    if len(matches) != 1:
        raise ValueError('Bias matrix does not bind this exact original PVT control')
    prior = ROOT/matches[0]['root']
    if any(not (prior/v/'summary.json').is_file() for v in control.VARIANTS):
        raise ValueError('Complete all original matched restorer cases before gain/balance tests')
    if any(sha(ROOT/'scripts'/n) != h for n,h in bm['identity']['code'].items()):
        raise ValueError('Qualified control matrix producer changed')
    calibrated = control.run(prior)
    if not next(r for r in calibrated['results'] if r['task']=='restore_lvt_n8')['passed']:
        raise ValueError('Matched P8/N8 LVT control failed')
    if (prior/'restore_lvt_n8/candidate.spice').read_text() != transform(original,'control'):
        raise ValueError('Gain/balance control differs from the admitted P8/N8 LVT source')
    pm = json.loads((parent/'manifest.json').read_text())
    paths = [parent/n for n in ['manifest.json', 'summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn']]
    paths.extend([ROOT/'requirements.json', ROOT/'analog/openlvds.spice'])
    paths.extend(control_matrix/n for n in ['manifest.json','summary.json','source_dc_admission/restore_lvt_n8.json'])
    paths.extend(prior/n for n in ['manifest.json','summary.json'])
    paths.extend(prior/'restore_lvt_n8'/n for n in ['candidate.spice','source.spice','bench.cir','bench.cir.prn','summary.json'])
    names = set(pm['identity']['code']) | {NAME, 'receiver_architecture_observations.py',
        'diagnose_architecture_rate.py', 'receiver_architecture_rate.py', 'spice_dispatch.py',
        'receiver_soft_common_mode.py', 'receiver_lvt_restore_experiment.py',
        'receiver_restore_threshold.py', 'retry_receiver_restore_static.py'}
    identity = dict(parent=str(parent.relative_to(ROOT)), variants=VARIANTS,
        inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
        code={n: sha(ROOT/'scripts'/n) for n in sorted(names)}, simulator_provenance=provenance(),
        numerical_policy=dict(maximum_step_ps=1, output_step_ps=10, stop_ns=144, input_points=12),
        scope='Three matched full 144 ns/twelve-point source DC/current/stress cases at uniform 1 ps maximum step. The source-qualified two-unit frontend with P8/N8 LVT first restorer is control. One candidate changes only that PMOS W8 to W4; the other changes only both LVT decision inputs W8 to W32, preserving tail W16 and PMOS mirror W8. Fixed supplies, original ramps, Gear method, tolerances and later stages remain. No clock, physical/native, timing or PHY admission.')
    root = ROOT/'build/diagnostics/receiver_gain_balance'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True); tasks = []
    for variant in VARIANTS:
        folder = root/variant; folder.mkdir(exist_ok=True)
        candidate = transform(original, variant); source = instrument(candidate)
        deck = tighten(observed.observe_deck((parent/'bench.cir').read_text(), parent, folder))
        prints = re.findall(r'(?im)^\.print tran[^\n]*$', deck)
        ProbeNetwork(probe_view(source)).validate(probe_view(deck), re.findall(r'V\(([^)]+)\)', prints[0], re.I))
        for name, text in [('candidate.spice', candidate), ('source.spice', source), ('bench.cir', deck)]:
            p = folder/name
            if p.exists() and p.read_text() != text:
                raise ValueError('Prepared receiver gain/balance pilot changed')
            if not p.exists():
                p.write_text(text)
        tasks.append(dict(id=variant, files={n: sha(folder/n) for n in ['candidate.spice', 'source.spice', 'bench.cir']}))
    capture_manifest(root/'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_gain_balance'):
        raise ValueError('Use a prepared receiver gain/balance pilot')
    m = json.loads((root/'manifest.json').read_text()); i = m['identity']; stamp = sha(root/'manifest.json')
    def unchanged():
        if (sha(root/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                [t['id'] for t in m['tasks']] != VARIANTS or
                any(sha(ROOT/'scripts'/n) != h for n, h in i['code'].items()) or
                any(sha(ROOT/n) != h for n, h in i['inputs'].items()) or
                any(sha(root/t['id']/n) != h for t in m['tasks'] for n, h in t['files'].items())):
            raise ValueError('Receiver gain/balance pilot context changed')
        if i.get('numerical_policy') != dict(maximum_step_ps=1, output_step_ps=10, stop_ns=144, input_points=12) or any(
                tighten((root/t['id']/'bench.cir').read_text()) != (root/t['id']/'bench.cir').read_text() for t in m['tasks']):
            raise ValueError('Every gain/balance control requires the declared uniform 1 ps maximum step')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged(); results = []
        for task in m['tasks']:
            folder = root/task['id']; cached = json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else None
            if cached is None:
                if any((folder/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
                    raise ValueError('Partial receiver gain/balance pilot retained; use a fresh context')
                atomic(root/'execution.json', dict(status='waiting_for_slot', task=task['id'], qualified_phy=False))
                with lease(ROOT, priority=0, label='receiver-gain-balance-static'):
                    unchanged(); atomic(root/'execution.json', dict(status='running', task=task['id'], qualified_phy=False))
                    p = subprocess.run(command(folder/'ngspice.log', folder/'bench.cir'), cwd=folder, capture_output=True, text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr); p.check_returncode()
            elif sha(folder/'bench.cir.prn') != cached['waveform_sha256']:
                raise ValueError('Completed receiver gain/balance pilot waveform changed')
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
                raise ValueError('Receiver gain/balance pilot remeasurement changed')
            capture_manifest(folder/'summary.json', result); results.append(result)
            if task['id'] == 'control' and not metrics['metrics']['passed']:
                atomic(root/'execution.json', dict(status='held_for_diagnosis', qualified_phy=False,
                    reason='Instrumented control does not reproduce original DC decisions'))
                raise ValueError('Receiver gain/balance pilot control failed original DC calibration')
        report = dict(diagnostic_complete=True, qualified_phy=False, manifest_sha256=stamp, results=results, scope=i['scope'])
        capture_manifest(root/'summary.json', report)
        atomic(root/'execution.json', dict(status='completed', qualified_phy=False))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path); p.add_argument('--control-matrix', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        if a.control_matrix is None:
            p.error('--control-matrix is required for preparation')
        print(prepare(a.artifact.resolve(), a.control_matrix.resolve()), flush=True)
    else:
        run(a.artifact.resolve()); print(a.artifact.resolve()/'summary.json', flush=True)
