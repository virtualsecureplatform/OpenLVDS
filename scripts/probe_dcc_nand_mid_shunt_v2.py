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
import os
import dcc_nand_mid_shunt_v2 as circuit
import probe_dcc_nand_latch_v2 as previous
from measure_dcc_native_events_v2 import measure
from spice_dispatch import lease
from spice_engine import command,provenance
from probe_digital_dcc_v2 import sha,write,atomic

ROOT=previous.ROOT
VERSION='native-mim-stack-shunted-static-nand-dcc-pilot-v2.1'


def fixture(out,spec,info,text):
    period=1000/spec['mhz'];s0=spec['slew0_ps']/1000;s1=spec['slew180_ps']/1000
    td1=2+period/2+(s0-s1)/2;release=2+3*period+s0/2+.150
    pg={'VGND':'0','VPWR':'VDD','clock_out':'Q','phase0':'P0','phase180':'P180','reset_n':'RESET_N'}
    if set(info['ports'])!=set(pg):raise ValueError('Unexpected static DCC interface')
    probes=['P0','P180','RESET_N','Q','VDD']
    for n in sorted({n for d in circuit.devices(text) for n in d['nodes']}):
        node=pg.get(n,'XD:'+n)
        if node!='0' and node not in probes:probes.append(node)
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    return (f'OpenLVDS {VERSION}\n.lib "{model}" {spec["process"]}\n.include "{out}/{spec["variant"]}.spice"\n'
        f'.options device temp={spec["temperature"]}\n.options timeint method=gear reltol=1e-4 abstol=1e-12\nVDD VDD 0 1.8\n'
        f'VR RESET_N 0 PWL(0 0 {release-.010:.15g}n 0 {release+.010:.15g}n 1.8)\n'
        f'VP0 P0 0 PULSE(0 1.8 2n {s0:.15g}n {s0:.15g}n {spec["duty"]*period-s0:.15g}n {period:.15g}n)\n'
        f'VP180 P180 0 PULSE(0 1.8 {td1:.15g}n {s1:.15g}n {s1:.15g}n {spec["duty"]*period-s1:.15g}n {period:.15g}n)\n'
        'XD '+' '.join(pg[p] for p in info['ports'])+' '+circuit.NAME+'\n'
        f'CQ Q 0 {spec["load_ff"]}f\n.tran 1p {2+22*period:.15g}n 0 1p\n'
        '.print tran '+' '.join('V('+p+')' for p in probes)+'\n.end\n')


def prepare(parent):
    m=previous.bound(parent);i=m['identity'];selected=[]
    for k in ['0','1']:
        row=json.loads((parent/k/'summary.json').read_text())
        if row['error'] is not None or row['result']['terminal_screen_passed']:
            raise ValueError('Require retained native transistor terminal failures')
        selected += [parent/k/'summary.json']
    pdk=Path(i['pdk']);variants={};stack_nodes={}
    for d in [1,2]:variants['mid'+str(d)],stack_nodes['mid'+str(d)]=circuit.source(d,pdk.read_text())
    files=[Path(__file__),Path(circuit.__file__),Path(circuit.unshunted.__file__),Path(previous.__file__),
        ROOT/'scripts/measure_dcc_native_events_v2.py',ROOT/'scripts/probe_dcc_toggle_pair_v4.py',ROOT/'scripts/probe_dcc_native_rc_v3.py',
        ROOT/'scripts/build_compound_drivers_v3.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py',
        ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/run_ngspice.py',parent/'manifest.json',*selected]
    specs=[dict(variant=v,process=p,temperature=40,mhz=410,load_ff=20,slew0_ps=a,slew180_ps=b,duty=d)
        for v,p,(a,b),d in itertools.product(variants,['ss','sf'],[(100,100),(20,250),(250,20)],[.3,.7])]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
        pdk=str(pdk),pdk_sha256=sha(pdk),pdk_files=i['pdk_files'],simulator=provenance(),specs=specs)
    out=ROOT/'build/diagnostics/dcc_nand_mid_shunt_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);tasks=[]
    info=dict(ports=circuit.PORTS)
    for v,text in variants.items():write(out/(v+'.spice'),text)
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,info,variants[spec['variant']]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,interface=info,stack_nodes=stack_nodes,
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
                result=measure(folder,task['spec'],circuit.devices((out/(task['spec']['variant']+'.spice')).read_text()),
                    'Native MIM stack-shunted static-gate source DCC only; no physical RC or PHY admission')
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
