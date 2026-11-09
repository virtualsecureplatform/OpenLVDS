#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh 300-profile routed DCC diagnostics; retain every electrical failure."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import routed_dcc_fixture_300_v1 as wiring
import routed_dcc_measure_300_v1 as metrology
import run_native_binary_v2 as runtime
from native_binary_raw_v2 import validate
from dcc_source_300 import model_closure
from replay_bank_300_v2 import same
from spice_dispatch import lease

proof=wiring.proof
ROOT=proof.ROOT
PROOF=ROOT/'build/diagnostics/retained_dcc_rc_proof_300_v1/fdc34b71008b5c20'
VERSION='retained-routed-dcc-fresh-300-profile-phase-release-pilot-v1'
CONTEXT='routed_dcc_pilot_300_v1'
SCOPE='Seven fresh ideal-phase routed-macro points only; no historical timing reuse, actual release circuit, full PVT, loaded DLL or PHY admission'
sha=proof.sha
atomic=proof.atomic


def specifications():
    points=[('ss',40,310,.6,250,250),('ss',40,310,.4,250,250),
            ('ss',40,310,.6,20,250),('ss',40,310,.6,250,20),
            ('sf',40,310,.6,250,250),('sf',40,310,.4,250,250),('tt',25,300,.5,20,20)]
    return [dict(process=p,temperature=t,mhz=f,r_duty=d,f_duty=d,r_slew_10_90_ps=a,
                 f_slew_10_90_ps=b,phase_error_ps=0,cycles=18) for p,t,f,d,a,b in points]


def material():
    i=proof.bound(PROOF);r=json.loads((PROOF/'summary.json').read_text())
    if (json.loads((PROOF/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
            or r['component_rc_model_proof_passed'] is not True or r['fresh_native_topology_passed'] is not True
            or r['exact_reduction_regenerated'] is not True or r['passivity_passed'] is not True
            or r['independent_terminal_current_proof']['passed'] is not True
            or r['qualified_phy'] is not False or r['electrical_qualification_passed'] is not False
            or r['historical_timing_reused'] is not False or r['extraction']!=i['extraction']
            or r['census']!=i['census'] or any(sha(PROOF/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require the complete unchanged routed DCC model proof')
    return i,r,proof.physical.checked_netlist(r['extraction'])


def prepare():
    pi,pr,text=material()
    paths=[PROOF/n for n in ('manifest.json','summary.json','state.json',*pr['files'])]
    paths+=[ROOT/'clocking_300mhz.json',ROOT/'build/tools/ngspice.json']
    paths+=[ROOT/n for n in json.loads((ROOT/'build/tools/ngspice.json').read_text())['files']]
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**pi['inputs'],**pi['technology'],**{str(p):sha(p) for p in paths}}
    model=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    inputs.update(model_closure(model))
    identity=dict(version=VERSION,inputs=inputs,model_proof=str(PROOF.relative_to(ROOT)),
        extraction=pr['extraction'],specs=specifications(),scope=SCOPE,max_workers=1,priority=2,
        retained_timing_cases=0,historical_timing_reused=False,actual_release_circuit_qualified=False,
        full_pvt_admitted=False,qualified_phy=False)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'dcc_native.spice').write_text(text);tasks=[]
    for k,s in enumerate(specifications()):
        folder=out/str(k);folder.mkdir();deck,obs=wiring.fixture(out,s,pr['extraction'],text)
        (folder/'bench.cir').write_text(deck);atomic(folder/'observations.json',obs)
        tasks.append(dict(id=str(k),spec=s,files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,library_sha256=sha(out/'dcc_native.spice'),qualified_phy=False))
    bound(out);return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['model_proof']!=str(PROOF.relative_to(ROOT)) or i['specs']!=specifications() or i['scope']!=SCOPE
            or (i['max_workers'],i['priority'],i['retained_timing_cases'])!=(1,2,0)
            or any(i[n] is not False for n in ('historical_timing_reused','actual_release_circuit_qualified','full_pvt_admitted','qualified_phy'))
            or m['qualified_phy'] is not False or any(sha(Path(n))!=h for n,h in i['inputs'].items())):
        raise ValueError('Fresh routed DCC pilot identity changed')
    _,pr,text=material()
    if i['extraction']!=pr['extraction'] or (out/'dcc_native.spice').read_text()!=text or sha(out/'dcc_native.spice')!=m['library_sha256']:
        raise ValueError('Routed DCC exact RC model changed')
    tasks=[]
    for k,s in enumerate(specifications()):
        folder=out/str(k)
        if full:
            deck,obs=wiring.fixture(out,s,i['extraction'],text)
            if (folder/'bench.cir').read_text()!=deck or json.loads((folder/'observations.json').read_text())!=obs:
                raise ValueError('Routed DCC native phase/release fixture changed')
        tasks.append(dict(id=str(k),spec=s,files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    if m['tasks']!=tasks:raise ValueError('Routed DCC complete pilot coverage changed')
    return m


def pilot_passed(rows):
    if [(r['task']['id'],r['task']['spec']) for r in rows]!=[(str(k),s) for k,s in enumerate(specifications())]:
        raise ValueError('Require all seven fresh routed DCC native cases')
    return all(r['error'] is None and r['result']['routed_point_passed'] is True for r in rows)


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial routed DCC pilot')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];error=result=independent=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                obs=json.loads((folder/'observations.json').read_text())
                names,w=validate(folder/'bench.raw',set(),wiring.waveform.capture_stop_ps(task['spec'])*1e-12)
                result=metrology.measure(names,w,task['spec'],obs)
                independent=metrology.measure(names,w,task['spec'],obs,independent=True)
                if not same(result,independent):raise ValueError('Independent full routed DCC measurements do not reproduce')
            except Exception as exc:error=str(exc)
            rows.append(dict(task=task,error=error,result=result,independent_result=independent,
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()}))
            atomic(folder/'summary.json',rows[-1]);atomic(out/'progress.json',dict(completed=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,all_pilot_points_passed=pilot_passed(rows),historical_timing_reused=False,
            actual_release_circuit_qualified=False,full_pvt_admitted=False,loaded_dll_admitted=False,qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=7,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:
        if a.artifact is None:p.error('Supply captured routed DCC pilot artifact')
        print(run(a.artifact.resolve()),flush=True)
