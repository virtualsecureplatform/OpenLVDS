#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure reset/disable on the selected extracted PFD at all fifteen PVT.

Source-prototype controls never transfer to this changed physical circuit.
This campaign requires the passing eighteen-case native seed pilot; it does
not replace expanded native phase coverage or any loop/signoff requirement.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess

import pilot_native_slew_dll as pilot
import pfd_control_protocol as protocol
import qualify_slew_frontend_controls as source_controls
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='dll_slew_native_controls'
sha=pilot.sha
OUTPUTS=pilot.OUTPUTS


def tasks(recipe):
    if recipe.get('version')!=pilot.coverage.VERSION:raise ValueError('Require the versioned repaired-DLL coverage recipe')
    return [dict(id=f'controls_{p}_{t}_{f}mhz_{sr}_{sf}',
                 spec=pilot.coverage.phase(p,t,f,(sr,sf),0))
            for p,t,f in source_controls.points(recipe['worst_screened_pvt'])
            for sr,sf in ((100,100),*pilot.coverage.SLEWS)]


def pilot_gate(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics'/pilot.NAMESPACE):raise ValueError('Require the extracted native seed pilot')
    with (parent/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        report=pilot.verify(parent)
        if report['native_pilot_passed'] is not True or report['known_false_bad_cases_restored'] is not True:
            raise ValueError('Both known false-BAD failures and the complete native pilot must pass')
        return pilot.bound(parent)


def fixture(task,observations,gate_probes,prefix,library,model):
    spec=task['spec']
    prefix=source_controls.expansion.corner_prefix(prefix,spec['process'],spec['temperature'])
    deck,aliases=pilot.fixture(spec,observations,gate_probes,prefix,library,model)
    deck=protocol.apply(deck);aliases.update(RST='RST',ENABLE='ENABLE')
    return deck,aliases


def fixture_context(identity):
    assembled=ROOT/identity['assembly'];am=json.loads((assembled/'manifest.json').read_text())
    observed=json.loads((assembled/'clock_observations.json').read_text())
    template=(ROOT/identity['template']).read_text()
    prefix=template[:template.index('XB PB NB VDDIO 0 lvds_bias')]
    return am['identity']['analog_observation_nodes'],observed['phase_probes'],prefix


def prepare(parent):
    pm=pilot_gate(parent);pi=pm['identity'];assembled=ROOT/pi['parent']
    am=json.loads((assembled/'manifest.json').read_text())
    q=ROOT/am['identity']['qualification_reference'];template=q/'slew_ss_40_0ps_20_200/bench.cir'
    pending=tasks(pi['coverage_recipe']);inputs=dict(pi['inputs'])
    paths=[parent/n for n in ('manifest.json','summary.json','full.spice')]
    for t in pm['tasks']:paths += [parent/t['id']/n for n in (*OUTPUTS,'summary.json','bench.cir')]
    paths += [assembled/'manifest.json',assembled/'clock_observations.json',template]
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code=dict(pi['code'])
    for n in (Path(__file__).name,'pfd_control_protocol.py','qualify_slew_frontend_controls.py','expand_dll_slew_frontends.py'):
        code[n]=sha(ROOT/'scripts'/n)
    identity=dict(parent=str(parent.relative_to(ROOT)),assembly=str(assembled.relative_to(ROOT)),template=str(template.relative_to(ROOT)),
                  variant=pi['variant'],coverage_recipe=pi['coverage_recipe'],protocol=protocol.VERSION,
                  simulator=provenance(),inputs=inputs,code=code,collateral=pi['collateral'],
                  scope='Fresh extracted-native reset/disable: all fifteen PVT at 400 MHz; 390/410 MHz at TT25, SS40 and measured source worst PVT; matched and both unequal slews. Complete original phase fixture and receiving MOS clock observations. Expanded native phase balance, loop, stability, readiness, stress and PHY qualification remain required.')
    out=ROOT/'build/diagnostics'/NAMESPACE/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);model=(parent/'full.spice').read_text()
    observations,gates,prefix=fixture_context(identity)
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        pilot.assembly.extraction.physical.write_once(out/'full.spice',model);prepared=[]
        for t in pending:
            folder=out/t['id'];folder.mkdir(exist_ok=True)
            deck,aliases=fixture(t,observations,gates,prefix,out/'full.spice',model)
            pilot.assembly.extraction.physical.write_once(folder/'bench.cir',deck)
            prepared.append(dict(t,aliases=aliases,deck_sha256=sha(folder/'bench.cir')))
        (out/'producers').mkdir(exist_ok=True)
        for n in code:pilot.assembly.extraction.physical.write_once(out/'producers'/n,(ROOT/'scripts'/n).read_text())
        capture_manifest(out/'manifest.json',dict(identity=identity,model_sha256=sha(out/'full.spice'),tasks=prepared,
                                                physical_admission=False,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics'/NAMESPACE) or
        out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
        i['protocol']!=protocol.VERSION or i['simulator']!=provenance() or
        m['physical_admission'] is not False or m['qualified_phy'] is not False or
        any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or
        any(sha(ROOT/'scripts'/n)!=h or sha(out/'producers'/n)!=h for n,h in i['code'].items()) or
        any(sha(Path(n))!=h for n,h in i['collateral'].items()) or sha(out/'full.spice')!=m['model_sha256'] or
        (out/'full.spice').read_bytes()!=(ROOT/i['parent']/'full.spice').read_bytes() or
        [{k:v for k,v in t.items() if k not in ('aliases','deck_sha256')} for t in m['tasks']]!=tasks(i['coverage_recipe'])):
        raise ValueError('Native reset/disable context changed')
    pm=pilot_gate(ROOT/i['parent']);pi=pm['identity']
    if i['assembly']!=pi['parent'] or i['variant']!=pi['variant'] or i['coverage_recipe']!=pi['coverage_recipe']:
        raise ValueError('Native reset/disable pilot admission changed')
    observations,gates,prefix=fixture_context(i);model=(out/'full.spice').read_text()
    for t in m['tasks']:
        deck,aliases=fixture(t,observations,gates,prefix,out/'full.spice',model)
        if deck!=(out/t['id']/'bench.cir').read_text() or aliases!=t['aliases'] or sha(out/t['id']/'bench.cir')!=t['deck_sha256']:
            raise ValueError('Native reset/disable fixture or observations changed')
    return m


def measure(folder,task):
    phase=pilot.measure(folder,task)
    wave,header=pilot.original.completed(folder)
    for alias,node in task['aliases'].items():header['V('+alias+')']=header['V('+node.upper()+')']
    gates=[n for n in task['aliases'] if n.startswith(('REF_FF_CLK_','FB_FF_CLK_'))]
    controls=protocol.measure(wave,header,task['spec']['mhz'],('REF','FDB',*gates))
    return dict(passed=bool(phase['passed'] and controls['passed']),recovered_phase=phase,controls=controls)


def aggregate(m,rows):
    expected={t['id']:t for t in m['tasks']}
    if (not expected or len(expected)!=len(m['tasks']) or len(rows)!=len(expected) or
        len({r['task'] for r in rows})!=len(rows) or
        any(r['task'] not in expected or r['spec']!=expected[r['task']]['spec'] for r in rows)):
        raise ValueError('Native reset/disable results missing, duplicated or unexpected')
    passed=sum(bool(r['error'] is None and r['result'] and r['result']['passed']) for r in rows)
    return dict(native_controls_passed=passed==len(expected),passed_cases=passed,required_cases=len(expected),results=rows,
                physical_admission=False,qualified_phy=False,scope=m['identity']['scope'])


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    def unchanged(t):
        if (sha(out/'manifest.json')!=stamp or sha(out/'full.spice')!=m['model_sha256'] or
            sha(out/t['id']/'bench.cir')!=t['deck_sha256'] or
            any(sha(ROOT/'scripts'/n)!=h for n,h in m['identity']['code'].items())):raise ValueError('Native reset/disable execution context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists() or any((out/t['id']/n).exists() for t in m['tasks'] for n in (*OUTPUTS,'summary.json')):
            raise ValueError('Partial native reset/disable output retained; no retry')
        atomic(out/'state.json',dict(status='qualifying_native_controls',qualified_phy=False))
        def execute(t):
            folder=out/t['id'];result=error=None
            try:
                with lease(ROOT,priority=1,label='native_slew_controls_'+t['id']):
                    unchanged(t);p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();unchanged(t)
                result=measure(folder,t);unchanged(t)
            except Exception as e:error=str(e)
            row=dict(task=t['id'],spec=t['spec'],result=result,error=error,manifest_sha256=stamp,
                     files={n:sha(folder/n) for n in OUTPUTS if (folder/n).exists()})
            capture_manifest(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        if sha(out/'manifest.json')!=stamp:raise ValueError('Native reset/disable manifest changed')
        report=dict(aggregate(m,rows),manifest_sha256=stamp);capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='native_controls_passed' if report['native_controls_passed'] else 'held_native_controls_failed',qualified_phy=False))
    return report


def verify(out):
    m=bound(out);stamp=sha(out/'manifest.json');rows=[]
    for t in m['tasks']:
        folder=out/t['id'];r=json.loads((folder/'summary.json').read_text())
        if (r['task']!=t['id'] or r['spec']!=t['spec'] or r['error'] is not None or r['manifest_sha256']!=stamp or
            set(r['files'])!=set(OUTPUTS) or any(sha(folder/n)!=h for n,h in r['files'].items()) or measure(folder,t)!=r['result']):
            raise ValueError('Native reset/disable result changed')
        rows.append(r)
    report=dict(aggregate(m,rows),manifest_sha256=stamp)
    if report!=json.loads((out/'summary.json').read_text()):raise ValueError('Native reset/disable aggregate changed')
    bound(out);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path)
    a=p.parse_args();r=globals()[a.action](a.artifact.resolve())
    print(r if a.action=='prepare' else json.dumps(r,indent=2),flush=True)
