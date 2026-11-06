#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay the compact counter with exact shared-wire RC and original native gates."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import native_clock_components_v2 as native
import probe_counter_native_repairs_v183 as pilot
import qualify_strong_storage_counter_rc_v231 as rc
from build_compound_drivers_v3 import cell_definition
from probe_digital_dcc_v2 import atomic
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=rc.ROOT
sha=rc.sha
VERSION='strong-storage-dual-request-full-native-counter-transient-v232.1'
CONTEXT='strong_storage_counter_shared_rc_v232'
HARNESS='openlvds_static_phase_release_loaded_v2'
PORTS=rc.physical.PORTS
MONITORS=('low0','high1','low1','armed','request_i')
LOADS=('Xprepare_load0','Xprepare_load1','Xmask_load')
baseline=pilot.source.source.source
SCOPE='Strong-storage dual-REQUEST 22-macro repaired counter/dual-clock-driver RC with original three downstream native loads, SS0/40 410MHz 40/50/60% duty both stopped levels; full original native/timing checks, no all-PVT/DCC/warmup/PHY admission'


def specifications():
    sample=baseline.specifications()[0]
    return [dict(sample,process='ss',temperature=t,duty=d,stop_level=level) for t in (0,40) for d in (.5,.4,.6) for level in (0,1)]


def libraries(cells,module,block):
    defs=native.definitions(block)
    if set(defs)!={rc.NAME} or defs[rc.NAME][0]!=PORTS or rc.NAME in native.definitions(cells):raise ValueError('Require exact qualified seven-port shared counter RC')
    ports,body=defs[rc.NAME];nodes=set(ports)
    for w in body:
        if w[0][0].upper() in ('R','C'):nodes.update(w[1:3])
        elif w[0][0].upper()=='X':
            end=next((k for k,v in enumerate(w) if '=' in v),len(w));nodes.update(w[1:end-1])
        else:raise ValueError('Unexpected actual counter active element')
    if set(MONITORS)&set(ports) or not set(MONITORS)<=nodes:raise ValueError('All actual internal monitor nodes must survive unchanged reduction')
    ds=native.definitions(module);original=cell_definition(module,HARNESS)
    if ds[HARNESS][0]!=PORTS:raise ValueError('Original counter harness ports changed')
    keep=[w for w in ds[HARNESS][1] if w[0] in LOADS or w[0]=='Cmask_load']
    if [w[0] for w in keep]!=[*LOADS,'Cmask_load'] or keep[-1]!=['Cmask_load','mask_load','VGND','20f']:raise ValueError('Original downstream load inventory changed')
    replaced=[w for w in ds[HARNESS][1] if w not in keep]
    if [w[0] for w in replaced]!=['Xclock_driver','Xclock_driver_parallel','XR']:raise ValueError('Unexpected original counter clock/core calls')
    rows=['.subckt '+HARNESS+' '+' '.join(PORTS),'XR '+' '.join(PORTS)+' '+rc.NAME,*[' '.join(w) for w in keep],'.ends '+HARNESS,'']
    after=module.replace(original,'\n'.join(rows),1)
    if cell_definition(after,'openlvds_routed_pair_static_phase_release_v2')!=cell_definition(module,'openlvds_routed_pair_static_phase_release_v2'):raise ValueError('Unused original component counter definition changed')
    return cells+'\n'+block,after


def observations(cells,module,previous):
    devices=native.mapped_mos(cells+module,HARNESS,{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in PORTS},'XD')
    prefix=lambda d:any(d['name'].startswith('XD:'+tag+':') for tag in LOADS)
    if len(devices)!=612 or len({d['name'] for d in devices})!=612 or len([d for d in devices if d['name'].startswith('XD:XR:')])!=548:raise ValueError('Require all 548 block MOS and all 64 downstream load MOS')
    if [d for d in devices if prefix(d)]!=[d for d in previous if prefix(d)]:raise ValueError('Original downstream native terminal/model/limit observations changed')
    return devices


def fixture(out,s,devices):
    text=baseline.fixture(out,s,devices);first,rest=text.split('\n',1)
    if first!='OpenLVDS '+baseline.VERSION:raise ValueError('Original full native counter fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+rest


def prepare(parent,source):
    m=rc.bound(parent);i=m['identity'];r=json.loads((parent/'summary.json').read_text())
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False) or r.get('counter_shared_wire_rc_qualified') is not True:raise ValueError('Require complete exact shared-wire RC proof')
    if any(sha(parent/n)!=h for n,h in r['files'].items()) or any(sha(ROOT/n)!=h for n,h in r['extracted_files'].items()):raise ValueError('Qualified shared-wire RC output changed')
    pm=pilot.bound(source);pi=pm['identity'];pr=json.loads((source/'summary.json').read_text())
    if engine()!='ngspice' or provenance()!=pi['simulator']:raise ValueError('Require original pinned native ngspice environment')
    if json.loads((source/'state.json').read_text())!=dict(status='complete',cases=6,errors=0,qualified_phy=False) or len(pr['rows'])!=6 or any(row['error'] is not None or not row['result']['hypothesis_point_checks_passed'] for row in pr['rows']):raise ValueError('Require complete passing repaired component pilot')
    block=ROOT/r['extraction']['netlist'];cells,module=libraries((source/'cells.spice').read_text(),(source/'pair.spice').read_text(),block.read_text());devices=observations(cells,module,pi['devices'])
    paths=[parent/n for n in ('manifest.json','summary.json','state.json',*r['files'])]+[ROOT/n for n in {*i['inputs'],*r['extracted_files'],*pi['inputs']}]
    paths += [source/n for n in ('manifest.json','summary.json','state.json','cells.spice','pair.spice')]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),source=str(source.relative_to(ROOT)),block=str(block.relative_to(ROOT)),block_sha256=sha(block),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},pdk_files=pi['pdk_files'],simulator=provenance(),devices=devices,specs=specifications(),max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    for name,text in [('cells.spice',cells),('pair.spice',module)]:(out/name).write_text(text)
    tasks=[]
    for k,s in enumerate(identity['specs']):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,s,devices));tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={n:sha(out/n) for n in ('cells.spice','pair.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['specs']!=specifications() or i['max_workers']!=2 or engine()!='ngspice' or provenance()!=i['simulator'] or len(m['tasks'])!=12
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items()) or any(sha(out/n)!=h for n,h in m['libraries'].items())):raise ValueError('Actual shared-wire native counter context changed')
    parent=ROOT/i['source'];cells,module=libraries((parent/'cells.spice').read_text(),(parent/'pair.spice').read_text(),(ROOT/i['block']).read_text())
    if cells!=(out/'cells.spice').read_text() or module!=(out/'pair.spice').read_text() or observations(cells,module,json.loads((parent/'manifest.json').read_text())['identity']['devices'])!=i['devices']:raise ValueError('Actual counter libraries or native observations changed')
    for k,t in enumerate(m['tasks']):
        f=out/str(k)/'bench.cir'
        if t!=dict(id=str(k),spec=i['specs'][k],deck_sha256=sha(f)) or f.read_text()!=fixture(out,t['spec'],i['devices']):raise ValueError('Actual counter full fixture changed')
    return m


def assess(rows):
    if len(rows)!=12 or any(r['error'] is not None or r['result'] is None for r in rows):return None
    if [r['task']['spec'] for r in rows]!=specifications():raise ValueError('Shared counter transient coverage changed')
    passed=all(r['result']['counter_feasibility_passed'] and math.isfinite(r['result']['minimum_clock_low_voltage_margin_v']) and r['result']['minimum_clock_low_voltage_margin_v']>=0 and r['result']['counter_shared_wire_rc_qualified'] is True for r in rows)
    return dict(actual_shared_counter_timing_pilot_passed=bool(passed),all_pvt_covered=False,whole_clock_rc_qualified=False,hardware_warmup_qualified=False,electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial actual shared-counter campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();result=baseline.measure(folder,task['spec'],i['devices'])
                result.update(counter_shared_wire_rc_qualified=True,whole_clock_rc_qualified=False,all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,comparison=assess(rows),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=12,errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--source',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.source is None:p.error('--source required for preparation')
        out=prepare(out,a.source.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
