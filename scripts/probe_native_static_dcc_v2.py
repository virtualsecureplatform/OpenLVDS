#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Join independently verified static phase release to the conditioned DCC.

Compare common release with early internal data prepare at the approved duty
endpoints. Source conditioner and ideal inter-component wires remain explicit;
this pilot does not admit whole-backend, full-PVT, or PHY operation.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import sys
import native_static_dcc_components_v2 as components
import stack_guard_release_rc_families_v2 as families
import verify_static_phase_profile_v2 as profile
import clocking_duty_profile_v2 as duty_profile
import probe_conditioned_dcc_v3 as joint
from verify_conditioned_clock_v2 import regenerated_front
from measure_native_static_dcc_v2 import measure
from probe_digital_dcc_v2 import sha,write,atomic
from spice_dispatch import lease
from spice_engine import provenance,engine

ROOT=joint.ROOT
VERSION='joint-static-phase-release-native-component-rc-dcc-v2.1'
CONTEXT='native_static_dcc_v2'


def specifications():
    return [dict(variant=v,process='ss',temperature=40,mhz=410,load_ff=20,
                 slew0_ps=100,slew180_ps=100,duty=d,raw_start_ns=22)
            for v,d in itertools.product(components.MODES,duty_profile.load()['timing']['rx_reference_duty_range'])]


def selected_profile(receipt):
    r=json.loads((receipt/'summary.json').read_text());i=r['identity']
    if (receipt.parent!=ROOT/'build/diagnostics/static_phase_profile_verification_v2'
        or i['version']!=profile.VERSION or receipt.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or not r['source_counter_feasibility_passed'] or r['qualified_phy']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):raise ValueError('Static phase profile receipt changed')
    counter=ROOT/i['parent'];m=profile.verification.pilot.bound(counter)
    expected=[t for t in m['tasks'] if t['spec']['variant']==i['variant']]
    if len(expected)!=4 or [row['task'] for row in r['rows']]!=expected or any(not row['result']['counter_feasibility_passed'] for row in r['rows']):
        raise ValueError('Require complete positive selected counter profile')
    return i['variant'],m,[receipt/'summary.json',counter/'manifest.json',*[ROOT/n for n in i['inputs']],*[ROOT/n for n in m['identity']['inputs']]]


def fixture(out,spec,devices):
    deck=joint.fixture(out,spec,devices)
    def replace_once(old,new):
        nonlocal deck
        if deck.count(old)!=1:raise ValueError('Joint fixture interface changed: '+old)
        deck=deck.replace(old,new)
    marker=f'.include "{out}/frontend.spice"\n'
    replace_once(marker,f'.include "{out}/cells.spice"\n'+marker)
    for tag,clk,ready,reset in [('XR0','P0','PREPARE_0','RESET_N'),('XR180','P180','PREPARE_180','RESET_180')]:
        replace_once(f'{tag} {clk} REQUEST {reset} VDD 0 {joint.release.NAME}\n',
                     f'{tag} {clk} REQUEST {ready} {reset} VDD 0 {components.release.NAME}\n')
    name,ports=components.dcc_interface(spec['variant'])
    pins=dict(VGND='0',VPWR='VDD',clock_out='Q',phase0='P0',phase180='P180',reset_n='RESET_N',prepare_n='PREPARE_0')
    replace_once('XD '+' '.join(pins[p] for p in joint.sizing.circuit.PORTS)+' '+joint.sizing.circuit.NAME+'\n',
                 'XD '+' '.join(pins[p] for p in ports)+' '+name+'\n')
    lines=[line for line in deck.splitlines() if line.startswith('.print tran ')]
    if len(lines)!=1:raise ValueError('Joint probe list changed')
    replace_once(lines[0],'.print tran '+' '.join(sorted(set(lines[0].split()[2:])|{'V(PREPARE_0)','V(PREPARE_180)'})))
    return deck.replace('OpenLVDS '+joint.VERSION,'OpenLVDS '+VERSION)


def assembly(parent,receipt,tg):
    variant,cm,paths=selected_profile(receipt);jm=joint.bound(parent)
    front_parent=ROOT/jm['identity']['parent'];front,front_devices=regenerated_front(front_parent)
    cells={};artifacts=[ROOT/n for n in cm['identity']['families']]+[tg]
    for artifact in artifacts:
        group,files=families.witnesses(artifact)
        if set(group)&set(cells):raise ValueError('Duplicate actual component model')
        cells.update(group);paths+=files
    modules=components.compose(cells,variant);modules.update({n:front[n] for n in ['frontend.spice','bias.spice']})
    devices={v:components.devices(modules,front_devices,v) for v in components.MODES}
    paths += [parent/'manifest.json',front_parent/'manifest.json',front_parent/'frontend.spice',front_parent/'bias.spice']
    paths += [ROOT/n for n in jm['identity']['inputs']]
    return modules,devices,paths,dict(jm['identity']['pdk_files'],**cm['identity']['pdk_files']),variant,artifacts


def prepare(parent,receipt,tg):
    if engine()!='ngspice':raise ValueError('Use the pinned ngspice engine')
    modules,devices,paths,pdk_files,variant,artifacts=assembly(parent,receipt,tg)
    code=['probe_native_static_dcc_v2.py','native_static_dcc_components_v2.py','measure_native_static_dcc_v2.py',
          'stack_guard_release_rc_families_v2.py','phase_release_rc_families_v2.py','verify_static_phase_profile_v2.py',
          'static_phase_clock_release_v5.py','static_phase_clock_release_v2.py','guarded_clock_prepare_v2.py',
          'native_clock_components_v3.py','native_clock_components_v2.py','verify_conditioned_clock_v2.py',
          'native_binary_raw_v2.py','run_native_binary_v2.py','probe_conditioned_dcc_v3.py',
          'spice_dispatch.py','spice_engine.py','probe_digital_dcc_v2.py','spice_library.py','clocking_duty_profile_v2.py']
    paths += [ROOT/'scripts'/n for n in code]+[duty_profile.PROFILE,ROOT/'clocking_v2.json']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),profile=str(receipt.relative_to(ROOT)),
        selected_counter=variant,tg=str(tg.relative_to(ROOT)),components=[str(p.relative_to(ROOT)) for p in artifacts],
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},pdk_files=pdk_files,simulator=provenance(),
        specs=specifications(),devices=devices,
        scope='SS40 410MHz 40/60 duty joint source analog conditioner plus bias RC, native component-RC DCC/static release and three actual drivers per phase; common versus early-data prepare; ideal common wires, no 256-clock hardware warmup, full-PVT, whole-backend or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for name,text in modules.items():write(out/name,text)
    tasks=[]
    for n,spec in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();write(folder/'bench.cir',fixture(out,spec,devices[spec['variant']]))
        tasks.append(dict(id=str(n),spec=spec,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:sha(p) for p in out.glob('*.spice')},qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or provenance()!=i['simulator'] or any(sha(out/n)!=h for n,h in m['libraries'].items())
        or i['specs']!=specifications() or len(m['tasks'])!=len(i['specs'])):raise ValueError('Joint static DCC context changed')
    for n,task in enumerate(m['tasks']):
        if task['id']!=str(n) or task['spec']!=i['specs'][n] or sha(out/str(n)/'bench.cir')!=task['deck_sha256']:raise ValueError('Joint static DCC task changed')
    return m


def run(out):
    m=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior joint static DCC run')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                write(folder/'console.log',p.stdout+p.stderr);p.check_returncode()
                result=measure(folder,task['spec'],m['identity']['devices'][task['spec']['variant']],m['identity']['scope'])
            except Exception as e:error=str(e)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()});atomic(folder/'summary.json',row)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out);atomic(out/'summary.json',dict(rows=rows,qualified_phy=False))
        atomic(out/'state.json',dict(status='joint_static_dcc_complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    p.add_argument('--profile',type=Path);p.add_argument('--tg',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if a.profile is None or a.tg is None:p.error('Provide independent counter profile and TG RC family')
        print(prepare(a.artifact.resolve(),a.profile.resolve(),a.tg.resolve()),flush=True)
    else:run(a.artifact.resolve())
