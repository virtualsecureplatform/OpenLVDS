#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Couple the audited 110:1 driver and admitted original differential-restoration native receiver."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import driver_current_native as driver
import qualify_receiver_differential_restore as receiver
from dll_campaign import atomic
from dll_candidate_library import audited
from dll_measurements import read_wave
from diagnose_link_clock import pulse_transport
from probe_receiver_candidate_link import receiver_overlay, rebind, analyze, edge_times, word_stream, REQ
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, engine, provenance
from spice_library import checked_netlist
from spice_scope import closure_hash
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
TOP = 'openlvds_receiver_core'
LEAVES = ['PP','PN','CO','CL','CT','RESTORE0','RESTORE1']
SCOPE = ('Corrected audited 110:1 native driver coupled to admitted original differential-restoration native RX, '
    'with original channel, native shared bias/digital RX, 188.049 ns/32-bit payload, '
    '60 ns training and ideal 410 MHz phase. Same 20 ps maximum step. Early diagnostic '
    'only; real DLL/startup, qualified aperture, full components/PVT, required long payloads '
    'and final PHY release remain open.')
sha = receiver.sha


def fixture(deck, old, new, nodes):
    lines = list(re.finditer(r'(?im)^\.tran[^\n]*$',deck))
    if len(lines) != 1 or lines[0][0].split()[1:] != ['20p','188.049n','0','20p']:
        raise ValueError('Require the unchanged complete 188.049 ns/20 ps corrected-link fixture')
    deck = rebind(deck,old,new)
    for instance in ['DR','CR']:
        for leaf in LEAVES:
            before = 'X'+instance+':'+TOP+'__'+leaf
            after = 'X'+instance+':'+nodes[leaf].split(':',1)[1]
            pattern = r'(?<!\S)V\('+re.escape(before)+r'\)(?=\s|$)'
            deck,count = re.subn(pattern,lambda _: 'V('+after+')',deck)
            if count != 1:
                raise ValueError('Ambiguous original coupled receiver probe '+before)
    return deck


def prepare(parent, replay, comparison):
    receiver.recheck(replay)
    if engine() != 'ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/analog_link_pilot'):
        raise ValueError('Use the preserved corrected-driver link fixture in pinned ngspice')
    p = json.loads((parent/'manifest.json').read_text()); old = p['identity']
    if (old.get('driver_variant') != 'restore_64_24' or
            old['code'].get('driver_current_native.py') != sha(Path(driver.__file__)) or
            any(sha(ROOT/n) != h for n,h in old['inputs'].items()) or
            any(sha(ROOT/'scripts'/n) != h for n,h in old['code'].items()) or
            any(sha(parent/n) != h for n,h in p['files'].items())):
        raise ValueError('Preserved corrected driver fixture changed or uses another current ratio')
    config = old['config']
    if (config['fast_rc'] or not config['diagnostic'] or config['dll_phase'] or
            config['bits'] != 32 or config['training_ns'] != 60 or config.get('clock_source') != 'ideal' or
            (config['process'],config['temperature'],config['mhz'],config['duty'],config['skew_ps'],config['jitter_pp_ps']) !=
            ('ss',40,410,.45,100,100)):
        raise ValueError('Use the exact original short-training full-RC diagnostic')
    cm = json.loads((comparison/'manifest.json').read_text())
    if not (comparison/'summary.json').is_file() or any(not (comparison/t['id']/'summary.json').is_file() for t in cm['tasks']):
        raise ValueError('Complete the corrected driver native comparison first')
    driver.run(comparison)  # Every driver case is already complete: cached remeasurement only.
    models, physical_files, code = driver.physical_models({k:ROOT/v for k,v in cm['identity']['layouts'].items()})
    base = (parent/'library.spice').read_text()
    if closure_hash(base,'openlvds_driver_core') != closure_hash(models['restore_64_24'],'openlvds_driver_core'):
        raise ValueError('Parent link does not use the exact audited 110:1 driver model')
    rm = json.loads((replay/'manifest.json').read_text()); i = rm['identity']; layout = ROOT/i['layout']
    physical = json.loads((layout/'summary.json').read_text()); info = json.loads((layout/'extraction.json').read_text())
    if (not physical['passed'] or sha(layout/'candidate.spice') != info['source_sha256'] or
            sha(ROOT/physical['designs'][TOP]['gds']) != info['gds_sha256']):
        raise ValueError('Selected native receiver physical source/GDS changed')
    audit = audited(layout,info)
    library = receiver_overlay(base,checked_netlist(info),info['ports'])
    paths = [parent/n for n in ['manifest.json','bench.cir','library.spice']]
    paths += [comparison/'manifest.json',comparison/'summary.json']+physical_files
    paths += [replay/n for n in ['manifest.json','summary.json','captured/summary.json','sharp_control/summary.json']]
    paths += [layout/n for n in ['summary.json','candidate.spice','extraction.json','rc_audit.json']]+[ROOT/info['netlist']]
    paths += [ROOT/physical['designs'][TOP]['gds'],ROOT/audit['report']]
    names = set(old['code'])|set(i['code'])|set(code)|{NAME,'qualify_receiver_differential_restore.py',
        'probe_receiver_candidate_link.py','spice_dispatch.py','spice_scope.py'}
    identity = dict(parent=str(parent.relative_to(ROOT)),replay=str(replay.relative_to(ROOT)),
        receiver=str(layout.relative_to(ROOT)),variant=i['differential_restore_variant'],
        driver_current_ratio=110,config=config,simulator_provenance=provenance(),scope=SCOPE,
        inputs={str(path.relative_to(ROOT)):sha(path) for path in paths},
        code={n:sha(ROOT/'scripts'/n) for n in names},observation_nodes=i['observation_nodes'])
    out = ROOT/'build/diagnostics/corrected_native_link'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    deck = fixture((parent/'bench.cir').read_text(),parent,out,i['observation_nodes'])
    prints = re.findall(r'(?im)^\.print tran[^\n]*',deck)
    if len(prints) != 1:
        raise ValueError('Require one original link print statement')
    ProbeNetwork(library).validate(deck,re.findall(r'V\(([^)]+)\)',prints[0],re.I))
    for n,text in [('library.spice',library),('bench.cir',deck)]:
        path = out/n
        if path.exists() and path.read_text() != text:
            raise ValueError('Prepared coupled native fixture changed')
        if not path.exists():
            path.write_text(text)
    capture_manifest(out/'manifest.json',dict(identity=identity,qualified_phy=False,
        files={n:sha(out/n) for n in ['library.spice','bench.cir']}))
    return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/corrected_native_link'):
        raise ValueError('Use the prepared corrected native coupled-link diagnostic')
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']; stamp = sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                any(sha(ROOT/n) != h for n,h in i['inputs'].items()) or
                any(sha(ROOT/'scripts'/n) != h for n,h in i['code'].items()) or
                any(sha(out/n) != h for n,h in m['files'].items())):
            raise ValueError('Corrected coupled native link context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged()
        cached = json.loads((out/'summary.json').read_text()) if (out/'summary.json').exists() else None
        if cached is None and any((out/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log']):
            raise ValueError('Partial corrected native link retained; use a fresh context')
        receiver.recheck(ROOT/i['replay'])
        if cached is None:
            atomic(out/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
            with lease(ROOT,priority=1,label='corrected_driver_differential_restore_native_receiver_link'):
                unchanged();atomic(out/'execution.json',dict(status='running',qualified_phy=False))
                p = subprocess.run(command(out/'ngspice.log',out/'bench.cir'),cwd=out,capture_output=True,text=True)
            (out/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
        elif sha(out/'bench.cir.prn') != cached['waveform_sha256']:
            raise ValueError('Completed corrected native link waveform changed')
        w,h = read_wave(out/'bench.cir.prn'); t = w[:,1]; config = i['config']
        if len(t)<2 or not np.isfinite(w).all() or t[0]>1e-15 or np.any(np.diff(t)<=0) or t[-1]<188.049e-9-1e-12:
            raise ValueError('Incomplete original corrected native link waveform')
        rises = edge_times(t,w[:,h['V(CLK0)']],.9,True)
        launch = rises[rises>=config['training_ns']*1e-9][:config['bits']//2]*1e9
        if len(launch) != config['bits']//2:
            raise ValueError('Incomplete corrected-link payload clocks')
        metrics = analyze(w,word_stream(len(launch)),launch,1000/config['mhz'])
        margin = all(metrics.get(k) is not None and metrics[k]>=REQ['minimum_sampling_margin_ps']
            for k in ['setup_margin_ps','hold_margin_ps'])
        col = lambda n:w[:,h['V('+n+')']]
        transport = pulse_transport(t,col('RCP')-col('RCN'),col('RXCLOCK'),60e-9,120e-9)
        clock = bool(transport['pulses'] and not transport['missing_output_edges'] and
            all(p['output_edges_in_next_input_period']==1 for p in transport['pulses']))
        result = dict(diagnostic_complete=True,qualified_phy=False,passed=bool(metrics['passed'] and margin and clock),
            metrics=metrics,sampling_margin_passed=margin,clock_transport=transport,
            manifest_sha256=stamp,waveform_sha256=sha(out/'bench.cir.prn'),scope=SCOPE)
        unchanged()
        if cached is not None and cached != result:
            raise ValueError('Corrected native link remeasurement changed')
        capture_manifest(out/'summary.json',result)
        atomic(out/'execution.json',dict(status='completed',passed=result['passed'],qualified_phy=False))
    return out/'summary.json'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    a=sub.add_parser('prepare');a.add_argument('parent',type=Path);a.add_argument('replay',type=Path);a.add_argument('comparison',type=Path)
    a=sub.add_parser('run');a.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':
        print(prepare(a.parent.resolve(),a.replay.resolve(),a.comparison.resolve()),flush=True)
    else:
        print(run(a.artifact.resolve()),flush=True)
