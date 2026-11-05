#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Screen a bank containing the measured native fine-cell component RC."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import itertools
import numpy as np
from native_binary_raw_v2 import validate
from dcdl_tg_tree_v5 import control_targets
import probe_regenerated_bank_joint_zero_v61 as zero
import verify_repair_prototypes_v71 as proof
import probe_regenerated_bank_v56 as component
import moscap_component_rc_bank_v90 as circuit
import exact_rc_candidate as exact
from regenerated_bank_periodic_measure_v67 import crossings


ROOT=zero.ROOT
baseline=zero.baseline
sha=zero.sha
VERSION='measured-gate-cap-fine-cell-component-rc-bank-feasibility-v91.1'
CONTEXT='moscap_component_rc_bank_v91'
PROFILES=('w084',)
SCOPE='Measured 0.84 um native fine-cell local RC and junctions at selected before final inverter; original other component RC retained, new common routing unextracted; no electrical or PHY admission'


def specifications():return [dict(zero.spec(),profile=p,coarse=c,fine=f) for p in PROFILES for c,f in ((0,0),(0,31),(1,0))]


def inherited(evidence,parent):
    binding=proof.bound(evidence);receipt=json.loads((evidence/'summary.json').read_text())
    larger=next(r for r in receipt['comparison'] if r['profile']=='buf4')
    if binding['kind']!='buffered' or larger['zero_code_fast_quarter_headroom_ps']>=0:
        raise ValueError('Require complete independent output-buffer latency failure')
    m=component.bound(parent)
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=1,errors=0,qualified_phy=False):
        raise ValueError('Require complete original component candidate')
    row=json.loads((parent/'0/summary.json').read_text())
    if row['error'] is not None or not row['result']['component_rc_zero_screen_passed'] or any(sha(parent/'0'/n)!=h for n,h in row['files'].items()):
        raise ValueError('Original component feasibility changed')
    return binding,m,receipt


def fixture(out,i,s):
    text=zero.fixture(out,dict(i,spec=s,top=circuit.name(s['profile'])));text=text.replace(str(out/'bank.spice'),str(out/('bank_'+s['profile']+'.spice')),1);title='OpenLVDS '+zero.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original routed zero fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def prepare(evidence,parent,fine_parent):
    binding,m,receipt=inherited(evidence,parent);old=m['identity'];text=(parent/'bank.spice').read_text()
    fine_identity,fine_report,fine_rc=circuit.checked_cell(fine_parent)
    if fine_report['profile']!='w084' or exact.math_runtime()!=fine_identity['math_runtime']:
        raise ValueError('Require measured 0.84 um component RC and its unchanged numeric runtime')
    banks={p:circuit.transform(text,p,fine_rc) for p in PROFILES}
    ports=circuit.source.native.definitions(banks['w084'])[circuit.name('w084')][0]
    observations={}
    for profile,bank in banks.items():
        observations[profile]=circuit.observations(bank,profile,old['observations'])
    paths=[evidence/'manifest.json',evidence/'summary.json',*[ROOT/n for n in binding['inputs']],
           parent/'manifest.json',parent/'bank.spice',parent/'state.json',parent/'0/summary.json',*[ROOT/n for n in old['inputs']]]
    paths += [parent/'0'/n for n in json.loads((parent/'0/summary.json').read_text())['files']]
    paths += [fine_parent/'manifest.json',fine_parent/'summary.json',*[fine_parent/n for n in fine_report['files']],*[ROOT/n for n in fine_report['original_extracted_files']],*[ROOT/n for n in fine_identity['inputs']]]
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,evidence=str(evidence.relative_to(ROOT)),parent=str(parent.relative_to(ROOT)),
        fine_parent=str(fine_parent.relative_to(ROOT)),fine_math_runtime=fine_identity['math_runtime'],fine_external_files=fine_identity['external_files'],
        specs=specifications(),ports=ports,model=old['model'],observations=observations,
        pdk_files=old['pdk_files'],external_files=old['external_files'],simulator=old['simulator'],
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},max_workers=2,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for p,bank in banks.items():zero.baseline.write(out/('bank_'+p+'.spice'),bank)
    tasks=[]
    for n,s in enumerate(identity['specs']):
        folder=out/str(n);folder.mkdir();zero.baseline.write(folder/'bench.cir',fixture(out,dict(identity,observations=observations[s['profile']]),s))
        tasks.append(dict(id=str(n),spec=s,deck_sha256=sha(folder/'bench.cir')))
    zero.baseline.atomic(out/'manifest.json',dict(identity=identity,tasks=tasks,libraries={p.name:sha(p) for p in out.glob('bank_*.spice')},qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['specs']!=specifications() or i['max_workers']!=2 or zero.engine()!='ngspice' or zero.provenance()!=i['simulator']
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files'],**i['fine_external_files']}.items())
            or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=3):
        raise ValueError('Gate-cap fine component context changed')
    fine_identity,fine_report,fine_rc=circuit.checked_cell(ROOT/i['fine_parent'])
    if exact.math_runtime()!=i['fine_math_runtime'] or fine_identity['external_files']!=i['fine_external_files'] or fine_report['profile']!='w084':
        raise ValueError('Measured fine-cell RC runtime/profile changed')
    original=(ROOT/i['parent']/'bank.spice').read_text()
    original_observations=json.loads((ROOT/i['parent']/'manifest.json').read_text())['identity']['observations']
    for profile in PROFILES:
        bank=(out/('bank_'+profile+'.spice')).read_text()
        if bank!=circuit.transform(original,profile,fine_rc):
            raise ValueError('Gate-cap fine component model cannot regenerate')
        devices=circuit.source.native.mapped_mos(bank,circuit.name(profile),{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in i['ports']},'XD')
        if devices!=i['observations'][profile]['devices'] or len(devices)!=1013:raise ValueError('Gate-cap native terminals changed')
        expected_gates=circuit.observations(bank,profile,original_observations)['programming_gates']
        if (circuit.source.native.definitions(bank)[circuit.name(profile)][0]!=i['ports']
                or i['observations'][profile]['controls']!=original_observations['controls'] or i['observations'][profile]['programming_gates']!=expected_gates):
            raise ValueError('Gate-cap native interface or control observations changed')
    for n,t in enumerate(m['tasks']):
        deck=out/str(n)/'bench.cir';view=dict(i,observations=i['observations'][t['spec']['profile']])
        if t['id']!=str(n) or t['spec']!=i['specs'][n] or t['deck_sha256']!=sha(deck) or deck.read_text()!=fixture(out,view,t['spec']):
            raise ValueError('Gate-cap native fixture changed')
    return m


def measure(folder,i,s):
    result=measure_trace(folder,dict(i,spec=s,observations=i['observations'][s['profile']]))
    names,w=validate(folder/'bench.raw',{'v(out)'},20e-9);time=w[:,names.index('time')]*1e12;out=w[:,names.index('v(out)')]
    slews={}
    for up,edge in ((True,'rise'),(False,'fall')):
        a=crossings(time,out,.18,up);b=crossings(time,out,1.62,up)
        ordered=len(a)==len(b)==2 and all(x<y if up else y<x for x,y in zip(a,b))
        slews[edge]=[abs(y-x) for x,y in zip(a,b)] if ordered else []
    maximum=max((v for vs in slews.values() for v in vs),default=None)
    result.update(scope=SCOPE,whole_bank_rc_retained=False,original_other_component_rc_retained=True,new_fine_cell_geometry_qualified=True,fine_cell_local_rc_qualified=True,new_common_routing_qualified=False,
        output_slews_10_90_ps=slews,maximum_output_slew_ps=maximum,
        output_slew_domain_passed=bool(all(len(vs)==2 for vs in slews.values()) and maximum is not None and maximum<=250))
    return result


def comparisons(rows):
    result=[]
    for profile in PROFILES:
        selected=[r for r in rows if r['spec']['profile']==profile]
        if len(selected)!=3 or any(r['error'] is not None for r in selected):continue
        by={(r['spec']['coarse'],r['spec']['fine']):r['result'] for r in selected}
        overlaps={edge+'_ps':by[0,31]['samples'][1][edge+'_delay_ps']-by[1,0]['samples'][1][edge+'_delay_ps'] for edge in ('rise','fall')}
        headroom=1e6/410/4-max(v for sample in by[0,0]['samples'] for v in sample.values())
        native=all(r['result']['static_native_screen_passed'] and r['result']['output_slew_domain_passed'] for r in selected)
        result.append(dict(profile=profile,coarse_overlap=overlaps,zero_code_fast_quarter_headroom_ps=headroom,
            gate_cap_component_feasibility_passed=bool(native and headroom>0 and all(v>0 for v in overlaps.values())),
            whole_bank_rc_retained=False,electrical_qualification_passed=False,qualified_phy=False))
    return result


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial sparse campaign')
        zero.baseline.atomic(out/'state.json',dict(status='running',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];result=error=wall=None
            try:
                with zero.lease(ROOT,priority=0,label=CONTEXT+'_'+task['id']):
                    bound(out);start=time.monotonic()
                    p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                    wall=time.monotonic()-start
                zero.baseline.write(folder/'console.log',p.stdout+p.stderr);p.check_returncode();result=measure(folder,i,task['spec'])
            except Exception as e:error=str(e)
            row=dict(task=task,spec=task['spec'],result=result,error=error,solver_wall_seconds=wall,
                files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
            zero.baseline.atomic(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=i['max_workers']) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        comparison=None
        if all(r['error'] is None for r in rows):comparison=comparisons(rows)
        zero.baseline.atomic(out/'summary.json',dict(rows=rows,comparison=comparison,qualified_phy=False,scope=SCOPE))
        zero.baseline.atomic(out/'state.json',dict(status='complete',cases=len(rows),errors=sum(r['error'] is not None for r in rows),qualified_phy=False));return out


def measure_trace(folder,i):
    o=i['observations'];s=i['spec'];targets=control_targets(s['coarse'],s['fine'])
    def column(n):return 'v('+n.replace(':','.').lower()+')'
    requested={column(n) for d in o['devices'] for n in d['terminals'] if n!='0'}
    requested.update(column(c['node']) for c in o['controls']);requested.update(column(n) for n in ('IN','OUT','VDD',*baseline.circuit.encode(s['coarse'],s['fine'])))
    names,w=validate(folder/'bench.raw',requested,20e-9);idx={n:k for k,n in enumerate(names)};t=w[:,idx['time']]*1e12
    if t[0]>1e-6:raise ValueError('Native trace omits startup interval')
    def get(n):return np.zeros(len(t)) if n=='0' else w[:,idx[column(n)]]
    samples=[]
    for base in (0,10000):
        window=(t>=base)&(t<=base+10000);sample={}
        for up,label in ((True,'rise'),(False,'fall')):
            a=baseline.crossings(t[window],get('IN')[window],up);b=baseline.crossings(t[window],get('OUT')[window],up)
            if len(a)!=1 or len(b)!=1 or b[0]<=a[0]:raise ValueError('Missing/extra pulse or wrong native epoch')
            sample[label+'_delay_ps']=float(b[0]-a[0])
        samples.append(sample)
    stress=[]
    for d in o['devices']:
        peak=max(float(np.max(np.abs(get(a)-get(b)))) for a,b in itertools.combinations(d['terminals'],2))
        stress.append(dict(device=d['name'],maximum_terminal_difference_v=peak,limit_v=d['limit_v'],passed=bool(peak<=d['limit_v'])))
    stable=t>=1500;controls=[];gates=[]
    for c in o['controls']:
        deviation=float(np.max(np.abs(get(c['node'])[stable]-1.8*targets[c['control']])))
        controls.append(dict(c,maximum_deviation_v=deviation,passed=bool(deviation<=.18)))
    for g in o['programming_gates']:
        deviation=float(np.max(np.abs(get(g['gate_node'])[stable]-1.8*targets[g['control']])))
        gates.append(dict(g,maximum_deviation_v=deviation,passed=bool(deviation<=.18)))
    for pin,value in baseline.circuit.encode(s['coarse'],s['fine']).items():
        if np.max(np.abs(get(pin)-1.8*value))>.01:raise ValueError('External control stimulus changed')
    repeat={k:abs(samples[1][k+'_delay_ps']-samples[0][k+'_delay_ps']) for k in ('rise','fall')}
    passed=all(s['passed'] for s in stress) and all(c['passed'] for c in controls+gates) and all(v<=20 for v in repeat.values())
    return dict(samples=samples,terminal_stress=stress,controls=controls,programming_gates=gates,
                terminal_screen_passed=all(s['passed'] for s in stress),control_settling_passed=all(c['passed'] for c in controls+gates),
                repeated_delay_difference_ps=repeat,static_native_screen_passed=bool(passed),
                whole_bank_rc_retained=True,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)



if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--component-parent',type=Path);p.add_argument('--fine-parent',type=Path)
    a=p.parse_args()
    if a.action=='prepare' and (a.component_parent is None or a.fine_parent is None):p.error('--component-parent and --fine-parent required')
    print(prepare(a.artifact.resolve(),a.component_parent.resolve(),a.fine_parent.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
