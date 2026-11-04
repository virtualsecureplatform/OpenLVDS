#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolated native shunted NAND RC pulse/load/stress pilot; no DCC admission."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import numpy as np
from continuous_clock_conditioner_v2 import mapped_mos
from probe_digital_dcc_v2 import sha,write,atomic,crossings
from run_ngspice import read_raw
from spice_library import checked_netlist
from spice_dispatch import lease
from spice_engine import command,provenance
import probe_dcc_tg_ratio_v2 as models

ROOT=models.ROOT
VERSION='native-shunted-nand-isolated-rc-pulse-load-stress-v2.1'


def witnesses(parent):
    m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    if (parent.parent!=ROOT/'build/diagnostics/nand_shunt_rc_v2' or i['version']!='native-shunted-nand-gate-rc-and-topology-v2.1'
        or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]):raise ValueError('Unexpected gate RC context')
    paths=[parent/n for n in ['manifest.json','summary.json','state.json']]
    if any(sha(ROOT/n)!=h for n,h in {**i['code'],**i['inputs']}.items()):raise ValueError('Changed extraction witness')
    paths += [ROOT/n for n in {**i['code'],**i['inputs']}]
    report=json.loads((parent/'summary.json').read_text());physical=ROOT/i['parent']
    pm=json.loads((physical/'manifest.json').read_text())['identity']
    # Native extraction was already independently topology checked. No PNR-tool
    # imports in the NumPy simulator interpreter; retain its exact receipts.
    for key in ['code','inputs']:
        for n,h in pm.get(key,{}).items():
            if sha(ROOT/n)!=h:raise ValueError('Changed physical source witness')
            paths.append(ROOT/n)
    if not report['passed'] or len(report['rows'])!=2:raise ValueError('Require two topology-clean gates')
    gates={}
    for row in report['rows']:
        name=row['macro'];info=row['extraction'];text=checked_netlist(info)
        if not row['rc_topology_passed'] or set(info['ports'])!={'A','B','Y','VPWR','VGND'}:raise ValueError('Gate interface/topology mismatch')
        folder=physical/name
        if sha(folder/(name+'.gds'))!=info['gds_sha256'] or sha(folder/(name+'.sch.spice'))!=info['source_scope_sha256']:
            raise ValueError('Gate geometry/schematic mismatch')
        gates[name]=dict(info=info,text=text)
        paths += [ROOT/info['netlist'],ROOT/info['raw_netlist'],parent/name/'summary.json',parent/name/'lvs.log']
    return gates,paths


def fixture(out,spec,gate,devices):
    p=1000/spec['mhz'];s=spec['slew_ps']/1000;mapping=dict(A='A',B='B',Y='Y',VPWR='VDD',VGND='0')
    probes={'A','B','Y','VDD'}|{n for d in devices for n in d['terminals'] if n!='0'}
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    rows=[f'OpenLVDS {VERSION}',f'.lib "{model}" {spec["process"]}',f'.include "{out}/{spec["macro"]}.spice"',
        f'.options device temp={spec["temperature"]}', '.options timeint method=gear reltol=1e-4 abstol=1e-12','VDD VDD 0 1.8']
    for pin,offset in [('A',p/4 if spec['swap'] else 0),('B',0 if spec['swap'] else p/4)]:
        rows.append(f'V{pin} {pin} 0 PULSE(0 1.8 {2+offset:.15g}n {s:.15g}n {s:.15g}n {p/2-s:.15g}n {p:.15g}n)')
    rows += ['XG '+' '.join(mapping[n] for n in gate['info']['ports'])+' '+spec['macro'],f'CY Y 0 {spec["load_ff"]}f',
        f'.tran 1p {2+9*p:.15g}n 0 1p','.print tran '+' '.join('V('+n+')' for n in sorted(probes)),'.end','']
    return '\n'.join(rows)


def analyze(folder,spec,devices):
    names,w=read_raw(folder/'bench.raw');idx={n:i for i,n in enumerate(names)};t=w[:,idx['time']]*1e12;stop=2000+9e6/spec['mhz']
    if not np.isfinite(w).all() or t[-1]<stop-.01:raise ValueError('Incomplete/nonfinite native gate transient')
    def get(n):return np.zeros(len(t)) if n=='0' else w[:,idx['v('+n.replace(':','.').lower()+')']]
    source=sorted((float(a),pin,up) for pin in ['A','B'] for up in [True,False] for a in crossings(t,get(pin),up))
    qr,qf=crossings(t,get('Y'),True),crossings(t,get('Y'),False);edges=np.sort(np.r_[qr,qf]);state=dict(A=False,B=False);old=True;checks=[];delays=[]
    for n,(a,pin,up) in enumerate(source):
        b=source[n+1][0] if n+1<len(source) else stop;state[pin]=up;new=not(state['A'] and state['B'])
        selected=edges[(edges>a)&(edges<b)];direction=qr if new else qf;correct=direction[(direction>a)&(direction<b)]
        expected=int(old!=new);ok=len(selected)==expected and len(correct)==expected
        # Require a settled full-swing truth value before the next input edge.
        value=float(np.interp(b-min(10.,(b-a)/4),t,get('Y')));ok=bool(ok and (value>=1.62 if new else value<=.18))
        checks.append(dict(input_edge_ps=a,pin=pin,new_input=up,expected_output_edges=expected,output_edges=len(selected),passed=ok))
        if expected and len(selected)==1:delays.append(float(selected[0]-a))
        old=new
    stress=[]
    for d in devices:
        values=[get(n) for n in d['terminals']];peak=max(float(np.max(np.abs(a-b))) for a,b in itertools.combinations(values,2))
        stress.append(dict(device=d['name'],max_terminal_difference_v=peak,limit_v=d['limit_v'],passed=peak<=d['limit_v']))
    initial=float(np.interp(1000,t,get('Y')))>=1.62
    event=bool(initial and checks and all(c['passed'] for c in checks));health=all(d['passed'] for d in stress)
    return dict(event_integrity_passed=event,checks=checks,propagation_delay_range_ps=[min(delays),max(delays)] if delays else None,
        terminal_stress=stress,terminal_screen_passed=health,pilot_passed=bool(event and health),qualified_phy=False,
        scope='Isolated extracted shunted NAND pulses and terminal screening only; no DCC, bank or clock backend admission')


def prepare(parent,model_parent):
    gates,paths=witnesses(parent);mm=models.bound(model_parent)
    code=[Path(__file__),ROOT/'scripts/continuous_clock_conditioner_v2.py',ROOT/'scripts/spice_library.py',ROOT/'scripts/run_ngspice.py',
        ROOT/'scripts/probe_digital_dcc_v2.py',ROOT/'scripts/spice_dispatch.py',ROOT/'scripts/spice_engine.py']
    paths+=code+[model_parent/'manifest.json'];specs=[];devices={}
    for name,gate in gates.items():
        devices[name]=mapped_mos(gate['text'],dict(A='A',B='B',Y='Y',VGND='0',VPWR='VDD'),'XG')
        loads=[5,20] if '_2_shunted_' in name else [20,100]
        specs += [dict(macro=name,process=p,temperature=t,mhz=410,slew_ps=s,load_ff=l,swap=swap)
            for (p,t),s,l,swap in itertools.product([('ss',40),('sf',40),('ff',0)],[20,250],loads,[False,True])]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
        pdk_files=mm['identity']['pdk_files'],simulator=provenance(),specs=specs,devices=devices,gates={n:g['info'] for n,g in gates.items()})
    out=ROOT/'build/diagnostics/nand_shunt_native_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name,g in gates.items():write(out/(name+'.spice'),g['text'])
    tasks=[]
    for n,spec in enumerate(specs):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,gates[spec['macro']],devices[spec['macro']]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:sha(p) for p in out.glob('*.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics/nand_shunt_native_v2' or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or provenance()!=i['simulator'] or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=len(i['specs'])):
        raise ValueError('Native shunted gate context changed')
    for n,task in enumerate(m['tasks']):
        if task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']:raise ValueError('Gate task/deck changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior native gate pilot')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='nand_shunt_native_v2_'+task['id']):
                    bound(out);p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=analyze(folder,task['spec'],m['identity']['devices'][task['spec']['macro']])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False));atomic(out/'state.json',dict(status='native_gate_pilot_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--models',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action=='prepare':
        if a.models is None:p.error('Provide the retained native PDK model context')
        print(prepare(out,a.models.resolve()),flush=True)
    else:run(out)
