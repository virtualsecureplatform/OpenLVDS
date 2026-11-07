#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test the unchanged REQUEST repair at the newly measured 40% startup peak."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import probe_request_taper_counter_v317 as candidate
from native_binary_raw_v2 import validate
from diagnose_shared_counter_v200 import terminal_peak
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT=candidate.ROOT
VERSION='unchanged-request-taper-ss0-forty-percent-startup-stress-boundary-v330.1'
CONTEXT='request_taper_forty_boundary_v330'
sha=candidate.sha
atomic=candidate.atomic
SCOPE=('Unchanged 808-MOS REQUEST-taper component circuit at the independently measured '
       'SS0/410MHz/40% stopped-low startup-stress boundary; original full 26ns fixture '
       'and gates, no other duty/stopped-level/PVT/shared-wire/PHY admission')


def specification():
    return dict(candidate.specifications()[0],duty=.4)


def fixture(out,spec,devices):
    text=candidate.fixture(out,spec,devices)
    old='OpenLVDS '+candidate.VERSION+'\n'
    if not text.startswith(old):raise ValueError('Original native fixture title changed')
    return text.replace(old,'OpenLVDS '+VERSION+'\n',1)


def require_cause(evidence):
    report=json.loads((evidence/'summary.json').read_text())
    parent=ROOT/'build/diagnostics/counter_matched_buffers_v306/f9b748a6ac5c2ee2'
    case=parent/'9';m=json.loads((parent/'manifest.json').read_text());row=json.loads((case/'summary.json').read_text())
    spec={**specification(),'buffer_variant':'matched'}
    if (report.get('all_stored_failed_peaks_reproduced') is not True or report.get('parameters_changed') is not False
            or report['case']!=str(case.relative_to(ROOT)) or row['task']!=m['tasks'][9]
            or row['task']['spec']!=spec or row['error'] is not None
            or any(sha(ROOT/n)!=h for n,h in report['inputs'].items())
            or any(sha(case/n)!=h for n,h in row['files'].items())):
        raise ValueError('Require exact completed unchanged SS0/40% matched-buffer stress diagnosis')
    measured=candidate.source.measure(case,m['identity'],spec)
    if measured!=row['result']:raise ValueError('Original full native 40% measurements do not reproduce')
    failed={d['device']:d for d in measured['terminal_stress'] if not d['passed']}
    faults=report['failed_devices'];groups={}
    if len(faults)!=96 or {d['device'] for d in faults}!=set(failed):
        raise ValueError('Require measured 96-device startup/REQUEST stress failure')
    devices={d['name']:d for d in m['identity']['devices']['matched']}
    column=lambda n:'v('+n.replace(':','.').lower()+')'
    names,data=validate(case/'bench.raw',{column(n) for d in faults for n in devices[d['device']]['terminals'] if n!='0'},26e-9)
    times=data[:,names.index('time')]*1e12
    for fault in faults:
        d=devices[fault['device']]
        if '0' in d['terminals']:raise ValueError('Unexpected grounded terminal in the measured failure group')
        values=[data[:,names.index(column(n))] for n in d['terminals']]
        peak,sample,a,b=terminal_peak(values)
        actual={label:dict(node=n,voltage_v=float(values[k][sample]))
                for k,(label,n) in enumerate(zip(('D','G','S','B'),d['terminals']))}
        if (peak!=fault['peak_v'] or peak!=failed[d['name']]['max_terminal_difference_v']
                or fault['time_ps']!=float(times[sample]) or fault['terminals']!=actual
                or fault['worst_pair']!=[('D','G','S','B')[k] for k in (a,b)] or fault['limit_v']!=1.95):
            raise ValueError('Exact native stress samples do not reproduce')
        group=d['name'].split(':')[2];groups[group]=groups.get(group,0)+1
    if groups!={'Xrequest_driver':36,'Xrequest_driver_parallel':36,'Xlow0_set_pair':8,'Xlow0_q':16}:
        raise ValueError('Measured REQUEST/setter/storage failure groups changed')
    worst=max(faults,key=lambda d:d['peak_v'])
    if (worst['device']!='XD:XR:Xlow0_set_pair:X11' or worst['worst_pair']!=['D','B']
            or not 3400<worst['time_ps']<4000 or worst['peak_v']<=1.95):
        raise ValueError('Require actual low0 startup stress, not only REQUEST reassertion overshoot')
    return dict(groups=groups,worst=worst),[evidence/'summary.json',parent/'manifest.json',case/'summary.json',
        *[ROOT/n for n in report['inputs']],*[case/n for n in row['files']]]


def prepare(parent,evidence):
    m=candidate.bound(parent,full=False);i=m['identity']
    cause,paths=require_cause(evidence)
    # Capture immutable candidate libraries/manifest, not its live campaign
    # state or its still-pending final 60% case.
    paths += [parent/'manifest.json',*[parent/n for n in m['libraries']],*[ROOT/n for n in i['inputs']]]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))}
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),diagnosis=str(evidence.relative_to(ROOT)),
        cause=cause,spec=specification(),devices=i['devices'],library_sha256=m['libraries'],
        simulator=i['simulator'],pdk_files=i['pdk_files'],external_files=i['external_files'],
        inputs=inputs,guards=candidate.guard_inputs(inputs),max_workers=1,priority=1,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    for n in m['libraries']:(out/n).write_bytes((parent/n).read_bytes())
    folder=out/'0';folder.mkdir();(folder/'bench.cir').write_text(fixture(out,identity['spec'],identity['devices'][candidate.VARIANT]))
    task=dict(id='0',spec=identity['spec'],deck_sha256=sha(folder/'bench.cir'))
    atomic(out/'manifest.json',dict(identity=identity,tasks=[task],libraries=m['libraries'],qualified_phy=False))
    return out


def bound(out,full=True):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or i['spec']!=specification() or i['max_workers']!=1 or i['priority']!=1 or i['scope']!=SCOPE
            or i['guards']!=candidate.guard_inputs(i['inputs']) or m['libraries']!=i['library_sha256']
            or any(sha(ROOT/n)!=h for n,h in (i['inputs'] if full else i['guards']).items())
            or any(sha(Path(n))!=h for n,h in {**i['pdk_files'],**i['external_files']}.items())
            or any(sha(out/n)!=h for n,h in m['libraries'].items())
            or engine()!='ngspice' or provenance()!=i['simulator']):
        raise ValueError('Unchanged REQUEST-taper boundary experiment context changed')
    devices=candidate.source.observations((out/'cells.spice').read_text(),(out/'pair.spice').read_text())
    if devices!=i['devices'][candidate.VARIANT] or len(devices)!=808:
        raise ValueError('Original REQUEST-taper native circuit/observations changed')
    path=out/'0/bench.cir'
    if m['tasks']!=[dict(id='0',spec=i['spec'],deck_sha256=sha(path))] or path.read_text()!=fixture(out,i['spec'],devices):
        raise ValueError('Original full-trace boundary fixture changed')
    return m


def run(out):
    m=bound(out);i=m['identity']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial boundary experiment')
        atomic(out/'state.json',dict(status='running',qualified_phy=False));folder=out/'0';result=error=None
        try:
            with lease(ROOT,priority=1,label=CONTEXT+'_0'):
                bound(out,full=False)
                p=subprocess.run([sys.executable,str(ROOT/'scripts/run_native_binary_v2.py'),'-l',str(folder/'ngspice.log'),str(folder/'bench.cir')],capture_output=True,text=True)
            (folder/'console.log').write_text(p.stdout+p.stderr);p.check_returncode()
            result=dict(candidate.measure(folder,i,i['spec']),scope=SCOPE)
        except Exception as exception:error=str(exception)
        row=dict(task=m['tasks'][0],result=result,error=error,files={p.name:sha(p) for p in folder.iterdir() if p.is_file()})
        atomic(folder/'summary.json',row);bound(out)
        atomic(out/'summary.json',dict(rows=[row],boundary_point_passed=bool(result and result['hypothesis_point_checks_passed']),
            all_duties_or_pvt_covered=False,shared_wire_rc_qualified=False,qualified_phy=False,scope=SCOPE))
        atomic(out/'state.json',dict(status='complete',cases=1,errors=int(error is not None),qualified_phy=False))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('prepare');q.add_argument('parent',type=Path);q.add_argument('diagnosis',type=Path)
    q=sub.add_parser('run');q.add_argument('artifact',type=Path);a=p.parse_args()
    print(prepare(a.parent.resolve(),a.diagnosis.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
