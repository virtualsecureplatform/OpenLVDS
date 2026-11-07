#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay all twelve loaded counter boundaries with actual new shared-wire RC."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import qualify_shunted_counter_rc_v346 as rc
import probe_large_shunt_counter_boundaries_v334 as source
import native_clock_components_v2 as native
from build_compound_drivers_v3 import cell_definition
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=rc.ROOT
VERSION='actual-23-macro-shunted-counter-shared-rc-native-boundaries-v347.1'
CONTEXT='shunted_counter_shared_rc_v347'
HARNESS='openlvds_static_phase_release_loaded_v2'
PORTS=rc.PORTS
BASELINE=rc.physical.material.BOUNDARY
LOADS=('Xprepare_load0','Xprepare_load1','Xmask_load')
MONITORS=('low0','high1','low1','armed','request_i')
VARIANT=source.source.candidate.VARIANT
sha=rc.sha
atomic=rc.atomic
SCOPE=('Twelve fresh full 26ns 808-MOS/57-MIM loaded native counter boundaries '
       'with actual v345 GDS shared-wire RC; SS0/SS40 410MHz 40/50/60% duty '
       'both stopped levels, worst hot points first; no other frequency, '
       'all-PVT, whole-clock, DLL or PHY admission; upstream baseline evidence '
       'bound through complete receipts without rehashing historical raw traces')


def specifications():
    original=source.specifications()
    return [original[k] for k in (6,11,0,1,2,3,4,5,7,8,9,10)]


def libraries(cells,module,block):
    defs=native.definitions(block)
    if set(defs)!={rc.NAME} or defs[rc.NAME][0]!=PORTS or rc.NAME in native.definitions(cells):
        raise ValueError('Require exact fresh seven-port shared-wire RC block')
    nodes=set(PORTS);resistors=capacitors=0
    for w in defs[rc.NAME][1]:
        kind=w[0][0].upper()
        if kind in ('R','C'):
            nodes.update(w[1:3]);resistors+=kind=='R';capacitors+=kind=='C'
        elif kind=='X':
            end=next((k for k,v in enumerate(w) if '=' in v),len(w));nodes.update(w[1:end-1])
        else:raise ValueError('Unexpected shared-wire RC active element')
    if not set(MONITORS)<=nodes or resistors!=17086 or capacitors!=4381:
        raise ValueError('Require all actual reduced shared wires, capacitors and named monitors')
    before=cell_definition(module,HARNESS);old=native.definitions(module)[HARNESS]
    if old[0]!=PORTS or [w[0] for w in old[1]]!=['XR',*LOADS,'Cmask_load']:
        raise ValueError('Original complete loaded counter harness changed')
    if old[1][0]!=['XR',*PORTS,source.source.candidate.source.CORE]:
        raise ValueError('Original component-only counter call changed')
    after=before.replace(' '.join(old[1][0])+'\n','XR '+' '.join(PORTS)+' '+rc.NAME+'\n',1)
    result=module.replace(before,after,1)
    if native.definitions(result)[HARNESS][1][1:]!=old[1][1:]:
        raise ValueError('Original three native loads or 20fF load changed')
    return cells+'\n'+block,result


def observations(cells,module,previous):
    devices=native.mapped_mos(cells+module,HARNESS,
        {p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in PORTS},'XD')
    load=lambda d:any(d['name'].startswith('XD:'+role+':') for role in LOADS)
    if (len(devices)!=808 or len({d['name'] for d in devices})!=808
            or sum(d['name'].startswith('XD:XR:') for d in devices)!=744
            or sum(load(d) for d in devices)!=64
            or [d for d in devices if load(d)]!=[d for d in previous if load(d)]):
        raise ValueError('Require 744 actual RC block MOS and unchanged 64 downstream load MOS')
    inventory=rc.physical.material.legacy.inventory
    _,actual=inventory.native_leaves(rc.collapse(cells+module),HARNESS)
    if sum('cap_mim' in d['model'] for d in actual)!=57:
        raise ValueError('Complete loaded native 57-MIM census changed')
    return devices


def fixture(out,spec,devices):
    text=source.fixture(out,spec,devices)
    prefix='OpenLVDS '+source.VERSION+'\n'
    if not text.startswith(prefix):raise ValueError('Original full 26ns counter fixture changed')
    return text.replace(prefix,'OpenLVDS '+VERSION+'\n',1)


def tasks(out,devices):
    return [dict(id=str(k),spec=s,mode='simulate',
        deck_sha256=hashlib.sha256(fixture(out/str(k),s,devices).encode()).hexdigest())
        for k,s in enumerate(specifications())]


def prepare(parent):
    ri=rc.bound(parent);report=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
            or report.get('whole_counter_shared_wire_rc_qualified') is not True
            or any(sha(parent/n)!=h for n,h in report['files'].items())
            or any(sha(ROOT/n)!=h for n,h in report['extracted_files'].items())):
        raise ValueError('Require complete passed actual-GDS shared-wire RC proof')
    old=source.bound(BASELINE,full=False);oi=old['identity']
    baseline=json.loads((BASELINE/'summary.json').read_text())
    if (json.loads((BASELINE/'state.json').read_text())!=dict(status='complete',cases=12,errors=0,qualified_phy=False)
            or baseline['comparison']!=source.assess(baseline['rows'])
            or baseline['comparison']['component_hypothesis_passed'] is not True
            or any(not source.point_passed(r['result']) for r in baseline['rows'])
            or engine()!='ngspice' or provenance()!=oi['simulator']):
        raise ValueError('Require the complete twelve-point native baseline and pinned simulator')
    block=ROOT/report['extraction']['netlist']
    cells,module=libraries((BASELINE/'cells.spice').read_text(),(BASELINE/'pair.spice').read_text(),block.read_text())
    devices=observations(cells,module,oi['devices'][VARIANT])
    paths=[parent/n for n in ('manifest.json','summary.json','state.json',*report['files'])]
    paths += [ROOT/n for n in {*ri['inputs'],*report['extracted_files']}]
    paths += [BASELINE/n for n in ('manifest.json','summary.json','state.json',*old['libraries'])]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in sorted(set(paths))}
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),baseline=str(BASELINE.relative_to(ROOT)),
        block=str(block.relative_to(ROOT)),inputs=inputs,pdk_files=oi['pdk_files'],
        external_files=ri['external_files'],simulator=provenance(),devices={VARIANT:devices},
        specs=specifications(),max_workers=2,priority=1,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'cells.spice').write_text(cells);(out/'pair.spice').write_text(module)
    planned=tasks(out,devices)
    for task in planned:
        folder=out/task['id'];folder.mkdir()
        # The original fixture resolves included libraries at its supplied
        # directory. Store each case's independent exact copies below it.
        (folder/'cells.spice').write_text(cells);(folder/'pair.spice').write_text(module)
        (folder/'bench.cir').write_text(fixture(folder,task['spec'],devices))
    atomic(out/'manifest.json',dict(identity=identity,tasks=planned,
        libraries={n:sha(out/n) for n in ('cells.spice','pair.spice')},qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['scope']!=SCOPE
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['specs']!=specifications() or (i['max_workers'],i['priority'])!=(2,1)
            or engine()!='ngspice' or provenance()!=i['simulator']
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
            or any(sha(out/n)!=h for n,h in m['libraries'].items())):
        raise ValueError('Actual shared-wire native counter context changed')
    baseline=ROOT/i['baseline'];old=json.loads((baseline/'manifest.json').read_text())['identity']
    cells,module=libraries((baseline/'cells.spice').read_text(),(baseline/'pair.spice').read_text(),(ROOT/i['block']).read_text())
    devices=observations(cells,module,old['devices'][VARIANT])
    if (cells!=(out/'cells.spice').read_text() or module!=(out/'pair.spice').read_text()
            or devices!=i['devices'][VARIANT] or m['tasks']!=tasks(out,devices)):
        raise ValueError('Actual RC libraries, separated native terminals or full coverage changed')
    for task in m['tasks']:
        folder=out/task['id']
        if ((folder/'bench.cir').read_text()!=fixture(folder,task['spec'],devices)
                or sha(folder/'bench.cir')!=task['deck_sha256']
                or any(sha(folder/n)!=h for n,h in m['libraries'].items())):
            raise ValueError('Actual shared-wire counter fixture or per-case library changed')
    return m


def assess(rows):
    if len(rows)!=12 or any(r['error'] is not None or r['result'] is None for r in rows):return None
    if [r['task']['spec'] for r in rows]!=specifications():raise ValueError('Native shared-wire coverage changed')
    return dict(all_twelve_fresh_native_points_present=True,
        actual_shared_counter_timing_pilot_passed=all(source.point_passed(r['result'])
            and r['result']['counter_shared_wire_rc_qualified'] is True for r in rows),
        all_pvt_covered=False,whole_clock_rc_qualified=False,electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial actual-RC native campaign')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                    bound(out)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),
                        '-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=dict(source.source.candidate.measure(folder,i,task['spec']),component_rc_only=False,
                    counter_shared_wire_rc_qualified=True,whole_clock_rc_qualified=False,all_pvt_covered=False,
                    electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
            except Exception as exc:error=str(exc)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,comparison=assess(rows),qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=12,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run','campaign'));parser.add_argument('artifact',type=Path)
    args=parser.parse_args();out=args.artifact.resolve()
    if args.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if args.action in ('run','campaign'):print(run(out),flush=True)
