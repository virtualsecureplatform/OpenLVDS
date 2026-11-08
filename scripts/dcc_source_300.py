#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh 300 MHz clock-aware DCC source screen; never physical/PHY admission."""
import argparse
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import clocking_profile_300 as policy
import probe_dcc_clock_hold_v2 as source
from spice_dispatch import lease
from spice_engine import command, engine, provenance

ROOT=policy.ROOT
VERSION='clock-aware-dcc-source-300-v1'
CONTEXT='dcc_source_300_v1'
PARENT=ROOT/'build/diagnostics/dcc_clock_hold_pvt_v2/8b83d935bd2d01f3'
sha=source.base.sha
atomic=source.base.atomic
SCOPE='Fresh source-cell DCC event/reset/half-cycle screen only; ideal input phases, 20fF load; no physical RC, terminal-stress, DLL or PHY admission'


def specifications():
    r=policy.load()['requirements']
    return [dict(process=p,temperature=t,mhz=f,duty=d,slew_ps=s,phase_error_ps=e,
                 buffers=0,drive=1,output_cell='inv_4',reset_drive=1)
        for p,t,f,d,s,e in itertools.product(
            ['sf','ss','ff','fs','tt'],[40,0,25],r['clock_test_mhz'][::-1],
            [.6,.4,.5],[20,250],[0,-140,140])]


def fixture(out,spec):
    if spec not in specifications():raise ValueError('Undeclared 300 MHz source point')
    text=source.fixture(out,spec)
    period=1000/spec['mhz'];slew=spec['slew_ps']/1000
    # Keep rising-event epochs, reset, load and all observations unchanged.
    # Pulse plateau excludes one ramp, so threshold-to-threshold duty is exact.
    for old,new in ((period*.3-slew,period*spec['duty']-slew),
                    (period*.7-slew,period*(1-spec['duty'])-slew)):
        token=f'{old}n {period}n)'
        if text.count(token)!=1:raise ValueError('Captured source pulse changed')
        text=text.replace(token,f'{new}n {period}n)',1)
    return text.replace('OpenLVDS '+source.base.VERSION,'OpenLVDS '+VERSION,1)


def model_closure(model,known=None):
    """Discover or check every model include, across all library sections."""
    pending=[model.resolve()];seen=set();observed={}
    while pending:
        path=pending.pop()
        if path in seen:continue
        seen.add(path)
        digest=sha(path)
        if known is not None and (str(path) not in known or digest!=known[str(path)]):
            raise ValueError('Missing or changed transitive PDK file: '+str(path))
        observed[str(path)]=digest
        for line in path.read_text().splitlines():
            if not re.match(r'(?i)^\s*\.(?:include|inc|lib)\s+',line):continue
            words=shlex.split(line)
            if words[0].lower()=='.lib' and len(words)==2:continue  # Local section.
            if len(words)<2:raise ValueError('Incomplete model include')
            pending.append((path.parent/words[1]).resolve())
    return {str(p):observed[str(p)] for p in sorted(seen)}


def prepare():
    if engine()!='ngspice':raise ValueError('Require declared ngspice runtime')
    # The historical certificate selects circuit bytes only; no old timing is reused.
    import dcc_source_admission_v2 as admission
    receipt=admission.source_admission(PARENT)
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    cell=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    models=model_closure(model)
    paths=[PARENT/n for n in ['manifest.json','summary.json','state.json','cells.spice','hold1.spice']]
    paths += [receipt,ROOT/'clocking_300mhz.json',ROOT/'build/tools/ngspice.json',cell]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    paths += [ROOT/n for n in json.loads((ROOT/'build/tools/ngspice.json').read_text())['files']]
    inputs={str(p):sha(p) for p in paths}
    if (PARENT/'hold1.spice').read_text()!=source.circuit(1):raise ValueError('Selected source circuit differs')
    identity=dict(version=VERSION,inputs=inputs,pdk_files=models,simulator=provenance(),
        specs=specifications(),max_workers=1,priority=2,scope=SCOPE,retained_cases=0)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for n in ['cells.spice','hold1.spice']:(out/n).write_bytes((PARENT/n).read_bytes())
    tasks=[]
    for k,spec in enumerate(identity['specs']):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,spec))
        tasks.append(dict(id=str(k),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        libraries={n:sha(out/n) for n in ['cells.spice','hold1.spice']},qualified_phy=False))
    bound(out)
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['specs']!=specifications() or (i['max_workers'],i['priority'])!=(1,2)
        or i['retained_cases']!=0 or i['scope']!=SCOPE or engine()!='ngspice'
        or i['simulator']!=provenance() or m['qualified_phy'] is not False):
        raise ValueError('DCC source profile/identity changed')
    for n,digest in {**i['inputs'],**i['pdk_files']}.items():
        if sha(Path(n))!=digest:raise ValueError('DCC source input changed: '+n)
    for n,digest in m['libraries'].items():
        if sha(out/n)!=digest:raise ValueError('DCC library changed')
    if len(m['tasks'])!=810 or [t['spec'] for t in m['tasks']]!=specifications():
        raise ValueError('Incomplete DCC source coverage')
    if full:
        for k,task in enumerate(m['tasks']):
            path=out/str(k)/'bench.cir'
            if task['id']!=str(k) or sha(path)!=task['deck_sha256'] or path.read_text()!=fixture(out,task['spec']):
                raise ValueError('Changed DCC source deck')
    return m


def passed(result,spec):
    return bool(result and result['event_integrity_passed']
        and result['pulse_generator_integrity_passed']
        and (spec['phase_error_ps']!=0 or result['symmetric_timing_passed']))


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior execution')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];result=error=None
            try:
                if sha(folder/'bench.cir')!=task['deck_sha256']:raise ValueError('Changed source task')
                with lease(ROOT,priority=2,label='dcc_source_300_'+task['id']):
                    bound(out,full=False)
                    proc=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),capture_output=True,text=True)
                source.base.write(folder/'console.log',proc.stdout+proc.stderr);proc.check_returncode()
                result=source.measure(folder,task['spec'])
            except Exception as exc:error=str(exc)
            row=dict(task=task,result=result,error=error,
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
            atomic(out/'progress.json',dict(completed=len(rows),errors=sum(r['error'] is not None for r in rows),
                failed_cases=[r['task']['id'] for r in rows if r['error'] or not passed(r['result'],r['task']['spec'])],qualified_phy=False))
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,source_screen_passed=all(not r['error'] and passed(r['result'],r['task']['spec']) for r in rows),scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','run','bound']);parser.add_argument('artifact',type=Path,nargs='?')
    args=parser.parse_args()
    if args.action=='prepare':print(prepare(),flush=True)
    elif args.artifact is None:parser.error('Require artifact')
    elif args.action=='run':run(args.artifact.resolve())
    else:print(json.dumps(bound(args.artifact.resolve()),indent=2))
