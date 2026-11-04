#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Real-TG DCC pilot; qualify every half-cycle, startup, events and terminals."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import dcc_tg_combiner_v2 as circuit
import probe_dcc_nand_node_shunt_v2 as previous
from measure_dcc_native_events_v2 import measure
from spice_dispatch import lease
from spice_engine import command,provenance
from probe_digital_dcc_v2 import sha,write,atomic

ROOT=previous.ROOT
VERSION='native-tg-dual-rail-static-storage-dcc-source-pilot-v2.1'


def fixture(out,spec,info,text):
    deck=previous.fixture(out,spec,info,text)
    deck,count=re.subn(r'(?m)^(XD[^\n]+ )'+re.escape(previous.circuit.NAME)+r'$',lambda m:m[1]+circuit.NAME,deck)
    if count!=1:raise ValueError('Require one exact real-TG DCC instance adaptation')
    return deck.replace('OpenLVDS '+previous.VERSION,'OpenLVDS '+VERSION)


def assess(folder,spec,text):
    result=measure(folder,spec,circuit.devices(text),'Native real-TG/static-storage source DCC only; no physical RC or PHY admission')
    result['mean_screen_passed']=result['pilot_passed']
    error=result['maximum_individual_half_cycle_error_ps']
    result['every_half_cycle_passed']=bool(error is not None and error<=50)
    result['pilot_passed']=result['mean_screen_passed'] and result['every_half_cycle_passed']
    return result


def prepare(parent):
    m=previous.bound(parent);i=m['identity'];witness=[]
    for k in ['0','1']:
        r=json.loads((parent/k/'summary.json').read_text())
        if r['error'] is not None or r['result']['event_integrity_passed']:
            raise ValueError('Require retained loaded-NAND event-window failures')
        witness.append(parent/k/'summary.json')
    pdk=Path(i['pdk']);variants={};shunts={}
    for v in circuit.VARIANTS:variants[v],shunts[v]=circuit.source(v,pdk.read_text())
    files=[Path(__file__),Path(circuit.__file__),Path(circuit.storage.__file__),ROOT/'scripts/native_static_cells_v2.py',
        ROOT/'scripts/dcc_nand_mid_shunt_v2.py',Path(previous.__file__),ROOT/'scripts/dcc_nand_node_shunt_v2.py',
        ROOT/'scripts/build_compound_drivers_v3.py',ROOT/'scripts/measure_dcc_native_events_v2.py',
        ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'scripts/probe_digital_dcc_v2.py',parent/'manifest.json',*witness]
    specs=[dict(variant=v,process=p,temperature=40,mhz=410,load_ff=20,slew0_ps=a,slew180_ps=b,duty=d)
        for v,p,(a,b),d in itertools.product(variants,['ss','sf'],[(100,100),(20,250),(250,20)],[.3,.7])]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
        pdk=str(pdk),pdk_sha256=sha(pdk),pdk_files=i['pdk_files'],simulator=provenance(),specs=specs,hardware=circuit.VARIANTS)
    out=ROOT/'build/diagnostics/dcc_tg_combiner_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);tasks=[]
    for v,text in variants.items():write(out/(v+'.spice'),text)
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,dict(ports=circuit.PORTS),variants[spec['variant']]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,interface=dict(ports=circuit.PORTS),shunts=shunts,
        libraries={v+'.spice':sha(out/(v+'.spice')) for v in variants},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics/dcc_tg_combiner_v2') or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or sha(Path(i['pdk']))!=i['pdk_sha256']
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or provenance()!=i['simulator']
        or any(sha(out/n)!=h for n,h in m['libraries'].items()) or m['interface']!=dict(ports=circuit.PORTS)
        or set(m['libraries'])!={v+'.spice' for v in i['hardware']} or len(m['tasks'])!=len(i['specs'])):
        raise ValueError('Native TG DCC pilot changed')
    for n,task in enumerate(m['tasks']):
        if task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']:
            raise ValueError('Native TG task metadata/deck changed')
    for v in i['hardware']:
        headers=re.findall(r'(?m)^\.subckt (\S+) ([^\n]+)',(out/(v+'.spice')).read_text())
        if headers!=[(circuit.NAME,' '.join(circuit.PORTS))]:raise ValueError('TG model header changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior native TG DCC pilot')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='dcc_tg_combiner_v2_'+task['id']):
                    bound(out);process=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                write(folder/'console.log',process.stdout+process.stderr);process.check_returncode()
                result=assess(folder,task['spec'],(out/(task['spec']['variant']+'.spice')).read_text())
            except Exception as exception:error=str(exception)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        atomic(out/'state.json',dict(status='real_tg_source_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':print(prepare(out),flush=True)
    elif a.action=='run':run(out)
    else:print(json.dumps(bound(out),indent=2))
