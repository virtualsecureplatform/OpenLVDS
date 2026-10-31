#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Probe native monitor internals and its DC equilibrium; never qualify a PHY."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

from dll_campaign import atomic,text_block,bias_reference_count
from dll_measurements import read_wave,column,average,phase,edges,complete
from qualify_dll_candidate import validate,evaluate,phase_fixture
from spice_engine import command,provenance
from spice_library import replace
from spice_probes import ProbeNetwork
from spice_slots import slot

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def logical(node,name):return bool(re.search(r'__'+re.escape(name)+r'(?:\.t\d+)?$',node,re.I))


def monitor_nodes(analog):
    devices=[]
    for line in analog.splitlines():
        w=line.split()
        if not w or not w[0].lower().startswith('x'):continue
        end=next((i for i,x in enumerate(w) if '=' in x),len(w))
        if 'fet_' not in w[end-1] or end!=6:continue
        devices.append((w[1:5],w[5],dict(x.split('=',1) for x in w[6:] if '=' in x)))
    nodes={n for row,_,_ in devices for n in row};groups={}
    for name in ['PA','PB','XPOS__O','XPOS__OB','XPOS__L','XPOS__T','POS','XNEG__O','LOW','HIGH','S']:
        selected=sorted(n for n in nodes if logical(n,'XAREA__'+name))
        if not selected:raise ValueError('Native monitor node group missing: '+name)
        groups[name]=selected
    tails=[row for row,model,p in devices if 'pfet_' in model and float(p['l'])==.5 and any(logical(n,'XAREA__XPOS__T') for n in row)]
    if not tails:raise ValueError('Native positive comparator tail missing')
    groups['PC_POS']=sorted({row[1] for row in tails})
    groups['VDDD_POS']=sorted({n for row in tails for n in row if re.match(r'^VDDD(?:\.t\d+)?$',n,re.I)})
    return groups


def expose(analog,nodes):
    header=re.search(r'(?im)^\.subckt\s+openlvds_dll_analog\s+[^\n]*(?:\n\+[^\n]*)*',analog)
    if not header:raise ValueError('Missing analog header')
    pins=header[0].replace('\n+',' ').split()[2:]
    if len(pins)!=15 or len(set(nodes))!=3 or any(n in pins for n in nodes):raise ValueError('Invalid diagnostic voltage clamps')
    return analog[:header.end()]+' '+' '.join(nodes)+analog[header.end():]


def run(qualification,case,stage='dc',stop_ns=160):
    qualification=qualification.resolve()
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):raise ValueError('Use an isolated native qualification')
    q=json.loads((qualification/'manifest.json').read_text());validate(qualification,q)
    selected=[t for t in q['tasks'] if t['id']==case]
    if len(selected)!=1 or selected[0]['fast_rc'] or selected[0]['spec']['kind']!='phase':raise ValueError('Select a full-RC phase fixture')
    task=selected[0];source=qualification/case;record=json.loads((source/'summary.json').read_text())
    if (record['deck_sha256']!=digest(source/'bench.cir') or record['waveform_sha256']!=digest(source/'bench.cir.prn') or
        record['metrics']!=evaluate(qualification,task)):raise ValueError('Native source evidence changed')
    wave,header=read_wave(source/'bench.cir.prn')
    for alias,node in task['aliases'].items():header['V('+alias.upper()+')']=header['V('+node.upper()+')']
    keep=(wave[:,1]>=120e-9)&(wave[:,1]<=160e-9)
    mean={name:average(wave[keep,1],column(wave,header,name)[keep]) for name in ['UP','DN','UF','DF','CTRL']}
    full=(qualification/'full.spice').read_text();analog=text_block(full,'openlvds_dll_analog');groups=monitor_nodes(analog)
    identity=dict(qualification=str(qualification.relative_to(ROOT)),case=case,manifest_sha256=digest(qualification/'manifest.json'),
        summary_sha256=digest(source/'summary.json'),waveform_sha256=digest(source/'bench.cir.prn'),
        library_sha256=digest(qualification/'full.spice'),producer_sha256=digest(Path(__file__)),
        simulator_provenance=provenance(),stop_ns=stop_ns,means_v=mean)
    root=ROOT/'build/diagnostics/monitor_native'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        pdk=re.search(r'(?m)^\.lib "([^"\n]+)"', (source/'bench.cir').read_text())[1]
        tasks={}
        for kind in ['dc','transient']:
            folder=root/kind;folder.mkdir(exist_ok=True);spec=dict(task['spec'])
            if kind=='dc':spec.update(kind='logic',up=mean['UP'],dn=mean['DN'])
            body,probes,_,_=phase_fixture(spec,q['identity']['full_models']['observation_nodes'])
            library=full;mapping={}
            if kind=='dc':
                nodes=[task['aliases'][n].split(':')[-1] for n in ['UF','DF','CTRL']]
                mapping=dict(zip(nodes,['UFORCE','DFORCE','CFORCE']))
                library=replace(full,'openlvds_dll_analog',expose(analog,nodes))
                body=body.replace(' 0 openlvds_dll_analog\n',' 0 UFORCE DFORCE CFORCE openlvds_dll_analog\n',1)
                body+=''.join(f'VF{i} {mapping[node]} 0 {mean[name]:.17g}\n' for i,(node,name) in enumerate(zip(nodes,['UF','DF','CTRL'])))
                for alias in ['UF','DF','CTRL']:probes[alias]=mapping[task['aliases'][alias].split(':')[-1]]
            group_aliases={}
            for group,nodes in groups.items():
                group_aliases[group]=[]
                for i,node in enumerate(nodes):
                    alias='MON_'+group+'_'+str(i);probes[alias]=mapping.get(node,'XA:'+node);group_aliases[group].append(alias)
            duration=2 if kind=='dc' else stop_ns
            deck=(f'OpenLVDS native monitor {kind} DIAGNOSTIC\n.lib "{pdk}" {spec["process"]}\n'
                f'.include "{folder}/library.spice"\n.options device temp={spec["temperature"]}\n'
                '.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
                'VA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\n'+body+
                f'.tran 5p {duration}n 0 20p\n.print tran '+' '.join('V('+n+')' for n in probes.values())+'\n.end\n')
            if bias_reference_count(deck,library)!=1:raise ValueError('Diagnostic duplicates bias reference')
            ProbeNetwork(library).validate(deck,probes.values())
            for filename,text in [('library.spice',library),('bench.cir',deck)]:
                path=folder/filename
                if path.exists() and path.read_text()!=text:raise ValueError('Native diagnostic fixture changed')
                path.write_text(text)
            tasks[kind]=dict(aliases=probes,groups=group_aliases,stop_ns=duration,
                files={name:digest(folder/name) for name in ['library.spice','bench.cir']})
        manifest=dict(identity=identity,tasks=tasks,qualified_phy=False,source_phase_passed=record['passed'])
        atomic(root/'manifest.json',manifest)
        folder=root/stage;spec=tasks[stage]
        if not (folder/'summary.json').exists():
            atomic(folder/'execution.json',dict(status='waiting_for_slot'))
            with slot():
                atomic(folder/'execution.json',dict(status='running'))
                result=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
            (folder/'console.log').write_text(result.stdout+result.stderr);result.check_returncode()
        w,h=read_wave(folder/'bench.cir.prn')
        for alias,node in spec['aliases'].items():h['V('+alias.upper()+')']=h['V('+node.upper()+')']
        if not complete(w,spec['stop_ns']):raise ValueError('Native diagnostic trace is incomplete')
        start=1 if stage=='dc' else 120;end=2 if stage=='dc' else 160;keep=(w[:,1]>=start*1e-9)&(w[:,1]<=end*1e-9)
        measured={name:dict(mean_v=sum(average(w[keep,1],column(w,h,alias)[keep]) for alias in aliases)/len(aliases),
            min_v=min(float(column(w,h,alias)[keep].min()) for alias in aliases),
            max_v=max(float(column(w,h,alias)[keep].max()) for alias in aliases)) for name,aliases in spec['groups'].items()}
        report=dict(diagnostic=True,qualified_phy=False,stage=stage,manifest_sha256=digest(root/'manifest.json'),groups=measured,
            bad_mean_v=average(w[keep,1],column(w,h,'BAD')[keep]),bad_rising_ns=(edges(w[:,1],column(w,h,'BAD'))*1e9).tolist(),
            files={name:digest(folder/name) for name in ['library.spice','bench.cir','bench.cir.prn','bench.raw']})
        if stage=='transient':report['original_window_phase_metrics']=phase(w,h,task['spec']['offset_ps'])
        validate(qualification,q)
        if identity['producer_sha256']!=digest(Path(__file__)):raise ValueError('Diagnostic producer changed')
        atomic(folder/'summary.json',report);atomic(folder/'execution.json',dict(status='completed'))
    print(folder/'summary.json',flush=True);return root


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('qualification',type=Path);p.add_argument('case')
    p.add_argument('--stage',choices=['dc','transient'],default='dc');p.add_argument('--stop-ns',type=int,choices=[160,320,600],default=160)
    a=p.parse_args();run(a.qualification,a.case,a.stage,a.stop_ns)


if __name__=='__main__':main()
