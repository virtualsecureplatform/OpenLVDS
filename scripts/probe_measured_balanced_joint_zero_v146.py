#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Full native zero-code screen of qualified measured balanced-bank joint RC."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np
import measured_bank_observations_v145 as observations
import probe_strong_coarse_bank_v123 as measurement
from native_binary_raw_v2 import validate
from regenerated_bank_periodic_measure_v67 import crossings

zero=measurement.zero
ROOT=zero.ROOT
sha=zero.sha
CAD=zero.CAD
VERSION='actual-measured-balanced-joint-rc-ss40-zero-full-observations-and-slew-v146.1'
CONTEXT='measured_balanced_joint_zero_v146'
SCOPE='Actual corrected routed joint RC SS/40 zero: all MOS terminals, typed programming gates, controls, repetition, quarter budget and 250 ps slew; sparse/dense/update/periodic/PVT/PHY remain unqualified'


def spec(profile):return dict(zero.spec(),profile=profile)


def evidence(parent):
    code='''import sys,json
from pathlib import Path
sys.path.insert(0,'scripts')
import verify_measured_balanced_joint_rc_v144 as p
import measured_bank_observations_v145 as observations
out=Path(sys.argv[1]);i,bi=p.bound(out);r=json.loads((out/'summary.json').read_text())
if json.loads((out/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False) or not r['joint_rc_passed'] or not r['native_topology_verified'] or any(p.sha(out/n)!=h for n,h in r['files'].items()) or any(p.sha(p.ROOT/n)!=h for n,h in r['original_extracted_files'].items()):raise ValueError('Require complete unchanged actual joint RC and native equivalence')
native=p.ROOT/i['parent']/'native';top=i['top'];folder=(p.ROOT/r['original_extraction']['raw_netlist']).parent
mag=native/(top+'.mag');ext=folder/(top+'_rcx.ext');netlist=p.ROOT/r['extraction']['netlist']
o=observations.mapping(mag.read_text(),ext.read_text(),netlist.read_text(),bi['graph'],bi['plan'],i['profile'])
files=[mag,ext,netlist,*[p.ROOT/n for n in i['inputs']],*[p.ROOT/n for n in r['original_extracted_files']]]
files += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==p.ROOT/'scripts'})
print(json.dumps(dict(identity=i,bank=bi,report=r,observations=o,files={str(f.relative_to(p.ROOT)):p.sha(f) for f in files}),sort_keys=True))
'''
    p=subprocess.run([CAD,'-c',code,str(parent)],cwd=ROOT,capture_output=True,text=True)
    if p.returncode:raise ValueError('Joint-RC zero admission refused:\n'+p.stderr[-3000:])
    return json.loads(p.stdout)


def fixture(out,i):
    text=zero.fixture(out,i);title='OpenLVDS '+zero.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Original complete native zero stimulus changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def prepare(parent):
    if zero.engine()!='ngspice':raise ValueError('Require pinned native ngspice')
    record=evidence(parent);pi=record['identity'];bi=record['bank'];r=record['report'];o=record['observations']
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json',*[parent/n for n in r['files']]]
    paths+=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    paths += [ROOT/'scripts'/n for n in ['run_native_binary_v2.py','run_ngspice.py','spice_dispatch.py','spice_slots.py']]
    paths += [ROOT/'clocking_v2.json',ROOT/'clocking_duty_v2_2.json',ROOT/'build/tools/ngspice.json']
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';model=pdk/'libs.tech/ngspice/sky130.lib.spice'
    models={model,*list((pdk/'libs.ref/sky130_fd_pr/spice').rglob('*.spice')),*list((pdk/'libs.tech/ngspice').rglob('*.spice'))}
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),profile=pi['profile'],spec=spec(pi['profile']),top=pi['top'],ports=bi['graph']['ports'],
           observations=o,netlist=r['extraction']['netlist'],model=str(model),inputs={**record['files'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}},
           pdk_files={str(p):sha(p) for p in sorted(models)},simulator=zero.provenance(),cad=dict(path=CAD,sha256=sha(Path(CAD))),max_workers=1,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'0').mkdir();(out/'bank.spice').write_bytes((ROOT/i['netlist']).read_bytes());(out/'0/bench.cir').write_text(fixture(out,i))
    zero.baseline.atomic(out/'manifest.json',dict(identity=i,bank_sha256=sha(out/'bank.spice'),deck_sha256=sha(out/'0/bench.cir'),qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];o=i['observations']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['spec']!=spec(i['profile']) or i['max_workers']!=1 or zero.engine()!='ngspice' or zero.provenance()!=i['simulator']
        or len(o['devices'])!=(1453 if i['profile']=='b2' else 1773) or len(o['programming_gates'])!=173
        or len(o['logical_controls'])!=86 or o['physical_instances']!=351 or o['observed_canonical_nets']!=150
        or not o['typed_per_control_gate_coverage_verified']
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['pdk_files'].items())
        or sha(Path(CAD))!=i['cad']['sha256'] or sha(out/'bank.spice')!=m['bank_sha256'] or sha(out/'bank.spice')!=sha(ROOT/i['netlist'])
        or sha(out/'0/bench.cir')!=m['deck_sha256'] or (out/'0/bench.cir').read_text()!=fixture(out,i)):
        raise ValueError('Actual measured joint-RC zero context changed')
    if evidence(ROOT/i['parent'])['observations']!=o:raise ValueError('Actual physical/RC observation mapping cannot regenerate')
    return i


def assess(result,slews):
    if len(result['samples'])!=2 or any(set(row)!={'rise_delay_ps','fall_delay_ps'} for row in result['samples']):raise ValueError('Require both complete native pulse samples')
    values=[v for row in result['samples'] for v in row.values()]
    if any(not np.isfinite(v) or v<=0 for v in values):raise ValueError('Invalid unwrapped native pulse delay')
    maximum=max((v for vs in slews.values() for v in vs),default=None)
    slew_ok=bool(set(slews)=={'rise','fall'} and all(len(vs)==2 and all(np.isfinite(v) and v>0 for v in vs) for vs in slews.values()) and maximum is not None and maximum<=250)
    headroom=1e6/410/4-max(values)
    result=dict(result,output_slews_10_90_ps=slews,maximum_output_slew_ps=maximum,output_slew_domain_passed=slew_ok,
                zero_code_fast_quarter_headroom_ps=headroom,joint_rc_zero_screen_passed=bool(result['static_native_screen_passed'] and slew_ok and headroom>=0),
                whole_bank_rc_retained=True,all_pvt_covered=False,electrical_qualification_passed=False,qualified_phy=False,scope=SCOPE)
    return result


def measure(folder,i):
    result=measurement.measure_trace(folder,i)
    names,w=validate(folder/'bench.raw',{'v(out)'},20e-9);t=w[:,names.index('time')]*1e12;v=w[:,names.index('v(out)')];slews={}
    for up,edge in [(True,'rise'),(False,'fall')]:
        low=crossings(t,v,.18,up);high=crossings(t,v,1.62,up)
        ordered=len(low)==len(high)==2 and all(a<b if up else b<a for a,b in zip(low,high))
        slews[edge]=[abs(b-a) for a,b in zip(low,high)] if ordered else []
    return assess(result,slews)


def run(out):
    i=bound(out);folder=out/'0'
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or live actual joint-RC zero campaign')
        zero.baseline.atomic(out/'state.json',dict(status='running',qualified_phy=False));result=error=wall=None
        try:
            with zero.lease(ROOT,priority=0,label=CONTEXT+'_0'):
                bound(out);start=time.monotonic()
                p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
                wall=time.monotonic()-start
            (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode();result=measure(folder,i)
        except Exception as e:error=str(e)
        row=dict(spec=i['spec'],result=result,error=error,solver_wall_seconds=wall,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
        zero.baseline.atomic(folder/'summary.json',row);bound(out)
        zero.baseline.atomic(out/'summary.json',dict(rows=[row],whole_bank_rc_retained=True,qualified_phy=False,scope=SCOPE))
        zero.baseline.atomic(out/'state.json',dict(status='complete',cases=1,errors=int(error is not None),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
