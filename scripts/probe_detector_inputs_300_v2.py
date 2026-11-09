#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh true-slew tagged-detector native pilot; never physical admission."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import detector_inputs_300_v1 as waveform
import detector_fixture_300_v2 as wiring
import detector_measure_300_v1 as metrology
import detector_native_observations_300_v1 as observations
import run_native_binary_v2 as runtime
from dcc_source_300 import model_closure
from replay_bank_300_v2 import same
from spice_dispatch import lease

legacy=waveform.donor.base
ROOT=legacy.ROOT
PARENT=ROOT/'build/diagnostics/phase_threshold_pvt_v2/7f2eeea8cd9e0678'
VERSION='corrected-static-detector-canonical-observations-native-pilot-300-v2'
CONTEXT='detector_corrected_input_pilot_300_v2'
sha=legacy.sha
atomic=legacy.atomic
SCOPE='36 isolated source-decision points only; full 900 matrix, native stress qualification, physical matching, loaded DLL and PHY remain required'
LIBRARIES=('cells.spice','frontend.spice','bias.spice','arbiter.spice','threshold.spice')


def specifications():
    return [s for s in waveform.specifications() if s['process']=='ss' and s['temperature']==40
            and (s['reference_slew_ps'],s['feedback_slew_ps']) in ((20,250),(250,20),(250,250))]


def prepare():
    donor=waveform.donor.bound(PARENT)
    # The donor selects exact circuit bytes, not any historical timing result.
    inputs={str(Path(n) if Path(n).is_absolute() else ROOT/n):h
        for n,h in donor['identity']['code'].items()}
    inputs.update(model_closure(Path(donor['identity']['model_library'])))
    original_devices=donor['tasks'][0]['devices']
    if any(t['devices']!=original_devices for t in donor['tasks']):raise ValueError('Historical detector custom-device maps differ')
    devices=observations.devices(PARENT,waveform.fixture(PARENT,specifications()[0],original_devices))
    paths=[PARENT/n for n in ('manifest.json',*LIBRARIES)]
    paths+=[ROOT/'clocking_300mhz.json',ROOT/'build/tools/ngspice.json']
    paths+=[ROOT/n for n in json.loads((ROOT/'build/tools/ngspice.json').read_text())['files']]
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs.update({str(p):sha(p) for p in paths})
    identity=dict(version=VERSION,source_cell_donor=str(PARENT.relative_to(ROOT)),inputs=inputs,
        specs=specifications(),devices=devices,scope=SCOPE,max_workers=1,priority=2,retained_cases=0,
        historical_timing_reused=False,complete_900_matrix_admitted=False,qualified_phy=False)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for n in LIBRARIES:(out/n).write_bytes((PARENT/n).read_bytes())
    tasks=[]
    for k,s in enumerate(specifications()):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(wiring.fixture(out,s,devices))
        tasks.append(dict(id=str(k),spec=s,devices=devices,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,
        libraries={n:sha(out/n) for n in LIBRARIES},qualified_phy=False))
    bound(out);return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['source_cell_donor']!=str(PARENT.relative_to(ROOT)) or i['specs']!=specifications()
            or i['scope']!=SCOPE or (i['max_workers'],i['priority'])!=(1,2) or i['retained_cases']!=0
            or any(i[n] is not False for n in ('historical_timing_reused','complete_900_matrix_admitted','qualified_phy'))
            or m['qualified_phy'] is not False):raise ValueError('Corrected detector source pilot identity changed')
    if any(sha(Path(n))!=h for n,h in i['inputs'].items()):raise ValueError('Captured detector source input changed')
    libraries={n:sha(out/n) for n in LIBRARIES}
    if m['libraries']!=libraries or any((out/n).read_bytes()!=(PARENT/n).read_bytes() for n in libraries):
        raise ValueError('Exact source-cell circuit changed')
    source=json.loads((PARENT/'manifest.json').read_text())
    if i['devices']!=observations.devices(PARENT,waveform.fixture(PARENT,specifications()[0],source['tasks'][0]['devices'])):
        raise ValueError('Full native detector observation map changed')
    tasks=[dict(id=str(k),spec=s,devices=i['devices'],deck_sha256=sha(out/str(k)/'bench.cir')) for k,s in enumerate(specifications())]
    if m['tasks']!=tasks:raise ValueError('Corrected detector source pilot coverage changed')
    if full:
        for task in tasks:
            if (out/task['id']/'bench.cir').read_text()!=wiring.fixture(out,task['spec'],i['devices']):
                raise ValueError('Corrected detector source stimulus changed')
    return m


def pilot_passed(rows):
    if len(rows)!=36 or [(r['task']['id'],r['task']['spec']) for r in rows]!=[(str(k),s) for k,s in enumerate(specifications())]:
        raise ValueError('Require all 36 corrected native detector cases')
    return all(r['error'] is None and r['result']['source_point_passed'] is True for r in rows)


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
                result=metrology.measure(folder,task)
                independent=metrology.measure(folder,task,independent=True)
                if not same(result,independent):raise ValueError('Independent corrected source metrics do not reproduce')
            except Exception as exc:error=str(exc)
            row=dict(task=task,error=error,result=result,independent_result=independent,
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
            atomic(out/'progress.json',dict(completed=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,all_pilot_cases_passed=pilot_passed(rows),
            complete_900_matrix_admitted=False,physical_detector_admitted=False,qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=36,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:
        if a.artifact is None:p.error('Supply corrected source pilot artifact')
        print(run(a.artifact.resolve()),flush=True)
