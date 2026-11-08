#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Evidence-gated strength/count/placement controls for a two-stage fine bank."""
import argparse,fcntl,hashlib,json,subprocess,sys
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
import numpy as np
import distributed_fine_bank_300 as architecture
import native_bank_mim4_300_v1 as prior
import clocking_profile_300 as policy
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings
from run_native_binary_v2 import translate
from spice_dispatch import lease
ROOT=policy.ROOT
VERSION='strong-pre-and-two-node-distributed-fine-native-300-v1'
CONTEXT='distributed_fine_pilot_300_v1'
PARENT=prior.PARENTS['restored'][1]
MIM=ROOT/'build/diagnostics/native_bank_mim4_300_v1/a8105c49e52731af'
REPLAY=ROOT/'build/diagnostics/bank_native_replay_300_v2/0c6d13870c127e06'
HISTORY=ROOT/'build/diagnostics/bank_stage_history_300_v2/27d64d057235a80a'
sha=prior.sha
atomic=prior.atomic


def evidence(full=True):
    inputs={};reports=[]
    for folder,version in ((REPLAY,'independent-fresh-bank-native-metrology-300-v2'),(HISTORY,'complete-restored-bank-stage-history-300-v2')):
        m=json.loads((folder/'manifest.json').read_text());i=m['identity'];r=json.loads((folder/'summary.json').read_text())
        if (i['version']!=version or folder.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
                or json.loads((folder/'state.json').read_text())!=dict(status='complete',cases=1,qualified_phy=False)
                or len(r['rows'])!=1 or r['rows'][0]['case']!=str((MIM/'1').relative_to(ROOT))):
            raise ValueError('Require complete exact independent MIM timing/recovery evidence')
        for name,digest in i['inputs'].items():
            if name in inputs and inputs[name]!=digest:raise ValueError('Conflicting independent failure evidence')
            inputs[name]=digest
        inputs.update({str((folder/n).relative_to(ROOT)):sha(folder/n) for n in ('manifest.json','summary.json','state.json')});reports.append(r)
    if (reports[0]['all_selected_native_metrics_reproduced'] is not True
            or reports[1]['original_outer_delays_reproduced'] is not True):raise ValueError('MIM failure did not independently reproduce')
    row=reports[1]['rows'][0];nodes=row['recovery']['nodes'];fine=nodes['XD:fine_node']
    caps=[v for n,v in nodes.items() if n!='XD:fine_node']
    stage=row['history']['rise']['stages']['XD:pre_out -> XD:fine_node']
    if (stage['span_ps']<=20 or fine['before_pre_out_rise_voltage_v'][0]-fine['before_pre_out_rise_voltage_v'][-1]<=.1
            or not caps or any(v['before_pre_out_rise_voltage_v'][0]-v['before_pre_out_rise_voltage_v'][-1]<=.2 for v in caps)):
        raise ValueError('Require observed fine-stage incomplete recovery before distributing capacitance')
    if any(sha(ROOT/n)!=h for n,h in inputs.items() if full or Path(n).suffix!='.raw'):
        raise ValueError('Observed MIM failure/recovery inputs changed')
    return inputs


def specifications():
    base=prior.specifications('restored');fine=base[1][0]
    tasks=[]
    for variant in architecture.VARIANTS:
        for centered in (False,True):tasks.append(dict(variant=variant,spec=dict(fine),centered=centered))
    for candidate in ('split_c1_c1','split_c2_c2'):
        for k in (2,3,4):
            s,_=base[k];tasks.append(dict(variant=candidate,spec=dict(s),centered=True))
    for task in tasks:
        variant=task['variant'];copies,split=architecture.VARIANTS[variant]
        task['spec'].update(architecture='strong_pre_distributed_fine_control',pre_driver='two_parallel_p40n16',
            fine_copies=copies,fine_copies_pre_node=copies//2 if split else 0,fine_copies_fine_node=copies//2 if split else copies)
    return tasks


def fixture(out,identity,task):
    variant=task['variant'];source_identity=deepcopy(identity['source_identity'])
    source_identity['observations']=identity['observations'][variant]
    i=dict(kind='restored',source_identity=source_identity,macro_top=identity['revisions'][variant]['macro_top'])
    text=prior.fixture(out/variant,i,task['spec'],task['centered']);translate(text)
    return text


def prepare():
    evidence_inputs=evidence();producer=prior.PARENTS['restored'][0];m=producer.bound(PARENT,full=False)
    # Full retained geometry/native/Schur proof before new scientific capture.
    cell,material_paths,material_identity=architecture.mim.materials()
    original=(PARENT/'bank.spice').read_text();i=m['identity']
    models={v:architecture.transform(original,i['observations'],v) for v in architecture.VARIANTS}
    paths=[PARENT/'manifest.json',PARENT/'bank.spice',ROOT/'clocking_300mhz.json',*material_paths]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={**evidence_inputs,**material_identity['external_files'],**i['guards'],**i['pdk_files'],**i['external_files'],**{str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in paths}}
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),source_identity=i,inputs=inputs,
        guards={n:h for n,h in inputs.items() if Path(n).suffix!='.raw'},specifications=specifications(),
        observations={v:data[1] for v,data in models.items()},revisions={v:data[2] for v,data in models.items()},
        max_workers=2,priority=1,profile_sha256=sha(ROOT/'clocking_300mhz.json'),
        bench_current_offset_a=.001,power_excludes_external_bench_load=True,
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
            or (i['max_workers'],i['priority'])!=(2,1) or i['profile_sha256']!=sha(ROOT/'clocking_300mhz.json')
            or m['qualified_phy'] is not False or i['bench_current_offset_a']!=.001 or i['power_excludes_external_bench_load'] is not True):
        raise ValueError('Distributed-fine experiment identity changed')
    original=prior.PARENTS['restored'][0].bound(PARENT,full=False)['identity']
    if original!=i['source_identity']:raise ValueError('Original source identity changed')
    for n,h in (i['inputs'] if full else i['guards']).items():
        if sha(ROOT/n)!=h:raise ValueError('Captured distributed-fine input changed: '+n)
    text=(PARENT/'bank.spice').read_text()
    if set(m['libraries'])!=set(architecture.VARIANTS):raise ValueError('One-factor controls missing')
    for variant in architecture.VARIANTS:
        native,observations,revision=architecture.transform(text,original['observations'],variant)
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
    diff=prior.numerical.wave_difference(names,x,other,y);errors=[]
    for node in ('v(in)','v(out)'):
        for up in (True,False):
            first=crossings(x[:,0]*1e12,x[:,names.index(node)],.9,up);second=crossings(y[:,0]*1e12,y[:,other.index(node)],.9,up)
            if len(first)!=8 or len(second)!=8:return dict(passed=False,reason='Missing active events')
            errors.extend(abs(v-w) for v,w in zip(first,second))
    flags=all(rows[a]['result'][k]==rows[b]['result'][k] for k in (*prior.KEYS,'current_downstream_250ps_slew_domain_passed'))
    for category in ('terminal_stress','controls','programming_gates'):
        flags=flags and [v['passed'] for v in rows[a]['result'][category]]==[v['passed'] for v in rows[b]['result'][category]]
    return dict(passed=bool(diff['maximum_all_vector_error_v']<=.002 and max(errors)<=.25 and flags),
        reference_difference=diff,maximum_crossing_error_ps=max(errors),all_gate_classifications_preserved=flags)


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
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        checks={v:parity(out,rows,2*k,2*k+1) for k,v in enumerate(architecture.VARIANTS)}
        screens={}
        for candidate,indices in (('split_c1_c1',(5,8,9,10)),('split_c2_c2',(7,11,12,13))):
            fine60,zero,fine40,coarse=indices;relevant=[rows[k] for k in indices]
            complete=all(r['result'] is not None and all(len(r['result']['edge_delays_ps'][e])==8 for e in ('rise','fall')) for r in relevant)
            overlap={edge:min(v for k in (fine60,fine40) for v in rows[k]['result']['edge_delays_ps'][edge])-max(rows[coarse]['result']['edge_delays_ps'][edge]) for edge in ('rise','fall')} if complete else None
            passed=bool(checks[candidate]['passed'] and overlap and all(v>0 for v in overlap.values()) and all(r['result']['current_clock_interface_screen_passed'] for r in relevant))
            screens[candidate]=dict(component_pilot_passed=passed,conservative_overlap_ps=overlap,qualified_phy=False)
        bound(out);atomic(out/'summary.json',dict(rows=rows,active_numerical_controls=checks,
            candidate_screens=screens,physical_area_and_full_qualification_pending=True,qualified_phy=False))
        atomic(out/'state.json',dict(status='complete',cases=14,errors=sum(r['error'] is not None for r in rows),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('prepare','run'));p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='prepare':print(prepare(),flush=True)
    else:print(run(a.artifact.resolve()),flush=True)
