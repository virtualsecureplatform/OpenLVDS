#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Complete SS/40 zero screen of the actual routed branch-regenerated bank."""
import argparse
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import regenerated_bank_observations_v60 as observations
import probe_dcdl_uniform_tree_v3 as baseline
from native_binary_raw_v2 import validate
from dcdl_tg_tree_v5 import control_targets
from spice_dispatch import lease
from spice_engine import engine,provenance

ROOT=baseline.ROOT
sha=baseline.sha
VERSION='actual-regenerated-joint-rc-ss40-zero-complete-control-screen-v61.1'
CONTEXT='regenerated_bank_joint_zero_v61'
CAD='/nix/store/nah36l3f04m5gsi98a7civz9n8szraml-devshell-dir/bin/python3'
SCOPE='Complete actual joint-RC 951-MOS/68-MIM bank SS/40 zero only; no sparse/dense/update/periodic/all-PVT or PHY admission'


def spec():return dict(process='ss',temperature=40,coarse=0,fine=0,input_slew_ps=100,load_ff=20)


def evidence(parent):
    code='import sys,json;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[1])/"scripts"));import verify_regenerated_bank_joint_rc_v59 as p;out=Path(sys.argv[2]);i,pi=p.bound(out);r=json.loads((out/"summary.json").read_text());assert r["joint_rc_passed"] and r["native_topology_verified"] and all(p.sha(out/n)==h for n,h in r["files"].items());print(json.dumps(dict(identity=i,placement=pi,report=r),sort_keys=True))'
    p=subprocess.run([CAD,'-c',code,str(ROOT),str(parent)],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)


def observe(record):
    i=record['identity'];pi=record['placement'];parent=ROOT/i['parent'];name=pi['graph']['top'];info=i['extraction']
    folder=(ROOT/info['raw_netlist']).parent
    return observations.mapping((parent/'native'/(name+'.mag')).read_text(),(folder/(name+'_rcx.ext')).read_text(),
                                (ROOT/info['netlist']).read_text(),pi['graph'],pi['plan'])


def fixture(out,i):
    s=i['spec'];name=i['top'];width=s['input_slew_ps']/1e12/(2*np.arctanh(.8))
    wave='+'.join(f'0.9*(tanh((time-{b+2.1:g}n)/{width:.17g})-tanh((time-{b+6.1:g}n)/{width:.17g}))' for b in (0,10))
    rows=['OpenLVDS '+VERSION,f'.lib "{i["model"]}" {s["process"]}',f'.include "{out}/bank.spice"',
          f'.options device temp={s["temperature"]}', '.options timeint method=gear reltol=1e-4 abstol=1e-12',
          'VDD VDD 0 1.8','BIN IN 0 V={'+wave+'}']
    for pin,value in baseline.circuit.encode(s['coarse'],s['fine']).items():rows.append(f'V{pin} {pin} 0 {1.8*value:g}')
    rows += ['XD '+' '.join('0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in i['ports'])+' '+name,
             f'CLOAD OUT 0 {s["load_ff"]}f','.tran 2p 20n 0 2p']
    probes={'IN','OUT','VDD',*baseline.circuit.encode(s['coarse'],s['fine'])}
    probes.update(n for d in i['observations']['devices'] for n in d['terminals'] if n!='0')
    probes.update(c['node'] for c in i['observations']['controls'])
    return '\n'.join(rows+['.print tran '+' '.join('V('+n+')' for n in sorted(probes)),'.end',''])


def prepare(parent):
    if engine()!='ngspice':raise ValueError('Require pinned native ngspice')
    record=evidence(parent);i=record['identity'];pi=record['placement'];o=observe(record)
    physical=ROOT/i['parent'];name=pi['graph']['top'];folder=(ROOT/i['extraction']['raw_netlist']).parent
    paths=[parent/'manifest.json',parent/'summary.json',*[parent/n for n in record['report']['files']],
           *[ROOT/n for n in i['inputs']],physical/'native'/(name+'.mag'),folder/(name+'_rcx.ext')]
    paths+=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    paths += [ROOT/'scripts'/n for n in ('run_native_binary_v2.py','run_ngspice.py','spice_slots.py','spice_dispatch.py')]
    paths += [ROOT/'clocking_v2.json',ROOT/'clocking_duty_v2_2.json',ROOT/'build/tools/ngspice.json']
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';model=pdk/'libs.tech/ngspice/sky130.lib.spice'
    models={model,*list((pdk/'libs.ref/sky130_fd_pr/spice').rglob('*.spice')),*list((pdk/'libs.tech/ngspice').rglob('*.spice'))}
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),spec=spec(),observations=o,top=name,ports=pi['graph']['ports'],
                  netlist=i['extraction']['netlist'],model=str(model),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
                  pdk_files={str(p):sha(p) for p in sorted(models)},simulator=provenance(),cad=dict(path=CAD,sha256=sha(Path(CAD))),
                  max_workers=1,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'0').mkdir()
    baseline.write(out/'bank.spice',(ROOT/identity['netlist']).read_text());baseline.write(out/'0/bench.cir',fixture(out,identity))
    baseline.atomic(out/'manifest.json',dict(identity=identity,libraries={'bank.spice':sha(out/'bank.spice')},deck_sha256=sha(out/'0/bench.cir'),qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];o=i['observations']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['spec']!=spec() or i['max_workers']!=1 or engine()!='ngspice' or provenance()!=i['simulator']
            or len(o['devices'])!=951 or len(o['programming_gates'])!=133 or o['observed_canonical_nets']!=150
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
            or sha(Path(i['cad']['path']))!=i['cad']['sha256'] or sha(out/'bank.spice')!=m['libraries']['bank.spice']
            or (out/'bank.spice').read_text()!=(ROOT/i['netlist']).read_text()
            or sha(out/'0/bench.cir')!=m['deck_sha256'] or (out/'0/bench.cir').read_text()!=fixture(out,i)):
        raise ValueError('Complete joint-RC zero campaign changed')
    if observe(evidence(ROOT/i['parent']))!=o:raise ValueError('Actual physical control observation mapping changed')
    return m


def measure(out,i):
    o=i['observations'];s=i['spec'];targets=control_targets(s['coarse'],s['fine'])
    def column(n):return 'v('+n.replace(':','.').lower()+')'
    requested={column(n) for d in o['devices'] for n in d['terminals'] if n!='0'}
    requested.update(column(c['node']) for c in o['controls']);requested.update(column(n) for n in ('IN','OUT','VDD',*baseline.circuit.encode(0,0)))
    names,w=validate(out/'0/bench.raw',requested,20e-9);idx={n:k for k,n in enumerate(names)};t=w[:,idx['time']]*1e12
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
    for pin,value in baseline.circuit.encode(0,0).items():
        if np.max(np.abs(get(pin)-1.8*value))>.01:raise ValueError('External control stimulus changed')
    repeat={k:abs(samples[1][k+'_delay_ps']-samples[0][k+'_delay_ps']) for k in ('rise','fall')}
    headroom=1e6/410/4-max(v for sample in samples for v in sample.values())
    passed=headroom>=0 and all(s['passed'] for s in stress) and all(c['passed'] for c in controls+gates) and all(v<=20 for v in repeat.values())
    return dict(samples=samples,terminal_stress=stress,controls=controls,programming_gates=gates,
                terminal_screen_passed=all(s['passed'] for s in stress),control_settling_passed=all(c['passed'] for c in controls+gates),
                repeated_delay_difference_ps=repeat,zero_code_fast_quarter_headroom_ps=headroom,joint_rc_zero_screen_passed=bool(passed),
                whole_bank_rc_retained=True,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or live joint-RC campaign')
        baseline.atomic(out/'state.json',dict(status='running',qualified_phy=False));result=error=None;wall=None
        try:
            with lease(ROOT,priority=0,label=CONTEXT+'_0'):
                bound(out);start=time.monotonic()
                p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(out/'0/ngspice.log'),str(out/'0/bench.cir')],capture_output=True,text=True)
                wall=time.monotonic()-start
            baseline.write(out/'0/console.log',p.stdout+p.stderr);p.check_returncode();result=measure(out,i)
        except Exception as e:error=str(e)
        row=dict(spec=i['spec'],result=result,error=error,solver_wall_seconds=wall,files={p.name:sha(p) for p in (out/'0').iterdir() if p.is_file()})
        baseline.atomic(out/'0/summary.json',row);bound(out)
        baseline.atomic(out/'summary.json',dict(rows=[row],qualified_phy=False,scope=SCOPE))
        baseline.atomic(out/'state.json',dict(status='complete',cases=1,errors=int(error is not None),qualified_phy=False));return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    a=p.parse_args();print(prepare(a.artifact.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
