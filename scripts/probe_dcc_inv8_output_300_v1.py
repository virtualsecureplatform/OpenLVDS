#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""One-factor INV8 source DCC repair pilot, all native MOS and events retained."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import probe_dcc_inputs_300_v2 as baseline
import dcc_inv8_output_300_v1 as architecture
import dcc_inv8_fixture_300_v1 as wiring
import dcc_inv8_measure_300_v1 as metrology
import dcc_path_timing_300_v1 as paths
import diagnose_dcc_paths_300_v1 as diagnostic
from native_binary_raw_v2 import validate
from replay_bank_300_v2 import same
from spice_dispatch import lease

ROOT=baseline.ROOT
PARENT=baseline.PARENT
REFERENCE=ROOT/'build/diagnostics/dcc_corrected_input_pilot_300_v2/bef3db10942b26f2'
DIAG=ROOT/'build/diagnostics/dcc_path_diagnostic_300_v1/988e8d528baf5be7'
VERSION='native-inv8-output-dcc-one-factor-repair-300-v1'
CONTEXT='dcc_inv8_output_pilot_300_v1'
SCOPE='Eight fresh INV8 source points, complete native health and path diagnosis; no physical output-driver, full PVT, loaded DLL or PHY admission'
sha=baseline.sha
atomic=baseline.atomic


def specifications():return baseline.specifications()


def evidence():
    m=baseline.bound(REFERENCE);i=json.loads((DIAG/'manifest.json').read_text())['identity']
    r=json.loads((DIAG/'summary.json').read_text())
    if (i['version']!=diagnostic.VERSION or i['parent']!=str(REFERENCE.relative_to(ROOT)) or i['cases']!=['0','1']
            or DIAG.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or json.loads((DIAG/'state.json').read_text())!=dict(status='complete',cases=2,qualified_phy=False)
            or r['timing_modified'] is not False or r['qualified_phy'] is not False
            or len(r['rows'])!=2 or [x['original_source_screen_passed'] for x in r['rows']]!=[True,False]
            or not all(x['all_original_metrics_reproduced'] and x['independent_path_metrics_reproduced'] for x in r['rows'])
            or any(sha(Path(n))!=h for n,h in i['inputs'].items())):
        raise ValueError('Require complete independently reproduced DCC passing/failing paths')
    failed=r['rows'][1]
    if (failed['task']!=m['tasks'][1] or failed['path']['reconstructed_mean_half_cycle_error_ps']<=50
            or failed['path']['mean_phase180_minus_phase0_stage_ps']['toggle_to_output']<=60):
        raise ValueError('Original output-stage symmetry failure changed')
    inputs=dict(i['inputs'])
    for n in ('manifest.json','summary.json','state.json'):inputs[str(DIAG/n)]=sha(DIAG/n)
    return inputs


def variant():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    return (*architecture.transform((PARENT/'cells.spice').read_text(),(PARENT/'hold1.spice').read_text(),pdk.read_text()),pdk)


def prepare():
    inputs=evidence();donor=baseline.legacy.bound(PARENT);cells,hold,pdk=variant()
    library=cells+'\n'+hold;obs=wiring.observations(library)
    inputs.update({**donor['identity']['inputs'],**donor['identity']['pdk_files']})
    files=[PARENT/'manifest.json',PARENT/'cells.spice',PARENT/'hold1.spice',pdk,ROOT/'clocking_300mhz.json',ROOT/'build/tools/ngspice.json']
    files+=[ROOT/n for n in json.loads((ROOT/'build/tools/ngspice.json').read_text())['files']]
    files+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs.update({str(p):sha(p) for p in files})
    identity=dict(version=VERSION,inputs=inputs,scope=SCOPE,specs=specifications(),observations=obs,
        output_driver=architecture.NEW,max_workers=1,priority=2,retained_cases=0,qualified_phy=False,
        complete_matrix_admitted=False,physical_source_admitted=False)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'cells.spice').write_text(cells);(out/'hold1.spice').write_text(hold);tasks=[]
    for k,s in enumerate(specifications()):
        folder=out/str(k);folder.mkdir();deck,observed=wiring.fixture(out,s,library)
        if observed!=obs:raise ValueError('Output driver native observations vary by source condition')
        (folder/'bench.cir').write_text(deck);tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={n:sha(out/n) for n in ('cells.spice','hold1.spice')},qualified_phy=False))
    bound(out);return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['scope']!=SCOPE or i['specs']!=specifications() or i['output_driver']!=architecture.NEW
            or (i['max_workers'],i['priority'],i['retained_cases'])!=(1,2,0)
            or any(i[n] is not False for n in ('qualified_phy','complete_matrix_admitted','physical_source_admitted'))
            or m['qualified_phy'] is not False or any(sha(Path(n))!=h for n,h in i['inputs'].items())):
        raise ValueError('INV8 output-drive repair capture changed')
    cells,hold,_=variant()
    if (out/'cells.spice').read_text()!=cells or (out/'hold1.spice').read_text()!=hold:
        raise ValueError('One-factor source output-drive change cannot regenerate')
    library=cells+'\n'+hold
    if m['libraries']!={n:sha(out/n) for n in ('cells.spice','hold1.spice')} or i['observations']!=wiring.observations(library):
        raise ValueError('INV8 exact library or native map changed')
    tasks=[]
    for k,s in enumerate(specifications()):
        folder=out/str(k)
        if full and (folder/'bench.cir').read_text()!=wiring.fixture(out,s,library)[0]:raise ValueError('INV8 native input fixture changed')
        tasks.append(dict(id=str(k),spec=s,deck_sha256=sha(folder/'bench.cir')))
    if m['tasks']!=tasks:raise ValueError('INV8 complete pilot coverage changed')
    return m


def pilot_passed(rows):
    if [(r['task']['id'],r['task']['spec']) for r in rows]!=[(str(k),s) for k,s in enumerate(specifications())]:
        raise ValueError('Require all eight INV8 native source cases')
    return all(r['error'] is None and r['result']['source_screen_passed'] is True for r in rows)


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial INV8 source evidence')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];error=result=independent=timing_paths=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                names,w=validate(folder/'bench.raw',set(),wiring.waveform.capture_stop_ps(task['spec'])*1e-12)
                result=metrology.measure(names,w,task['spec'],m['identity']['observations'])
                independent=metrology.measure(names,w,task['spec'],m['identity']['observations'],independent=True)
                if not same(result,independent):raise ValueError('Independent INV8 native health does not reproduce')
                if all(result['source'][k] for k in ('event_integrity_passed','initial_high_output_passed','alternating_output_order_passed','pulse_generator_integrity_passed','full_swing_output_passed')):
                    timing_paths=paths.measure(names,w,task['spec']);witness=paths.measure(names,w,task['spec'],independent=True)
                    if not same(timing_paths,witness):raise ValueError('Independent INV8 path timing does not reproduce')
            except Exception as exc:error=str(exc)
            rows.append(dict(task=task,error=error,result=result,independent_result=independent,timing_paths=timing_paths,
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()}))
            atomic(folder/'summary.json',rows[-1]);atomic(out/'progress.json',dict(completed=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
        bound(out);atomic(out/'summary.json',dict(rows=rows,all_pilot_cases_passed=pilot_passed(rows),
            complete_matrix_admitted=False,physical_source_admitted=False,qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=8,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:
        if a.artifact is None:p.error('Supply captured INV8 source repair artifact')
        print(run(a.artifact.resolve()),flush=True)
