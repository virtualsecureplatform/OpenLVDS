#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Conditionally prototype the four approved analog frontends at fixed rails.

All four bounded standard-cell candidates must complete and independently
fail before any analog circuit artifact is created. DC readiness is only a
headroom/current/level/stress gate; timing repair still requires transients.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import dll_analog_frontend as policy
import screen_dll_slew_frontends as screen
from dll_campaign import atomic,bias_reference_count
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from spice_dispatch import lease
from spice_engine import engine,provenance
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
NAMESPACE='dll_analog_frontend_dc'
sha=screen.sha
OUTPUTS=('bench.raw','ngspice.log','console.log')
POINTS=((0,0),(.9,.9),(1.8,1.8),(0,1.8),(1.8,0))


def fallback_gate(parent):
    if not parent.is_relative_to(ROOT/'build/diagnostics/dll_slew_screen'):raise ValueError('Require the complete bounded standard-cell screen')
    with (parent/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        report=screen.verify(parent);m=screen.bound(parent)
        if (report['ranked_survivors'] or len(report['candidates'])!=len(screen.cal.CANDIDATES) or
            {c['variant'] for c in report['candidates']}!=set(screen.cal.CANDIDATES) or
            any(c['passed'] is not False for c in report['candidates']) or
            len(report['results'])!=len(screen.tasks()) or any(r['error'] is not None for r in report['results'])):
            raise ValueError('Analog fallback requires all four completed standard-cell candidates to fail')
    return m


def tasks():
    return [dict(id=f'{v}_point{i}',variant=v,ref_v=r,fb_v=f) for v in policy.VARIANTS for i,(r,f) in enumerate(POINTS)]


def fixture(task,out,pdk,model):
    _,devices=policy.circuit(task['variant'])
    nodes=sorted({'REF','FDB','REF_FAST','FDB_FAST','VDDIO','VDDD','XF:VCM','XF:NTAIL'}|
                 {n for d in devices for n in d['terminals'] if n!='0'})
    saves=['v('+n.replace(':','.').lower()+')' for n in nodes]+['i(va)','i(vd)',*policy.op_parameters().values()]
    deck=(f'OpenLVDS conditional analog frontend DC {task["id"]}\n.lib "{pdk}" ss\n'
          f'.include "{out}/{task["variant"]}.spice"\n.temp 40\n.options klu reltol=1e-4 abstol=1e-12\n'
          'VA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\nXB PB NB VDDIO 0 lvds_bias\n'
          f'VR REF 0 {task["ref_v"]:g}\nVF FDB 0 {task["fb_v"]:g}\n'
          'XF REF FDB REF_FAST FDB_FAST PB VDDIO VDDD 0 '+policy.PAIR+'\n'+
          '.save '+' '.join(saves)+'\n.control\nset filetype=binary\nset noaskquit\nop\nwrite bench.raw all\nquit\n.endc\n.end\n')
    if bias_reference_count(deck,model)!=1:raise ValueError('Analog fallback duplicated endpoint bias')
    ProbeNetwork(model).validate(deck,nodes)
    return deck,nodes


def prepare(parent):
    if engine()!='ngspice':raise ValueError('Use the pinned ngspice environment')
    pm=fallback_gate(parent);cm=screen.cal.bound(ROOT/pm['identity']['calibration'])
    original=screen.cal.old.bound(ROOT/cm['identity']['parent']);q=ROOT/original['identity']['qualification']
    template=q/'slew_ss_40_0ps_20_200/bench.cir'
    pdk=Path(re.search(r'(?m)^\.lib "([^"\n]+)"',template.read_text())[1])
    paths=[parent/n for n in ('manifest.json','summary.json')]+[q/'full.spice',template,ROOT/'requirements.json']
    for t in pm['tasks']:paths += [parent/t['id']/n for n in ('bench.raw','bench.cir.prn','ngspice.log','console.log','summary.json','bench.cir','library.spice')]
    inputs=dict(pm['identity']['inputs']);inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code=dict(pm['identity']['code'])
    for n in (Path(__file__).name,'dll_analog_frontend.py','run_ngspice.py','spice_dispatch.py','expand_dll_slew_frontends.py'):
        code[n]=sha(ROOT/'scripts'/n)
    identity=dict(parent=str(parent.relative_to(ROOT)),qualification_reference=str(q.relative_to(ROOT)),policy=policy.VERSION,
                  simulator=provenance(),inputs=inputs,code=code,pdk=dict(path=str(pdk),sha256=sha(pdk)),
                  scope='Conditional four-variant analog frontend DC readiness at SS40, fixed 3.3/1.8 V rails, five static input states. Retained native endpoint bias; local shared current mirror, VDDD/2 reference and restored outputs. No supply sweep, transient timing, physical, PVT or PHY admission.')
    out=ROOT/'build/diagnostics'/NAMESPACE/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);native=(q/'full.spice').read_text()
    # Reuse only immutable file-writing utilities, never old electrical results.
    from expand_dll_slew_frontends import write_once
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);libraries={};prepared=[]
        for variant in policy.VARIANTS:
            model=native+policy.circuit(variant)[0];write_once(out/(variant+'.spice'),model)
            libraries[variant+'.spice']=sha(out/(variant+'.spice'))
        for t in tasks():
            folder=out/t['id'];folder.mkdir(exist_ok=True)
            deck,nodes=fixture(t,out,pdk,(out/(t['variant']+'.spice')).read_text());write_once(folder/'bench.cir',deck)
            prepared.append(dict(t,voltage_nodes=nodes,deck_sha256=sha(folder/'bench.cir')))
        (out/'producers').mkdir(exist_ok=True)
        for n in code:write_once(out/'producers'/n,(ROOT/'scripts'/n).read_text())
        capture_manifest(out/'manifest.json',dict(identity=identity,libraries=libraries,tasks=prepared,physical_admission=False,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (not out.is_relative_to(ROOT/'build/diagnostics'/NAMESPACE) or
        out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
        i['policy']!=policy.VERSION or i['simulator']!=provenance() or m['physical_admission'] is not False or m['qualified_phy'] is not False or
        any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or
        any(sha(ROOT/'scripts'/n)!=h or sha(out/'producers'/n)!=h for n,h in i['code'].items()) or
        sha(Path(i['pdk']['path']))!=i['pdk']['sha256'] or
        set(m['libraries'])!={v+'.spice' for v in policy.VARIANTS} or any(sha(out/n)!=h for n,h in m['libraries'].items()) or
        [{k:v for k,v in t.items() if k not in ('voltage_nodes','deck_sha256')} for t in m['tasks']]!=tasks()):
        raise ValueError('Analog frontend DC context changed')
    fallback_gate(ROOT/i['parent']);native=(ROOT/i['qualification_reference']/'full.spice').read_text()
    for v in policy.VARIANTS:
        if (out/(v+'.spice')).read_text()!=native+policy.circuit(v)[0]:raise ValueError('Analog frontend circuit changed')
    for t in m['tasks']:
        deck,nodes=fixture(t,out,Path(i['pdk']['path']),(out/(t['variant']+'.spice')).read_text())
        if deck!=(out/t['id']/'bench.cir').read_text() or nodes!=t['voltage_nodes'] or sha(out/t['id']/'bench.cir')!=t['deck_sha256']:
            raise ValueError('Analog frontend DC fixture changed')
    return m


def measurements(values,task):
    if not all(np.isfinite(v) for v in values.values()):raise ValueError('Nonfinite analog operating point')
    def voltage(node):return 0. if node=='0' else float(values['v('+node.replace(':','.').lower()+')'])
    def parameter(name,vector):
        field=name.rsplit('_',1)[-1];keys=[vector]
        if field in ('id','vdsat'):keys += [('i' if field=='id' else 'v')+'('+vector+')']
        found=[float(values[k]) for k in keys if k in values]
        if not found or any(x!=found[0] for x in found):raise ValueError('Missing or inconsistent model vector: '+name)
        return found[0]
    params={n:parameter(n,v) for n,v in policy.op_parameters().items()}
    if (abs(voltage('REF')-task['ref_v'])>1e-8 or abs(voltage('FDB')-task['fb_v'])>1e-8 or
        abs(voltage('VDDIO')-3.3)>1e-8 or abs(voltage('VDDD')-1.8)>1e-8):raise ValueError('Analog DC signal or fixed rail changed')
    ref_current=params['reference_id'];target=policy.VARIANTS[task['variant']]['tail_ua']*1e-6
    current_ok=bool(.75*target<=ref_current<=1.25*target and params['reference_gm']>0)
    tails={}
    for side,path in [('ref','XF:XREF:T'),('fb','XF:XFB:T')]:
        p={field:params[side+'_tail_'+field] for field in ('id','gm','gds','vdsat')}
        headroom=voltage(path)-p['vdsat']
        p.update(headroom_v=headroom,passed=bool(headroom>=.02 and p['vdsat']>0 and p['gm']>0 and p['gds']>=0 and
                  .75*target<=p['id']<=1.25*target and .8*ref_current<=p['id']<=1.2*ref_current))
        tails[side]=p
    outputs={}
    for side,node,signal in [('ref','REF_FAST',task['ref_v']),('fb','FDB_FAST',task['fb_v'])]:
        value=voltage(node);outputs[side]=dict(voltage_v=value,expected_high=signal> .9 if signal!=.9 else None,
            passed=bool(signal==.9 or (value<.36 if signal==0 else value>1.44)))
    stress=[]
    for device in policy.circuit(task['variant'])[1]:
        volts=[voltage(n) for n in device['terminals']]
        worst=max(abs(a-b) for a,b in itertools.combinations(volts,2));limit=5.5 if device['model']==policy.P5 else 1.95
        stress.append(dict(device=device['name'],max_terminal_difference_v=worst,limit_v=limit,passed=bool(worst<=limit)))
    cm=voltage('XF:VCM');cm_ok=abs(cm-.9)<=.01
    passed=bool(current_ok and cm_ok and all(t['passed'] for t in tails.values()) and all(o['passed'] for o in outputs.values()) and all(s['passed'] for s in stress))
    return dict(passed=passed,reference_current_a=ref_current,reference_current_passed=current_ok,common_mode_v=cm,common_mode_passed=cm_ok,
                tails=tails,outputs=outputs,stress=stress,rail_power_w=float(-3.3*values['i(va)']-1.8*values['i(vd)']))


def measure(folder,task):
    names,wave=read_raw(folder/'bench.raw')
    if wave.shape!=(1,len(names)) or len(set(names))!=len(names) or not np.isfinite(wave).all():raise ValueError('Require one complete finite operating point')
    return measurements(dict(zip(names,wave[0])),task)


def aggregate(m,rows):
    expected={t['id']:t for t in m['tasks']}
    if ([{k:v for k,v in t.items() if k not in ('voltage_nodes','deck_sha256')} for t in m['tasks']]!=tasks() or
        len(rows)!=len(expected) or len({r['task'] for r in rows})!=len(rows) or
        any(r['task'] not in expected or r['variant']!=expected[r['task']]['variant'] for r in rows)):
        raise ValueError('Analog DC results missing, duplicated or unexpected')
    ready=[v for v in policy.VARIANTS if all(r['error'] is None and r['result'] and r['result']['passed'] for r in rows if r['variant']==v)]
    return dict(dc_ready_variants=ready,results=rows,timing_repair_verified=False,physical_admission=False,qualified_phy=False,scope=m['identity']['scope'])


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    def unchanged(t):
        if (sha(out/'manifest.json')!=stamp or sha(out/t['id']/'bench.cir')!=t['deck_sha256'] or
            sha(out/(t['variant']+'.spice'))!=m['libraries'][t['variant']+'.spice'] or
            any(sha(ROOT/'scripts'/n)!=h for n,h in m['identity']['code'].items())):raise ValueError('Analog DC execution context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists() or any((out/t['id']/n).exists() for t in m['tasks'] for n in (*OUTPUTS,'summary.json')):raise ValueError('Partial analog DC output retained; no retry')
        atomic(out/'state.json',dict(status='probing_analog_headroom',qualified_phy=False))
        def execute(t):
            folder=out/t['id'];result=error=None
            try:
                with lease(ROOT,priority=0,label='dll_analog_dc_'+t['id']):
                    unchanged(t);runtime=ROOT/'build/tools/ngspice-runtime';binary=ROOT/'build/tools/ngspice-root/usr/bin/ngspice'
                    pinned=json.loads((ROOT/'build/tools/ngspice.json').read_text())
                    if any(sha(ROOT/n)!=h for n,h in pinned['files'].items()):raise ValueError('Pinned ngspice runtime changed')
                    p=subprocess.run([str(runtime/'ld-linux-x86-64.so.2'),'--library-path',str(runtime),str(binary),'-n','-b','-o',str(folder/'ngspice.log'),str(folder/'bench.cir')],cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();unchanged(t);result=measure(folder,t);unchanged(t)
            except Exception as e:error=str(e)
            row=dict(task=t['id'],variant=t['variant'],result=result,error=error,manifest_sha256=stamp,files={n:sha(folder/n) for n in OUTPUTS if (folder/n).exists()})
            capture_manifest(folder/'summary.json',row);return row
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(execute,m['tasks']))
        bound(out)
        if sha(out/'manifest.json')!=stamp:raise ValueError('Analog DC manifest changed')
        report=dict(aggregate(m,rows),manifest_sha256=stamp);capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='analog_dc_complete',dc_ready_variants=report['dc_ready_variants'],qualified_phy=False))
    return report


def verify(out):
    m=bound(out);stamp=sha(out/'manifest.json');rows=[]
    for t in m['tasks']:
        f=out/t['id'];r=json.loads((f/'summary.json').read_text())
        if (r['task']!=t['id'] or r['variant']!=t['variant'] or r['error'] is not None or r['manifest_sha256']!=stamp or
            set(r['files'])!=set(OUTPUTS) or any(sha(f/n)!=h for n,h in r['files'].items()) or measure(f,t)!=r['result']):raise ValueError('Analog DC result changed')
        rows.append(r)
    report=dict(aggregate(m,rows),manifest_sha256=stamp)
    if report!=json.loads((out/'summary.json').read_text()):raise ValueError('Analog DC aggregate changed')
    bound(out);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path)
    a=p.parse_args();r=globals()[a.action](a.artifact.resolve());print(r if a.action=='prepare' else json.dumps(r,indent=2),flush=True)
