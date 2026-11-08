#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fresh combined source-DCC/chain loading diagnostic, with native reference."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import dcc_chain_materials_300_v1 as materials
import dcc_chain_measure_300_v2 as metrology
import four_bank_numerical_pair_300_v1 as chain_pair
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from spice_dispatch import lease

ROOT=materials.ROOT
MATERIAL=ROOT/'build/diagnostics/dcc_four_section_materials_300_v1/30fcd6cff3a7457d'
VERSION='fresh-source-dcc-four-section-native-loading-300-v1'
CONTEXT='dcc_four_section_pilot_300_v1'
sha=materials.sha
atomic=materials.atomic


def booleans(value,path=()):
    if isinstance(value,bool):return {path:value}
    if isinstance(value,dict):return {p:v for k,x in value.items() for p,v in booleans(x,path+(k,)).items()}
    if isinstance(value,list):return {p:v for k,x in enumerate(value) for p,v in booleans(x,path+(k,)).items()}
    return {}


def numerical_pair(out,rows):
    shaped=[dict(r,result=r['result']['chain'] if r['result'] is not None else None) for r in rows]
    base=chain_pair.numerical_pair(out,shaped,1,0)
    if rows[0]['error'] is not None or rows[1]['error'] is not None:return base
    names,x=validate(out/'1/bench.raw',set(),40e-9)
    other,y=validate(out/'0/bench.raw',set(names),40e-9)
    errors=[]
    nodes=['v(dcc0_out)','v(dcc1_out)']+[f'v(xdc{k}.{n})' for k in range(2) for n in ('a','b')]
    for node in nodes:
        for up in (True,False):
            a=crossings(x[:,0]*1e12,x[:,names.index(node)],.9,up)
            b=crossings(y[:,0]*1e12,y[:,other.index(node)],.9,up)
            if len(a)!=8 or len(b)!=8:return dict(base,passed=False,reason='Missing startup-inclusive DCC/pulse events')
            errors.extend(abs(v-w) for v,w in zip(a,b))
    preserved=booleans(rows[0]['result'])==booleans(rows[1]['result'])
    return dict(base,passed=bool(base['passed'] and preserved and max(errors)<=.25),
        maximum_dcc_and_pulse_crossing_error_ps=max(errors),all_combined_gate_classifications_preserved=preserved)


def fixture(text,out):
    for name in ('bank.spice','dcc.spice'):
        old=f'.include "{MATERIAL/name}"'
        if text.count(old)!=1:raise ValueError('Combined material library include changed')
        text=text.replace(old,f'.include "{out/name}"',1)
    return text


def prepare():
    m=materials.check(MATERIAL)
    if json.loads((MATERIAL/'state.json').read_text())!=dict(status='prepared_unqualified',simulations=0,qualified_phy=False):
        raise ValueError('Require validated diagnostic materials without admission')
    paths=[MATERIAL/n for n in ('manifest.json','state.json','bank.spice','dcc.spice')]
    paths += [MATERIAL/t['id']/n for t in m['tasks'] for n in ('bench.cir','observations.json')]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**m['identity']['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    identity=dict(version=VERSION,material=str(MATERIAL.relative_to(ROOT)),inputs=inputs,
        guards={n:h for n,h in inputs.items() if Path(n).suffix!='.raw'},max_workers=1,priority=2,
        source_chain_qualified=False,source_dcc_qualified=False,detector_fanout_present=False,
        shared_wire_rc_qualified=False,qualified_phy=False,
        scope='Source-DCC/four-section loading and pulse diagnostic only; no calibration, detector, routing or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for n in ('bank.spice','dcc.spice'):(out/n).write_bytes((MATERIAL/n).read_bytes())
    tasks=[]
    for task in m['tasks']:
        folder=out/task['id'];folder.mkdir();(folder/'bench.cir').write_text(fixture((MATERIAL/task['id']/'bench.cir').read_text(),out))
        (folder/'observations.json').write_bytes((MATERIAL/task['id']/'observations.json').read_bytes())
        tasks.append(dict(task,files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries=m['libraries'],qualified_phy=False))
    bound(out)
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['material']!=str(MATERIAL.relative_to(ROOT)) or (i['max_workers'],i['priority'])!=(1,2)
            or any(i[n] is not False for n in ('source_chain_qualified','source_dcc_qualified','detector_fanout_present','shared_wire_rc_qualified','qualified_phy'))
            or i['guards']!={n:h for n,h in i['inputs'].items() if Path(n).suffix!='.raw'}
            or m['qualified_phy'] is not False):raise ValueError('Combined native experiment identity changed')
    if any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items()):
        raise ValueError('Captured combined experiment input changed')
    material=json.loads((MATERIAL/'manifest.json').read_text())
    if any(str((MATERIAL/n).relative_to(ROOT)) not in i['guards'] for n in ('manifest.json','state.json','bank.spice','dcc.spice')):
        raise ValueError('Combined material binding changed')
    if m['libraries']!=material['libraries'] or any(sha(out/n)!=h for n,h in m['libraries'].items()):
        raise ValueError('Combined native library changed')
    expected=[]
    for task in material['tasks']:
        folder=out/task['id']
        if ((folder/'bench.cir').read_text()!=fixture((MATERIAL/task['id']/'bench.cir').read_text(),out)
                or (folder/'observations.json').read_bytes()!=(MATERIAL/task['id']/'observations.json').read_bytes()):
            raise ValueError('Combined actual deck or observations changed')
        expected.append(dict(task,files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    if m['tasks']!=expected:raise ValueError('Combined fresh reference tasks changed')
    return m


def pilot_passed(rows,pair):
    if len(rows)!=2 or [(r['task']['id'],r['task']['centered']) for r in rows]!=[('0',True),('1',False)] or rows[0]['task']['spec']!=rows[1]['task']['spec']:
        raise ValueError('Require both complete fresh combined cases')
    return bool(pair['passed'] and all(r['error'] is None and r['result']['combined_loading_transport_passed'] for r in rows))


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial combined native experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];error=result=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                result=metrology.measure(folder,json.loads((folder/'observations.json').read_text()),task['spec'])
            except Exception as exc:error=str(exc)
            row=dict(task=task,error=error,result=result,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
        pair=numerical_pair(out,rows);passed=pilot_passed(rows,pair);bound(out)
        atomic(out/'summary.json',dict(rows=rows,active_numerical_control=pair,combined_loading_pilot_passed=passed,
            source_chain_qualified=False,source_dcc_qualified=False,calibrated_phase_qualified=False,
            detector_fanout_qualified=False,shared_wire_rc_qualified=False,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=2,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',nargs='?',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:
        if a.artifact is None:p.error('Supply captured experiment directory')
        print(run(a.artifact.resolve()),flush=True)
