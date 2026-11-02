#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""After line isolation, restore the preferred TIA r2 and extend its coupled test."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
import numpy as np
import isolate_channel_model as channel
import receiver_spec_screen as receiver
from dll_campaign import atomic,text_block
from dll_candidate_library import audited
from dll_measurements import read_wave
from receiver_static_diagnosis import capture_manifest
from spice_library import checked_netlist,replace
from spice_probes import ProbeNetwork
from spice_scope import closure_hash
from spice_engine import command,provenance
from spice_dispatch import lease
from simulate_link import analyze,edge_times,word_stream
from diagnose_link_clock import pulse_transport

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
CODE=['restore_baseline_coupled.py','isolate_channel_model.py','receiver_spec_screen.py',
      'dll_campaign.py','dll_candidate_library.py','dll_measurements.py','receiver_static_diagnosis.py',
      'spice_library.py','spice_probes.py','spice_scope.py','spice_engine.py','spice_dispatch.py',
      'run_ngspice.py','simulate_link.py','diagnose_link_clock.py']


def context(root):
    m=json.loads((root/'manifest.json').read_text());i=m['identity']
    if root.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]:raise ValueError('Prerequisite identity changed')
    if any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()):raise ValueError('Prerequisite source/producer changed')
    return m


def complete(names,w,stop):
    if w.ndim!=2 or len(w)<2 or 'time' not in names:return False
    t=w[:,names.index('time')]
    return bool(np.isfinite(w).all() and t[0]<=1e-15 and np.all(np.diff(t)>0) and t[-1]>=stop-1e-12)


def receipt(root,m,task):
    folder=root/task['id'];r=json.loads((folder/'summary.json').read_text())
    if r.get('numerically_completed') is not True or r.get('returncode')!=0 or r.get('manifest_sha256')!=sha(root/'manifest.json'):raise ValueError('Require completed numerical prerequisite')
    if any(sha(folder/n)!=h for n,h in dict(task['files'],**r['files']).items()):raise ValueError('Completed prerequisite fixture/output changed')
    if not complete(*channel.read_raw(folder/'bench.raw'),12e-9):raise ValueError('Incomplete line prerequisite')
    return r,[folder/n for n in set(task['files'])|set(r['files'])|{'summary.json'}]


def receiver_probes(deck,model):
    # Only replace the fourteen receiver-internal observations; the complete
    # native TX/RX/bias/driver interface and public print order are preserved.
    def bind(match):
        prefix,leaf=match.groups()
        found=sorted(set(re.findall(r'\b'+TOP+'__'+leaf+r'(?:\.(?:t|n)\d+)?\b',model)))
        if not found:raise ValueError('Missing preferred receiver observation '+leaf)
        return 'V('+prefix+found[0]+')'
    result,count=re.subn(r'V\((X[DC]R:)'+TOP+r'__(PP|PN|CO|CL|CT|RESTORE0|RESTORE1)(?:\.(?:t|n)\d+)?\)',bind,deck)
    if count!=14:raise ValueError('Require fourteen original coupled receiver observations')
    return result


def prepare(campaign,screen):
    if not campaign.is_relative_to(ROOT/'build/diagnostics/channel_model_isolation') or not screen.is_relative_to(ROOT/'build/diagnostics/receiver_spec_screen'):raise ValueError('Use line isolation and preferred receiver specification screen')
    cm=context(campaign);sm=context(screen);paths=[campaign/'manifest.json',screen/'manifest.json']
    if provenance()!=cm['identity']['simulator'] or provenance()!=sm['identity']['simulator']:raise ValueError('Prerequisite runtime changed')
    if [c['load_ohm'] for c in cm['calibrations']]!=[25,50,100]:raise ValueError('Require all line calibration loads')
    for task in cm['calibrations']:
        r,files=receipt(campaign,cm,task);w,h=read_wave(campaign/task['id']/'bench.cir.prn')
        metrics=channel.calibrated(w,h,task['load_ohm'])
        if r['metrics']!=metrics or metrics['passed'] is not True:raise ValueError('Line calibration failed or changed')
        paths+=files
    tasks=[t for t in cm['tasks'] if t['id']=='ltra_lossless']
    if len(tasks)!=1:raise ValueError('Require unique equivalent-delay line control')
    _,files=receipt(campaign,cm,tasks[0]);paths+=files
    native=[t for t in sm['tasks'] if t['test']=='rate']
    if len(native)!=3 or {t['mhz'] for t in native}!={390,400,410}:raise ValueError('Require all three preferred native rate screens')
    for task in native:
        folder=screen/task['id'];r=json.loads((folder/'summary.json').read_text())
        if any(sha(folder/n)!=h for n,h in task['files'].items()):raise ValueError('Native rate fixture changed')
        w,h=read_wave(folder/'bench.cir.prn');metrics=receiver.measure(w,h,task)
        expected=dict(task=task['id'],**metrics,waveform_sha256=sha(folder/'bench.cir.prn'),manifest_sha256=sha(screen/'manifest.json'),qualified_phy=False)
        if metrics['passed'] is not True or r!=expected:raise ValueError('Preferred native rate evidence failed or changed')
        paths += [folder/n for n in ['bench.cir','library.spice','summary.json','bench.cir.prn']]
    layout=ROOT/sm['identity']['layout'];physical=json.loads((layout/'summary.json').read_text());info=json.loads((layout/'extraction.json').read_text())
    if physical['identity'].get('tia_restore_variant')!='tia_r2' or physical['passed'] is not True:raise ValueError('Use the preferred original two-resistor TIA physical model')
    audited(layout,info);model=checked_netlist(info)
    if sha(layout/'candidate.spice')!=info['source_sha256'] or sha(ROOT/physical['designs'][TOP]['gds'])!=info['gds_sha256']:raise ValueError('Preferred receiver source/GDS changed')
    source=campaign/'ltra_lossless';base=(source/'library.spice').read_text()
    header=lambda t:re.search(r'(?im)^\.subckt '+TOP+r'[^\n]*(?:\n\+[^\n]*)*',t)[0].replace('\n+',' ').split()[2:]
    if header(base)!=header(model):raise ValueError('Preferred receiver changes public terminal order')
    library=replace(base,TOP,text_block(model,TOP))
    for name in ['lvds_bias','openlvds_driver_core','openlvds_tx_core','openlvds_ddr_rx']:
        if closure_hash(base,name)!=closure_hash(library,name):raise ValueError('Restoring baseline changed unrelated block '+name)
    paths += [layout/n for n in ['summary.json','candidate.spice','extraction.json','rc_audit.json']]+[ROOT/info['netlist'],ROOT/physical['designs'][TOP]['gds']]
    identity=dict(campaign=str(campaign.relative_to(ROOT)),screen=str(screen.relative_to(ROOT)),layout=str(layout.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},code={**cm['identity']['code'],**sm['identity']['code'],**{n:sha(ROOT/'scripts'/n) for n in CODE}},
        simulator=provenance(),scope='Preferred two-resistor TIA, original raw TX/native digital RX, corrected 110:1 driver and calibrated original-delay LTRA channel. Fresh twelve-ns numerical check before full 188.049 ns/32-bit/60 ns training diagnostic. Full components, 256-cycle training, measured aperture, DLL and PHY release remain required.')
    out=ROOT/'build/diagnostics/baseline_coupled_restoration'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True);prepared=[]
    for name,stop in [('short',12),('payload',188.049)]:
        folder=out/name;folder.mkdir(exist_ok=True);deck=(source/'bench.cir').read_text();include=f'.include "{source}/library.spice"'
        if deck.count(include)!=1 or re.findall(r'(?im)^\.tran[^\n]+',deck)!=['.tran 1p 12n 0 1p']:raise ValueError('Require exact complete line-control fixture')
        deck=receiver_probes(deck.replace(include,f'.include "{folder}/library.spice"').replace('.tran 1p 12n 0 1p',f'.tran 1p {stop}n 0 1p'),model)
        ProbeNetwork(library).validate(deck,re.findall(r'V\(([^)]+)\)',re.search(r'(?im)^\.print tran[^\n]+',deck)[0]))
        for n,body in [('bench.cir',deck),('library.spice',library)]:
            p=folder/n
            if p.exists() and p.read_text()!=body:raise ValueError('Prepared preferred receiver coupled fixture changed')
            if not p.exists():p.write_text(body)
        prepared.append(dict(id=name,stop_ns=stop,files={n:sha(folder/n) for n in ['bench.cir','library.spice']}))
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=prepared,qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/baseline_coupled_restoration'):raise ValueError('Use preferred baseline coupled restoration context')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    if [(t['id'],t['stop_ns']) for t in m['tasks']]!=[('short',12),('payload',188.049)]:raise ValueError('Require short check before full original payload diagnostic')
    def unchanged():
        context(out)
        if sha(out/'manifest.json')!=stamp or provenance()!=i['simulator']:raise ValueError('Baseline restoration context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior baseline coupled output retained')
        results=[]
        for task in m['tasks']:
            folder=out/task['id']
            if any(sha(folder/n)!=h for n,h in task['files'].items()):raise ValueError('Baseline fixture changed')
            if any((folder/n).exists() for n in ['bench.raw','summary.json','ngspice.log']):raise ValueError('Partial baseline output retained')
            atomic(out/'state.json',dict(status='waiting_for_'+task['id'],qualified_phy=False))
            with lease(ROOT,priority=2,label='baseline_coupled_'+task['id']):
                unchanged();atomic(out/'state.json',dict(status='running_'+task['id'],qualified_phy=False))
                p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
            (folder/'console.log').write_text(p.stdout+p.stderr);unchanged();numerical=False;metrics=None;transport=None
            if p.returncode==0:
                names,w=read_raw(folder/'bench.raw');numerical=complete(names,w,task['stop_ns']*1e-9)
                if numerical and task['id']=='payload':
                    wave,h=read_wave(folder/'bench.cir.prn');t=wave[:,1];v=lambda n:wave[:,h['V('+n+')']]
                    rises=edge_times(t,v('CLK0'),rising=True);launch=rises[rises>=60e-9][:16]*1e9
                    if len(launch)!=16:raise ValueError('Incomplete original 32-bit payload launch clocks')
                    metrics=analyze(wave,word_stream(16),launch,1000/410)
                    transport=pulse_transport(t,v('RCP')-v('RCN'),v('RXCLOCK'),60e-9,120e-9)
            log=(folder/'ngspice.log').read_text();failure=re.search(r'Timestep too small;[^\n]+',log)
            result=dict(task=task['id'],numerically_completed=numerical,returncode=p.returncode,metrics=metrics,clock_transport=transport,
                failure=failure[0] if failure else None,electrical_verdict=None,qualified_phy=False,manifest_sha256=stamp,
                files={n:sha(folder/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (folder/n).exists()})
            capture_manifest(folder/'summary.json',result);results.append(result)
            if not numerical:break
        capture_manifest(out/'summary.json',dict(results=results,manifest_sha256=stamp,qualified_phy=False,scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_diagnostic' if len(results)==2 and results[-1]['numerically_completed'] else 'held_numerical_failure',qualified_phy=False))


def owner(unit):
    p=subprocess.run(['systemctl','--user','show',unit,'--property=MainPID,ActiveState,InvocationID,ExecStart'],capture_output=True,text=True,check=True)
    return dict(line.split('=',1) for line in p.stdout.splitlines())


def prepare_followup(campaign,screen,unit):
    if not campaign.is_relative_to(ROOT/'build/diagnostics/channel_model_isolation') or not screen.is_relative_to(ROOT/'build/diagnostics/receiver_spec_screen'):raise ValueError('Use line campaign and preferred screen')
    live=owner(unit);relative=str(campaign.relative_to(ROOT))
    if live.get('MainPID','0')=='0' or live.get('ActiveState')!='active' or 'scripts/isolate_channel_model.py run '+relative not in live.get('ExecStart',''):raise ValueError('Require exact live channel-control owner')
    paths=[campaign/'manifest.json',screen/'manifest.json',Path(__file__),ROOT/'scripts/env.sh']
    i=dict(campaign=relative,screen=str(screen.relative_to(ROOT)),unit=unit,owner=live,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        scope='Resource handoff only. Complete calibrated LTRA twelve-ns control before preferred TIA r2 short/payload diagnostics. The scientific preparer rechecks every prerequisite. No outer SPICE lease and no qualification promotion.')
    out=ROOT/'build/diagnostics/baseline_coupled_followup'/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    capture_manifest(out/'manifest.json',dict(identity=i,qualified_phy=False));return out


def followup(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/baseline_coupled_followup'):raise ValueError('Use prepared baseline coupled handoff')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    source=ROOT/i['campaign'];receipt_path=source/'ltra_lossless/summary.json'
    def unchanged():
        if sha(out/'manifest.json')!=stamp or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()):raise ValueError('Baseline coupled resource handoff changed')
    def call(args,label):
        unchanged()
        with (out/(label+'.log')).open('x') as log:
            p=subprocess.run([str(ROOT/'scripts/env.sh'),'--ngspice','/usr/bin/python3','scripts/restore_baseline_coupled.py']+args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        p.check_returncode();unchanged();lines=(out/(label+'.log')).read_text().strip().splitlines()
        return lines[-1] if lines else ''
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if (out/'state.json').exists():raise ValueError('Prior baseline resource handoff retained')
        while not receipt_path.exists():
            unchanged()
            if owner(i['unit'])!=i['owner']:
                if receipt_path.exists():continue
                raise ValueError('Exact channel owner ended or changed before terminal LTRA evidence')
            atomic(out/'state.json',dict(status='waiting_for_full_ltra_control',qualified_phy=False));time.sleep(20)
        r=json.loads(receipt_path.read_text())
        if r.get('manifest_sha256')!=sha(source/'manifest.json'):raise ValueError('LTRA terminal result binding changed')
        if r.get('numerically_completed') is not True:
            capture_manifest(out/'summary.json',dict(status='held_ltra_control_failed',qualified_phy=False,manifest_sha256=stamp))
            atomic(out/'state.json',dict(status='held_ltra_control_failed',qualified_phy=False));return
        atomic(out/'state.json',dict(status='preparing_preferred_receiver',qualified_phy=False))
        inside=Path(call(['prepare',i['campaign'],'--receiver-screen',i['screen']],'prepare'))
        if not inside.is_relative_to('/work/OpenLVDS/build/diagnostics/baseline_coupled_restoration'):raise ValueError('Unexpected baseline restoration artifact')
        relative=str(inside.relative_to('/work/OpenLVDS'))
        capture_manifest(out/'prepared.json',dict(artifact=relative,manifest_sha256=sha(ROOT/relative/'manifest.json'),qualified_phy=False))
        atomic(out/'state.json',dict(status='running_preferred_receiver_diagnostics',artifact=relative,qualified_phy=False))
        call(['run',relative],'run');r=json.loads((ROOT/relative/'summary.json').read_text())
        capture_manifest(out/'summary.json',dict(artifact=relative,report_sha256=sha(ROOT/relative/'summary.json'),qualified_phy=False,manifest_sha256=stamp))
        atomic(out/'state.json',dict(status='finished_preferred_receiver_diagnostics',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','prepare-followup','followup']);p.add_argument('artifact',type=Path);p.add_argument('--receiver-screen',type=Path);p.add_argument('--producer-unit');a=p.parse_args()
    if a.action in ['prepare','prepare-followup']:
        if not a.receiver_screen:p.error('--receiver-screen required')
        if a.action=='prepare':print(prepare(a.artifact.resolve(),a.receiver_screen.resolve()),flush=True)
        else:
            if not a.producer_unit:p.error('--producer-unit required')
            print(prepare_followup(a.artifact.resolve(),a.receiver_screen.resolve(),a.producer_unit),flush=True)
    elif a.action=='run':run(a.artifact.resolve())
    else:followup(a.artifact.resolve())
