#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded native static-gate DCC pilot with complete terminal monitoring.

Keep prior toggle-FF/XNOR failures. No reset, waveform, threshold or stress
measurement is relaxed; the public output is held HIGH by a real NAND in reset.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess
import dcc_nand_latch_v2 as circuit
import probe_dcc_toggle_pair_v4 as previous
from spice_dispatch import lease
from spice_engine import command,provenance
from probe_digital_dcc_v2 import sha,write,atomic

ROOT=previous.ROOT
VERSION='static-nand-master-slave-toggle-dcc-source-pilot-v2.1'


def fixture(out,spec,info,text):
    deck=previous.fixture(out,spec,info,text)
    deck,count=re.subn(r'(?m)^(XD[^\n]+ )'+re.escape(previous.native.NAME)+r'$',lambda m:m[1]+circuit.NAME,deck)
    if count!=1:raise ValueError('Require exact static DCC instance adaptation')
    return deck.replace('OpenLVDS '+previous.native.VERSION,'OpenLVDS '+VERSION)


def prepare(parent):
    m=previous.bound(parent);i=m['identity'];selected=[]
    for k in ['0','1']:
        row=json.loads((parent/k/'summary.json').read_text())
        if row['error'] is not None or row['result']['terminal_screen_passed']:
            raise ValueError('Require retained native transistor terminal failures')
        selected += [parent/k/'summary.json']
    pdk=Path(i['pdk']);variants={'nand'+str(d):circuit.source(d,pdk.read_text()) for d in [1,2]}
    files=[Path(__file__),Path(circuit.__file__),Path(previous.__file__),Path(previous.native.__file__),
        ROOT/'scripts/build_compound_drivers_v3.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/run_ngspice.py',parent/'manifest.json',*selected]
    specs=[dict(variant=v,process=p,temperature=40,mhz=410,load_ff=20,slew0_ps=a,slew180_ps=b,duty=d)
        for v,p,(a,b),d in itertools.product(variants,['ss','sf'],[(100,100),(20,250),(250,20)],[.3,.7])]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
        pdk=str(pdk),pdk_sha256=sha(pdk),pdk_files=i['pdk_files'],simulator=provenance(),specs=specs)
    out=ROOT/'build/diagnostics/dcc_nand_latch_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);tasks=[]
    info=dict(ports=circuit.PORTS)
    for v,text in variants.items():write(out/(v+'.spice'),text)
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,info,variants[spec['variant']]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,interface=info,
        libraries={v+'.spice':sha(out/(v+'.spice')) for v in variants},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or sha(Path(i['pdk']))!=i['pdk_sha256']
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or provenance()!=i['simulator']
        or any(sha(out/n)!=h for n,h in m['libraries'].items())
        or any(sha(out/t['id']/'bench.cir')!=t['deck_sha256'] for t in m['tasks'])):
        raise ValueError('Static NAND DCC pilot changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior static NAND DCC pilot')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='dcc_nand_latch_v2_'+task['id']):
                    bound(out);process=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                write(folder/'console.log',process.stdout+process.stderr);process.check_returncode()
                result=previous.measure(folder,task['spec'],m['interface'],(out/(task['spec']['variant']+'.spice')).read_text())
                result['scope']='Native static NAND/inverter source DCC only; synchronous internal reset, real output reset NAND; no RC or PHY admission'
            except Exception as exception:error=str(exception)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        atomic(out/'state.json',dict(status='static_gate_source_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','bound']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':print(prepare(out),flush=True)
    elif a.action=='run':run(out)
    else:print(json.dumps(bound(out),indent=2))
