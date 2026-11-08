#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Evidence-gated P40/N32 recovery intervention with DC-preserving numerical origin."""
import argparse,fcntl,hashlib,json,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import numpy as np
import p40n32_pre_distributed_bank_300 as architecture
import probe_ramped_center_300 as numerical_trial
import probe_medium_pre_distributed_300 as predecessor
import native_bank_mim4_300_v1 as prior
import clocking_profile_300 as policy
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from run_native_binary_v2 import translate
from spice_dispatch import lease
ROOT=policy.ROOT
VERSION='p40n32-pre-recovery-ramped-native-300-v1'
CONTEXT='p40n32_pre_distributed_pilot_300_v1'
VARIANT='p40n32_pre_c1_c1'
PREVIOUS=ROOT/'build/diagnostics/medium_pre_distributed_pilot_300_v1/42cbec6c352fbe01'
RECOVERY=ROOT/'build/diagnostics/distributed_voltage_recovery_300_v2/58bb46bef11400bf'
RAMP=ROOT/'build/diagnostics/ramped_current_center_300_v1/4dd1b69e62d555ef'
REPLAYS=tuple(ROOT/'build/diagnostics/medium_pre_distributed_native_replay_300'/n
              for n in ('3d82eff834a0cc6a','b27c1c08c4db9ff7','f145131864472508'))
PARENT=prior.PARENTS['restored'][1]
sha=prior.sha
atomic=prior.atomic


def evidence(full=True):
    inputs=predecessor.evidence(full=full)
    manifest=predecessor.bound(PREVIOUS,full=full)
    def retain(path):inputs[str(path.relative_to(ROOT))]=sha(path)
    def merge(values):
        for name,digest in values.items():
            if name in inputs and inputs[name]!=digest:raise ValueError('Conflicting recovery evidence')
            inputs[name]=digest
    retain(PREVIOUS/'manifest.json')
    for k in (0,1,2):
        folder=PREVIOUS/str(k);row=json.loads((folder/'summary.json').read_text())
        if (row['error'] is not None or row['task']!=manifest['tasks'][k]
                or not {'bench.raw','bench.cir','ngspice.log'}<=set(row['files'])):
            raise ValueError('Require complete exact predecessor points')
        for name,digest in row['files'].items():
            path=folder/name
            if (full or path.suffix!='.raw') and sha(path)!=digest:raise ValueError('Native predecessor changed')
            merge({str(path.relative_to(ROOT)):digest})
        retain(folder/'summary.json')
        if k==0 and row['result']['zero_code_quarter_passed'] is not True:
            raise ValueError('Require measured single-P40 zero-code repair')
        if k==1 and row['result']['repeated_delay_screen_passed'] is not False:
            raise ValueError('Require measured single-P40 history failure')
    for k,folder in enumerate(REPLAYS):
        m=json.loads((folder/'manifest.json').read_text());i=m['identity']
        report=json.loads((folder/'summary.json').read_text())
        if (folder.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
                or json.loads((folder/'state.json').read_text())!=dict(status='complete',cases=1,qualified_phy=False)
                or report['all_selected_native_metrics_reproduced'] is not True
                or [r['task']['id'] for r in report['rows']]!=[str(k)]
                or not all(report['rows'][0][key] is True for key in
                    ('independent_timing_reproduced','independent_terminal_envelope_reproduced',
                     'independent_control_and_gate_settling_reproduced'))):
            raise ValueError('Require independent exact predecessor replay')
        merge(i['inputs'])
        for name in ('manifest.json','summary.json','state.json'):retain(folder/name)
    m=json.loads((RECOVERY/'manifest.json').read_text());i=m['identity']
    report=json.loads((RECOVERY/'summary.json').read_text())
    if (RECOVERY.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or json.loads((RECOVERY/'state.json').read_text())!=dict(status='complete',cases=2,qualified_phy=False)
            or report['all_selected_outer_delays_reproduced'] is not True
            or [r['task']['id'] for r in report['rows']]!=['0','1']):
        raise ValueError('Require exact topology-resolved recovery evidence')
    recovery=report['rows'][1]['voltage_recovery']
    pre=recovery['pre']['nodes']['XD:pre_out']['before_input_falling_voltage_v']
    fine=recovery['fine']['nodes']['XD:fine_node']['before_input_rising_voltage_v']
    if pre[-1]-pre[0]<=.1 or fine[0]-fine[-1]<=.05:
        raise ValueError('Require observed low/high recovery differences before changing pull-down')
    merge(i['inputs'])
    for name in ('manifest.json','summary.json','state.json'):retain(RECOVERY/name)
    m=numerical_trial.bound(RAMP);merge(m['identity']['inputs'])
    report=json.loads((RAMP/'summary.json').read_text());row=report['rows'][0]
    if (json.loads((RAMP/'state.json').read_text())!=dict(status='complete',cases_executed=1,errors=0,qualified_phy=False)
            or row['error'] is not None or row['task']!=m['tasks'][0]
            or not {'bench.raw','bench.cir','ngspice.log'}<=set(row['files'])
            or row['parity']['passed'] is not True
            or row['parity']['maximum_dc_voltage_error_v']!=0
            or row['parity']['original_failed_history_preserved'] is not True):
        raise ValueError('Require admitted exact DC-preserving numerical trial')
    for name in ('manifest.json','summary.json','state.json'):retain(RAMP/name)
    for name,digest in row['files'].items():
        path=RAMP/'0'/name
        if (full or path.suffix!='.raw') and sha(path)!=digest:raise ValueError('Numerical trial changed')
        merge({str(path.relative_to(ROOT)):digest})
    retain(RAMP/'0/summary.json')
    if any(sha(ROOT/n)!=h for n,h in inputs.items() if full or Path(n).suffix!='.raw'):
        raise ValueError('Captured recovery/numerical evidence changed')
    return inputs


def specifications():
    # Check the zero-code bottleneck first; retain both numerical origins at fine 60.
    old=predecessor.specifications()
    tasks=deepcopy(old)
    for task in tasks:
        task['variant']=VARIANT
        task['spec'].update(architecture='p40n32_pre_split_fine_recovery_control',
                            pre_driver='two_parallel_qualified_p20n16')
    return tasks


def fixture(out,identity,task):
    variant=task['variant'];source_identity=deepcopy(identity['source_identity'])
    source_identity['observations']=identity['observations'][variant]
    i=dict(kind='restored',source_identity=source_identity,macro_top=identity['revisions'][variant]['macro_top'])
    text=prior.fixture(out/variant,i,task['spec'],task['centered'])
    if task['centered']:
        if text.count(prior.numerical.CARD)!=1:raise ValueError('Require exact original bench-current card')
        text=text.replace(prior.numerical.CARD,numerical_trial.CARD,1)
    elif 'I_BENCH_CURRENT_CENTER' in text:raise ValueError('Unshifted reference changed')
    translate(text)
    return text


def prepare():
    evidence_inputs=evidence();producer=prior.PARENTS['restored'][0];m=producer.bound(PARENT,full=False)
    # Full retained geometry/native/Schur proof before new scientific capture.
    cell,material_paths,material_identity=architecture.parent.parent.mim.materials()
    original=(PARENT/'bank.spice').read_text();i=m['identity']
    models={VARIANT:architecture.transform(original,i['observations'])}
    paths=[PARENT/'manifest.json',PARENT/'bank.spice',ROOT/'clocking_300mhz.json',*material_paths]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**evidence_inputs,**material_identity['external_files'],**i['guards'],**i['pdk_files'],**i['external_files'],**{str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in paths}}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),source_identity=i,inputs=inputs,
        guards={n:h for n,h in inputs.items() if Path(n).suffix!='.raw'},specifications=specifications(),
        observations={v:data[1] for v,data in models.items()},revisions={v:data[2] for v,data in models.items()},
        max_workers=1,priority=1,profile_sha256=sha(ROOT/'clocking_300mhz.json'),
        bench_current_offset_a=.001,bench_current_dc_a=0,bench_current_card=numerical_trial.CARD,power_excludes_external_bench_load=True,
        scope='Qualified components and native SS40/310MHz controls only; new common routing, actual loading, PVT, DLL and PHY remain unqualified')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);libraries={}
    for v,data in models.items():
        folder=out/v;folder.mkdir();(folder/'bank.spice').write_text(data[0]);libraries[v]=sha(folder/'bank.spice')
    tasks=[]
    for k,task in enumerate(specifications()):
        folder=out/str(k);folder.mkdir();(folder/'bench.cir').write_text(fixture(out,identity,task))
        tasks.append(dict(id=str(k),**task,deck_sha256=sha(folder/'bench.cir')))
    atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries=libraries,qualified_phy=False));bound(out)
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['parent']!=str(PARENT.relative_to(ROOT)) or i['specifications']!=specifications()
            or i['guards']!={n:h for n,h in i['inputs'].items() if Path(n).suffix!='.raw'}
            or (i['max_workers'],i['priority'])!=(1,1) or i['profile_sha256']!=sha(ROOT/'clocking_300mhz.json')
            or i['bench_current_dc_a']!=0 or i['bench_current_card']!=numerical_trial.CARD
            or m['qualified_phy'] is not False or i['bench_current_offset_a']!=.001 or i['power_excludes_external_bench_load'] is not True):
        raise ValueError('Distributed-fine experiment identity changed')
    original=prior.PARENTS['restored'][0].bound(PARENT,full=False)['identity']
    if original!=i['source_identity']:raise ValueError('Original source identity changed')
    for n,h in (i['inputs'] if full else i['guards']).items():
        if sha(ROOT/n)!=h:raise ValueError('Captured distributed-fine input changed: '+n)
    text=(PARENT/'bank.spice').read_text()
    if set(m['libraries'])!={VARIANT}:raise ValueError('One-factor controls missing')
    for variant in (VARIANT,):
        native,observations,revision=architecture.transform(text,original['observations'])
        path=out/variant/'bank.spice'
        if path.read_text()!=native or sha(path)!=m['libraries'][variant] or observations!=i['observations'][variant] or revision!=i['revisions'][variant]:
            raise ValueError('Native topology, complete observations or component definitions changed')
    expected=[]
    for k,t in enumerate(specifications()):
        path=out/str(k)/'bench.cir'
        if path.read_text()!=fixture(out,i,t):raise ValueError('Captured native stimulus changed')
        expected.append(dict(id=str(k),**t,deck_sha256=sha(path)))
    if expected!=m['tasks']:raise ValueError('Distributed-fine scientific coverage changed')
    return m


def parity(out,rows,a,b):
    if any(rows[k]['error'] is not None for k in (a,b)):return dict(passed=False,reason='Native control incomplete')
    names,x=validate(out/str(a)/'bench.raw',set(),40e-9);other,y=validate(out/str(b)/'bench.raw',set(names),40e-9)
    diff=prior.numerical.wave_difference(names,x,other,y)
    reverse=prior.numerical.wave_difference(other,y,names,x)
    if x[0,0]!=0 or y[0,0]!=0:raise ValueError('Missing DC sample')
    dc=max(abs(float(x[0,names.index(n)])-float(y[0,other.index(n)])) for n in names if n.startswith('v('))
    errors=[]
    for node in ('v(in)','v(out)'):
        for up in (True,False):
            first=crossings(x[:,0]*1e12,x[:,names.index(node)],.9,up);second=crossings(y[:,0]*1e12,y[:,other.index(node)],.9,up)
            if len(first)!=8 or len(second)!=8:return dict(passed=False,reason='Missing active events')
            errors.extend(abs(v-w) for v,w in zip(first,second))
    flags=all(rows[a]['result'][k]==rows[b]['result'][k] for k in (*prior.KEYS,'current_downstream_250ps_slew_domain_passed'))
    for category in ('terminal_stress','controls','programming_gates'):
        flags=flags and [v['passed'] for v in rows[a]['result'][category]]==[v['passed'] for v in rows[b]['result'][category]]
    return dict(passed=bool(max(diff['maximum_all_vector_error_v'],reverse['maximum_all_vector_error_v'])<=.002 and max(errors)<=.25 and flags and dc<=1e-9),
        reference_difference=diff,reverse_difference=reverse,maximum_dc_voltage_error_v=dc,maximum_crossing_error_ps=max(errors),all_gate_classifications_preserved=flags)


def run(out):
    m=bound(out);i=m['identity'];producer=prior.PARENTS['restored'][0]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];error=result=None
            try:
                with lease(ROOT,priority=1,label=CONTEXT+'_'+task['id']):
                    bound(out,full=False)
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
                source=deepcopy(i['source_identity']);source['observations']=i['observations'][task['variant']]
                result=prior.contract(producer.measure(folder,source,task['spec']),task['spec'])
            except Exception as exc:error=str(exc)
            row=dict(task=task,result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=1) as pool:rows=list(pool.map(execute,m['tasks']))
        check=parity(out,rows,4,1)
        complete=all(r['result'] is not None and all(len(r['result']['edge_delays_ps'][e])==8
                     for e in ('rise','fall')) for r in rows)
        overlap={edge:min(v for k in (1,2) for v in rows[k]['result']['edge_delays_ps'][edge])
                 -max(rows[3]['result']['edge_delays_ps'][edge]) for edge in ('rise','fall')} if complete else None
        passed=bool(check['passed'] and overlap and all(v>0 for v in overlap.values())
                    and all(r['result']['current_clock_interface_screen_passed'] for r in rows))
        checks={VARIANT:check}
        screens={VARIANT:dict(component_pilot_passed=passed,conservative_overlap_ps=overlap,qualified_phy=False)}
        bound(out);atomic(out/'summary.json',dict(rows=rows,active_numerical_controls=checks,
            candidate_screens=screens,physical_area_and_full_qualification_pending=True,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=5,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:print(run(a.artifact.resolve()),flush=True)
