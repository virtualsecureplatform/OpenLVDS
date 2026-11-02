#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Screen unit-matched trip-referenced differential restoration with the original complete source DC fixtures."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import receiver_lvt_pair_experiment as baseline
import receiver_gain_balance as previous
import receiver_matched_trip_restore as factory
import numpy as np
import receiver_restore_threshold as control
from receiver_lvt_restore_experiment import HELPER
from retry_receiver_restore_static import tighten
import receiver_architecture_observations as observed
from diagnose_architecture_rate import measure as base_measure
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
VARIANTS = factory.VARIANTS


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def transform(source, variant):
    return factory.transform(previous.transform(source,'control'),variant)


def instrument(source):
    source=previous.instrument(source)
    if 'XAT AMP_CT ' not in source:
        return source
    block=text_block(source,TOP)
    if block.count('XAT AMP_CT ')!=1:
        raise ValueError('Unexpected amplifier tail binding')
    block=block.replace('XAT AMP_CT ','XAT OBS_AMP_D ',1)
    block=block.replace('.ends '+TOP,'VOBS_AMP AMP_CT OBS_AMP_D 0\nHOBS_AMP OBS_IAMP VSS VOBS_AMP 1\n.ends '+TOP)
    return replace(source,TOP,block)


def observed_devices(source):
    modified='XAT OBS_AMP_D ' in source
    meters=[('CT','TAIL'),('NBC','REPLICA')]+([('AMP_CT','AMP')] if modified else [])
    for node,label in meters:
        for line in [f'VOBS_{label} {node} OBS_{label}_D 0',f'HOBS_{label} OBS_I{label} VSS VOBS_{label} 1']:
            if source.splitlines().count(line)!=1:
                raise ValueError('Missing or changed source current meter')
            source=source.replace(line+'\n','')
    definitions=circuits(source);rows={r[0]:r for r in definitions[TOP][1]}
    names=['XCT','XC0','XC1','XCD','XCM','XNCB']+(factory.AMPLIFIER if modified else [])
    devices={name:rows[name] for name in names}
    for instance in ['XIB0','XIB1','XIB2','XTRACK']:
        _,nodes,helper,_=rows[instance];ports,children=definitions[helper];mapping=dict(zip(ports,nodes,strict=True))
        for child,terminals,model,params in children:
            if len(terminals)!=4 or not re.fullmatch(r'sky130_fd_pr__(?:n|p)fet_.*',model) or any(n not in mapping for n in terminals):
                raise ValueError('Unknown internal restoring/reference terminal')
            name=instance+'/'+child
            devices[name]=(name,[mapping[n] for n in terminals],model,params)
    if len(devices)!=(21 if modified else 14):
        raise ValueError('Incomplete decision/amplifier/reference/restoration observation')
    return devices


def observe_deck(deck,parent,folder,source):
    deck=observed.observe_deck(deck,parent,folder)
    devices=observed_devices(source)
    nodes={n for _,terminals,_,_ in devices.values() for n in terminals}
    nodes -= {'VSS','PB','VDDIO','VDDD','Q'}
    if 'XAT' in devices:
        nodes |= {'AMP_CT','OBS_AMP_D','OBS_IAMP'}
    match=re.search(r'(?im)^\.print tran[^\n]*',deck)
    if not match:
        raise ValueError('Missing original source print statement')
    extras=['V(XR:XCORE:'+n+')' for n in sorted(nodes) if ('V(XR:XCORE:'+n+')').upper() not in match[0].upper().split()]
    return deck[:match.end()]+' '+' '.join(extras)+deck[match.end():]


def measure(wave,headers,devices):
    result=base_measure(wave,headers,devices)
    if 'XAT' in devices:
        col=lambda n:wave[:,headers['V(XR:XCORE:'+n+')']]
        if np.max(abs(col('AMP_CT')-col('OBS_AMP_D')))>1e-8:
            raise ValueError('Amplifier current meter changed a terminal potential')
        amps=col('OBS_IAMP');t=wave[:,1]
        result['currents']['amplifier']=dict(minimum_signed_a=float(amps.min()),maximum_signed_a=float(amps.max()),
            mean_absolute_a=float(np.sum((abs(amps[1:])+abs(amps[:-1]))*.5*np.diff(t))/(t[-1]-t[0])))
    return result


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
        raise ValueError('Complete all original matched restorer cases before trip-referenced restoration tests')
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
    names = set(pm['identity']['code']) | {NAME, 'receiver_gain_balance.py', 'receiver_differential_restore.py', 'receiver_matched_trip_restore.py', 'receiver_architecture_observations.py',
        'diagnose_architecture_rate.py', 'receiver_architecture_rate.py', 'spice_dispatch.py',
        'receiver_soft_common_mode.py', 'receiver_lvt_restore_experiment.py',
        'receiver_restore_threshold.py', 'retry_receiver_restore_static.py'}
    identity = dict(parent=str(parent.relative_to(ROOT)), variants=VARIANTS,
        inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
        code={n: sha(ROOT/'scripts'/n) for n in sorted(names)}, simulator_provenance=provenance(),
        numerical_policy=dict(maximum_step_ps=1, output_step_ps=10, stop_ns=144, input_points=12),
        scope='Three matched full 144 ns/twelve-point source DC/current/stress cases at uniform 1 ps maximum step. Exact qualified two-unit N8 input-pair control. New differential CO/CL amplifier with seven parallel original poly units shunting its current output to CO_TRACK; first standard inverter and two parallel reference units use identical individual models and widths, removing whole-width model-bin offset. Two amplifier scales, original frontend/first decision/bias and later buffers. Fourteen control or twenty-one modified MOS observed, including functional reference and amplifier tail current. Fixed supplies and original sensitivity thresholds. No clock, physical/native, rate, aperture, timing or PHY admission.')
    root = ROOT/'build/diagnostics/receiver_matched_trip_static'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True); tasks = []
    for variant in VARIANTS:
        folder = root/variant; folder.mkdir(exist_ok=True)
        candidate = transform(original, variant); source = instrument(candidate)
        deck = tighten(observe_deck((parent/'bench.cir').read_text(), parent, folder, source))
        prints = re.findall(r'(?im)^\.print tran[^\n]*$', deck)
        ProbeNetwork(probe_view(source)).validate(probe_view(deck), re.findall(r'V\(([^)]+)\)', prints[0], re.I))
        for name, text in [('candidate.spice', candidate), ('source.spice', source), ('bench.cir', deck)]:
            p = folder/name
            if p.exists() and p.read_text() != text:
                raise ValueError('Prepared receiver trip-referenced restoration pilot changed')
            if not p.exists():
                p.write_text(text)
        tasks.append(dict(id=variant, files={n: sha(folder/n) for n in ['candidate.spice', 'source.spice', 'bench.cir']}))
    capture_manifest(root/'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_matched_trip_static'):
        raise ValueError('Use a prepared receiver trip-referenced restoration pilot')
    m = json.loads((root/'manifest.json').read_text()); i = m['identity']; stamp = sha(root/'manifest.json')
    def unchanged():
        if (sha(root/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                [t['id'] for t in m['tasks']] != VARIANTS or
                any(sha(ROOT/'scripts'/n) != h for n, h in i['code'].items()) or
                any(sha(ROOT/n) != h for n, h in i['inputs'].items()) or
                any(sha(root/t['id']/n) != h for t in m['tasks'] for n, h in t['files'].items())):
            raise ValueError('Receiver trip-referenced restoration pilot context changed')
        if i.get('numerical_policy') != dict(maximum_step_ps=1, output_step_ps=10, stop_ns=144, input_points=12) or any(
                tighten((root/t['id']/'bench.cir').read_text()) != (root/t['id']/'bench.cir').read_text() for t in m['tasks']):
            raise ValueError('Every trip-referenced restoration control requires the declared uniform 1 ps maximum step')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged(); results = []
        for task in m['tasks']:
            folder = root/task['id']; cached = json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else None
            if cached is None:
                if any((folder/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
                    raise ValueError('Partial receiver trip-referenced restoration pilot retained; use a fresh context')
                atomic(root/'execution.json', dict(status='waiting_for_slot', task=task['id'], qualified_phy=False))
                with lease(ROOT, priority=0, label='receiver-matched-trip-static'):
                    unchanged(); atomic(root/'execution.json', dict(status='running', task=task['id'], qualified_phy=False))
                    p = subprocess.run(command(folder/'ngspice.log', folder/'bench.cir'), cwd=folder, capture_output=True, text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr); p.check_returncode()
            elif sha(folder/'bench.cir.prn') != cached['waveform_sha256']:
                raise ValueError('Completed receiver trip-referenced restoration pilot waveform changed')
            unchanged(); w, h = read_wave(folder/'bench.cir.prn')
            if (len(w)<2 or not np.isfinite(w).all() or np.any(np.diff(w[:,1])<=0) or w[0,1]>1e-15 or w[-1,1]<144e-9-1e-12):
                raise ValueError('Require the complete finite original 144 ns source waveform')
            metrics = measured(w, h, True)
            rows = {r[0]: r for r in circuits((folder/'candidate.spice').read_text())[TOP][1]}
            six = observed.observations(w, h, rows)
            twelve = measure(w, h, observed_devices((folder/'source.spice').read_text()))
            twelve['scope'] = 'Full original 144 ns trace; fourteen control or twenty-one decision/bias/reference/restoration devices. 1.95 V project screen, not foundry absolute ratings. Remaining frontend/bias stress and native/rate qualification remain open.'
            result = dict(task=task['id'], metrics=metrics, current_and_headroom=six,
                terminal_observations=twelve, qualified_phy=False,
                passed=bool(metrics['metrics']['passed'] and twelve['observed_thin_guard_passed']),
                manifest_sha256=stamp, waveform_sha256=sha(folder/'bench.cir.prn'))
            unchanged()
            if cached is not None and cached != result:
                raise ValueError('Receiver trip-referenced restoration pilot remeasurement changed')
            capture_manifest(folder/'summary.json', result); results.append(result)
            if task['id'] == 'control' and not metrics['metrics']['passed']:
                atomic(root/'execution.json', dict(status='held_for_diagnosis', qualified_phy=False,
                    reason='Instrumented control does not reproduce original DC decisions'))
                raise ValueError('Receiver trip-referenced restoration pilot control failed original DC calibration')
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
