#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Diagnose audited 110:1 TX/RX coupling without granting receiver qualification."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import driver_current_native as driver
import qualify_receiver_tia_restore as receiver
import probe_receiver_tia_restore as native_probe
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
SCOPE = ('Exploratory corrected audited 110:1 native driver coupled to a source-qualified, physically audited feedback receiver whose full original native controls are complete. '
    'A failed legacy transport result is retained and does not prevent this diagnostic. Original channel, shared native bias/digital RX, '
    '188.049 ns/32-bit payload, 60 ns training and ideal 410 MHz phase; maximum step tightened from 20 ps to 1 ps. '
    'This short-training diagnostic cannot qualify receiver components, native transport, startup, DLL, aperture, PVT, long payloads or PHY release. No original admission gate is changed.')

sha = receiver.sha


def completed_replay(replay):
    if not replay.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):
        raise ValueError('Use a complete isolated feedback-receiver replay')
    required=['manifest.json','summary.json']+[case+'/summary.json' for case in ['captured','sharp_control']]
    if any(not (replay/name).is_file() for name in required):
        raise ValueError('Complete both full native controls before exploratory coupling')
    manifest=json.loads((replay/'manifest.json').read_text())
    if manifest['identity'].get('tia_restore_variant') not in ['tia_r2','tia_r4']:
        raise ValueError('Use the declared original feedback-receiver family')
    # Both summaries already exist: the unchanged original producer can only
    # remeasure its completed native waveforms. It retains a false verdict.
    native_probe.run(replay)
    report=json.loads((replay/'summary.json').read_text())
    if (report.get('diagnostic_complete') is not True or type(report.get('native_clock_passed')) is not bool or
            report.get('manifest_sha256')!=sha(replay/'manifest.json')):
        raise ValueError('Native diagnostic evidence is incomplete or stale')
    return dict(legacy_native_clock_passed=report['native_clock_passed'],legacy_native_report_sha256=sha(replay/'summary.json'))


def fixture(deck, old, new, nodes):
    lines = list(re.finditer(r'(?im)^\.tran[^\n]*$',deck))
    if len(lines) != 1 or lines[0][0].split()[1:] != ['20p','188.049n','0','20p']:
        raise ValueError('Require the unchanged complete 188.049 ns/20 ps corrected-link fixture')
    deck = rebind(deck,old,new)
    deck=deck.replace(lines[0][0],'.tran 20p 188.049n 0 1p',1)
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
    legacy=completed_replay(replay)
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
    names = set(old['code'])|set(i['code'])|set(code)|{NAME,'probe_receiver_tia_restore.py',
        'probe_receiver_candidate_link.py','spice_dispatch.py','spice_scope.py'}
    identity = dict(parent=str(parent.relative_to(ROOT)),replay=str(replay.relative_to(ROOT)),
        receiver=str(layout.relative_to(ROOT)),variant=i['tia_restore_variant'],
        driver_current_ratio=110,config=config,simulator_provenance=provenance(),scope=SCOPE,
        diagnostic_only=True,maximum_step_ps=1,**legacy,
        inputs={str(path.relative_to(ROOT)):sha(path) for path in paths},
        code={n:sha(ROOT/'scripts'/n) for n in names},observation_nodes=i['observation_nodes'])
    out = ROOT/'build/diagnostics/receiver_feedback_link_diagnostic'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
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
    if not out.is_relative_to(ROOT/'build/diagnostics/receiver_feedback_link_diagnostic'):
        raise ValueError('Use the prepared corrected native coupled-link diagnostic')
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']; stamp = sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                i.get('diagnostic_only') is not True or i.get('maximum_step_ps')!=1 or
                any(sha(ROOT/n) != h for n,h in i['inputs'].items()) or
                any(sha(ROOT/'scripts'/n) != h for n,h in i['code'].items()) or
                any(sha(out/n) != h for n,h in m['files'].items())):
            raise ValueError('Corrected coupled native link context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged()
        cached = json.loads((out/'summary.json').read_text()) if (out/'summary.json').exists() else None
        if cached is None and any((out/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log']):
            raise ValueError('Partial corrected native link retained; use a fresh context')
        legacy=completed_replay(ROOT/i['replay'])
        if any(i.get(k)!=v for k,v in legacy.items()):raise ValueError('Legacy receiver verdict changed')
        if cached is None:
            atomic(out/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
            with lease(ROOT,priority=2,label='exploratory_corrected_driver_feedback_receiver'):
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
        result = dict(diagnostic_complete=True,qualified_phy=False,legacy_native_clock_passed=i['legacy_native_clock_passed'],passed=bool(metrics['passed'] and margin and clock),
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
