#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Early native two-bank zero loading diagnostic; coverage and source parity remain open."""
import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import next_bank_tg2_materials_300_v1 as materials
import two_bank_native_measure_300_v1 as metrology
import replay_distributed_native_300_v3 as source_replay
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from spice_dispatch import lease

ROOT=materials.ROOT
SOURCE=materials.producer
PARENT=materials.PARENT
MATERIAL=ROOT/'build/diagnostics/tg2_next_bank_zero_materials_300_v1/e0fb1a825657793f'
VERSION='double-tg-early-two-bank-zero-diagnostic-300-v2'
CONTEXT='tg2_next_bank_early_zero_pilot_300_v2'
MATERIAL_ORDER=('1','3','0','2')
sha=materials.sha
atomic=materials.atomic


def require_source(proofs):
    # Independent completed point evidence is enough to diagnose loading, but
    # does not qualify source coverage or its still-pending numerical pair.
    if len(proofs)!=2:raise ValueError('Require independent zero and fine60 point receipts')
    for k in (0,1):
        if not (PARENT/str(k)/'summary.json').is_file():
            raise ValueError('Required source point is still pending: '+str(k))
    m=SOURCE.bound(PARENT);i=m['identity'];inputs=deepcopy(i['inputs'])
    def retain(path):inputs[str(path.relative_to(ROOT))]=sha(path)
    retain(PARENT/'manifest.json')
    for k,proof in enumerate(proofs):
        folder=PARENT/str(k);row=json.loads((folder/'summary.json').read_text())
        if (row['task']!=m['tasks'][k] or row['error'] is not None
                or row['result']['current_clock_interface_screen_passed'] is not True):
            raise ValueError('Required source point did not pass its complete native screen')
        retain(folder/'summary.json')
        for n,h in row['files'].items():
            if sha(folder/n)!=h:raise ValueError('Completed source point changed')
            retain(folder/n)
        pm=json.loads((proof/'manifest.json').read_text());pi=pm['identity']
        pr=json.loads((proof/'summary.json').read_text())
        if (proof.parent!=ROOT/'build/diagnostics/distributed_family_native_replay_300_v3'
                or pi['version']!=source_replay.VERSION
                or proof.name!=hashlib.sha256(json.dumps(pi,sort_keys=True).encode()).hexdigest()[:16]
                or pi['parent']!=str(PARENT.relative_to(ROOT)) or pi['cases']!=[str(k)]
                or json.loads((proof/'state.json').read_text())!=dict(status='complete',cases=1,qualified_phy=False)
                or pr['all_selected_native_metrics_reproduced'] is not True
                or len(pr['rows'])!=1 or pr['rows'][0]['task']!=m['tasks'][k]
                or not all(pr['rows'][0][key] is True for key in
                    ('all_original_metrics_reproduced','independent_timing_reproduced',
                     'independent_terminal_envelope_reproduced','independent_control_and_gate_settling_reproduced'))
                or pr['qualified_phy'] is not False or pr['whole_bank_admitted'] is not False):
            raise ValueError('Require exact independent zero/fine60 native point receipts')
        for n,h in pi['inputs'].items():
            if sha(ROOT/n)!=h or (n in inputs and inputs[n]!=h):
                raise ValueError('Independent source point provenance changed')
            inputs[n]=h
        for n in ('manifest.json','summary.json','state.json'):retain(proof/n)
    return m,inputs


def fixture(material_deck,out):
    include=f'.include "{MATERIAL}/bank.spice"'
    if material_deck.count(include)!=1:raise ValueError('Require the captured actual next-bank library')
    return material_deck.replace(include,f'.include "{out}/bank.spice"',1)


def prepare(proofs):
    source,evidence=require_source(proofs)
    material=materials.check(MATERIAL)
    paths=[MATERIAL/'manifest.json',MATERIAL/'state.json',MATERIAL/'bank.spice',ROOT/'clocking_300mhz.json']
    paths += [MATERIAL/t['id']/n for t in material['tasks'] for n in t['files']]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**evidence,**material['identity']['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),material=str(MATERIAL.relative_to(ROOT)),
        source_point_proofs=[str(p.relative_to(ROOT)) for p in proofs],inputs=inputs,
        source_full_bank_coverage_qualified=False,source_active_numerical_parity_qualified=False,
        guards={n:h for n,h in inputs.items() if Path(n).suffix!='.raw'},
        spec=source['tasks'][0]['spec'],max_workers=1,priority=2,
        profile_sha256=sha(ROOT/'clocking_300mhz.json'),
        scope='Early actual native next-bank zero diagnostic; source coverage and source numerical pair pending, common wires ideal, no bank/DLL/PVT/PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'bank.spice').write_bytes((MATERIAL/'bank.spice').read_bytes())
    tasks=[]
    for k,material_id in enumerate(MATERIAL_ORDER):
        t=material['tasks'][int(material_id)]
        folder=out/str(k);folder.mkdir()
        (folder/'bench.cir').write_text(fixture((MATERIAL/t['id']/'bench.cir').read_text(),out))
        (folder/'observations.json').write_bytes((MATERIAL/t['id']/'observations.json').read_bytes())
        tasks.append(dict(id=str(k),material_case_id=material_id,next_coarse=t['next_coarse'],next_fine=t['next_fine'],centered=t['centered'],
                          files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,bank_sha256=sha(out/'bank.spice'),qualified_phy=False))
    bound(out)
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['parent']!=str(PARENT.relative_to(ROOT)) or i['material']!=str(MATERIAL.relative_to(ROOT))
            or (i['max_workers'],i['priority'])!=(1,2) or i['profile_sha256']!=sha(ROOT/'clocking_300mhz.json')
            or i['guards']!={n:h for n,h in i['inputs'].items() if Path(n).suffix!='.raw'}
            or m['qualified_phy'] is not False):raise ValueError('Actual next-bank experiment identity changed')
    if any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items()):
        raise ValueError('Captured next-bank experiment input changed')
    source=json.loads((PARENT/'manifest.json').read_text())
    proofs=[ROOT/n for n in i['source_point_proofs']]
    if (i['spec']!=source['tasks'][0]['spec'] or len(proofs)!=2
            or i['source_full_bank_coverage_qualified'] is not False
            or i['source_active_numerical_parity_qualified'] is not False
            or any(proof.parent!=ROOT/'build/diagnostics/distributed_family_native_replay_300_v3' for proof in proofs)
            or any(str((proof/n).relative_to(ROOT)) not in i['guards']
                   for proof in proofs for n in ('manifest.json','summary.json','state.json'))):
        raise ValueError('Early loading source specification or independent point binding changed')
    material=materials.check(MATERIAL)
    if (sha(out/'bank.spice')!=m['bank_sha256']
            or (out/'bank.spice').read_bytes()!=(MATERIAL/'bank.spice').read_bytes()):
        raise ValueError('Actual native next-bank library changed')
    expected=[]
    for k,material_id in enumerate(MATERIAL_ORDER):
        t=material['tasks'][int(material_id)]
        folder=out/str(k)
        if ((folder/'bench.cir').read_text()!=fixture((MATERIAL/t['id']/'bench.cir').read_text(),out)
                or (folder/'observations.json').read_bytes()!=(MATERIAL/t['id']/'observations.json').read_bytes()):
            raise ValueError('Actual next-bank stimulus or native observation map changed')
        expected.append(dict(id=str(k),material_case_id=material_id,next_coarse=t['next_coarse'],next_fine=t['next_fine'],centered=t['centered'],
                             files={n:sha(folder/n) for n in ('bench.cir','observations.json')}))
    if m['tasks']!=expected:raise ValueError('Actual next-bank experiment coverage changed')
    return m


def numerical_pair(out,rows,a,b):
    if rows[a]['error'] is not None or rows[b]['error'] is not None:
        return dict(passed=False,reason='Native pair incomplete')
    names,x=validate(out/str(a)/'bench.raw',set(),40e-9)
    other,y=validate(out/str(b)/'bench.raw',set(names),40e-9)
    method=SOURCE.prior.numerical
    forward=method.wave_difference(names,x,other,y);reverse=method.wave_difference(other,y,names,x)
    dc=max(abs(float(x[0,names.index(n)])-float(y[0,other.index(n)])) for n in names if n.startswith('v('))
    errors=[]
    for node in ('v(in)','v(out)','v(next_out)'):
        for up in (True,False):
            first=crossings(x[:,0]*1e12,x[:,names.index(node)],.9,up)
            second=crossings(y[:,0]*1e12,y[:,other.index(node)],.9,up)
            if len(first)!=8 or len(second)!=8:return dict(passed=False,reason='Missing complete active events')
            errors.extend(abs(v-w) for v,w in zip(first,second))
    flags=True
    for label in ('first','next'):
        u=rows[a]['result']['banks'][label];v=rows[b]['result']['banks'][label]
        for key in ('bank_screen_passed','terminal_screen_passed','control_settling_passed'):
            flags=flags and u[key]==v[key]
        for key,value in u['timing'].items():
            if key.endswith('_passed'):flags=flags and value==v['timing'][key]
        for category in ('terminal_stress','controls','programming_gates','external_controls'):
            flags=flags and [q['passed'] for q in u[category]]==[q['passed'] for q in v[category]]
    flags=flags and rows[a]['result']['fixed_supply_passed']==rows[b]['result']['fixed_supply_passed']
    passed=bool(x[0,0]==y[0,0]==0 and dc<=1e-9 and flags and max(errors)<=.25
        and max(forward['maximum_all_vector_error_v'],reverse['maximum_all_vector_error_v'])<=.002)
    return dict(passed=passed,reference_difference=forward,reverse_difference=reverse,
                maximum_dc_voltage_error_v=dc,maximum_crossing_error_ps=max(errors),all_gate_classifications_preserved=flags)


def pilot_passed(rows,pairs):
    expected=[('0',0,True),('1',31,True),('2',0,False),('3',31,False)]
    if ([(r['task']['id'],r['task']['next_fine'],r['task']['centered']) for r in rows]!=expected
            or set(pairs)!={'0','31'}):
        raise ValueError('Require all four loaded native cases and both fresh numerical pairs')
    return bool(all(r['error'] is None and r['result']['two_bank_zero_pilot_passed'] for r in rows)
                and all(p['passed'] is True for p in pairs.values()))


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial actual next-bank experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));rows=[]
        for task in m['tasks']:
            folder=out/task['id'];error=result=None
            try:
                with lease(ROOT,priority=2,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                observations=json.loads((folder/'observations.json').read_text())
                result=metrology.measure(folder,observations,i['spec'],next_coarse=task['next_coarse'],next_fine=task['next_fine'])
            except Exception as exc:error=str(exc)
            row=dict(task=task,error=error,result=result,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
        pairs={str(f):numerical_pair(out,rows,a,b) for f,a,b in ((0,2,0),(31,3,1))}
        passed=pilot_passed(rows,pairs)
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,active_numerical_controls=pairs,actual_next_bank_zero_pilot_passed=passed,
            source_full_bank_coverage_qualified=False,source_active_numerical_parity_qualified=False,
            shared_wire_rc_qualified=False,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=4,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'))
    p.add_argument('artifacts',nargs='+',type=Path)
    a=p.parse_args();targets=[v.resolve() for v in a.artifacts]
    if a.action=='prepare':
        if len(targets)!=2:p.error('Supply independent zero and fine60 point receipts, in that order')
        print(prepare(targets),flush=True)
    else:
        if len(targets)!=1:p.error('Supply one captured early loaded experiment')
        print(run(targets[0]),flush=True)
