#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh eight-case native corrected-input DCC pilot; never matrix admission."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import dcc_input_waveforms_300_v2 as waveform
import dcc_source_measure_300_v2 as metrology
import run_native_binary_v2 as runtime
from native_binary_raw_v2 import validate
from replay_bank_300_v2 import same
from spice_dispatch import lease

legacy=waveform.previous
ROOT=legacy.ROOT
PARENT=ROOT/'build/diagnostics/dcc_source_300_v1/1a4f4e8eabb896e4'
VERSION='corrected-independent-dcc-input-native-pilot-300-v2'
CONTEXT='dcc_corrected_input_pilot_300_v2'
sha=legacy.sha
atomic=legacy.atomic
SCOPE='Eight ideal-input source points only; full independent-input matrix, native stress, physical RC, loaded DLL and PHY remain required'


def specifications():
    return [dict(process='sf',temperature=40,mhz=310,r_duty=d,f_duty=d,
        r_slew_10_90_ps=a,f_slew_10_90_ps=b,phase_error_ps=0,cycles=18)
        for d in (.6,.4) for a,b in ((250,250),(20,250),(250,20),(20,20))]


def prepare():
    donor=legacy.bound(PARENT)
    # The donor selects exact circuit bytes, not any historical timing result.
    inputs={**donor['identity']['inputs'],**donor['identity']['pdk_files']}
    paths=[PARENT/n for n in ('manifest.json','cells.spice','hold1.spice')]
    paths+=[ROOT/'clocking_300mhz.json',ROOT/'build/tools/ngspice.json']
    paths+=[ROOT/n for n in json.loads((ROOT/'build/tools/ngspice.json').read_text())['files']]
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs.update({str(p):sha(p) for p in paths})
    identity=dict(version=VERSION,source_cell_donor=str(PARENT.relative_to(ROOT)),inputs=inputs,
        specs=specifications(),scope=SCOPE,max_workers=1,priority=2,retained_cases=0,
        historical_timing_reused=False,complete_4860_matrix_admitted=False,qualified_phy=False)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for n in ('cells.spice','hold1.spice'):(out/n).write_bytes((PARENT/n).read_bytes())
    tasks=[]
    for k,s in enumerate(specifications()):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(waveform.fixture(out,s))
        tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        libraries={n:sha(out/n) for n in ('cells.spice','hold1.spice')},qualified_phy=False))
    bound(out);return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['source_cell_donor']!=str(PARENT.relative_to(ROOT)) or i['specs']!=specifications()
            or i['scope']!=SCOPE or (i['max_workers'],i['priority'])!=(1,2) or i['retained_cases']!=0
            or any(i[n] is not False for n in ('historical_timing_reused','complete_4860_matrix_admitted','qualified_phy'))
            or m['qualified_phy'] is not False):raise ValueError('Corrected DCC source pilot identity changed')
    if any(sha(Path(n))!=h for n,h in i['inputs'].items()):raise ValueError('Captured DCC source input changed')
    libraries={n:sha(out/n) for n in ('cells.spice','hold1.spice')}
    if m['libraries']!=libraries or any((out/n).read_bytes()!=(PARENT/n).read_bytes() for n in libraries):
        raise ValueError('Exact source-cell circuit changed')
    tasks=[dict(id=str(k),spec=s,deck_sha256=sha(out/str(k)/'bench.cir')) for k,s in enumerate(specifications())]
    if m['tasks']!=tasks:raise ValueError('Corrected DCC source pilot coverage changed')
    if full:
        for task in tasks:
            if (out/task['id']/'bench.cir').read_text()!=waveform.fixture(out,task['spec']):
                raise ValueError('Corrected DCC source stimulus changed')
    return m


def pilot_passed(rows):
    if len(rows)!=8 or [(r['task']['id'],r['task']['spec']) for r in rows]!=[(str(k),s) for k,s in enumerate(specifications())]:
        raise ValueError('Require all eight corrected native source cases')
    return all(r['error'] is None and r['result']['source_screen_passed'] is True for r in rows)


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial corrected source pilot')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];error=result=independent=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                names,w=validate(folder/'bench.raw',set(),waveform.capture_stop_ps(task['spec'])*1e-12)
                result=metrology.measure(names,w,task['spec'])
                independent=metrology.measure(names,w,task['spec'],independent=True)
                if not same(result,independent):raise ValueError('Independent corrected source metrics do not reproduce')
            except Exception as exc:error=str(exc)
            row=dict(task=task,error=error,result=result,independent_result=independent,
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
            atomic(out/'progress.json',dict(completed=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,all_pilot_cases_passed=pilot_passed(rows),
            complete_4860_matrix_admitted=False,physical_source_admitted=False,qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=8,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:
        if a.artifact is None:p.error('Supply corrected source pilot artifact')
        print(run(a.artifact.resolve()),flush=True)
