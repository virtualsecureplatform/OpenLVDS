#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare a completed fine31 point after integrating measured inverter gangs.

One diagnostic case only: no zero/coarse/PVT/PHY admission or parent promotion.
Retain the original 20 ns fixture and every native terminal/control observation.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import probe_strong_coarse_bank_v123 as parent_producer
import measured_gang_bank_v125 as circuit

ROOT=circuit.ROOT
zero=parent_producer.zero
sha=parent_producer.sha
VERSION='measured-group-final-gangs-completed-fine31-comparison-v127.1'
CONTEXT='measured_gang_fine_v127'
SCOPE='Complete measured coarse/fine/group/final component RC, one matched fine31 diagnostic; first/root TG gang and common bank wiring unextracted; no zero/coarse/PVT/electrical/PHY admission'


def fixture(out,i):
    text=zero.fixture(out,dict(i,spec=i['spec'],top=circuit.name(i['spec']['profile'])))
    title='OpenLVDS '+zero.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original native fine31 fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def prepare(case):
    parent=case.parent;m=parent_producer.bound(parent);pi=m['identity'];row=json.loads((case/'summary.json').read_text());s=row['spec'];profile=s['profile']
    tasks=[t for t in m['tasks'] if t['id']==case.name]
    if (len(tasks)!=1 or tasks[0]!=row['task'] or row['error'] is not None
        or s!=dict(zero.spec(),profile=profile,coarse=0,fine=31)
        or not row['result']['static_native_screen_passed'] or not row['result']['output_slew_domain_passed']
        or any(sha(case/n)!=h for n,h in row['files'].items())
        or parent_producer.measure(case,pi,s)!=row['result']):
        raise ValueError('Require unchanged complete safe fine31 parent point')
    bank=circuit.transform_existing((parent/('bank_'+profile+'.spice')).read_text(),profile)
    original=ROOT/pi['parent'];previous=json.loads((original/'manifest.json').read_text())['identity']['observations']
    observations=circuit.observations(bank,profile,previous)
    paths=[parent/'manifest.json',parent/('bank_'+profile+'.spice'),case/'summary.json',*[case/n for n in row['files']],*[ROOT/n for n in pi['inputs']]]
    paths+=circuit.driver_inputs()
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    ports=circuit.source.native.definitions(bank)[circuit.name(profile)][0]
    i=dict(version=VERSION,parent_case=str(case.relative_to(ROOT)),spec=s,ports=ports,observations=observations,
           model=pi['model'],simulator=pi['simulator'],pdk_files=pi['pdk_files'],external_files={**pi['external_files'],**pi['fine_external_files']},
           original_observations=str((original/'manifest.json').relative_to(ROOT)),
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},scope=SCOPE,max_workers=1)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'0').mkdir();(out/'bank.spice').write_text(bank)
    (out/'0/bench.cir').write_text(fixture(out,i))
    (out/'manifest.json').write_text(json.dumps(dict(identity=i,bank_sha256=sha(out/'bank.spice'),deck_sha256=sha(out/'0/bench.cir'),qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];s=i['spec'];profile=s['profile']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or zero.engine()!='ngspice' or zero.provenance()!=i['simulator'] or i['max_workers']!=1
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
        or sha(out/'bank.spice')!=m['bank_sha256'] or sha(out/'0/bench.cir')!=m['deck_sha256']
        or (out/'0/bench.cir').read_text()!=fixture(out,i)):
        raise ValueError('Measured gang fine31 context changed')
    parent=(ROOT/i['parent_case']).parent
    bank=circuit.transform_existing((parent/('bank_'+profile+'.spice')).read_text(),profile)
    previous=json.loads((ROOT/i['original_observations']).read_text())['identity']['observations']
    if bank!=(out/'bank.spice').read_text() or circuit.observations(bank,profile,previous)!=i['observations']:
        raise ValueError('Measured gang model/terminals cannot regenerate')
    return i


def measure(folder,i):
    view=dict(i,observations={i['spec']['profile']:i['observations']})
    r=parent_producer.measure(folder,view,i['spec'])
    r.update(scope=SCOPE,group_gang_component_rc_qualified=True,parallel_final_inverter_interconnect_qualified=True,
             whole_bank_rc_retained=False,electrical_qualification_passed=False,qualified_phy=False)
    return r


def run(out):
    i=bound(out);folder=out/'0'
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial measured-gang comparison')
        zero.baseline.atomic(out/'state.json',dict(status='running',qualified_phy=False));result=error=wall=None
        try:
            with zero.lease(ROOT,priority=0,label=CONTEXT):
                bound(out);start=time.monotonic()
                p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                wall=time.monotonic()-start
            (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();result=measure(folder,i)
        except Exception as e:error=str(e)
        row=dict(spec=i['spec'],result=result,error=error,solver_wall_seconds=wall,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
        zero.baseline.atomic(folder/'summary.json',row);bound(out)
        parent=json.loads((ROOT/i['parent_case']/'summary.json').read_text())['result']
        comparison=None
        if result is not None:
            comparison=dict(repeated_delay_change_ps={edge:result['samples'][1][edge+'_delay_ps']-parent['samples'][1][edge+'_delay_ps'] for edge in ['rise','fall']},
                maximum_slew_change_ps=(result['maximum_output_slew_ps']-parent['maximum_output_slew_ps']
                    if result['maximum_output_slew_ps'] is not None and parent['maximum_output_slew_ps'] is not None else None))
        zero.baseline.atomic(out/'summary.json',dict(rows=[row],comparison=comparison,qualified_phy=False,scope=SCOPE))
        zero.baseline.atomic(out/'state.json',dict(status='complete',cases=1,errors=int(error is not None),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(prepare(a.artifact.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
