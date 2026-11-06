#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test stronger native isolation drivers after complete INV1 pulse-loss traces.

Component RC only: new shared wiring is ideal and has no physical admission.
All eight startup/steady cycles and original safety/timing/slew limits remain.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import numpy as np
import native_clock_components_v2 as native
import probe_measured_gang_sparse_v131 as source
import probe_isolated_fine_bank_v187 as weak
import probe_counter_native_repairs_v183 as clock
import regenerated_bank_periodic_measure_v67 as periodic
from build_compound_drivers_v3 import cell_definition
from native_binary_raw_v2 import validate
from probe_digital_dcc_v2 import sha, atomic
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT=source.ROOT
VERSION='strong-native-fine-isolation-after-inv1-pulse-loss-v190.1'
CONTEXT='strong_isolated_fine_bank_v190'
OLD='openlvds_measured_gangs_b2_v125'
TOP='openlvds_strong_isolated_fine_v190'
INV='openlvds_inv_8_regular_o4_v14'
NAND='openlvds_nand2_8_shunted_v2'
BUF='openlvds_buf_8_o4_shunted_v2'
SCOPE='Stronger native INV8 or tied-input NAND2_8 fine isolation, consumed complete INV1 pulse-loss evidence, SS40 410MHz endpoint/zero/coarse pilot; ideal shared wiring, no whole-bank RC/dense/update/full-frequency-duty/all-PVT/PHY admission'


def variants():return [dict(driver=d,fine_copies=n) for d in ('inv','nand') for n in (1,)]
def key(v):return v['driver']+'_c'+str(v['fine_copies'])
def specifications():
    return [dict(process='ss',temperature=40,coarse=c,fine=f,input_slew_ps=100,load_ff=20,
                 frequency_mhz=410,duty=d,cycles=8,stop_ns=25,**v)
            for v in variants() for c,f,d in ((0,31,.4),(0,31,.6),(0,0,.5),(1,0,.5))]


def transform(bank,cells,v):
    if v not in variants():raise ValueError('Unknown native fine-stage variant')
    defs=native.definitions(bank);extra=native.definitions(cell_definition(bank,INV)+'\n'+'\n'.join(cell_definition(cells,m) for m in (NAND,BUF)))
    if any(m in defs for m in (NAND,BUF)):raise ValueError('Fine-driver namespace collision')
    for model,ports in [(INV,['A','Y','VGND','VPWR']),(NAND,['A','B','Y','VGND','VPWR']),(BUF,['A','X','VGND','VPWR'])]:
        if extra[model][0]!=ports:raise ValueError('Native driver port order changed')
    body=defs[OLD][1];block=cell_definition(bank,OLD);after=block
    original=['Xfine_compound','selected','OUT','VPWR','VGND','openlvds_parallel_inv8_v110']
    if [w for w in body if w[0]=='Xfine_compound']!=[original]:raise ValueError('Original final gang changed')
    rows=[]
    if v['driver'] in ('inv','mixed'):rows.append('Xfine_isolate_inv selected fine_node VGND VPWR '+INV)
    if v['driver'] in ('nand','mixed'):rows.append('Xfine_isolate_nand selected selected fine_node VGND VPWR '+NAND)
    rows.append('Xfine_regenerate fine_node OUT VGND VPWR '+BUF)
    after=after.replace(' '.join(original)+'\n','\n'.join(rows)+'\n',1)
    for k in range(31):
        old=[f'Xfine_unit{k}','selected',f'fine{k}',f'fine_b{k}','VPWR','VGND',OLD+'_unit']
        if [w for w in body if w[0]==old[0]]!=[old]:raise ValueError('Measured fine-cell wiring changed')
        new=[list(old) for _ in range(v['fine_copies'])]
        for j,w in enumerate(new):
            w[1]='fine_node'
            if j:w[0]+='_copy'+str(j)
        after=after.replace(' '.join(old)+'\n','\n'.join(' '.join(w) for w in new)+'\n',1)
    after=after.replace('.subckt '+OLD+' ','.subckt '+TOP+' ',1).replace('.ends '+OLD+'\n','.ends '+TOP+'\n',1)
    result=bank.replace(block,after,1)
    # Every definition other than the explicitly replaced top is byte-preserved.
    for model in defs:
        if model!=OLD and cell_definition(result,model)!=cell_definition(bank,model):raise ValueError('Unrelated native component changed')
    return result+'\n'+'\n'.join(cell_definition(cells,m) for m in (NAND,BUF))


def observations(bank,previous,v):
    ports=native.definitions(bank)[TOP][0]
    devices=native.mapped_mos(bank,TOP,{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports},'XD')
    byname={d['name']:d for d in devices};old={d['name']:d for d in previous['devices']}
    removed=[d for d in old.values() if d['name'].startswith('XD:Xfine_compound:')]
    if len(removed)!=32 or len(byname)!=len(devices):raise ValueError('Fine-stage device inventory changed')
    for name,d in old.items():
        if name not in {r['name'] for r in removed} and byname.get(name)!=d:raise ValueError('Unrelated native MOS terminal changed')
    extra=[d for d in devices if d['name'] not in old]
    # Five native MOS per original fine unit, plus exact extracted driver census.
    expected_fine=155*(v['fine_copies']-1)
    driver_count=sum(len(native.mapped_mos(cell_definition(bank,m),m,{p:p for p in native.definitions(bank)[m][0]},'D'))
                     for m in ([INV] if v['driver']=='inv' else [NAND] if v['driver']=='nand' else [INV,NAND])+[BUF])
    if len(devices)!=len(old)-32+expected_fine+driver_count or len(extra)!=expected_fine+driver_count:raise ValueError('Incomplete native fine-driver observations')
    gates=[]
    for g in previous['programming_gates']:
        gates.append(dict(g,gate_node=byname[g['device']]['terminals'][1]))
        if ':Xfine_unit' in g['device']:
            prefix,leaf=g['device'].rsplit(':',1)
            for j in range(1,v['fine_copies']):
                name=prefix+'_copy'+str(j)+':'+leaf
                gates.append(dict(g,device=name,gate_node=byname[name]['terminals'][1]))
    if len(gates)!=173+93*(v['fine_copies']-1) or len({g['device'] for g in gates})!=len(gates):raise ValueError('Incomplete programming-gate observations')
    return dict(devices=devices,controls=previous['controls'],programming_gates=gates)


def fixture(out,i,s):
    name=key(s);o=i['observations'][name];width=s['input_slew_ps']/1e12/(2*np.arctanh(.8));period=1e-6/s['frequency_mhz']
    wave='+'.join(f'0.9*(tanh((time-{2.1e-9+k*period:.17g})/{width:.17g})-tanh((time-{2.1e-9+(k+s["duty"])*period:.17g})/{width:.17g}))' for k in range(s['cycles']))
    rows=['OpenLVDS '+VERSION,f'.lib "{i["model"]}" {s["process"]}',f'.include "{out/name}/bank.spice"',
          f'.options device temp={s["temperature"]}', '.options timeint method=gear reltol=1e-4 abstol=1e-12',
          'VDD VDD 0 1.8','BIN IN 0 V={'+wave+'}']
    pins=periodic.baseline.circuit.encode(s['coarse'],s['fine'])
    rows += [f'V{p} {p} 0 {1.8*v:g}' for p,v in pins.items()]
    rows += ['XD '+' '.join('0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in i['ports'])+' '+TOP,
             f'CLOAD OUT 0 {s["load_ff"]}f',f'.tran 2p {s["stop_ns"]}n 0 2p']
    probes={'IN','OUT','VDD','XD:selected','XD:fine_node',*pins}
    probes.update(n for d in o['devices'] for n in d['terminals'] if n!='0');probes.update(c['node'] for c in o['controls'])
    return '\n'.join(rows+['.print tran '+' '.join('V('+n+')' for n in sorted(probes)),'.end',''])


def failure_evidence(parent):
    m=weak.bound(parent);i=m['identity'];folder=parent/'1';row=json.loads((folder/'summary.json').read_text());s=row['spec'];d=row['result']
    if (row['task']!=m['tasks'][1] or s!=m['tasks'][1]['spec'] or (s['driver'],s['fine_copies'],s['coarse'],s['fine'],s['frequency_mhz'],s['duty'])!=('inv',1,0,31,410,.6)
        or row['error'] is not None or d is None or any(sha(folder/n)!=h for n,h in row['files'].items())
        or weak.measure(folder,i,s)!=d or d['all_input_output_pulses_present'] or not d['terminal_screen_passed'] or not d['control_settling_passed']
        or max(c['max_v'] for c in d['internal_node_cycles']['fine_node'])>=.9
        or min(c['max_v'] for c in d['internal_node_cycles']['selected'])<=1.62):raise ValueError('Require exact complete INV1 pulse-loss and restored-mux evidence')
    return [parent/'manifest.json',parent/'inv_c1/bank.spice',folder/'summary.json',*[folder/n for n in row['files']],*[ROOT/n for n in i['inputs']]]


def prepare(parent,clock_parent,failed):
    m=source.bound(parent);pi=m['identity'];cm=clock.bound(clock_parent)
    for p,cases in [(parent,2),(clock_parent,6)]:
        state=json.loads((p/'state.json').read_text());r=json.loads((p/'summary.json').read_text())
        if state['status']!='complete' or state['cases']!=cases or state['errors'] or any(row['error'] is not None for row in r['rows']):raise ValueError('Require completed source native evidence')
    sparse=json.loads((parent/'summary.json').read_text())
    if not sparse['comparison']['measured_component_sparse_feasibility_passed']:raise ValueError('Require passing component sparse source')
    for task,row in zip(m['tasks'],sparse['rows']):
        folder=parent/task['id']
        if row!=json.loads((folder/'summary.json').read_text()) or row['task']!=task or any(sha(folder/n)!=h for n,h in row['files'].items()):raise ValueError('Source sparse native files changed')
        current=source.fine.measure(folder,dict(pi,spec=task['spec']));current.update(scope=source.SCOPE)
        if current!=row['result']:raise ValueError('Source sparse metrics do not reproduce')
    if sparse['comparison']!=source.compare(sparse['rows'],pi['source_fine_result']):raise ValueError('Source sparse comparison changed')
    clock_rows=json.loads((clock_parent/'summary.json').read_text())['rows']
    if not all(r['result']['hypothesis_point_checks_passed'] for r in clock_rows):raise ValueError('Require passing native clock source')
    bank=(parent/'bank.spice').read_text();cells=(clock_parent/'cells.spice').read_text()
    libraries={key(v):transform(bank,cells,v) for v in variants()}
    obs={key(v):observations(libraries[key(v)],pi['observations'],v) for v in variants()}
    paths=failure_evidence(failed)+[parent/n for n in ('manifest.json','summary.json','state.json','bank.spice')]+[clock_parent/n for n in ('manifest.json','summary.json','state.json','cells.spice')]
    for p,rows in [(parent,sparse['rows']),(clock_parent,clock_rows)]:
        for row in rows:
            folder=p/row['task']['id']
            if row!=json.loads((folder/'summary.json').read_text()) or any(sha(folder/n)!=h for n,h in row['files'].items()):raise ValueError('Completed source trace changed')
            paths += [folder/'summary.json',*[folder/n for n in row['files']]]
    paths += [ROOT/n for n in {*pi['inputs'],*cm['identity']['inputs']}]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),clock_parent=str(clock_parent.relative_to(ROOT)),source_failure_case=str((failed/'1').relative_to(ROOT)),
           model=pi['model'],pdk_files={**pi['pdk_files'],**cm['identity']['pdk_files']},external_files=pi['external_files'],simulator=provenance(),
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},specs=specifications(),ports=native.definitions(libraries[key(variants()[0])])[TOP][0],
           observations=obs,max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    hashes={}
    for name,text in libraries.items():
        d=out/name;d.mkdir();(d/'bank.spice').write_text(text);hashes[name]=sha(d/'bank.spice')
    tasks=[]
    for k,s in enumerate(i['specs']):
        f=out/str(k);f.mkdir();(f/'bench.cir').write_text(fixture(out,i,s));tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(f/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=i,tasks=tasks,libraries=hashes,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['specs']!=specifications() or i['max_workers']!=2 or engine()!='ngspice' or provenance()!=i['simulator']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())):raise ValueError('Isolated fine-bank context changed')
    if set(m['libraries'])!={key(v) for v in variants()} or len(m['tasks'])!=8:raise ValueError('Fine-stage matrix changed')
    for v in variants():
        name=key(v);text=(out/name/'bank.spice').read_text()
        if sha(out/name/'bank.spice')!=m['libraries'][name] or observations(text,json.loads((ROOT/i['parent']/'manifest.json').read_text())['identity']['observations'],v)!=i['observations'][name]:raise ValueError('Fine-stage native coverage changed')
    for k,t in enumerate(m['tasks']):
        f=out/str(k)/'bench.cir'
        if t!=dict(id=str(k),spec=i['specs'][k],deck_sha256=sha(f)) or f.read_text()!=fixture(out,i,t['spec']):raise ValueError('Fine-stage complete fixture changed')
    return m


def measure(folder,i,s):
    result=periodic.measure(folder,dict(i,spec=s,observations=i['observations'][key(s)]))
    names,w=validate(folder/'bench.raw',{'v(xd.selected)','v(xd.fine_node)'},s['stop_ns']*1e-9);t=w[:,names.index('time')]*1e12;recovery={}
    for n in ('selected','fine_node'):
        v=w[:,names.index('v(xd.'+n+')')];cycles=[]
        for k in range(s['cycles']):
            a=2100+k*1e6/s['frequency_mhz'];window=(t>=a)&(t<a+1e6/s['frequency_mhz'])
            cycles.append(dict(min_v=float(v[window].min()),max_v=float(v[window].max())))
        recovery[n]=cycles
    result.update(whole_bank_rc_retained=False,new_common_routing_qualified=False,internal_node_cycles=recovery,scope=SCOPE,
                  native_component_rc_hypothesis_only=True,electrical_qualification_passed=False,qualified_phy=False)
    return result


def compare(rows):
    if len(rows)!=8 or any(r['error'] is not None for r in rows):return None
    if [r['spec'] for r in rows]!=specifications():raise ValueError('Fine-stage comparison coverage changed')
    comparisons=[]
    for v in variants():
        selected=[r for r in rows if key(r['spec'])==key(v)];by={(r['spec']['coarse'],r['spec']['fine'],r['spec']['duty']):r['result'] for r in selected}
        # Both endpoint histories must cover the entire first-coarse history.
        complete=all(len(r['result']['edge_delays_ps'][edge])==8 and all(math.isfinite(x) for x in r['result']['edge_delays_ps'][edge]) for r in selected for edge in ('rise','fall'))
        overlap={edge:(min(x for d in (.4,.6) for x in by[0,31,d]['edge_delays_ps'][edge])-max(by[1,0,.5]['edge_delays_ps'][edge]) if complete else None) for edge in ('rise','fall')}
        comparisons.append(dict(variant=v,conservative_coarse_overlap_ps=overlap,
            component_hypothesis_passed=all(r['result']['current_clock_interface_screen_passed'] for r in selected) and complete and all(x>0 for x in overlap.values()),
            whole_bank_rc_qualified=False,all_pvt_covered=False,qualified_phy=False))
    return comparisons


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial isolation campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];r=error=None
            try:
                with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();r=measure(folder,i,task['spec'])
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=r,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,comparison=compare(rows),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--clock',type=Path);p.add_argument('--failed',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.clock is None or a.failed is None:p.error('--clock and --failed required for preparation')
        out=prepare(out,a.clock.resolve(),a.failed.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
