#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Probe native RX output stages with unchanged aperture stimuli and score windows."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import characterize_rx_aperture as capture
from dll_campaign import atomic
from dll_measurements import column, read_wave
from rx_aperture_evidence import sha, verify_witness
from spice_engine import command, provenance
from spice_probes import ProbeNetwork
from spice_slots import slot

ROOT=Path(__file__).resolve().parents[1]
CODE=['probe_rx_publication.py','rx_aperture_evidence.py','spice_probes.py','spice_slots.py']+capture.CODE


def groups(library):
    # Resistor connectivity determines equipotential signal identity, but the
    # diagnostic saves each actual device terminal without collapsing the RC.
    parent={}
    def find(n):
        parent.setdefault(n,n)
        if parent[n]!=n:parent[n]=find(parent[n])
        return parent[n]
    devices=[]
    for line in library.splitlines():
        w=line.split()
        if not w:continue
        if w[0].lower().startswith('r'):
            parent[find(w[1])]=find(w[2])
        if w[0].lower().startswith('x') and len(w)>5 and 'fet_' in w[5]:devices.append(w[1:5])
    for terminals in devices:
        for n in terminals:find(n)
    result={}
    rails={find(n) for n in ['VPWR','VGND']}
    for pin in ['data[0]','data[1]','valid']:
        roots={find(pin)}
        for depth in range(3):
            if roots & rails:raise ValueError('Output-stage traversal reached a supply')
            selected=[d for d in devices if find(d[0]) in roots or find(d[2]) in roots]
            if not selected:raise ValueError('No native output driver for '+pin)
            result[f'{pin}_stage_{depth}']=sorted({n for d in selected for n in [d[0],d[2]] if find(n) in roots})
            result[f'{pin}_supply_{depth}']=sorted({n for d in selected for n in [d[0],d[2],d[3]] if find(n) in rails})
            gates={d[1] for d in selected}
            result[f'{pin}_gate_{depth}']=sorted(gates)
            roots={find(n) for n in gates}
    clock_devices=[d for d in devices if find(d[1])==find('clk')]
    result['CLK_LOCAL_GATES']=sorted({d[1] for d in clock_devices})
    result['CLK_CONTROLLED_SIGNALS']=sorted({n for d in clock_devices for n in [d[0],d[2]] if find(n) not in rails})
    if not result['CLK_LOCAL_GATES']:raise ValueError('No native clock input transistor terminals')
    return result


def code_hashes():return {n:sha(ROOT/'scripts'/n) for n in CODE}


def validate(root,m):
    identity=m['identity']
    source=ROOT/identity['campaign'];captured=json.loads((source/'manifest.json').read_text())
    capture.validate(source,captured)
    if (identity['producer_code']!=code_hashes() or identity['simulator_provenance']!=provenance() or
            identity['source_manifest_sha256']!=sha(source/'manifest.json') or
            identity['source_report'] not in ['table.json','seed_summary.json'] or
            identity['source_report_sha256']!=sha(source/identity['source_report']) or
            identity['library_sha256']!=sha(root/'library.spice')):
        raise ValueError('RX diagnostic input or producer changed')
    for name,value in identity['producer_code'].items():
        if sha(root/'producers'/name)!=value:raise ValueError('Captured RX diagnostic producer changed')
    for task in m['tasks']:
        if sha(root/task['id']/'bench.cir')!=task['deck_sha256']:raise ValueError('RX diagnostic deck changed')


def prepare(source,case=None):
    source=source.resolve()
    if not source.is_relative_to(ROOT/'build/characterization/rx_aperture'):raise ValueError('Use a captured RX campaign')
    m=json.loads((source/'manifest.json').read_text());capture.validate(source,m)
    lib=(source/'library.spice').read_text();observations=groups(lib)
    report='seed_summary.json' if case is not None and (source/'seed_summary.json').exists() else 'table.json'
    identity=dict(campaign=str(source.relative_to(ROOT)),source_manifest_sha256=sha(source/'manifest.json'),
        source_report=report,source_report_sha256=sha(source/report),library_sha256=sha(source/'library.spice'),
        producer_code=code_hashes(),simulator_provenance=provenance(),selected_case=case)
    root=ROOT/'build/diagnostics/rx_publication'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if (root/'manifest.json').exists():
        validate(root,json.loads((root/'manifest.json').read_text()));return root
    root.mkdir(parents=True,exist_ok=True);(root/'library.spice').write_text(lib)
    archive=root/'producers';archive.mkdir()
    for n in CODE:(archive/n).write_bytes((ROOT/'scripts'/n).read_bytes())
    tasks=[]
    if case is None:
        specs=[dict(process=p,temperature=t,edge='rising',polarity='rise',clock_slew_ps=clock,data_slew_ps=20,kind='setup')
            for p,t,clock in [('ss',0,20),('tt',0,200),('ff',0,200)]]
    else:
        specs=[s for s in m['conditions'] if capture.condition_id(s)==case]
        if len(specs)!=1:raise ValueError('Select one captured aperture condition')
    for spec in specs:
        process,temp,clock=(spec[n] for n in ['process','temperature','clock_slew_ps'])
        distance=800.;base=source/capture.condition_id(spec)/'point_800p000000'
        record=json.loads((base/'summary.json').read_text());verify_witness(source,m,spec,distance,record['measurement']['passed'])
        for load in [20,0]:
            name=f'{process}_{temp}_{clock}ps_{load}ff';out=root/name;out.mkdir()
            deck=(base/'bench.cir').read_text();deck=deck.replace(deck.splitlines()[0],'OpenLVDS RX publication DIAGNOSTIC '+name,1)
            deck=re.sub(r'(?m)^\.include "[^"\n]+"$',f'.include "{root}/library.spice"',deck)
            if load==0:
                for line in ['C0 Q0 0 20f\n','C1 Q1 0 20f\n']:deck=deck.replace(line,'')
            aliases={n:n for n in ['CLK','D','Q0','Q1','VALID']}
            for nodes in observations.values():
                for node in nodes:aliases.setdefault('N'+str(len(aliases)),'XR:'+node)
            deck=re.sub(r'(?m)^\.print tran .+$','.print tran '+' '.join('V('+n+')' for n in aliases.values()),deck)
            ProbeNetwork(lib).validate(deck,aliases.values());(out/'bench.cir').write_text(deck)
            _,timing=capture.fixture(spec,distance,m['identity']['model']['ports'])
            tasks.append(dict(id=name,spec=spec,distance_ps=distance,load_ff=load,timing=timing,aliases=aliases,
                deck_sha256=sha(out/'bench.cir'),source_record_sha256=sha(base/'summary.json'),
                source_measurement=record['measurement']))
    atomic(root/'manifest.json',dict(identity=identity,tasks=tasks,groups=observations,qualified_phy=False))
    return root


def execute(root,m,task):
    validate(root,m);out=root/task['id'];record=out/'summary.json'
    if not record.exists():
        atomic(out/'execution.json',dict(status='waiting_for_slot'))
        with slot():
            atomic(out/'execution.json',dict(status='running'))
            run=subprocess.run(command(out/'ngspice.log',out/'bench.cir'),cwd=out,capture_output=True,text=True)
        (out/'console.log').write_text(run.stdout+run.stderr);run.check_returncode()
    wave,header=read_wave(out/'bench.cir.prn')
    for alias,node in task['aliases'].items():header['V('+alias.upper()+')']=header['V('+node.upper()+')']
    measured=capture.measure(wave,header,task['spec'],task['timing'],task['distance_ps'])
    if 'error' in measured:raise ValueError(measured['error'])
    sample=(task['timing']['publication_ns']+np.arange(.80,1.051,.005))*1e-9
    observed={key:[dict(node=n,min_v=float(np.interp(sample,wave[:,1],column(wave,header,'XR:'+n)).min()),
        max_v=float(np.interp(sample,wave[:,1],column(wave,header,'XR:'+n)).max())) for n in nodes] for key,nodes in m['groups'].items()}
    reference=task['source_measurement']
    difference=max(abs(a-b) for pair,old in zip(measured['output_limits_v'],reference['output_limits_v']) for a,b in zip(pair,old))
    result=dict(diagnostic=True,qualified_phy=False,manifest_sha256=sha(root/'manifest.json'),measurement=measured,groups=observed,
        original_load_control=task['load_ff']==20,original_public_limits_max_delta_v=difference,
        waveform_sha256=sha(out/'bench.cir.prn'),raw_sha256=sha(out/'bench.raw'),deck_sha256=task['deck_sha256'])
    if record.exists() and json.loads(record.read_text())!=result:raise ValueError('Saved diagnostic changed')
    validate(root,m);atomic(record,result);atomic(out/'execution.json',dict(status='completed'));print(task['id'],measured['passed'],flush=True)
    return result


def run(root,jobs):
    root=root.resolve()
    if not root.is_relative_to(ROOT/'build/diagnostics/rx_publication') or jobs not in [1,2,3]:raise ValueError('Use an isolated diagnostic and 1–3 workers')
    m=json.loads((root/'manifest.json').read_text());validate(root,m)
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with ThreadPoolExecutor(max_workers=jobs) as pool:results=list(pool.map(lambda t:execute(root,m,t),m['tasks']))
        atomic(root/'summary.json',dict(diagnostic=True,qualified_phy=False,manifest_sha256=sha(root/'manifest.json'),
            completed=len(results),case_reports={t['id']:sha(root/t['id']/'summary.json') for t in m['tasks']}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('campaign',type=Path);a.add_argument('--case',help='One captured endpoint condition')
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a.add_argument('--jobs',type=int,default=1)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(a.campaign,a.case),flush=True)
    else:run(a.artifact,a.jobs)
