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
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=pilot.ROOT
PARENT=ROOT/'build/diagnostics/local_setter_shared_rc_v351/b8297d638d69090d'
VERSION='verified-local-route-counter-full-pvt-clock-boundaries-v354.1'
CONTEXT='routed_counter_pvt_v354'
SCOPE=('Actual local-first-setter v349/v350 shared-wire RC loaded counter: '
       'five process corners, 0/25/40C, 390/400/410MHz, 40/50/60% duty and both '
       'stopped levels, fixed 1.8V, original full 26ns protocol and 808 native MOS; '
       'twelve independently replayed retained traces plus 258 new traces; '
       'counter boundary coverage only, no full clock/DCC/DLL or PHY admission')
sha=pilot.sha
atomic=pilot.atomic


def specifications():
    base=pilot.specifications()[0]
    return [dict(base,process=p,temperature=t,mhz=f,duty=d,stop_level=level)
        for p in ('ss','ff','sf','fs','tt') for t in (40,0,25)
        for f in (410,390,400) for d in (.6,.4,.5) for level in (1,0)]


def fixture(folder,spec,devices):
    text=pilot.fixture(folder,spec,devices)
    prefix='OpenLVDS '+pilot.VERSION+'\n'
    if not text.startswith(prefix):raise ValueError('Original full native fixture changed')
    return text.replace(prefix,'OpenLVDS '+VERSION+'\n',1)


def replay_coverage(reports,manifest,rows):
    """Validate receipt coverage before collecting each immutable input once."""
    covered=set();inputs={}
    tasks=manifest['tasks']
    if len(tasks)!=12 or len(rows)!=12:raise ValueError('Require complete twelve-point pilot')
    for report in reports:
        if (report.get('all_original_native_metrics_reproduced') is not True
                or report.get('parameters_changed') is not False
                or report.get('analysis_completed') is not True):
            raise ValueError('Require completed unchanged independent native replay')
        for name,digest in report['inputs'].items():
            if name in inputs and inputs[name]!=digest:raise ValueError('Conflicting replay input')
            inputs[name]=digest
        for row in report['rows']:
            number=row['task']['id']
            if (number not in [str(k) for k in range(12)] or number in covered
                    or row['task']!=tasks[int(number)]
                    or row['case']!=str((PARENT/number).relative_to(ROOT))
                    or row.get('all_original_native_metrics_reproduced') is not True
                    or row.get('native_mos')!=808):
                raise ValueError('Missing, duplicate or unrelated replay case')
            stored=rows[int(number)]
            sample=row['exact_limiting_samples']['whole_counter']
            worst=max(stored['result']['terminal_stress'],key=lambda d:d['max_terminal_difference_v'])
            if (stored['task']!=row['task'] or stored['error'] is not None
                    or not pilot.source.point_passed(stored['result'])
                    or sample['device']!=worst['device']
                    or sample['peak_v']!=worst['max_terminal_difference_v'] or sample['margin_v']<=0
                    or row['low_windows']!=stored['result']['low_windows']):
                raise ValueError('Replayed pilot timing or exact limiting sample changed')
            # The receipts must bind the actual original raw, deck and result,
            # as well as both libraries and captured measurement source.
            required={str((PARENT/number/n).relative_to(ROOT)) for n in
                      ('bench.raw','bench.cir','summary.json')}
            required.update(str((PARENT/n).relative_to(ROOT)) for n in ('cells.spice','pair.spice','manifest.json'))
            if not required<=set(report['inputs']):raise ValueError('Unbound pilot replay')
            covered.add(number)
    if covered!={str(k) for k in range(12)}:raise ValueError('Require all twelve independent native replays')
    return inputs


def tasks(out,devices,previous):
    rows=[]
    for k,spec in enumerate(specifications()):
        matches=[t for t in previous['tasks'] if t['spec']==spec]
        if len(matches)>1:raise ValueError('Duplicate retained pilot point')
        if matches:
            old=matches[0]
            rows.append(dict(id=str(k),spec=spec,mode='retained',source_case=str((PARENT/old['id']).relative_to(ROOT)),
                             deck_sha256=old['deck_sha256']))
        else:
            rows.append(dict(id=str(k),spec=spec,mode='simulate',
                deck_sha256=hashlib.sha256(fixture(out/str(k),spec,devices).encode()).hexdigest()))
    return rows


def prepare(receipts):
    if json.loads((PARENT/'state.json').read_text())!=dict(status='complete',cases=12,errors=0,qualified_phy=False):
        raise ValueError('Wait for naturally complete zero-error routed pilot')
    previous=pilot.bound(PARENT);i=previous['identity']
    summary=json.loads((PARENT/'summary.json').read_text())
    if (summary['comparison']!=pilot.assess(summary['rows'])
            or summary['comparison']['actual_shared_counter_timing_pilot_passed'] is not True):
        raise ValueError('Require passing original actual-RC pilot')
    reports=[json.loads(path.read_text()) for path in receipts]
    evidence=replay_coverage(reports,previous,summary['rows'])
    for name,digest in evidence.items():
        if sha(ROOT/name)!=digest:raise ValueError('Independent native replay input changed: '+name)
    paths=[PARENT/n for n in ('manifest.json','summary.json','state.json',*previous['libraries'])]
    paths += receipts
    paths += sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module,'__file__',None) and Path(module.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**evidence,**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    guards=pilot.source.source.candidate.guard_inputs(inputs)
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),specs=specifications(),
        inputs=inputs,guards=guards,receipts=[str(p.relative_to(ROOT)) for p in receipts],
        devices=i['devices'],simulator=i['simulator'],pdk_files=i['pdk_files'],external_files=i['external_files'],
        library_sha256=previous['libraries'],max_workers=2,priority=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name in previous['libraries']:(out/name).write_bytes((PARENT/name).read_bytes())
    planned=tasks(out,i['devices'][pilot.VARIANT],previous)
    for task in planned:
        folder=out/task['id'];folder.mkdir()
        if task['mode']=='simulate':
            for name in previous['libraries']:(folder/name).write_bytes((PARENT/name).read_bytes())
            (folder/'bench.cir').write_text(fixture(folder,task['spec'],i['devices'][pilot.VARIANT]))
    atomic(out/'manifest.json',dict(identity=identity,tasks=planned,libraries=previous['libraries'],qualified_phy=False))
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['scope']!=SCOPE
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['specs']!=specifications() or (i['max_workers'],i['priority'])!=(2,2)
            or i['guards']!=pilot.source.source.candidate.guard_inputs(i['inputs'])
            or engine()!='ngspice' or provenance()!=i['simulator']
            or m['libraries']!=i['library_sha256']):raise ValueError('Routed PVT identity changed')
    for name,digest in {**(i['inputs'] if full else i['guards']),**i['pdk_files'],**i['external_files']}.items():
        if sha(ROOT/name)!=digest:raise ValueError('Routed PVT input changed: '+name)
    for name,digest in m['libraries'].items():
        if sha(out/name)!=digest:raise ValueError('Original actual-RC library changed')
    old=json.loads((PARENT/'manifest.json').read_text())
    devices=pilot.native.mapped_mos((out/'cells.spice').read_text()+'\n'+(out/'pair.spice').read_text(),pilot.HARNESS,
        {p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in pilot.PORTS},'XD')
    if devices!=i['devices'][pilot.VARIANT] or m['tasks']!=tasks(out,devices,old):
        raise ValueError('Routed PVT native maps or coverage changed')
    for task in m['tasks']:
        if task['mode']=='retained':continue
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
                if task['mode']=='retained':
                    original=ROOT/task['source_case'];stored=json.loads((original/'summary.json').read_text())
                    if (stored['task']['spec']!=task['spec'] or stored['error'] is not None
                            or sha(original/'bench.cir')!=task['deck_sha256']
                            or any(sha(original/n)!=h for n,h in stored['files'].items())):
                        raise ValueError('Retained independently replayed native case changed')
                    result=stored['result']
                else:
                    with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                        bound(out,full=False)
                        p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),
                            '-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                    result=dict(pilot.source.source.candidate.measure(folder,i,task['spec']),component_rc_only=False,
                        counter_shared_wire_rc_qualified=True,whole_clock_rc_qualified=False,all_pvt_covered=False,
                        electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
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
    parser.add_argument('--replay',type=Path,action='append',default=[])
    args=parser.parse_args()
    out=prepare([p.resolve() for p in args.replay]) if args.action in ('prepare','campaign') else args.artifact.resolve()
    print(out,flush=True)
    if args.action in ('run','campaign'):print(run(out),flush=True)
