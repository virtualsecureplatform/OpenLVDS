#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Localize completed common-release startup misses at real RC/MOS terminals."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import verify_native_static_dcc_v2 as verification
from native_clock_components_v2 import definitions
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import crossings,sha,atomic

ROOT=verification.ROOT
VERSION='complete-common-dcc-startup-native-master-observations-v2.1'
TAGS=['data_n','data','clock','master_s','master_q','slave_q']


def output_drains(defs,model,port='Y'):
    ports,body=defs[model]
    if port not in ports:raise ValueError('Missing real component output port')
    parent={}
    def root(n):
        parent.setdefault(n,n)
        if parent[n]!=n:parent[n]=root(parent[n])
        return parent[n]
    for row in body:
        if row[0][0].upper()=='R':parent[root(row[1])]=root(row[2])
    group=root(port);nodes=set()
    for row in body:
        if row[0][0].upper()!='X':continue
        end=next((i for i,v in enumerate(row) if '=' in v),len(row));leaf=row[end-1]
        if leaf not in ['sky130_fd_pr__nfet_01v8','sky130_fd_pr__pfet_01v8','sky130_fd_pr__pfet_01v8_hvt']:continue
        if end!=6:raise ValueError('Native MOS terminal count changed')
        nodes.update(n for n in [row[1],row[3]] if root(n)==group)
    if not nodes:raise ValueError('No real MOS output drain/source on native RC port')
    return sorted(nodes)


def diagnose(parent):
    m,devices=verification.regenerate(parent);i=m['identity']
    tasks=[t for t in m['tasks'] if t['spec']['variant']=='common']
    if len(tasks)!=2 or {t['spec']['duty'] for t in tasks}!={.4,.6}:raise ValueError('Require both approved common-release duties')
    text=(parent/'cells.spice').read_text()+(parent/'common.spice').read_text();defs=definitions(text)
    name,ports=verification.pilot.components.dcc_interface('common');rows=defs[name][1];pins=dict(zip(ports,['0','VDD','Q','P0','P180','RESET_N']))
    if pins!=dict(VGND='0',VPWR='VDD',clock_out='Q',phase0='P0',phase180='P180',reset_n='RESET_N'):raise ValueError('Common DCC port order changed')
    observers={}
    for phase in ['a','b']:
        for suffix in TAGS:
            tag=phase+'_'+suffix;matches=[row for row in rows if row[0]=='X'+tag]
            if len(matches)!=1:raise ValueError('Missing exact native DCC stage')
            row=matches[0];model=row[-1];order=defs[model][0];mapping=dict(zip(order,row[1:-1]))
            observers[tag]=[pins.get(mapping[n], 'XD:'+mapping[n]) if n in mapping else 'XD:X'+tag+':'+n for n in output_drains(defs,model)]
    paths=[parent/'manifest.json',*[parent/n for n in m['libraries']]];reports=[]
    for task in tasks:
        folder=parent/task['id'];r=json.loads((folder/'summary.json').read_text());spec=task['spec'];ds=devices['common']
        if (r['task']!=task or r['error'] is not None or not r['result']['terminal_screen_passed'] or not r['result']['half_cycle_passed']
            or (folder/'bench.cir').read_text()!=verification.pilot.fixture(parent,spec,ds)
            or not {'bench.cir','bench.raw','bench.ngspice.cir','console.log','ngspice.log'}<=set(r['files'])
            or any(sha(folder/n)!=h for n,h in r['files'].items())):raise ValueError('Require exact complete voltage-safe common-release cases')
        measured=verification.pilot.measure(folder,spec,ds,i['scope'])
        if measured!=r['result']:raise ValueError('Common startup independent remeasurement changed')
        bad=[c for c in measured['output_event_checks'] if not c['passed']]
        if (not measured['startup_passed'] or len(bad)!=2 or [b['phase'] for b in bad]!=['P180','P0'] or any(b['output_count']!=0 for b in bad)):
            raise ValueError('Require the exact two initial missing events')
        requested={'v('+n.replace(':','.').lower()+')' for nodes in observers.values() for n in nodes}
        stop=(spec['raw_start_ns']+22*1000/spec['mhz'])*1e-9;names,w=validate(folder/'bench.raw',requested,stop)
        idx={n:j for j,n in enumerate(names)};t=w[:,idx['time']]*1e12;release=measured['reset_release_time_ps'];stages={}
        for tag,nodes in observers.items():
            observed=[]
            for node in nodes:
                v=w[:,idx['v('+node.replace(':','.').lower()+')']];up=crossings(t,v);down=crossings(t,v,False)
                observed.append(dict(node=node,rises_ps=[float(x) for x in up[(up>=release)&(up<release+3e6/spec['mhz'])]],
                                     falls_ps=[float(x) for x in down[(down>=release)&(down<release+3e6/spec['mhz'])]]))
            stages[tag]=observed
        ready=[node['rises_ps'][0] for node in stages['b_master_q'] if node['rises_ps']]
        first_b=bad[0]['source_edge_ps']
        reports.append(dict(id=task['id'],spec=spec,reset_release_time_ps=release,missing_events=bad,
            b_master_first_rise_after_release_ps=[min(ready),max(ready)],
            b_master_first_rise_minus_first_b_clock_ps=[min(ready)-first_b,max(ready)-first_b],
            native_output_terminal_events=stages,half_cycle_error_ps=measured['half_cycle_error_ps'],
            all_native_terminals_passed=measured['terminal_screen_passed'],qualified_phy=False))
        paths += [folder/n for n in ['summary.json',*r['files']]]
    verification.pilot.bound(parent)
    code=[Path(__file__),Path(verification.__file__),Path(verification.pilot.__file__),ROOT/'scripts/measure_native_static_dcc_v2.py',ROOT/'scripts/native_clock_components_v2.py',ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/probe_digital_dcc_v2.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths+code})
    out=ROOT/'build/diagnostics/common_dcc_startup_diagnosis_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Common-startup evidence changed')
    out.mkdir(parents=True,exist_ok=False);atomic(out/'summary.json',dict(identity=identity,rows=reports,qualified_phy=False,
        scope='Both complete common-release waveforms independently remeasured; all actual native output drain/source nodes connected by resistor-only paths observed, no ideal aliases, new simulation, early-prepare repair proof or PHY admission'))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(diagnose(a.artifact.resolve()),flush=True)
