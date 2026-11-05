#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate return-net drive/shunt tradeoffs around unchanged whole-bank RC.

Add one independently verified native NAND2B guard-pair RC in parallel at
turn0, with/without a source 2x2 MIM. New common wiring and added MIM routing
are ideal diagnostic connections. This cannot qualify a physical repair.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
import numpy as np
import diagnose_weighted_routed_prefix_v2 as diagnosis
import probe_weighted_routed_v2 as original
import wide_guard_pair_rc_families_v2 as families
import native_clock_components_v2 as native
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=original.ROOT
VERSION='routed-return-net-native-drive-shunt-isolation-v2.1'
CONTEXT='routed_return_drive_v2'
BANK='openlvds_weighted_bank_physical_v2'
PAIR='openlvds_nand2b_4_o1_stack_guard_pair_v2'
ANCHORS=dict(A_N='forward0.B',B='IN',Y='turn0.Y',VGND='VGND',VPWR='VPWR')
STOP=8e-9


def specifications():
    return [dict(tag=tag,shunt_um=dim) for tag,dim in [('boost_only',0),('boost_and_mim',2)]]


def check_anchors(bank,ext):
    defs=native.definitions(bank)
    if set(defs)!={BANK}:raise ValueError('Require the original flat full-bank RC')
    ports,body=defs[BANK];nodes=set(ports)
    for w in body:
        if w[0][0].upper() in ['R','C']:nodes.update(w[1:3])
        else:
            first=next((i for i,v in enumerate(w) if '=' in v),len(w));nodes.update(w[1:first-1])
    if not set(ANCHORS.values())<=nodes or 'XBOOST' in bank or PAIR in defs:
        raise ValueError('Missing physical anchor or preexisting diagnostic boost')
    aliases=original.observation.Groups();known=set()
    for line in ext.splitlines():
        if line.startswith('node '):
            w=shlex.split(line);known.add(w[1]);aliases.root(w[1])
        elif line.startswith('equiv '):
            w=shlex.split(line);known.update(w[1:3]);aliases.join(w[1],w[2])
    for pin in ['A_N','B','Y']:
        if 'turn0.'+pin not in known or ANCHORS[pin] not in known:raise ValueError('Missing physical return pin alias')
        if aliases.root('turn0.'+pin)!=aliases.root(ANCHORS[pin]):
            raise ValueError('Return-net physical pin aliases disagree: '+pin)
    return ports


def augment(bank,pair,spec,old_devices):
    if spec not in specifications():raise ValueError('Unknown explicit return-drive case')
    defs=native.definitions(pair)
    if set(defs)!={PAIR} or set(defs[PAIR][0])!=set(ANCHORS):raise ValueError('Native boost pair interface changed')
    endings=list(re.finditer(r'(?m)^\.ends(?:[ \t]+[^\n]*)?[ \t]*$',bank))
    if len(endings)!=1 or 'XBOOST' in bank:raise ValueError('Require one unchanged root bank')
    rows=['XBOOST '+' '.join(ANCHORS[p] for p in defs[PAIR][0])+' '+PAIR]
    if spec['shunt_um']:
        rows.append('XBOOST_SHUNT '+ANCHORS['Y']+' '+ANCHORS['VGND']+' sky130_fd_pr__cap_mim_m3_1 w=2 l=2')
    insertion='\n'.join(rows)+'\n';pos=endings[0].start()
    text=bank[:pos]+insertion+bank[pos:]+pair
    # Exact byte identity of every original element, including all diodes and
    # distributed rails; no topology collapse or source-device replacement.
    if text[:pos]+text[pos+len(insertion):len(text)-len(pair)]!=bank:
        raise ValueError('Original whole-bank RC bytes changed')
    ports=native.definitions(bank)[BANK][0]
    def observed(node):return '0' if node=='VGND' else 'VDD' if node=='VPWR' else node if node in ports else 'XD:'+node
    added=native.mapped_mos(pair,PAIR,{p:observed(ANCHORS[p]) for p in ANCHORS},'XD:XBOOST')
    if not added or any(d['limit_v']!=1.95 for d in added):raise ValueError('Missing complete native boost MOS coverage')
    devices=old_devices+added
    if len({d['name'] for d in devices})!=len(devices):raise ValueError('Native boost witness collides with retained devices')
    return text,devices,len(added)


def fixture(folder,spec,witness):
    deck=original.fixture(folder,spec,witness)
    title='OpenLVDS '+original.VERSION+'\n';stop='.tran 2p 60n 0 2p'
    if not deck.startswith(title) or deck.count(stop)!=1:raise ValueError('Original pulse source/options/stop changed')
    return deck.replace(title,'OpenLVDS '+VERSION+'\n',1).replace(stop,'.tran 2p 8n 0 2p',1)


def measure(folder,spec,witness):
    requested={'v('+n.replace(':','.').lower()+')' for d in witness['devices'] for n in d['terminals'] if n!='0'}
    requested.update('v('+n.replace(':','.').lower()+')' for c in witness['controls'] for n in c['nodes'] if n!='0')
    requested.update({'v(in)','v(out)',*[f'v(b{i})' for i in range(5)],*[f'v(c{i})' for i in range(15)]})
    names,w=validate(folder/'bench.raw',requested,STOP)
    return dict(analyze(names,w,witness),completed_diagnostic_ns=8)


def analyze(names,w,witness):
    idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12
    stress=diagnosis.terminal_observations(names,w,witness['devices']);pulses={};pulse_ok=True
    for up,label in [(True,'rise'),(False,'fall')]:
        a=crossings(t,w[:,idx['v(in)']],up);b=crossings(t,w[:,idx['v(out)']],up)
        valid=len(a)==len(b)==1 and b[0]>a[0];pulse_ok &= valid
        pulses[label+'_delay_ps']=float(b[0]-a[0]) if valid else None
    for pin in [*[f'v(b{i})' for i in range(5)],*[f'v(c{i})' for i in range(15)]]:
        if np.max(np.abs(w[:,idx[pin]]))>.01:raise ValueError('First-pulse all-zero external control stimulus changed')
    controls=[];stable=(t>=1500)&(t<=7500)
    if not np.any(stable):raise ValueError('Missing first-pulse settled interval')
    for c in witness.get('controls',[]):
        target=1.8 if c['kind']=='fine_b' else 0.
        error=max(float(np.max(np.abs(w[stable,idx['v('+n.replace(':','.').lower()+')']]-target))) for n in c['nodes'])
        controls.append(dict(kind=c['kind'],bit=c['bit'],maximum_deviation_v=error,passed=error<=.18))
    control_ok=all(c['passed'] for c in controls)
    headroom=1e6/410/4-max(pulses.values()) if pulse_ok else None
    return dict(pulses=pulses,pulse_integrity_passed=bool(pulse_ok),terminal_observations=stress,
        controls=controls,routed_control_settling_passed=control_ok,
        terminal_screen_passed=stress['violating_devices']==0,minimum_quarter_headroom_ps=headroom,
        first_pulse_diagnostic_passed=bool(pulse_ok and control_ok and stress['violating_devices']==0 and headroom>0),
        qualified_phy=False,electrical_qualification_passed=False,
        scope='One complete 8ns SS40 pulse at coarse/fine zero; original whole-bank RC plus native guard pair and optional source MIM, ideal new common wiring; no physical repair, dense codes, periodic clocks, all-PVT or PHY admission')


def components(parent,receipt):
    m=original.bound(parent);group,files=families.witnesses(receipt)
    if set(group)!={PAIR}:raise ValueError('Require the independently verified wide-power native pair alone')
    bank=(parent/'bank.spice').read_text();pair=group[PAIR]['text'];exts=[ROOT/n for n in m['identity']['inputs'] if n.endswith('_rcx.ext')]
    if len(exts)!=1:raise ValueError('Missing exact whole-bank alias extraction')
    check_anchors(bank,exts[0].read_text());return m,bank,pair,files


def prepare(prefix_receipt,pair_receipt):
    if engine()!='ngspice':raise ValueError('Use pinned native ngspice')
    diagnosis.verify(prefix_receipt);r=json.loads((prefix_receipt/'summary.json').read_text());di=r['identity'];parent=ROOT/di['parent']
    if (di['case']!='0' or di['task']['spec']['coarse']!=0 or not r['terminal_observations']['violating_devices']
        or di['raw']['last_time_s']<=STOP):raise ValueError('Require the exact observed first-pulse routed overvoltage baseline')
    m,bank,pair,paths=components(parent,pair_receipt);old=m['identity']['witness'];variants={};devices=None;added=None
    for spec in specifications():
        text,mos,count=augment(bank,pair,spec,old['devices']);variants[spec['tag']]=text
        if devices is not None and (mos!=devices or count!=added):raise ValueError('Return-drive cases changed MOS coverage')
        devices,added=mos,count
    witness=dict(old,devices=devices)
    paths += [prefix_receipt/'summary.json',parent/'manifest.json',parent/'bank.spice',parent/'control_gate.json']
    paths += [ROOT/n for n in di['inputs']]
    paths += [Path(__file__),Path(diagnosis.__file__),Path(original.__file__),Path(families.__file__),Path(native.__file__),
              ROOT/'scripts/run_native_binary_v2.py',ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),prefix_receipt=str(prefix_receipt.relative_to(ROOT)),
        pair_receipt=str(pair_receipt.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        pdk_files=m['identity']['pdk_files'],simulator=provenance(),specs=specifications(),baseline_spec=di['task']['spec'],
        witness=witness,anchors=ANCHORS,original_native_mos=len(old['devices']),added_native_mos=added,
        unchanged_original_bank_rc=True,maximum_step_ps=2,stop_ns=8,
        new_shared_wiring='ideal diagnostic connections',optional_mim='source native 2x2 MIM; no new routed physical geometry')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);write(out/'baseline.spice',bank);write(out/'pair.spice',pair);tasks=[]
    for number,spec in enumerate(identity['specs']):
        folder=out/str(number);folder.mkdir();write(folder/'bank.spice',variants[spec['tag']]);write(folder/'bench.cir',fixture(folder,identity['baseline_spec'],witness))
        tasks.append(dict(id=str(number),spec=spec,library_sha256=sha(folder/'bank.spice'),deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={n:sha(out/n) for n in ['baseline.spice','pair.spice']},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or engine()!='ngspice' or provenance()!=i['simulator'] or i['specs']!=specifications() or len(m['tasks'])!=2
        or any(sha(out/n)!=h for n,h in m['libraries'].items()) or i['anchors']!=ANCHORS or not i['unchanged_original_bank_rc']):
        raise ValueError('Native routed return-drive context changed')
    parent=ROOT/i['parent'];pm=original.bound(parent);old=pm['identity']['witness'];bank=(out/'baseline.spice').read_text();pair=(out/'pair.spice').read_text()
    if bank!=(parent/'bank.spice').read_text():raise ValueError('Retained whole-bank RC changed')
    for number,(task,spec) in enumerate(zip(m['tasks'],specifications())):
        text,devices,added=augment(bank,pair,spec,old['devices']);folder=out/str(number)
        if (task['id']!=str(number) or task['spec']!=spec or sha(folder/'bank.spice')!=task['library_sha256']
            or sha(folder/'bench.cir')!=task['deck_sha256'] or (folder/'bank.spice').read_text()!=text
            or (folder/'bench.cir').read_text()!=fixture(folder,i['baseline_spec'],i['witness'])
            or devices!=i['witness']['devices'] or added!=i['added_native_mos']):raise ValueError('Native return-drive library/deck/witness changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain the prior return-drive diagnostic')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,task['spec'],m['identity']['witness'])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False));atomic(out/'state.json',dict(status='return_drive_diagnostic_complete',cases=2,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--pair-receipt',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if a.pair_receipt is None:p.error('Provide --pair-receipt')
        print(prepare(a.artifact.resolve(),a.pair_receipt.resolve()),flush=True)
    else:run(a.artifact.resolve())
