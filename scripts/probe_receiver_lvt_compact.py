#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay original saved pins through the audited compact LVT decision receiver."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from diagnose_link_clock import pulse_transport
from dll_campaign import atomic
from dll_candidate_library import audited
from dll_measurements import read_wave
from receiver_lvt_pair_experiment import source_variant
import receiver_lvt_pair_clock as source_clock
from receiver_static_diagnosis import capture_manifest
from rx_candidate_aperture import lease
from receiver_tail_timestep_retry import tighten
from spice_engine import command,engine,provenance
from spice_library import checked_netlist,replace
from spice_scope import closure_hash
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
PROFILE=dict(clamp_variant='unclamped_lvt_pair_compact',
    diagnostic_stage='three_passing_source_DC_pilots',
    placement='Four folded frontend columns on shared M4 trunks; packed summing/decision/restoration row; critical M3 buses first')
CODE=['probe_receiver_lvt_compact.py','receiver_lvt_pair_clock.py','receiver_decision_load_clock.py',
      'receiver_lvt_pair_matrix.py','receiver_lvt_pair_experiment.py','receiver_tail_timestep_retry.py',
      'receiver_candidate_rc.py','probe_link_clock_restore.py','diagnose_link_clock.py',
      'dll_campaign.py','dll_candidate_library.py','dll_measurements.py','spice_engine.py',
      'spice_library.py','spice_scope.py','spice_probes.py','spice_slots.py',
      'run_ngspice.py','simulate_link.py','rx_candidate_aperture.py','receiver_static_diagnosis.py']


def source_gate(screen,clock):
    # Require every completed child before invoking scientific runners: the
    # admission path may remeasure cached evidence but cannot launch a source job.
    proofs=source_clock.static_gate(screen)
    if not clock.is_relative_to(ROOT/'build/diagnostics/receiver_clamp'):
        raise ValueError('Use the admitted LVT source-clock context')
    manifest=json.loads((clock/'manifest.json').read_text())
    if (manifest['identity'].get('static_screen')!=str(screen.relative_to(ROOT)) or
            manifest['identity'].get('static_proofs')!=proofs or
            not (clock/'source_clock_admission.json').is_file() or
            not (clock/'summary.json').is_file() or
            any(not (clock/t['id']/'summary.json').is_file() for t in manifest['tasks'])):
        raise ValueError('Complete all three admitted LVT source-clock controls first')
    source_clock.run(clock)
    admission=json.loads((clock/'source_clock_admission.json').read_text())
    if (admission.get('source_clock_passed') is not True or
            admission.get('manifest_sha256')!=digest(clock/'manifest.json') or
            admission.get('report_sha256')!=digest(clock/'summary.json')):
        raise ValueError('LVT source clocks failed or their evidence changed')
    files=[clock/n for n in ['manifest.json','summary.json','source_clock_admission.json']]
    for task in manifest['tasks']:
        files.extend(clock/task['id']/n for n in ['summary.json','bench.cir.prn'])
        files.extend(clock/task['id']/n for n in task['files'])
    return dict(proofs,**{str(p.relative_to(ROOT)):digest(p) for p in files})


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_profile(identity):
    if any(identity.get(name)!=value for name,value in PROFILE.items()):
        raise ValueError('Expected the exact compact LVT decision receiver profile')


def replay_deck(deck,maximum_step_ps):
    if type(maximum_step_ps) is not int or maximum_step_ps!=1:
        raise ValueError('Compact LVT native receiver requires the declared 1 ps maximum step')
    return tighten(deck)


def prepare(parent,layout,screen,clock):
    if engine()!='ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/clock_restore') or not layout.is_relative_to(ROOT/'build/diagnostics/receiver_layout'):
        raise ValueError('Use isolated receiver/replay inputs in the pinned ngspice environment')
    if any(not (layout/n).is_file() for n in ['summary.json','extraction.json','rc_audit.json','candidate.spice']):
        raise ValueError('Complete the audited compact LVT receiver geometry before native replay')
    if (layout/'rejected_candidate.json').exists():raise ValueError('Receiver candidate was rejected')
    physical=json.loads((layout/'summary.json').read_text());info=json.loads((layout/'extraction.json').read_text())
    validate_profile(physical['identity'])
    source_proofs=source_gate(screen,clock)
    if any(digest(ROOT/name)!=value for name,value in physical['identity']['source_proofs'].items()):
        raise ValueError('Physical source pilot evidence changed')
    maximum_step_ps=1
    if not physical['passed'] or (layout/'candidate.spice').read_text()!=source_variant((ROOT/'analog/openlvds.spice').read_text(),True):
        raise ValueError('Receiver source differs from the admitted LVT circuit')
    for name,value in physical['identity']['code'].items():
        if digest(ROOT/'scripts'/name)!=value:raise ValueError('Receiver physical producer changed')
    audited(layout,info);gds=ROOT/physical['designs']['openlvds_receiver_core']['gds']
    if digest(gds)!=info['gds_sha256'] or digest(layout/'candidate.spice')!=info['source_sha256']:
        raise ValueError('Receiver extraction changed')
    model=checked_netlist(info);previous=json.loads((parent/'manifest.json').read_text())
    if len(previous['tasks'])!=2 or {t['id'] for t in previous['tasks']}!={'captured','sharp_control'}:
        raise ValueError('Expected exactly the two original captured/sharp replay fixtures')
    if digest(parent/'library.spice')!=previous['library_sha256']:raise ValueError('Parent replay library changed')
    baseline=(parent/'library.spice').read_text()
    header=re.search(r'(?im)^\.subckt[ \t]+openlvds_receiver_core[^\n]*(?:\n\+[^\n]*)*',baseline)
    if not header or header[0].replace('\n+',' ').split()[2:]!=info['ports']:
        raise ValueError('Receiver candidate changes captured terminal order')
    library=replace(baseline,'openlvds_receiver_core',model)
    for name in ['lvds_bias','openlvds_ddr_rx']:
        if closure_hash(library,name)!=closure_hash(baseline,name):raise ValueError('Receiver changed unrelated replay circuits')
    aliases={}
    for leaf in ['PP','PN','CO','RESTORE0','RESTORE1','CO_TRACK','CL','CT','NBC']:
        nodes=sorted(set(re.findall(r'\bopenlvds_receiver_core__'+leaf+r'(?:\.t\d+)?\b',model)))
        if not nodes:raise ValueError('Missing native receiver observation terminal '+leaf)
        aliases[leaf]='XRC:'+nodes[0]
    paths=[layout/n for n in ['summary.json','extraction.json','rc_audit.json','candidate.spice']]+[gds,ROOT/info['netlist']]
    paths += [ROOT/name for name in source_proofs]
    paths += [parent/'manifest.json',parent/'library.spice']+[parent/t['id']/'bench.cir' for t in previous['tasks']]
    inherited=set(physical['identity']['code'])
    for path in source_proofs:
        if path.endswith('/manifest.json'):
            inherited.update(json.loads((ROOT/path).read_text()).get('identity',{}).get('code',{}))
    identity=dict(PROFILE,parent=str(parent.relative_to(ROOT)),layout=str(layout.relative_to(ROOT)),
        static_screen=str(screen.relative_to(ROOT)),source_screen=str(clock.relative_to(ROOT)),
        replay_parallel_jobs=2,source_maximum_step_ps=maximum_step_ps,native_maximum_step_ps=maximum_step_ps,
        inputs={str(p.relative_to(ROOT)):digest(p) for p in paths},
        code={n:digest(ROOT/'scripts'/n) for n in set(CODE)|inherited},
        simulator_provenance=provenance(),observation_nodes=aliases)
    root=ROOT/'build/diagnostics/receiver_replay'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    def store(path,text):
        if path.exists() and path.read_text()!=text:raise ValueError('Prepared native fixture changed')
        if not path.exists():path.write_text(text)
    store(root/'library.spice',library);tasks=[]
    for task in previous['tasks']:
        old=parent/task['id'];folder=root/task['id'];folder.mkdir(exist_ok=True);deck=(old/'bench.cir').read_text()
        if digest(old/'bench.cir')!=task['deck_sha256']:raise ValueError('Parent replay fixture changed')
        include=f'.include "{parent}/library.spice"'
        if deck.count(include)!=1:raise ValueError('Ambiguous parent library binding')
        deck=deck.replace(include,f'.include "{root}/library.spice"')
        probes=re.search(r'(?im)^\.print tran[^\n]*',deck)
        if not probes:raise ValueError('Missing parent probes')
        deck=deck[:probes.end()]+' '+ ' '.join('V('+n+')' for n in aliases.values())+deck[probes.end():]
        deck=replay_deck(deck,maximum_step_ps)
        ProbeNetwork(library).validate(deck,aliases.values())
        store(folder/'bench.cir',deck);tasks.append(dict(id=task['id'],deck_sha256=digest(folder/'bench.cir')))
    capture_manifest(root/'manifest.json',dict(identity=identity,tasks=tasks,library_sha256=digest(root/'library.spice'),qualified_phy=False))
    return root


def run(root,wait_slots=None):
    wait_slots=list(wait_slots or [])
    if len(wait_slots)>2 or any(type(n) is not int or n not in range(6) for n in wait_slots):
        raise ValueError('Use zero, one or two actual shared wait slots within the six-slot budget')
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):raise ValueError('Use a captured candidate replay')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity']
    stamp=digest(root/'manifest.json');validate_profile(identity)
    if (type(identity.get('native_maximum_step_ps')) is not int or type(identity.get('source_maximum_step_ps')) is not int or identity.get('native_maximum_step_ps')!=1 or
        identity.get('source_maximum_step_ps')!=identity['native_maximum_step_ps']):
        raise ValueError('Native receiver numerical policy differs from its source')
    if identity.get('replay_parallel_jobs')!=2:raise ValueError('Expected two independent native receiver controls')
    if len(manifest['tasks'])!=2 or {t['id'] for t in manifest['tasks']}!={'captured','sharp_control'}:
        raise ValueError('Expected both original native receiver fixtures exactly once')
    def unchanged():
        if digest(root/'manifest.json')!=stamp or provenance()!=identity['simulator_provenance'] or any(digest(ROOT/'scripts'/n)!=h for n,h in identity['code'].items()):
            raise ValueError('Receiver replay producer changed')
        if any(digest(ROOT/p)!=h for p,h in identity['inputs'].items()):raise ValueError('Receiver replay input changed')
        if digest(root/'library.spice')!=manifest['library_sha256']:raise ValueError('Receiver replay library changed')
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        policy=dict(manifest_sha256=digest(root/'manifest.json'),producer_sha256=digest(Path(__file__)),wait_slots=wait_slots,global_slot_budget=6)
        schedule=root/'execution_scheduling'/hashlib.sha256(json.dumps(policy,sort_keys=True).encode()).hexdigest()[:16]
        schedule.mkdir(parents=True,exist_ok=True);capture_manifest(schedule/'manifest.json',policy)
        def execute(task):
            folder=root/task['id'];deck=folder/'bench.cir';path=folder/'summary.json';cached=None
            if digest(deck)!=task['deck_sha256']:raise ValueError('Receiver replay fixture changed')
            if replay_deck(deck.read_text(),identity['native_maximum_step_ps'])!=deck.read_text():
                raise ValueError('Native receiver deck differs from its numerical policy')
            if path.exists():
                cached=json.loads(path.read_text())
                if digest(folder/'bench.cir.prn')!=cached['waveform_sha256']:raise ValueError('Receiver replay waveform changed')
            else:
                if any((folder/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log']):
                    raise ValueError('Incomplete native execution retained; use a fresh retry context')
                atomic(folder/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
                index=next(i for i,t in enumerate(manifest['tasks']) if t['id']==task['id'])
                with lease(wait_slots[index%len(wait_slots)] if wait_slots else None):
                    unchanged();atomic(folder/'execution.json',dict(status='running',qualified_phy=False))
                    process=subprocess.run(command(folder/'ngspice.log',deck),cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(process.stdout+process.stderr);process.check_returncode()
            wave,head=read_wave(folder/'bench.cir.prn');t=wave[:,1]
            if (len(t)<2 or not np.isfinite(wave).all() or np.any(np.diff(t)<=0) or
                t[0]>1e-15 or t[-1]<80e-9-1e-12):
                raise ValueError('Incomplete original 80 ns receiver replay')
            transport=pulse_transport(t,wave[:,head['V(RCP)']]-wave[:,head['V(RCN)']],wave[:,head['V(RXCLOCK)']],15e-9,75e-9)
            keep=(t>=15e-9)&(t<=75e-9);observations={}
            for name,node in identity['observation_nodes'].items():
                v=wave[keep,head['V('+node.upper()+')']];observations[name]=dict(min_v=float(v.min()),max_v=float(v.max()))
            result=dict(task=task['id'],qualified_phy=False,qualification_verdict=None,**PROFILE,
                native_maximum_step_ps=identity['native_maximum_step_ps'],
                receiver_transport=transport,clock_internal_node_ranges_v=observations,
                manifest_sha256=digest(root/'manifest.json'),deck_sha256=task['deck_sha256'],waveform_sha256=digest(folder/'bench.cir.prn'))
            unchanged()
            if cached is not None and cached!=result:raise ValueError('Receiver replay saved analysis differs from its waveform')
            atomic(path,result)
            atomic(folder/'execution.json',dict(status='completed',qualified_phy=False,missing_output_edges=transport['missing_output_edges']))
            return result
        # Both fixtures are independent. Each holds its own shared SPICE lease;
        # executor shutdown waits for both even if one fixture raises an error.
        def checked_execute(task):
            try:return execute(task)
            except Exception as error:
                atomic(root/task['id']/'execution.json',dict(status='held_for_diagnosis',qualified_phy=False,error=str(error)))
                raise
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(checked_execute,manifest['tasks']))
        except Exception as error:
            atomic(root/'execution.json',dict(status='held_for_diagnosis',qualified_phy=False,error=str(error)))
            raise
        unchanged()
        atomic(root/'summary.json',dict(diagnostic_complete=True,qualified_phy=False,qualification_verdict=None,
            native_clock_passed=all(len(r['receiver_transport']['pulses'])==47 and not r['receiver_transport']['missing_output_edges'] and all(p['output_edges_in_next_input_period']==1 for p in r['receiver_transport']['pulses']) for r in results),
            scope='Native compact LVT decision-pair experiment with original pin stimuli and RX load; no PVT, stress, aperture or link qualification',
            manifest_sha256=digest(root/'manifest.json'),results=results))
    print(root/'summary.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('parent',type=Path);a.add_argument('layout',type=Path)
    a.add_argument('--dc-matrix',type=Path,required=True);a.add_argument('--source-clock',type=Path,required=True)
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a.add_argument('--wait-slot',type=int,choices=range(6),action='append',default=[]);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.parent.resolve(),a.layout.resolve(),a.dc_matrix.resolve(),a.source_clock.resolve()),flush=True)
    else:run(a.artifact.resolve(),a.wait_slot)
