#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Paired fixed-supply 15-PVT device switching controls; no model admission."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import xyce_profile_300 as xyce
from dcc_source_300 import model_closure
from native_binary_raw_v2 import validate
from xyce_raw_aliases_v148 import normalize
from spice_dispatch import lease
from qualify_dcc_xyce_300_v1 import save
import clocking_profile_300 as contract
import model_stimulus_300_v1
import generic_poly_xyce_300_v2 as poly

ROOT = xyce.ROOT
CONTEXT = 'model_switching_xyce_300_v5'
PDK = Path('/opt/pdk/ciel/sky130/versions/1689ac3f2dc763876eaf967227c7dfe831b031ae/sky130A')
FETS = ['nfet_01v8','nfet_01v8_lvt','pfet_01v8','pfet_01v8_hvt','nfet_g5v0d10v5','pfet_g5v0d10v5']
NODES = [*[f'm{k}' for k in range(len(FETS))], 'poly', 'generic', 'generic_tie', 'generic_wide', 'mim']
STOP = 6e-9


def deck(folder,process,temp,engine):
    header = f'OpenLVDS fixed supply device controls {process} {temp}C\n.lib "{PDK}/libs.tech/ngspice/sky130.lib.spice" {process}\n'
    options = (f'.options device temp={temp}\n'+xyce.options('strict') if engine=='xyce' else
               f'.temp {temp}\n.options klu method=gear reltol=1e-5 abstol=1e-12\n')
    text = header+options+'V18 V18 0 1.8\nV33 V33 0 3.3\n'
    # Input excursions characterize devices at fixed rails, not supply sweeps.
    text += 'VIN IN 0 PWL(0 0 1n 0 1.025n 1.8 2.5n 1.8 2.525n 0 4n 0 4.3125n 1.8 5.5n 1.8 5.8125n 0)\n'
    text += 'VIN33 IN33 0 PWL(0 0 1n 0 1.025n 3.3 2.5n 3.3 2.525n 0 4n 0 4.3125n 3.3 5.5n 3.3 5.8125n 0)\n'
    for k,model in enumerate(FETS):
        thick = 'g5v' in model
        rail, gate = ('V33','IN33') if thick else ('V18','IN')
        source = rail if model.startswith('p') else '0'
        load = '0' if model.startswith('p') else rail
        length = .5 if thick else .15
        text += f'XM{k} M{k} {gate} {source} {source} sky130_fd_pr__{model} w=2 l={length}\n'
        text += f'RL{k} M{k} {load} 1000\nCL{k} M{k} 0 20f\n'
    text += ('XRP V18 POLY 0 sky130_fd_pr__res_high_po_0p35 w=0.35 l=1.25\nRP POLY 0 1000\n'
             'XRG V18 GENERIC sky130_fd_pr__res_generic_po w=0.5 l=1\nRG GENERIC 0 1000\n'
             'RM IN MIM 1000\nXCM MIM 0 sky130_fd_pr__cap_mim_m3_1 w=10 l=10\n'
             '.tran .5p 6n 0 .5p\n')
    tokens = ' '.join('V('+n+')' for n in ['in','in33',*NODES])
    if engine=='xyce':
        text += f'.print tran format=raw precision=17 file={folder}/bench.xyce.raw {tokens}\n'
    else:
        text += f'.save {tokens}\n.control\nset num_threads = 1\nset filetype = binary\nrun\nwrite {folder}/bench.raw all\n.endc\n'
    return text+'.end\n'


original_deck = deck


def deck(folder,process,temp,engine):
    from model_stimulus_300_v1 import smooth_inputs
    text = smooth_inputs(original_deck(folder,process,temp,engine))
    text = text.replace('.tran .5p', 'XRT V18 GENERIC_TIE sky130_fd_pr__res_generic_po w=0.48 l=0.5\nRT GENERIC_TIE 0 1000\nXRW V18 GENERIC_WIDE sky130_fd_pr__res_generic_po w=1 l=2\nRW GENERIC_WIDE 0 1000\n.tran .5p')
    if engine=='xyce':
        text = text.replace('sky130_fd_pr__res_generic_po w=',poly.NAME+' w=')
        text = text.replace('.end\n',poly.MODEL+'.end\n')
    return text


def prepare():
    policy = contract.load()
    runtime = xyce.runtime()
    ng = ROOT/'build/tools/ngspice.json'
    inputs = model_closure(PDK/'libs.tech/ngspice/sky130.lib.spice')
    inputs.update({str(ROOT/n):h for n,h in json.loads(ng.read_text())['files'].items()})
    helpers = {Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'}
    helpers.update([Path(__file__).resolve(),ROOT/'clocking_300mhz.json',ng])
    inputs.update({str(p):xyce.sha(p) for p in helpers})
    specs = [dict(process=p,temperature=t) for p in policy['requirements']['process_corners'] for t in policy['requirements']['temperatures_c']]
    identity = dict(version=CONTEXT,inputs=inputs,runtime=runtime,specs=specs,fets=FETS,
                    max_workers=2,priority=2,timeout_seconds=180,numerical_profile=xyce.PROFILES['strict'],
                    qualified_models=False,qualified_phy=False)
    key = hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out = ROOT/'build/diagnostics'/CONTEXT/key
    out.mkdir(parents=True,exist_ok=False)
    tasks = []
    for index,spec in enumerate(specs):
        for engine in ['xyce','ngspice']:
            folder = out/f'{index}_{engine}'
            folder.mkdir()
            (folder/'bench.cir').write_text(deck(folder,spec['process'],spec['temperature'],engine))
            tasks.append(dict(id=folder.name,engine=engine,spec_index=index,spec=spec,
                              deck_sha256=xyce.sha(folder/'bench.cir')))
    save(out/'manifest.json',dict(identity=identity,tasks=tasks))
    return out


def bound(out):
    m = json.loads((out/'manifest.json').read_text())
    i = m['identity']
    if out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or i['runtime']!=xyce.runtime() or len(m['tasks'])!=30:
        raise ValueError('Model campaign identity/runtime/coverage changed')
    files = {**i['inputs'],**i['runtime']['files']}
    files.update({str(out/t['id']/'bench.cir'):t['deck_sha256'] for t in m['tasks']})
    for name,h in files.items():
        if xyce.sha(name)!=h:
            raise ValueError('Captured input changed: '+name)
    return m


def compare(out,rows):
    comparisons = []
    for index in range(15):
        pair = {r['task']['engine']:r for r in rows if r['task']['spec_index']==index}
        result = dict(spec_index=index,complete=False)
        if len(pair)==2 and all(r['complete'] for r in pair.values()):
            n,a = validate(out/pair['ngspice']['task']['id']/'bench.raw',set(),STOP)
            m,b = validate(out/pair['xyce']['task']['id']/'bench.raw',set(),STOP)
            t = a[:,n.index('time')]
            tb = b[:,m.index('time')]
            dc = {}; transient = {}; crossings = {}
            for node in NODES:
                name = 'v('+node+')'
                va,vb = a[:,n.index(name)],b[:,m.index(name)]
                dc[node] = abs(float(va[0]-vb[0]))
                transient[node] = float(np.max(np.abs(va-np.interp(t,tb,vb))))
                level = (float(np.max(va))+float(np.min(va)))/2
                if np.ptp(va)>.1:
                    events=[]
                    for up in [True,False]:
                        edges=[]
                        for times,values in [(t,va),(tb,vb)]:
                            ix=np.flatnonzero((values[:-1]<level)&(values[1:]>=level) if up else (values[:-1]>level)&(values[1:]<=level))
                            edges.append(times[ix]+(level-values[ix])*(times[ix+1]-times[ix])/(values[ix+1]-values[ix]))
                        events.append(dict(up=up,reference_count=len(edges[0]),candidate_count=len(edges[1]),
                                           maximum_error_ps=float(max(abs(edges[1]-edges[0]))*1e12) if len(edges[0])==len(edges[1]) and len(edges[0]) else None))
                    crossings[node]=events
            result.update(complete=True,spec=pair['xyce']['task']['spec'],dc_error_v=dc,
                          peak_pointwise_error_v=transient,mid_swing_crossings=crossings)
        comparisons.append(result)
    return comparisons


def run(out):
    m = bound(out)
    with (out/'state.json').open('x') as f:
        json.dump(dict(status='running',qualified_models=False),f)
    def one(task):
        folder = out/task['id']
        row = dict(task=task,complete=False,error=None)
        start = time.monotonic()
        try:
            if task['engine']=='xyce':
                command=xyce.command(folder/'native.log',folder/'bench.cir')
            else:
                runtime=ROOT/'build/tools/ngspice-runtime'
                command=[str(runtime/'ld-linux-x86-64.so.2'),'--library-path',str(runtime),str(ROOT/'build/tools/ngspice-root/usr/bin/ngspice'),'-n','-b','-o',str(folder/'native.log'),str(folder/'bench.cir')]
            row['command']=command
            with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                with (folder/'console.log').open('w') as log:
                    p=subprocess.run(command,cwd=folder,env=xyce.environment(),stdout=log,stderr=subprocess.STDOUT,timeout=180)
                row['returncode']=p.returncode
                if p.returncode:
                    raise ValueError('Simulator returned '+str(p.returncode))
            if task['engine']=='xyce':
                row['normalization']=normalize(folder/'bench.xyce.raw',folder/'bench.raw')
            names,w=validate(folder/'bench.raw',{'v('+n+')' for n in NODES},STOP)
            row.update(complete=True,records=len(w))
        except Exception as exc:
            row['error']=str(exc)
        row['wall_seconds']=time.monotonic()-start
        row['warnings']=xyce.warnings('\n'.join(p.read_text(errors='replace') for p in [folder/'console.log',folder/'native.log'] if p.exists()))
        row['files']={p.name:xyce.sha(p) for p in folder.iterdir() if p.is_file()}
        save(folder/'summary.json',row)
        return row
    rows=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(one,t) for t in m['tasks']]):
            rows.append(future.result())
            save(out/'progress.json',dict(completed=len(rows),total=30,errors=sum(r['error'] is not None for r in rows)))
    bound(out)
    rows.sort(key=lambda r:r['task']['id'])
    save(out/'summary.json',dict(rows=rows,comparisons=compare(out,rows),qualified_models=False,qualified_phy=False,
                                scope='Representative fixed-supply MOS/resistor/MIM switching controls, not full DC/charge/geometry/diode qualification'))
    save(out/'state.json',dict(status='complete',cases=30,errors=sum(r['error'] is not None for r in rows),qualified_models=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','run'])
    p.add_argument('artifact',type=Path,nargs='?')
    a=p.parse_args()
    if a.action=='prepare':
        print(prepare(),flush=True)
    elif a.artifact is None:
        p.error('Supply fresh artifact')
    else:
        run(a.artifact.resolve())
