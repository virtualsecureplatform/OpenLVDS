#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Output-buffer prototype preserving the original actual joint-RC bank."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import probe_regenerated_bank_joint_zero_v61 as zero
import verify_regenerated_bank_periodic_v68 as proof
import probe_regenerated_bank_periodic_v67 as periodic
import probe_regenerated_bank_v56 as component
import buffered_bank_model_v70 as circuit
import probe_regenerated_bank_sparse_v63 as static
from native_binary_raw_v2 import validate as validate_output
from regenerated_bank_periodic_measure_v67 import crossings


ROOT=zero.ROOT
sha=zero.sha
VERSION='actual-bank-rc-with-native-buf1-buf4-output-regeneration-prototype-v70.1'
CONTEXT='buffered_bank_prototype_v70'
SCOPE='Actual original bank RC plus ideal-interconnect native output buffer; added cell junctions/routing not physically qualified; no complete-wrapper RC, electrical or PHY admission'


def specifications():return [dict(zero.spec(),profile=p,coarse=c,fine=f) for p in ('buf1','buf4') for c,f in ((0,0),(0,31),(1,0))]


def inherited(evidence,parent):
    binding=proof.bound(evidence);receipt=json.loads((evidence/'summary.json').read_text())
    zero_rows=[r for r in receipt['rows'] if r['spec']['fine']==0]
    if len(zero_rows)!=2 or any(not r['result']['periodic_transport_screen_passed'] or
            not r['result']['downstream_slew_domain_widening_required'] for r in zero_rows):
        raise ValueError('Require complete transported zero clocks exceeding the existing slew domain')
    source=periodic.bound(ROOT/binding['parent']);original=source['identity']
    model_parent=ROOT/original['zero_parent'];m=zero.bound(model_parent)
    c=component.bound(parent)
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=1,errors=0,qualified_phy=False):
        raise ValueError('Require unchanged complete native component source')
    return binding,m,c,receipt,model_parent


def fixture(out,i,s):
    text=zero.fixture(out,dict(i,spec=s,top=circuit.NAME));text=text.replace(str(out/'bank.spice'),str(out/('bank_'+s['profile']+'.spice')),1);title='OpenLVDS '+zero.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original routed zero fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def prepare(evidence,parent):
    binding,m,c,receipt,model_parent=inherited(evidence,parent);old=m['identity']
    text=(model_parent/'bank.spice').read_text();components=(parent/'bank.spice').read_text()
    banks={p:circuit.model(text,components,p) for p in ('buf1','buf4')}
    observations={p:circuit.observations(bank,old['observations']) for p,bank in banks.items()}
    ports=circuit.native_source.native.definitions(banks['buf1'])[circuit.NAME][0]
    if {p:len(o['devices']) for p,o in observations.items()}!={'buf1':955,'buf4':961}:raise ValueError('Unexpected buffered native inventory')
    paths=[evidence/'manifest.json',evidence/'summary.json',*[ROOT/n for n in binding['inputs']],
           model_parent/'manifest.json',model_parent/'bank.spice',*[ROOT/n for n in old['inputs']],
           parent/'manifest.json',parent/'bank.spice',*[ROOT/n for n in c['identity']['inputs']]]
    paths+=sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,evidence=str(evidence.relative_to(ROOT)),parent=str(parent.relative_to(ROOT)),bank_parent=str(model_parent.relative_to(ROOT)),
        specs=specifications(),top=circuit.NAME,ports=ports,model=old['model'],observations=observations,
        pdk_files=old['pdk_files'],external_files=c['identity']['external_files'],simulator=old['simulator'],
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
            or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
            or any(sha(out/n)!=h for n,h in m['libraries'].items()) or len(m['tasks'])!=6):
        raise ValueError('Buffered prototype context changed')
    original=(ROOT/i['bank_parent']/'bank.spice').read_text();components=(ROOT/i['parent']/'bank.spice').read_text()
    original_observations=json.loads((ROOT/i['bank_parent']/'manifest.json').read_text())['identity']['observations']
    for profile in ('buf1','buf4'):
        bank=(out/('bank_'+profile+'.spice')).read_text()
        if bank!=circuit.model(original,components,profile) or circuit.observations(bank,original_observations)!=i['observations'][profile]:
            raise ValueError('Original actual bank or output-buffer mapping cannot regenerate')
    for n,t in enumerate(m['tasks']):
        deck=out/str(n)/'bench.cir';view=dict(i,observations=i['observations'][t['spec']['profile']])
        if t['id']!=str(n) or t['spec']!=i['specs'][n] or t['deck_sha256']!=sha(deck) or deck.read_text()!=fixture(out,view,t['spec']):
            raise ValueError('Buffered native fixture changed')
    return m


def measure(folder,i,s):
    view=dict(i,spec=s,observations=i['observations'][s['profile']]);result=static.measure_trace(folder,view)
    names,w=validate_output(folder/'bench.raw',{'v(out)'},20e-9);t=w[:,names.index('time')]*1e12;v=w[:,names.index('v(out)')]
    slews={}
    for up,edge in ((True,'rise'),(False,'fall')):
        a=crossings(t,v,.18,up);b=crossings(t,v,1.62,up)
        ordered=len(a)==len(b)==2 and all(x<y if up else y<x for x,y in zip(a,b))
        slews[edge]=[abs(y-x) for x,y in zip(a,b)] if ordered else []
    maximum=max((v for vs in slews.values() for v in vs),default=None)
    result.update(scope=SCOPE,whole_bank_rc_retained=False,original_bank_rc_retained=True,
        added_stage_junctions_and_routing_qualified=False,output_slews_10_90_ps=slews,maximum_output_slew_ps=maximum,
        output_slew_domain_passed=bool(all(len(vs)==2 for vs in slews.values()) and maximum is not None and maximum<=250))
    return result


def comparisons(rows):
    result=[]
    for profile in ('buf1','buf4'):
        selected=[r for r in rows if r['spec']['profile']==profile]
        if len(selected)!=3 or any(r['error'] is not None for r in selected):continue
        by={(r['spec']['coarse'],r['spec']['fine']):r['result'] for r in selected}
        overlaps={edge+'_ps':by[0,31]['samples'][1][edge+'_delay_ps']-by[1,0]['samples'][1][edge+'_delay_ps'] for edge in ('rise','fall')}
        headroom=1e6/410/4-max(v for sample in by[0,0]['samples'] for v in sample.values())
        native=all(r['result']['static_native_screen_passed'] and r['result']['output_slew_domain_passed'] for r in selected)
        result.append(dict(profile=profile,coarse_overlap=overlaps,zero_code_fast_quarter_headroom_ps=headroom,
            buffered_prototype_feasibility_passed=bool(native and headroom>0 and all(v>0 for v in overlaps.values())),
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



if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);p.add_argument('--component-parent',type=Path)
    a=p.parse_args()
    if a.action=='prepare' and a.component_parent is None:p.error('--component-parent required')
    print(prepare(a.artifact.resolve(),a.component_parent.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
