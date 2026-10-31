#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Diagnostic monitor repair using unchanged thresholds and captured capacitive loads."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

from benchmark_exact_dll import candidate
from dll_campaign import atomic,text_block,bias_reference_count
from dll_design import block,native_block
from dll_measurements import read_wave,column,phase,edges,average
from layout import circuits
from qualify_dll_candidate import phase_fixture
from reduce_rc import number
from spice_engine import command,provenance
from spice_library import replace
from spice_probes import ProbeNetwork,scope
from spice_slots import slot
from ota_operating_points import pdk_library

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def repaired_source(source,factor=4):
    defs=circuits(source);ports,rows=defs['lvds_phase_area'];scaled=[];caps=set();resistors=0
    for name,nodes,model,params in rows:
        p=dict(params)
        if model=='sky130_fd_pr__res_high_po_0p35':
            p['l']=f'{float(p["l"])/factor:g}';resistors+=1
        if name in ['XCU','XCD']:
            if model!='sky130_fd_pr__cap_mim_m3_1':raise ValueError('Unexpected averaging capacitor')
            caps.add(name)
            scaled.extend((f'{name}_{i}',nodes,model,p) for i in range(factor))
        else:scaled.append((name,nodes,model,p))
    if caps!={'XCU','XCD'} or not resistors:raise ValueError('Expected the complete area monitor')
    source=replace(source,'lvds_phase_area',block('lvds_phase_area',ports,scaled))
    ports,rows=defs['lvds_area_compare'];scaled=[];changed=set()
    for name,nodes,model,params in rows:
        p=dict(params)
        if name in ['XTAIL','XP','XM','XNL','XNR']:
            p['w']=f'{float(p["w"])*factor:g}';changed.add(name)
        scaled.append((name,nodes,model,p))
    if changed!={'XTAIL','XP','XM','XNL','XNR'}:raise ValueError('Unexpected comparator architecture')
    return replace(source,'lvds_area_compare',block('lvds_area_compare',ports,scaled))


def logical_node(node,known):
    node=re.sub(r'\.t\d+$','',node)
    node=re.sub(r'^dll_(?:control|monitor)_island\.','',node)
    return node.lower() if node.lower() in known else None


def loaded_block(source,extracted):
    native=native_block(source,'openlvds_dll_analog');known=scope(native)[0]
    capacitors=[];counts=dict(both_mapped=0,one_grounded=0,unmapped=0,same_node=0)
    totals={}
    for line in extracted.splitlines():
        words=line.split()
        if len(words)!=4 or not words[0].lower().startswith('c'):continue
        a,b=[logical_node(node,known) for node in words[1:3]]
        if a is None and b is None:counts['unmapped']+=1;continue
        if a is None or b is None:counts['one_grounded']+=1;a=a or '0';b=b or '0'
        else:counts['both_mapped']+=1
        if a==b:counts['same_node']+=1;continue
        capacitance=number(words[3])
        capacitors.append(f'CPROXY{len(capacitors)} {a} {b} {capacitance:.17g}')
        for node in {a,b}:totals[node]=totals.get(node,0)+capacitance
    end=native.lower().rfind('.ends')
    return native[:end]+'* Diagnostic captured capacitive loading; distributed R is omitted\n'+'\n'.join(capacitors)+'\n'+native[end:],dict(counts=counts,capacitances_f=totals)


def run(reference,layout,jobs=2):
    reference=reference.resolve();layout=layout.resolve()
    manifest=json.loads((reference/'manifest.json').read_text());full,models=candidate(layout,reference,manifest)
    source=(layout/'candidate.spice').read_text();repaired=repaired_source(source)
    extracted=text_block(full,'openlvds_dll_analog')
    views={};loading={}
    for label,text,loaded in [('baseline_unloaded',source,False),('baseline_loaded',source,True),('repair_loaded',repaired,True)]:
        analog,info=loaded_block(text,extracted) if loaded else (native_block(text,'openlvds_dll_analog'),{})
        views[label]=replace(full,'openlvds_dll_analog',analog);loading[label]=info
    identity=dict(reference=str(reference.relative_to(ROOT)),reference_manifest_sha256=digest(reference/'manifest.json'),
        layout=str(layout.relative_to(ROOT)),layout_manifest_sha256=digest(layout/'manifest.json'),
        code={p.name:digest(p) for p in [Path(__file__),ROOT/'scripts/ota_operating_points.py']},
        simulator_provenance=provenance(),models=models)
    root=ROOT/'build/diagnostics/monitor_repair'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True)
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        (root/'candidate.spice').write_text(repaired);tasks=[]
        for label,text in views.items():(root/(label+'.spice')).write_text(text)
        # Run the failing slow-corner pair first. Baselines are explicit controls.
        conditions=[('baseline_loaded','ss',0,150,False),('repair_loaded','ss',0,150,True),
                    ('baseline_loaded','ss',0,300,False),('baseline_unloaded','ss',0,150,True),
                    ('baseline_unloaded','ss',0,300,True)]
        conditions += [('repair_loaded',p,t,o,True) for p,t in [('ss',0),('tt',25),('ff',0)]
                       for o in [0,50,-50,150,-150,300,-300] if (p,t,o)!=('ss',0,150)]
        pdk=pdk_library(reference)
        for view,process,temp,offset,expected in conditions:
            name=f'{view}_{process}_{temp}_{offset}ps';folder=root/name;folder.mkdir(exist_ok=True)
            spec=dict(kind='phase',process=process,temperature=temp,mhz=400,offset_ps=offset,
                reference_slew_ps=100,feedback_slew_ps=100,architecture='averaged_pfd_ota')
            body,probes,stop,timing=phase_fixture(spec)
            for node in ['PA','PB','S','POS','NEG','LOW','HIGH','XPOS__O','XPOS__L','XPOS__T','XNEG__O']:
                probes['MON_'+node]='XA:openlvds_dll_analog__XAREA__'+node
            text=(f'OpenLVDS monitor loading diagnostic {name}\n.lib "{pdk}" {process}\n'
                f'.include "{root}/{view}.spice"\n.options device temp={temp}\n'
                '.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
                'VA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\n'+body+
                f'.tran 5p {stop}n 0 20p\n.print tran '+' '.join('V('+node+')' for node in probes.values())+'\n.end\n')
            if bias_reference_count(text,views[view])!=1:raise ValueError('Monitor diagnostic duplicates bias reference')
            ProbeNetwork(views[view]).validate(text,probes.values())
            deck=folder/'bench.cir'
            if deck.exists() and deck.read_text()!=text:raise ValueError('Captured monitor diagnostic changed')
            deck.write_text(text)
            tasks.append(dict(id=name,spec=spec,aliases=probes,expected_pass=expected,view=view,deck_sha256=digest(deck),**timing))
        atomic(root/'manifest.json',dict(identity=identity,tasks=tasks,loading=loading,qualified=False,
            view='Diagnostic schematic devices with captured capacitance; not native extracted qualification'))
        def measure(task):
            folder=root/task['id'];previous=folder/'summary.json'
            if previous.exists():
                report=json.loads(previous.read_text())
                if report['waveform_sha256']!=digest(folder/'bench.cir.prn'):raise ValueError('Diagnostic waveform changed')
                return report
            atomic(folder/'execution.json',dict(status='waiting_for_slot'))
            with slot():
                atomic(folder/'execution.json',dict(status='running'))
                result=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
            (folder/'console.log').write_text(result.stdout+result.stderr);result.check_returncode()
            wave,header=read_wave(folder/'bench.cir.prn')
            for name,node in task['aliases'].items():header['V('+name.upper()+')']=header['V('+node.upper()+')']
            metrics=phase(wave,header,task['spec']['offset_ps']);t=wave[:,1];bad=column(wave,header,'BAD')
            keep=(t>=120e-9)&(t<=160e-9)
            report=dict(task=task['id'],phase_passed=metrics['passed'],expected_pass=task['expected_pass'],
                matched_expectation=metrics['passed']==task['expected_pass'],metrics=metrics,
                bad_rising_ns=(edges(t,bad)*1e9).tolist(),bad_falling_ns=(edges(t,bad,rising=False)*1e9).tolist(),
                window_mean_v={name:average(t[keep],column(wave,header,'MON_'+name)[keep])
                               for name in ['PA','PB','S','XPOS__O','XPOS__L','XPOS__T','XNEG__O']},
                waveform_sha256=digest(folder/'bench.cir.prn'),deck_sha256=digest(folder/'bench.cir'))
            atomic(previous,report);print(task['id'],report['phase_passed'],flush=True);return report
        with ThreadPoolExecutor(max_workers=jobs) as pool:results=list(pool.map(measure,tasks))
        candidate(layout,reference,manifest)
        if identity['code']!={p.name:digest(p) for p in [Path(__file__),ROOT/'scripts/ota_operating_points.py']}:
            raise ValueError('Monitor diagnostic producer changed')
        atomic(root/'summary.json',dict(diagnostic=True,qualified_phy=False,
            matched_all_expectations=all(r['matched_expectation'] for r in results),
            repaired_proxy_passed=all(r['phase_passed'] for r in results if r['task'].startswith('repair_loaded_')),results=results))
        print(root/'summary.json',flush=True)
        return root


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('reference',type=Path)
    p.add_argument('--layout',required=True,type=Path);p.add_argument('--jobs',type=int,choices=range(1,7),default=2)
    a=p.parse_args();run(a.reference,a.layout,a.jobs)


if __name__=='__main__':main()
