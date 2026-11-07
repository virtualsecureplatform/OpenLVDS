#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate quiet native bank cells without changing models or solver settings.

This is a performance diagnosis, never a replacement for full bank qualification.
The complete v352 library is copied unchanged; each fixture instantiates one cell.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import numpy as np
import probe_restored_balanced_bank_v352 as bank
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT=bank.ROOT
VERSION='unchanged-native-static-cell-stepping-diagnosis-v353.1'
PARENT=ROOT/'build/diagnostics/restored_balanced_bank_v352/67d491be912b3621'
AND='sky130_fd_sc_hd__and2_4'
STOP=200e-12
SCOPE=('Isolated constant-logic-input SS40 native cell timestep diagnosis only; '
       'fixed 1.8V, unchanged original Gear/KLU/models/tolerances; no bank timing, '
       'coupled loading, PVT, whole-clock or PHY qualification')
sha=bank.sha


def specifications():
    rows=[dict(model=AND,a=a,b=b) for a,b in ((0,0),(0,1),(1,0),(1,1))]
    rows += [dict(model=model,a=a) for model in
             (bank.GROUP,bank.SMALL,bank.FINE,bank.COARSE) for a in (0,1)]
    return rows


def observations(text,spec):
    definitions=bank.native.definitions(text)
    if spec not in specifications():raise ValueError('Unknown static diagnostic')
    model=spec['model'];ports=definitions[model][0]
    expected=(['A','B','VGND','VNB','VPB','VPWR','X'] if model==AND else
              ['A','Y','VGND','VPWR'] if model in (bank.SMALL,bank.FINE) else
              ['IN','OUT','VPWR','VGND'])
    if ports!=expected:raise ValueError('Unexpected native cell interface')
    mapping={p:'0' if p in ('VGND','VNB') else 'VDD' if p in ('VPWR','VPB')
             else 'A' if p in ('A','IN') else 'B' if p=='B' else 'OUT' for p in ports}
    devices=bank.native.mapped_mos(text,model,mapping,'XD')
    expected_count={AND:12,bank.GROUP:32,bank.SMALL:18,bank.FINE:72,bank.COARSE:64}
    if len(devices)!=expected_count[model]:raise ValueError('Actual native cell inventory changed')
    nodes=sorted({'A','OUT','VDD',*(('B',) if model==AND else ()),
                  *(n for d in devices for n in d['terminals'] if n!='0')})
    return ports,mapping,devices,nodes


def fixture(out,text,spec,lib):
    ports,mapping,_,nodes=observations(text,spec)
    lines=['OpenLVDS '+VERSION,lib,
           '.include "'+str(out.parent/'bank.spice')+'"',
           '.options device temp=40',
           '.options timeint method=gear reltol=1e-4 abstol=1e-12',
           'VDD VDD 0 1.8','VA A 0 '+str(1.8*spec['a'])]
    if spec['model']==AND:lines.append('VB B 0 '+str(1.8*spec['b']))
    lines += ['XD '+' '.join(mapping[p] for p in ports)+' '+spec['model'],
              'CLOAD OUT 0 20f','.tran 2p 200p 0 2p',
              '.print tran '+' '.join('V('+n+')' for n in nodes),'.end','']
    return '\n'.join(lines)


def source():
    m=json.loads((PARENT/'manifest.json').read_text());i=m['identity']
    if (m['bank_sha256']!=sha(PARENT/'bank.spice') or engine()!='ngspice'
            or provenance()!=i['simulator']):raise ValueError('Original native library/runtime changed')
    if PARENT.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]:
        raise ValueError('Original native manifest identity changed')
    deck=(PARENT/'0/bench.cir').read_text()
    if sha(PARENT/'0/bench.cir')!=m['tasks'][0]['deck_sha256']:
        raise ValueError('Original full native fixture changed')
    libs=re.findall(r'(?m)^\.lib .+$',deck)
    if len(libs)!=1 or not libs[0].endswith(' ss'):raise ValueError('Require original SS model library')
    for line in ('.options device temp=40','.options timeint method=gear reltol=1e-4 abstol=1e-12',
                 'VDD VDD 0 1.8','.tran 2p 25n 0 2p'):
        if line not in deck.splitlines():raise ValueError('Original solver/supply fixture changed')
    for name,digest in i['pdk_files'].items():
        if sha(Path(name))!=digest:raise ValueError('Original native PDK changed')
    return m,libs[0]


def prepare():
    m,lib=source()
    inputs={str(p.relative_to(ROOT)):sha(p) for p in
            [PARENT/'manifest.json',PARENT/'bank.spice',PARENT/'0/bench.cir',
             *sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
                if getattr(module,'__file__',None) and Path(module.__file__).resolve().parent==ROOT/'scripts'})]}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),inputs=inputs,
        source_bank_sha256=m['bank_sha256'],pdk_files=m['identity']['pdk_files'],
        simulator=provenance(),lib=lib,specs=specifications(),priority=2,max_workers=1,scope=SCOPE)
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out=ROOT/'build/diagnostics/bank_static_cells_v353'/key
    out.mkdir(parents=True,exist_ok=False)
    text=(PARENT/'bank.spice').read_text();(out/'bank.spice').write_text(text)
    tasks=[]
    for k,spec in enumerate(specifications()):
        folder=out/str(k);folder.mkdir();deck=folder/'bench.cir'
        deck.write_text(fixture(folder,text,spec,lib))
        tasks.append(dict(id=str(k),spec=spec,deck_sha256=sha(deck)))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (i['version']!=VERSION or i['specs']!=specifications() or i['priority']!=2 or i['max_workers']!=1
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or engine()!='ngspice' or provenance()!=i['simulator']
            or sha(out/'bank.spice')!=i['source_bank_sha256']):
        raise ValueError('Static diagnostic identity/library changed')
    for name,digest in {**i['inputs'],**i['pdk_files']}.items():
        if sha(ROOT/name)!=digest:raise ValueError('Static diagnostic input changed: '+name)
    if len(m['tasks'])!=len(specifications()):raise ValueError('Missing diagnostic task')
    text=(out/'bank.spice').read_text()
    for k,(task,spec) in enumerate(zip(m['tasks'],specifications())):
        folder=out/str(k)
        if (task['id']!=str(k) or task['spec']!=spec or sha(folder/'bench.cir')!=task['deck_sha256']
                or (folder/'bench.cir').read_text()!=fixture(folder,text,spec,i['lib'])):
            raise ValueError('Static diagnostic fixture changed')
    return m


def measure(folder,text,spec):
    _,_,devices,nodes=observations(text,spec)
    names,wave=validate(folder/'bench.raw',{'v('+n.replace(':','.').lower()+')' for n in nodes},STOP)
    index={n:k for k,n in enumerate(names)};t=wave[:,index['time']];steps=np.diff(t)*1e12
    stress=[]
    for d in devices:
        v=[np.zeros(len(t)) if n=='0' else wave[:,index['v('+n.replace(':','.').lower()+')']] for n in d['terminals']]
        peak=float(np.max(np.max(v,axis=0)-np.min(v,axis=0)))
        stress.append(dict(device=d['name'],peak_v=peak,limit_v=d['limit_v'],passed=peak<=d['limit_v']))
    ranges=[]
    for name in names:
        if name=='time':continue
        v=wave[:,index[name]]
        ranges.append(dict(node=name,minimum_v=float(v.min()),maximum_v=float(v.max()),
                           range_v=float(np.ptp(v)),final_v=float(v[-1])))
    return dict(records=len(t),stop_ps=float(t[-1]*1e12),native_mos=len(devices),
        steps_ps=dict(minimum=float(steps.min()),median=float(np.median(steps)),
                      mean=float(steps.mean()),maximum=float(steps.max())),
        below_0_01ps_steps=int(np.count_nonzero(steps<.01)),
        smallest_twenty_steps_ps=sorted(float(v) for v in steps)[:20],
        node_ranges=sorted(ranges,key=lambda r:r['range_v'],reverse=True),terminal_stress=stress,
        diagnostic_complete=True,bank_timing_qualified=False,qualified_phy=False)


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial diagnostic')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];result=error=None;started=time.monotonic()
            try:
                with lease(ROOT,priority=2,label='bank_static_cells_v353_'+task['id']):
                    bound(out);started=time.monotonic()
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),
                        '-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=measure(folder,(out/'bank.spice').read_text(),task['spec'])
            except Exception as exc:error=str(exc)
            row=dict(task=task,result=result,error=error,elapsed_seconds=time.monotonic()-started,
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=len(rows),
                                    errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run','campaign'));parser.add_argument('artifact',type=Path,nargs='?')
    args=parser.parse_args()
    out=prepare() if args.action in ('prepare','campaign') else args.artifact.resolve()
    print(out,flush=True)
    if args.action in ('run','campaign'):print(run(out),flush=True)
