#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test an exactly voltage-invariant bench current offset after traced VDD failures.

For an ideal voltage source, adding a constant external parallel current sink
changes only its branch current: I_original = I_centered + I_offset. The
nonlinear device equations and voltage constraints stay unchanged. This alters
the relative convergence norm of that bench current unknown; it requires native
waveform/flag parity, and is never silently applied to qualification jobs.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import numpy as np
import probe_restored_balanced_bank_v352 as source
import analyze_step_trace_v361 as traced
from native_binary_raw_v2 import validate
from run_native_binary_v2 import translate
from regenerated_bank_periodic_measure_v67 import crossings
from spice_dispatch import lease

ROOT=source.ROOT
VERSION='traced-ideal-supply-current-unknown-centering-v362.1'
CONTEXT='supply_current_centering_v362'
PARENT=ROOT/'build/diagnostics/restored_balanced_bank_v352/67d491be912b3621'
REFERENCE=ROOT/'build/reports/quiet_native_reference_v357/20261107T124136Z'
OBSERVER=ROOT/'build/tools/ngspice42-step-observer-v356/67d47f2680c332a2'
OFFSET_A=.001
CARD='I_BENCH_CURRENT_CENTER VDD 0 0.001'
VARIANTS=('quiet_production','quiet_observer','active_production')
sha=source.sha
atomic=source.atomic
SCOPE=('Diagnostic external ideal-supply branch-current centering at unchanged '
       '1.8V/SS40/native cells/models/tolerances. Extra fixed 1mA sink is outside '
       'the macro; chip power must exclude it. All native voltages/currents are '
       'mathematically invariant, while the bench source-current convergence '
       'norm changes. Quiet/all-vector and active original-failure parity are '
       'required; no bank/PVT/PHY admission or default-runtime replacement')


def fixture(text,variant):
    if variant not in VARIANTS:raise ValueError('Unknown controlled diagnostic')
    if text.splitlines().count('VDD VDD 0 1.8')!=1 or CARD.split()[0].lower() in text.lower():
        raise ValueError('Require unchanged explicit ideal 1.8V source and fresh bench-current name')
    if re.search(r'(?i)\bi\s*\(\s*vdd\s*\)',text):raise ValueError('Supply-current feedback breaks voltage-invariance proof')
    if any(line and line[0].upper() in ('F','H') for line in text.splitlines()):
        raise ValueError('Current-controlled sources require explicit source-current reference compensation')
    if text.splitlines().count('.tran 2p 25n 0 2p')!=1:raise ValueError('Original native transient changed')
    text=text.replace('VDD VDD 0 1.8\n','VDD VDD 0 1.8\n'+CARD+'\n',1)
    if variant.startswith('quiet_'):text=text.replace('.tran 2p 25n 0 2p','.tran 2p 200p 0 2p',1)
    return 'OpenLVDS '+VERSION+' '+variant+'\n'+text.split('\n',1)[1]


def prepare(evidence):
    proof=json.loads((evidence/'summary.json').read_text());data=(evidence/'events.log').read_bytes()
    actual=traced.analyze(data.decode())
    if (hashlib.sha256(data).hexdigest()!=proof['captured_log_sha256']
            or actual['supply_current_iteration_bottleneck_observed'] is not True
            or proof['supply_current_iteration_bottleneck_observed'] is not True
            or actual['positive_time_counts']!=proof['positive_time_counts']
            or any(sha(ROOT/n)!=h for n,h in proof['inputs'].items())):
        raise ValueError('Require frozen observed VDD-current-only Newton rejections and matching original control')
    m=source.bound(PARENT,full=False);i=m['identity']
    active=json.loads((PARENT/'1/summary.json').read_text())
    if (active['error'] is not None or active['result']['period_screen_passed'] is not False
            or active['result']['repeated_delay_screen_passed'] is not False):
        raise ValueError('Require complete known native timing failure as active numerical reference')
    bank=(PARENT/'bank.spice').read_text()
    if re.search(r'(?i)\bi\s*\(\s*vdd\s*\)',bank):raise ValueError('Macro observes supply-source branch current')
    if any(line and line[0].upper() in ('F','H') for line in bank.splitlines()):raise ValueError('Unreviewed current-controlled macro element')
    built=json.loads((OBSERVER/'summary.json').read_text());binary=ROOT/built['binary']
    if not built['ready_for_diagnostic_parity_only'] or sha(binary)!=built['binary_sha256']:
        raise ValueError('Require unchanged complete diagnostic observer')
    if binary.read_bytes()[:4]!=b'\x7fELF':binary=binary.parent/'.libs'/binary.name
    if binary.read_bytes()[:4]!=b'\x7fELF':raise ValueError('Require actual observer ELF')
    paths=[evidence/'summary.json',evidence/'events.log',REFERENCE/'summary.json',REFERENCE/'reference_prefix.raw',
        PARENT/'manifest.json',PARENT/'bank.spice',PARENT/'0/bench.cir',PARENT/'1/bench.cir',PARENT/'1/summary.json',
        PARENT/'1/bench.raw',OBSERVER/'summary.json',binary,*[ROOT/n for n in i['guards']]]
    runtime=ROOT/'build/tools/ngspice.json';runtime_files=json.loads(runtime.read_text())['files']
    paths += [runtime,*[ROOT/n for n in runtime_files]]
    paths += [Path(n) for n in {*i['pdk_files'],*i['external_files']}]
    paths += sorted({Path(module.__file__).resolve() for module in list(sys.modules.values())
        if getattr(module,'__file__',None) and Path(module.__file__).resolve().parent==ROOT/'scripts'})
    inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in sorted(set(paths))}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),evidence=str(evidence.relative_to(ROOT)),
        inputs=inputs,guards={n:h for n,h in inputs.items() if not n.endswith('.raw')},
        observer_binary=str(binary.relative_to(ROOT)),observer_binary_sha256=sha(binary),
        observations=i['observations'],source_spec=active['spec'],source_identity=i,
        external_bench_offset_a=OFFSET_A,source_current_recovery='I(VDD)_original=I(VDD)_centered+0.001A',
        max_workers=1,priority=0,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);tasks=[]
    for k,variant in enumerate(VARIANTS):
        (out/str(k)).mkdir();original=(PARENT/('1' if variant=='active_production' else '0')/'bench.cir').read_text()
        (out/str(k)/'bench.cir').write_text(fixture(original,variant))
        tasks.append(dict(id=str(k),variant=variant,deck_sha256=sha(out/str(k)/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['scope']!=SCOPE
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['external_bench_offset_a']!=OFFSET_A or (i['max_workers'],i['priority'])!=(1,0)
            or i['guards']!={n:h for n,h in i['inputs'].items() if not n.endswith('.raw')}
            or any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items())):
        raise ValueError('Controlled current-centering evidence/circuit/code/runtime changed')
    tasks=[]
    for k,variant in enumerate(VARIANTS):
        original=(PARENT/('1' if variant=='active_production' else '0')/'bench.cir').read_text()
        if (out/str(k)/'bench.cir').read_text()!=fixture(original,variant):raise ValueError('Original model/stimulus altered beyond explicit bench transformation')
        tasks.append(dict(id=str(k),variant=variant,deck_sha256=sha(out/str(k)/'bench.cir')))
    if tasks!=m['tasks']:raise ValueError('Required controlled prefix/observer/active sequence changed')
    return m


def wave_difference(old_names,old,names,new):
    if set(names)!=set(old_names):raise ValueError('Missing original native voltage vectors')
    ot=old[:,old_names.index('time')];t=new[:,names.index('time')];worst=0.;node=None
    for k,n in enumerate(old_names):
        if n=='time':continue
        err=float(np.max(np.abs(np.interp(ot,t,new[:,names.index(n)])-old[:,k])))
        if err>worst:worst,node=err,n
    return dict(maximum_all_vector_error_v=worst,worst_vector=node,original_samples=len(old),vectors=len(names)-1)


def quiet_measure(folder):
    r=json.loads((REFERENCE/'summary.json').read_text())
    on,old=validate(REFERENCE/'reference_prefix.raw',set(),r['last_copied_ps']*1e-12)
    names,new=validate(folder/'bench.raw',set(on),200e-12);t=new[:,names.index('time')];dt=np.diff(t)*1e12
    diff=wave_difference(on,old,names,new)
    return dict(reference_difference=diff,records=len(new),minimum_step_ps=float(dt.min()),
        mean_step_ps=float(dt.mean()),steps_below_0_01ps=int(np.count_nonzero(dt<.01)),
        quiet_parity_passed=bool(diff['maximum_all_vector_error_v']<=1e-6),
        fewer_than_half_original_steps=bool(len(new)<len(old)/2),qualified_phy=False)


def active_measure(folder,i):
    oldrow=json.loads((PARENT/'1/summary.json').read_text());original=oldrow['result']
    measured=source.measure(folder,i['source_identity'],i['source_spec'])
    old_names,old=validate(PARENT/'1/bench.raw',set(),25e-9);names,new=validate(folder/'bench.raw',set(old_names),25e-9)
    diff=wave_difference(old_names,old,names,new);errors=[]
    ot=old[:,old_names.index('time')]*1e12;t=new[:,names.index('time')]*1e12
    for n in ('v(in)','v(xd.selected)','v(xd.pre_out)','v(xd.fine_node)','v(out)'):
        for up in (True,False):
            a=crossings(ot,old[:,old_names.index(n)],.9,up);b=crossings(t,new[:,names.index(n)],.9,up)
            if len(a)!=8 or len(b)!=8:raise ValueError('Active parity must retain all eight native stage events')
            errors.extend(abs(x-y) for x,y in zip(a,b))
    gates={k:v for k,v in original.items() if k.endswith('_passed') or k=='all_input_output_pulses_present'}
    flags_same=all(measured[k]==v for k,v in gates.items())
    voltage_classifications_same=[d['passed'] for d in original['terminal_stress']]==[d['passed'] for d in measured['terminal_stress']]
    return dict(reference_difference=diff,maximum_crossing_error_ps=max(errors),
        all_original_gate_classifications_preserved=flags_same,all_original_native_voltage_classifications_preserved=voltage_classifications_same,
        parity_passed=bool(diff['maximum_all_vector_error_v']<=.002 and max(errors)<=.25 and flags_same and voltage_classifications_same),
        measured=measured,original_real_history_failure_retained=bool(measured['period_screen_passed'] is False and measured['repeated_delay_screen_passed'] is False),
        qualified_phy=False)


def allowed(variant,rows):
    if variant=='quiet_production':return not rows
    if not rows or rows[0]['result'] is None or rows[0]['result'].get('quiet_parity_passed') is not True:return False
    if variant=='quiet_observer':return True
    if variant=='active_production':
        return bool(len(rows)==2 and rows[0]['result'].get('fewer_than_half_original_steps') is True
            and rows[1]['result'] is not None and rows[1]['result'].get('quiet_parity_passed') is True)
    raise ValueError('Unknown controlled diagnostic')


def run(out):
    m=bound(out);i=m['identity'];rows=[]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous/partial numerical diagnostic')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        for task in m['tasks']:
            folder=out/task['id'];variant=task['variant'];result=error=None
            guarded=not allowed(variant,rows)
            if not guarded:
                try:
                    with lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                        bound(out,full=False);start=time.monotonic()
                        if variant=='quiet_observer':
                            text,names=translate((folder/'bench.cir').read_text());(folder/'bench.ngspice.cir').write_text(text)
                            import os
                            env=dict(os.environ,OPENLVDS_STEP_TRACE='1')
                            with (folder/'console.log').open('w') as log:
                                p=subprocess.run([str(ROOT/'build/tools/ngspice-runtime/ld-linux-x86-64.so.2'),
                                    '--library-path',str(ROOT/'build/tools/ngspice-runtime'),str(ROOT/i['observer_binary']),'-n','-b',
                                    '-r',str(folder/'bench.raw'),'-o',str(folder/'ngspice.log'),str(folder/'bench.ngspice.cir')],
                                    cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT)
                        else:
                            p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                            (folder/'console.log').write_text(p.stdout+p.stderr)
                    p.check_returncode()
                    result=active_measure(folder,i) if variant=='active_production' else quiet_measure(folder)
                    result['elapsed_seconds_including_startup']=time.monotonic()-start
                    if variant=='quiet_observer':result['trace']=traced.analyze((folder/'ngspice.log').read_text())
                except Exception as exc:error=str(exc)
            row=dict(task=task,result=result,error=error,guarded=guarded,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);rows.append(row)
        bound(out)
        atomic(out/'summary.json',dict(rows=rows,scope=SCOPE,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=3,errors=sum(r['error'] is not None for r in rows),guarded=sum(r['guarded'] for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=('prepare','run','campaign'));parser.add_argument('artifact',type=Path)
    args=parser.parse_args();out=prepare(args.artifact.resolve()) if args.action in ('prepare','campaign') else args.artifact.resolve()
    print(out,flush=True)
    if args.action in ('run','campaign'):print(run(out),flush=True)
