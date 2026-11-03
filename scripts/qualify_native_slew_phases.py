#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify the complete native phase/stuck-fault partition of repaired DLL coverage.

Retain every original native phase/logic signature and all versioned slew
additions. The unchanged-circuit seed pilot supplies matching phase evidence;
other cases require fresh transients. No loop, fast-RC or PHY admission.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import qualify_native_slew_controls as controls
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from spice_dispatch import lease
from spice_engine import command, provenance

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='dll_slew_native_phase_matrix'
pilot=controls.pilot
coverage=pilot.coverage
sha=pilot.sha
OUTPUTS=pilot.OUTPUTS


def required(requirements,recipe):
    if recipe.get('version')!=coverage.VERSION:raise ValueError('Require the versioned repaired-DLL coverage recipe')
    return {s for s in coverage.required_cases(requirements,recipe['worst_screened_pvt'])
            if s[0] is False and s[1] in ('phase','logic')}


def tasks(requirements,recipe,pilot_tasks):
    donors={coverage.original.signature(t['spec']):t for t in pilot_tasks}
    if len(donors)!=len(pilot_tasks):raise ValueError('Duplicated native seed signature')
    result=[]
    for sig in sorted(required(requirements,recipe),key=repr):
        spec={k:v for k,v in zip(coverage.original.FIELDS,sig[1:-1]) if v is not None}
        if sig[-1]:raise ValueError('Unexpected phase interruption')
        if spec['kind']=='logic':spec['expected']=True
        name='phase_'+hashlib.sha256(json.dumps(sig,separators=(',',':')).encode()).hexdigest()[:16]
        donor=donors.get(sig)
        result.append(dict(id=name,spec=spec,pilot_task=donor['id'] if donor else None))
    return result


def descriptor(requirements,recipe):
    signatures=sorted(required(requirements,recipe),key=repr)
    return dict(version=coverage.VERSION,partition='native-phase-and-logic',required_cases=len(signatures),
                signatures_sha256=hashlib.sha256(json.dumps(signatures,separators=(',',':')).encode()).hexdigest())


def fixture(task,observations,gate_probes,prefix,library,model):
    spec=task['spec'];gates=gate_probes if spec['kind']=='phase' else {}
    prefix=controls.source_controls.expansion.corner_prefix(prefix,spec['process'],spec['temperature'])
    return pilot.fixture(spec,observations,gates,prefix,library,model)


def normalized(deck):
    import re
    result,count=re.subn(r'(?m)^\.include "[^"\n]+"$', '.include "__SELECTED_NATIVE_MODEL__"',deck)
    if count!=1:raise ValueError('Require exactly one selected native model include')
    return result


def pilot_equivalence(parent,task,deck,aliases):
    pm=json.loads((parent/'manifest.json').read_text())
    donor=next(t for t in pm['tasks'] if t['id']==task['pilot_task'])
    folder=parent/donor['id']
    if (coverage.original.signature(donor['spec'])!=coverage.original.signature(task['spec']) or
        aliases!=donor['aliases'] or sha(folder/'bench.cir')!=donor['deck_sha256'] or
        normalized(deck)!=normalized((folder/'bench.cir').read_text())):
        raise ValueError('Native pilot circuit/stimulus/observation equivalence failed')


def prepare(parent):
    pm=controls.pilot_gate(parent);pi=pm['identity'];assembled=ROOT/pi['parent']
    am=json.loads((assembled/'manifest.json').read_text());q=ROOT/am['identity']['qualification_reference']
    template=q/'slew_ss_40_0ps_20_200/bench.cir';req=json.loads((ROOT/'requirements.json').read_text())
    pending=tasks(req,pi['coverage_recipe'],pm['tasks']);inputs=dict(pi['inputs'])
    paths=[parent/n for n in ('manifest.json','summary.json','full.spice')]
    for t in pm['tasks']:paths += [parent/t['id']/n for n in (*OUTPUTS,'summary.json','bench.cir')]
    paths += [assembled/'manifest.json',assembled/'clock_observations.json',template,ROOT/'requirements.json']
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code=dict(pi['code'])
    for n in (Path(__file__).name,'qualify_native_slew_controls.py','qualify_slew_frontend_controls.py',
              'expand_dll_slew_frontends.py','dll_slew_coverage.py','dll_native_evidence.py'):
        code[n]=sha(ROOT/'scripts'/n)
    identity=dict(parent=str(parent.relative_to(ROOT)),assembly=str(assembled.relative_to(ROOT)),template=str(template.relative_to(ROOT)),
                  variant=pi['variant'],coverage_recipe=pi['coverage_recipe'],phase_coverage=descriptor(req,pi['coverage_recipe']),
                  simulator=provenance(),inputs=inputs,code=code,collateral=pi['collateral'],
                  scope='Complete native phase/stuck-fault partition: all original signatures plus versioned unequal-slew PVT additions. Same selected extracted model; proven equivalent pilot evidence reused. No loop, fast-RC comparison, reset/disable, stability, readiness, stress or PHY admission.')
    out=ROOT/'build/diagnostics'/NAMESPACE/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);model=(parent/'full.spice').read_text()
    observations,gates,prefix=controls.fixture_context(identity)
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        write=pilot.assembly.extraction.physical.write_once;write(out/'full.spice',model);prepared=[]
        for t in pending:
            folder=out/t['id'];folder.mkdir(exist_ok=True)
            deck,aliases=fixture(t,observations,gates,prefix,out/'full.spice',model)
            if t['pilot_task']:pilot_equivalence(parent,t,deck,aliases)
            write(folder/'bench.cir',deck)
            prepared.append(dict(t,aliases=aliases,deck_sha256=sha(folder/'bench.cir')))
        (out/'producers').mkdir(exist_ok=True)
        for n in code:write(out/'producers'/n,(ROOT/'scripts'/n).read_text())
        capture_manifest(out/'manifest.json',dict(identity=identity,model_sha256=sha(out/'full.spice'),tasks=prepared,
                                                physical_admission=False,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];parent=ROOT/i['parent']
    req=json.loads((ROOT/'requirements.json').read_text())
    if (not out.is_relative_to(ROOT/'build/diagnostics'/NAMESPACE) or
        out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or i['simulator']!=provenance() or
        m['physical_admission'] is not False or m['qualified_phy'] is not False or
        i['phase_coverage']!=descriptor(req,i['coverage_recipe']) or
        any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or
        any(sha(ROOT/'scripts'/n)!=h or sha(out/'producers'/n)!=h for n,h in i['code'].items()) or
        any(sha(Path(n))!=h for n,h in i['collateral'].items()) or sha(out/'full.spice')!=m['model_sha256'] or
        (out/'full.spice').read_bytes()!=(parent/'full.spice').read_bytes()):raise ValueError('Native phase matrix context changed')
    pm=controls.pilot_gate(parent);pi=pm['identity']
    if (i['assembly']!=pi['parent'] or i['variant']!=pi['variant'] or i['coverage_recipe']!=pi['coverage_recipe'] or
        [{k:v for k,v in t.items() if k not in ('aliases','deck_sha256')} for t in m['tasks']]!=tasks(req,pi['coverage_recipe'],pm['tasks'])):
        raise ValueError('Native phase matrix pilot or coverage changed')
    observations,gates,prefix=controls.fixture_context(i);model=(out/'full.spice').read_text()
    for t in m['tasks']:
        deck,aliases=fixture(t,observations,gates,prefix,out/'full.spice',model)
        if deck!=(out/t['id']/'bench.cir').read_text() or aliases!=t['aliases'] or sha(out/t['id']/'bench.cir')!=t['deck_sha256']:
            raise ValueError('Native phase matrix fixture or observations changed')
        if t['pilot_task']:pilot_equivalence(parent,t,deck,aliases)
    return m


def measure(folder,task):
    if task['spec']['kind']=='phase':return pilot.measure(folder,task)
    wave,header=pilot.original.completed(folder)
    for alias,node in task['aliases'].items():header['V('+alias+')']=header['V('+node.upper()+')']
    logic=pilot.original.measurement.logic(wave,header,True)
    names,raw=read_raw(folder/'bench.raw');keep=(wave[:,1]>120e-9)&(wave[:,1]<160e-9)
    power=-3.3*raw[:,names.index('i(va)')]-1.8*raw[:,names.index('i(vd)')]
    return dict(passed=bool(logic['passed']),logic=logic,mean_power_w=pilot.original.measurement.average(wave[keep,1],power[keep]))


def aggregate(m,rows,requirements):
    expected={t['id']:t for t in m['tasks']};recipe=m['identity']['coverage_recipe']
    actual=[coverage.original.signature(t['spec']) for t in m['tasks']]
    if (len(actual)!=len(set(actual)) or set(actual)!=required(requirements,recipe) or
        len(expected)!=len(actual) or len(rows)!=len(expected) or len({r['task'] for r in rows})!=len(rows) or
        any(r['task'] not in expected or r['spec']!=expected[r['task']]['spec'] for r in rows)):
        raise ValueError('Native phase matrix results or required coverage missing, duplicated or unexpected')
    curves=[];by_signature={coverage.original.signature(r['spec']):r for r in rows}
    points=dict.fromkeys((s['process'],s['temperature'],s['mhz'],s['reference_slew_ps'],s['feedback_slew_ps'])
                         for s in coverage.native_additions(requirements,recipe['worst_screened_pvt']))
    for p,t,f,sr,sf in points:
        selected=[by_signature[coverage.original.signature(coverage.phase(p,t,f,(sr,sf),o))] for o in coverage.OFFSETS]
        valid=all(r['error'] is None and r['result'] and r['result']['passed'] for r in selected)
        monotonic=balance=False;zero=None
        if valid:
            values=[r['result']['phase']['filtered_area_difference_v'] for r in selected]
            monotonic=bool(np.isfinite(values).all() and all(b>a for a,b in zip(values,values[1:])))
            lo,hi=values[coverage.OFFSETS.index(-20)],values[coverage.OFFSETS.index(20)]
            balance=bool(lo<0<hi)
            if balance:zero=float(-20+40*(-lo)/(hi-lo))
        curves.append(dict(process=p,temperature=t,mhz=f,slew=[sr,sf],monotonic=monotonic,zero_bracket_passed=balance,estimated_zero_offset_ps=zero))
    passed=bool(all(r['error'] is None and r['result'] and r['result']['passed'] for r in rows) and
                all(c['monotonic'] and c['zero_bracket_passed'] for c in curves))
    return dict(native_phase_matrix_passed=passed,required_cases=len(expected),reused_pilot_cases=sum(t['pilot_task'] is not None for t in m['tasks']),
                checks=curves,results=rows,physical_admission=False,qualified_phy=False,scope=m['identity']['scope'])


def evidence_folder(out,m,task):
    return ROOT/m['identity']['parent']/task['pilot_task'] if task['pilot_task'] else out/task['id']


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    def unchanged(t):
        if (sha(out/'manifest.json')!=stamp or sha(out/'full.spice')!=m['model_sha256'] or
            sha(out/t['id']/'bench.cir')!=t['deck_sha256'] or any(sha(ROOT/'scripts'/n)!=h for n,h in m['identity']['code'].items())):
            raise ValueError('Native phase matrix execution context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists() or any((out/t['id']/n).exists() for t in m['tasks'] for n in (*OUTPUTS,'summary.json')):
            raise ValueError('Partial native phase matrix retained; no retry')
        atomic(out/'state.json',dict(status='qualifying_native_phases',qualified_phy=False))
        def execute(t):
            folder=evidence_folder(out,m,t);result=error=None
            try:
                if t['pilot_task']:unchanged(t)
                else:
                    with lease(ROOT,priority=1,label='native_slew_phase_'+t['id']):
                        unchanged(t);p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
                    (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();unchanged(t)
                result=measure(folder,t);unchanged(t)
            except Exception as e:error=str(e)
            row=dict(task=t['id'],spec=t['spec'],pilot_task=t['pilot_task'],result=result,error=error,manifest_sha256=stamp,
                     files={n:sha(folder/n) for n in OUTPUTS if (folder/n).exists()})
            capture_manifest(out/t['id']/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        if sha(out/'manifest.json')!=stamp:raise ValueError('Native phase matrix manifest changed')
        report=dict(aggregate(m,rows,json.loads((ROOT/'requirements.json').read_text())),manifest_sha256=stamp)
        capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='native_phase_matrix_passed' if report['native_phase_matrix_passed'] else 'held_native_phase_matrix_failed',qualified_phy=False))
    return report


def verify(out):
    m=bound(out);stamp=sha(out/'manifest.json');rows=[]
    for t in m['tasks']:
        folder=evidence_folder(out,m,t);r=json.loads((out/t['id']/'summary.json').read_text())
        if (r['task']!=t['id'] or r['spec']!=t['spec'] or r['pilot_task']!=t['pilot_task'] or r['error'] is not None or
            r['manifest_sha256']!=stamp or set(r['files'])!=set(OUTPUTS) or
            any(sha(folder/n)!=h for n,h in r['files'].items()) or measure(folder,t)!=r['result']):raise ValueError('Native phase matrix result changed')
        rows.append(r)
    report=dict(aggregate(m,rows,json.loads((ROOT/'requirements.json').read_text())),manifest_sha256=stamp)
    if report!=json.loads((out/'summary.json').read_text()):raise ValueError('Native phase matrix aggregate changed')
    bound(out);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path)
    a=p.parse_args();r=globals()[a.action](a.artifact.resolve())
    print(r if a.action=='prepare' else json.dumps(r,indent=2),flush=True)
