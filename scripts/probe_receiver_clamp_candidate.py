#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay saved pins through the audited tracked-clamp receiver candidate."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
from diagnose_link_clock import pulse_transport
from dll_campaign import atomic
from dll_candidate_library import audited
from dll_measurements import read_wave
from receiver_clamp_experiment import source_variant
from layout_receiver_clamp_candidate import source_gate
from spice_engine import command,engine,provenance
from spice_library import checked_netlist,replace
from spice_scope import closure_hash
from spice_probes import ProbeNetwork
from spice_slots import slot

ROOT=Path(__file__).resolve().parents[1]
CODE=['probe_receiver_clamp_candidate.py','layout_receiver_clamp_candidate.py','receiver_clamp_experiment.py','layout_receiver_gain_candidate.py','layout_receiver_variant.py','layout_receiver_tail_candidate.py','receiver_candidate_rc.py',
      'probe_link_clock_restore.py','diagnose_link_clock.py','dll_campaign.py','dll_candidate_library.py',
      'dll_measurements.py','spice_engine.py','spice_library.py','spice_scope.py','spice_probes.py','spice_slots.py','run_ngspice.py','simulate_link.py']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(parent,layout):
    if engine()!='ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/clock_restore') or not layout.is_relative_to(ROOT/'build/diagnostics/receiver_layout'):
        raise ValueError('Use isolated receiver/replay inputs in the pinned ngspice environment')
    if (layout/'rejected_candidate.json').exists():raise ValueError('Receiver candidate was rejected')
    physical=json.loads((layout/'summary.json').read_text());info=json.loads((layout/'extraction.json').read_text())
    scale=physical['identity']['input_tail_scale']
    if scale!=2 or physical['identity'].get('decision_clamped') is not True:
        raise ValueError('Expected the tracked-clamp physical receiver')
    source_proofs=physical['identity']['source_screen_proofs']
    if source_gate(ROOT/physical['identity']['source_screen'])!=source_proofs:
        raise ValueError('Schematic clamp gate differs from physical preparation')
    if any(digest(ROOT/name)!=value for name,value in source_proofs.items()):
        raise ValueError('Schematic clamp evidence changed')
    if not physical['passed'] or (layout/'candidate.spice').read_text()!=source_variant((ROOT/'analog/openlvds.spice').read_text(),True):
        raise ValueError('Receiver source differs from its declared tracked-clamp experiment')
    for name,value in physical['identity']['code'].items():
        if digest(ROOT/'scripts'/name)!=value:raise ValueError('Receiver physical producer changed')
    audited(layout,info);gds=ROOT/physical['designs']['openlvds_receiver_core']['gds']
    if digest(gds)!=info['gds_sha256'] or digest(layout/'candidate.spice')!=info['source_sha256']:
        raise ValueError('Receiver extraction changed')
    model=checked_netlist(info);previous=json.loads((parent/'manifest.json').read_text())
    if digest(parent/'library.spice')!=previous['library_sha256']:raise ValueError('Parent replay library changed')
    baseline=(parent/'library.spice').read_text()
    header=re.search(r'(?im)^\.subckt[ \t]+openlvds_receiver_core[^\n]*(?:\n\+[^\n]*)*',baseline)
    if not header or header[0].replace('\n+',' ').split()[2:]!=info['ports']:
        raise ValueError('Receiver candidate changes captured terminal order')
    library=replace(baseline,'openlvds_receiver_core',model)
    for name in ['lvds_bias','openlvds_ddr_rx']:
        if closure_hash(library,name)!=closure_hash(baseline,name):raise ValueError('Receiver changed unrelated replay circuits')
    aliases={}
    for leaf in ['PP','PN','CO','RESTORE0','RESTORE1','CO_TRACK']:
        nodes=sorted(set(re.findall(r'\bopenlvds_receiver_core__'+leaf+r'(?:\.t\d+)?\b',model)))
        if not nodes:raise ValueError('Missing native receiver observation terminal '+leaf)
        aliases[leaf]='XRC:'+nodes[0]
    paths=[layout/n for n in ['summary.json','extraction.json','rc_audit.json','candidate.spice']]+[gds,ROOT/info['netlist']]
    paths += [ROOT/name for name in source_proofs]
    paths += [parent/'manifest.json',parent/'library.spice']+[parent/t['id']/'bench.cir' for t in previous['tasks']]
    identity=dict(parent=str(parent.relative_to(ROOT)),layout=str(layout.relative_to(ROOT)),decision_clamped=True,input_tail_scale=scale,decision_scale=physical['identity']['decision_scale'],restoration=physical['identity']['restoration'],
        inputs={str(p.relative_to(ROOT)):digest(p) for p in paths},code={n:digest(ROOT/'scripts'/n) for n in set(CODE)|set(physical['identity']['code'])},
        simulator_provenance=provenance(),observation_nodes=aliases)
    root=ROOT/'build/diagnostics/receiver_replay'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if (root/'manifest.json').exists():return root
    root.mkdir(parents=True);(root/'library.spice').write_text(library);tasks=[]
    for task in previous['tasks']:
        old=parent/task['id'];folder=root/task['id'];folder.mkdir();deck=(old/'bench.cir').read_text()
        if digest(old/'bench.cir')!=task['deck_sha256']:raise ValueError('Parent replay fixture changed')
        include=f'.include "{parent}/library.spice"'
        if deck.count(include)!=1:raise ValueError('Ambiguous parent library binding')
        deck=deck.replace(include,f'.include "{root}/library.spice"')
        probes=re.search(r'(?im)^\.print tran[^\n]*',deck)
        if not probes:raise ValueError('Missing parent probes')
        deck=deck[:probes.end()]+' '+ ' '.join('V('+n+')' for n in aliases.values())+deck[probes.end():]
        ProbeNetwork(library).validate(deck,aliases.values())
        (folder/'bench.cir').write_text(deck);tasks.append(dict(id=task['id'],deck_sha256=digest(folder/'bench.cir')))
    atomic(root/'manifest.json',dict(identity=identity,tasks=tasks,library_sha256=digest(root/'library.spice'),qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):raise ValueError('Use a captured candidate replay')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity']
    def unchanged():
        if provenance()!=identity['simulator_provenance'] or any(digest(ROOT/'scripts'/n)!=h for n,h in identity['code'].items()):
            raise ValueError('Receiver replay producer changed')
        if any(digest(ROOT/p)!=h for p,h in identity['inputs'].items()):raise ValueError('Receiver replay input changed')
        if digest(root/'library.spice')!=manifest['library_sha256']:raise ValueError('Receiver replay library changed')
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged();results=[]
        for task in manifest['tasks']:
            folder=root/task['id'];deck=folder/'bench.cir';path=folder/'summary.json';cached=None
            if digest(deck)!=task['deck_sha256']:raise ValueError('Receiver replay fixture changed')
            if path.exists():
                cached=json.loads(path.read_text())
                if digest(folder/'bench.cir.prn')!=cached['waveform_sha256']:raise ValueError('Receiver replay waveform changed')
            else:
                atomic(folder/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
                with slot():
                    unchanged();atomic(folder/'execution.json',dict(status='running',qualified_phy=False))
                    process=subprocess.run(command(folder/'ngspice.log',deck),cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(process.stdout+process.stderr);process.check_returncode()
            wave,head=read_wave(folder/'bench.cir.prn');t=wave[:,1]
            transport=pulse_transport(t,wave[:,head['V(RCP)']]-wave[:,head['V(RCN)']],wave[:,head['V(RXCLOCK)']],15e-9,75e-9)
            keep=(t>=15e-9)&(t<=75e-9);observations={}
            for name,node in identity['observation_nodes'].items():
                v=wave[keep,head['V('+node.upper()+')']];observations[name]=dict(min_v=float(v.min()),max_v=float(v.max()))
            result=dict(task=task['id'],qualified_phy=False,qualification_verdict=None,decision_clamped=True,input_tail_scale=identity['input_tail_scale'],decision_scale=identity['decision_scale'],restoration=identity['restoration'],
                receiver_transport=transport,clock_internal_node_ranges_v=observations,
                manifest_sha256=digest(root/'manifest.json'),deck_sha256=task['deck_sha256'],waveform_sha256=digest(folder/'bench.cir.prn'))
            unchanged()
            if cached is not None and cached!=result:raise ValueError('Receiver replay saved analysis differs from its waveform')
            atomic(path,result);results.append(result)
        atomic(root/'summary.json',dict(diagnostic_complete=True,qualified_phy=False,qualification_verdict=None,
            scope='Native tracked decision-clamp and staged-restoration experiment with original pin stimuli and RX load; no PVT, stress, aperture or link qualification',
            manifest_sha256=digest(root/'manifest.json'),results=results))
    print(root/'summary.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('parent',type=Path);a.add_argument('layout',type=Path)
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.parent.resolve(),a.layout.resolve()),flush=True)
    else:run(a.artifact.resolve())
