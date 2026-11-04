#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Inspect retained passive-RC reset failures at actual saved MOS terminals."""
import argparse
import hashlib
import heapq
import json
from pathlib import Path
import re
import numpy as np
import probe_native_clock_components_v3 as pilot
from reduce_rc import number
from probe_digital_dcc_v2 import crossings,sha,atomic

ROOT=pilot.ROOT
VERSION='passive-native-reset-release-failure-localization-v2.1'


def read_mapped(path):
    with path.open('rb') as f:header=f.read(1024*1024)
    end=header.find(b'Binary:\n')+8
    if end<8:raise ValueError('Missing native binary raw header')
    text=header[:end].decode();count=int(re.search(r'No\. Points:\s*(\d+)',text)[1]);n=int(re.search(r'No\. Variables:\s*(\d+)',text)[1])
    names=[m[1].lower() for m in re.finditer(r'^\s*\d+\s+(\S+)\s+\S+\s*$',text,re.M)]
    if count<=0 or len(names)!=n or path.stat().st_size!=end+count*n*8:raise ValueError('Incomplete native raw')
    return names,np.memmap(path,dtype='<f8',mode='r',offset=end,shape=(count,n))


def sense_node(body,port):
    """Choose the nearest saved physical MOS terminal on this output's R net."""
    graph={};terminals=set()
    for original in body:
        w=' '.join(original).split('$',1)[0].split()
        if w[0][0].upper()=='R':
            a,b=w[1:3];r=number(w[3]);graph.setdefault(a,[]).append((b,r));graph.setdefault(b,[]).append((a,r))
        elif w[0][0].upper()=='X':
            first=next((i for i,v in enumerate(w) if '=' in v),len(w));model=w[first-1]
            if model.startswith('sky130_fd_pr__') and ('nfet_' in model or 'pfet_' in model):terminals.update(w[1:first-1])
    queue=[(0.,port)];seen=set()
    while queue:
        distance,node=heapq.heappop(queue)
        if node in seen:continue
        seen.add(node)
        if node in terminals:return node,distance
        for target,r in graph.get(node,[]):
            if target not in seen:heapq.heappush(queue,(distance+r,target))
    raise ValueError('Output has no saved MOS terminal')


def describe(t,v,start):
    if not np.isfinite(v).all():raise ValueError('Nonfinite native voltage')
    rising=crossings(t,v,True);falling=crossings(t,v,False);window=t>=start
    return dict(min_v=float(v[window].min()),max_v=float(v[window].max()),last_v=float(v[-1]),
        rising_crossings_ps=rising.tolist(),falling_crossings_ps=falling.tolist())


def diagnose(parent,cases):
    m=pilot.bound(parent);defs=pilot.components.definitions((parent/'cells.spice').read_text());files=[parent/'manifest.json',parent/'cells.spice'];rows=[]
    for case in cases:
        folder=parent/str(case);row=json.loads((folder/'summary.json').read_text());task=m['tasks'][case]
        if row['task']!=task or row['error']!='Reset release count' or row['result'] is not None:raise ValueError('Require retained reset-count failure')
        for name in ['bench.cir','bench.raw']:
            if sha(folder/name)!=row['files'][name]:raise ValueError('Changed native failure witness')
        files += [folder/n for n in ['summary.json','bench.cir','bench.raw','ngspice.log']]
        names,w=read_mapped(folder/'bench.raw');index={n:i for i,n in enumerate(names)};t=w[:,index['time']]*1e12;start=task['spec']['raw_start_ns']*1000
        def voltage(n):return w[:,index['v('+n.replace(':','.').lower()+')']]
        public={n:describe(t,voltage(n),start) for n in ['P0','P180','REQUEST','RESET_N','RESET_180','Q']};controllers={}
        for prefix,clock,reset in [('XR0','P0','RESET_N'),('XR180','P180','RESET_180')]:
            outputs={};samples={};clk=crossings(t,voltage(clock),True)
            for tag,short,pins in pilot.components.release.gates():
                node,distance=sense_node(defs[pilot.components.MODELS[short]][1],'Y');physical=prefix+':X'+tag+':'+node
                info=describe(t,voltage(physical),start);info.update(sense_node=physical,resistance_path_to_formal_output_ohm=distance,logical_output=pins['Y'])
                outputs[tag]=info
                if tag in ['r0_master_q','r0_slave_q','r1_master_q','r1_slave_q','qualify','output']:
                    samples[tag]=np.interp(clk+500,t,voltage(physical)).tolist()
            controllers[prefix]=dict(outputs=outputs,clock_rising_edges_ps=clk.tolist(),values_500ps_after_clock=samples)
        rows.append(dict(case=case,spec=task['spec'],public=public,controllers=controllers,qualified_phy=False))
    pilot.bound(parent);code=[Path(__file__),Path(pilot.__file__),Path(pilot.components.__file__),ROOT/'scripts/reduce_rc.py',ROOT/'scripts/probe_digital_dcc_v2.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},code={str(p.relative_to(ROOT)):sha(p) for p in code})
    out=ROOT/'build/diagnostics/native_clock_release_failure_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'summary.json',dict(identity=identity,rows=rows,qualified_phy=False,
        scope='Saved physical MOS terminal localization of completed passive-RC reset failures; nearest resistor-path output senses are not ideal formal-port waveforms'))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--cases',nargs='+',type=int,default=[0,1]);a=p.parse_args();print(diagnose(a.artifact.resolve(),a.cases),flush=True)
