#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extend the verified actual-RC counter to all requested PVT/clock boundaries."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import probe_local_setter_shared_rc_v351 as pilot
import counter_protocol_300 as protocol
import clocking_profile_300 as policy
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=pilot.ROOT
PARENT=ROOT/'build/diagnostics/local_setter_shared_rc_v351/b8297d638d69090d'
VERSION='fresh-profile-bound-300mhz-actual-rc-counter-v1'
CONTEXT='counter_pvt_300_v1'
SCOPE=('Fresh 270-case 290/300/310 MHz actual shared-wire RC counter; fixed 1.8 V, '
       'five corners at 0/25/40 C, 40/50/60% duty, both stopped levels, '
       'complete 40 ns seven-clock protocol; no full clock or PHY admission')
sha=pilot.sha
atomic=pilot.atomic


def specifications():
    r=policy.load()['requirements'];base=pilot.specifications()[0]
    if (set(r['process_corners'])!={'ss','ff','sf','fs','tt'} or set(r['temperatures_c'])!={0,25,40}):
        raise ValueError('Require all fifteen approved PVT conditions')
    return [dict(base,process=p,temperature=t,mhz=f,duty=d,stop_level=level)
        for p in ('ss','ff','sf','fs','tt') for t in (40,0,25)
        for f in (310,290,300) for d in (.6,.4,.5) for level in (1,0)]


def fixture(folder,spec,devices):
    text=protocol.fixture(folder,spec,devices)
    return text.replace('OpenLVDS '+pilot.VERSION+'\n','OpenLVDS '+VERSION+'\n',1)


def tasks(out,devices):
    return [dict(id=str(k),spec=s,mode='simulate',
                 deck_sha256=hashlib.sha256(fixture(out/str(k),s,devices).encode()).hexdigest())
            for k,s in enumerate(specifications())]


def prepare():
    policy.load();previous=pilot.bound(PARENT);i=previous['identity']
    if json.loads((PARENT/'state.json').read_text())!=dict(status='complete',cases=12,errors=0,qualified_phy=False):
        raise ValueError('Require complete actual shared-RC parent')
    report=json.loads((PARENT/'summary.json').read_text())
    if report['comparison']!=pilot.assess(report['rows']) or report['comparison']['actual_shared_counter_timing_pilot_passed'] is not True:
        raise ValueError('Require passing historical topology certificate; no timing cases are reused')
    paths=[PARENT/n for n in ('manifest.json','summary.json','state.json',*previous['libraries'])]
    paths += [ROOT/'clocking_300mhz.json']
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**i['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),specs=specifications(),
        inputs=inputs,guards=pilot.source.source.candidate.guard_inputs(inputs),
        devices=i['devices'],simulator=i['simulator'],pdk_files=i['pdk_files'],external_files=i['external_files'],
        library_sha256=previous['libraries'],max_workers=2,priority=2,scope=SCOPE,
        profile_sha256=sha(ROOT/'clocking_300mhz.json'),retained_cases=0,protocol_stop_ns=40)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name in previous['libraries']:(out/name).write_bytes((PARENT/name).read_bytes())
    planned=tasks(out,i['devices'][pilot.VARIANT])
    for task in planned:
        folder=out/task['id'];folder.mkdir()
        for name in previous['libraries']:(folder/name).write_bytes((PARENT/name).read_bytes())
        (folder/'bench.cir').write_text(fixture(folder,task['spec'],i['devices'][pilot.VARIANT]))
    atomic(out/'manifest.json',dict(identity=identity,tasks=planned,libraries=previous['libraries'],qualified_phy=False))
    bound(out)
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['scope']!=SCOPE
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['specs']!=specifications() or (i['max_workers'],i['priority'])!=(2,2)
            or i['guards']!=pilot.source.source.candidate.guard_inputs(i['inputs'])
            or engine()!='ngspice' or provenance()!=i['simulator']
            or m['libraries']!=i['library_sha256'] or i['profile_sha256']!=sha(ROOT/'clocking_300mhz.json')
            or i['retained_cases']!=0 or i['protocol_stop_ns']!=40 or i['parent']!=str(PARENT.relative_to(ROOT))):raise ValueError('Routed PVT identity changed')
    for name,digest in {**(i['inputs'] if full else i['guards']),**i['pdk_files'],**i['external_files']}.items():
        if sha(ROOT/name)!=digest:raise ValueError('Routed PVT input changed: '+name)
    for name,digest in m['libraries'].items():
        if sha(out/name)!=digest:raise ValueError('Original actual-RC library changed')
    old=json.loads((PARENT/'manifest.json').read_text())
    devices=pilot.native.mapped_mos((out/'cells.spice').read_text()+'\n'+(out/'pair.spice').read_text(),pilot.HARNESS,
        {p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in pilot.PORTS},'XD')
    if devices!=i['devices'][pilot.VARIANT] or m['tasks']!=tasks(out,devices) or i['devices']!=old['identity']['devices'] or m['libraries']!=old['libraries']:
        raise ValueError('Routed PVT native maps or coverage changed')
    for task in m['tasks']:
        folder=out/task['id']
        if ((folder/'bench.cir').read_text()!=fixture(folder,task['spec'],devices)
                or sha(folder/'bench.cir')!=task['deck_sha256']
                or any(sha(folder/name)!=digest for name,digest in m['libraries'].items())):
            raise ValueError('Routed PVT independent full fixture changed')
    return m


def assess(rows):
    if len(rows)!=270 or any(r['error'] is not None or r['result'] is None for r in rows):return None
    if [r['task']['spec'] for r in rows]!=specifications():raise ValueError('Full PVT counter coverage changed')
    passed=all(pilot.source.point_passed(r['result']) and r['result']['counter_shared_wire_rc_qualified'] is True for r in rows)
    return dict(all_270_counter_boundaries_present=True,all_15_counter_pvt_covered=True,
        retained_cases=sum(r['task']['mode']=='retained' for r in rows),
        routed_counter_pvt_boundary_screen_passed=passed,whole_clock_rc_qualified=False,
        electrical_qualification_passed=False,qualified_phy=False)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial routed PVT run')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),
                        '-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=dict(protocol.measure(folder,i,task['spec']),scope=SCOPE)
            except Exception as exc:error=str(exc)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,comparison=assess(rows),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=270,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('prepare','run','campaign'));parser.add_argument('artifact',type=Path,nargs='?')
    args=parser.parse_args()
    out=prepare() if args.action in ('prepare','campaign') else args.artifact.resolve()
    print(out,flush=True)
    if args.action in ('run','campaign'):print(run(out),flush=True)
