#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Resize only the added output MIM from 3x3 to 5x5 at the measured startup peak."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import probe_request_taper_counter_v317 as candidate
import probe_request_taper_output_shunt_v331 as boundary
from native_binary_raw_v2 import validate
from diagnose_shared_counter_v200 import terminal_peak
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT=candidate.ROOT
VERSION='request-taper-low0-extra-5x5-output-mim-startup-repair-v332.1'
CONTEXT='request_taper_output_shunt_v332'
sha=candidate.sha
atomic=candidate.atomic
SCOPE=('Resize the additional native MIM from 3x3 to 5x5 on low0 setter output of the unchanged 808-MOS '
       'REQUEST-taper counter; SS0/410MHz/40% stopped-low full 26ns original gates; '
       'component RC and ideal new shared wire only, added shunt geometry/RC and '
       'other duty/stopped-level/PVT/PHY qualification remain required')
CAP='sky130_fd_pr__cap_mim_m3_1'
SHUNT='Xlow0_output_extra_v331 low0_sn VGND '+CAP+' w=5 l=5'


def transform(cells,module,devices):
    core=candidate.source.CORE
    old=candidate.source.cell_definition(cells,core)
    if old.splitlines().count(boundary.SHUNT)!=1 or SHUNT in old:
        raise ValueError('Require exactly the existing 3x3 output shunt')
    result=cells.replace(old,old.replace(boundary.SHUNT,SHUNT,1),1)
    if candidate.source.observations(result,module)!=devices or len(devices)!=808:
        raise ValueError('All original 808 native MOS terminal maps must remain unchanged')
    return result,module


def specification():
    return dict(candidate.specifications()[0],duty=.4)


def fixture(out,spec,devices):
    text=candidate.fixture(out,spec,devices)
    old='OpenLVDS '+candidate.VERSION+'\n'
    if not text.startswith(old):raise ValueError('Original native fixture title changed')
    return text.replace(old,'OpenLVDS '+VERSION+'\n',1)


def require_cause(parent,evidence):
    m=boundary.bound(parent);i=m['identity'];folder=parent/'0'
    row=json.loads((folder/'summary.json').read_text())
    if json.loads((parent/'state.json').read_text())!=dict(status='complete',cases=1,errors=0,qualified_phy=False):
        raise ValueError('Require terminal complete original 3x3 output-shunt trial')
    report=json.loads((evidence/'summary.json').read_text())
    if (row['task']!=m['tasks'][0] or row['error'] is not None or row['result'] is None
            or report.get('all_original_native_metrics_reproduced') is not True
            or report.get('all_stored_failed_peaks_reproduced') is not True
            or report.get('parameters_changed') is not False or report.get('native_mos')!=808
            or report['case']!=str(folder.relative_to(ROOT))
            or any(sha(ROOT/n)!=h for n,h in report['inputs'].items())
            or any(sha(folder/n)!=h for n,h in row['files'].items())):
        raise ValueError('Require exact completed native 40% output-stress replay')
    measured=dict(candidate.measure(folder,i,i['spec']),scope=boundary.SCOPE)
    if measured!=row['result']:raise ValueError('Original full native metrics changed')
    failed={d['device'] for d in measured['terminal_stress'] if not d['passed']}
    faults=report['failed_devices'];groups={}
    for d in faults:
        group=d['device'].split(':')[2];groups[group]=groups.get(group,0)+1
    worst=max(faults,key=lambda d:d['peak_v'])
    if ({d['device'] for d in faults}!=failed or len(faults)!=16
            or groups!={'Xlow0_q':8,'Xlow0_set_pair':8}
            or worst['device']!='XD:XR:Xlow0_set_pair:X11'
            or worst['worst_pair']!=['D','B'] or worst['peak_v']<=1.95
            or not 3400<worst['time_ps']<4000
            or not all(measured[k] for k in ('held_before_request_passed',
                'stopped_clock_clear_and_reassert_passed','phase_arming_passed',
                'stopped_clock_arm_clear_passed','alternating_phase_order_passed',
                'stopped_clock_intermediate_clear_passed'))):
        raise ValueError('Require the measured 16 setter/storage startup faults with passing function')
    paths=[evidence/'summary.json',parent/'state.json',parent/'summary.json',folder/'summary.json',*[folder/n for n in row['files']],
           *[ROOT/n for n in report['inputs']]]
    return m,dict(groups=groups,worst=worst),paths


def prepare(parent,evidence):
    m,cause,paths=require_cause(parent,evidence);i=m['identity']
    cells,module=transform((parent/'cells.spice').read_text(),(parent/'pair.spice').read_text(),
                           i['devices'][candidate.VARIANT])
    paths += [parent/'manifest.json',*[parent/n for n in m['libraries']],*[ROOT/n for n in i['inputs']]]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))}
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),diagnosis=str(evidence.relative_to(ROOT)),
        cause=cause,spec=specification(),devices=i['devices'],
        library_sha256={n:hashlib.sha256(t.encode()).hexdigest() for n,t in [('cells.spice',cells),('pair.spice',module)]},
        added_native_mim=dict(model=CAP,width_um=5,length_um=5,connected_nodes=['low0_sn','VGND'],
            original_mims=57,total_mims=57,prior_width_um=3,prior_length_um=3,geometry_qualified=False,shared_wire_rc_qualified=False),
        simulator=i['simulator'],pdk_files=i['pdk_files'],external_files=i['external_files'],
        inputs=inputs,guards=candidate.guard_inputs(inputs),max_workers=1,priority=1,scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'cells.spice').write_text(cells);(out/'pair.spice').write_text(module)
    folder=out/'0';folder.mkdir();(folder/'bench.cir').write_text(fixture(out,identity['spec'],identity['devices'][candidate.VARIANT]))
    task=dict(id='0',spec=identity['spec'],deck_sha256=sha(folder/'bench.cir'))
    atomic(out/'manifest.json',dict(identity=identity,tasks=[task],libraries=identity['library_sha256'],qualified_phy=False))
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
        raise ValueError('Output-shunt hypothesis context changed')
    parent=ROOT/i['parent']
    expected=transform((parent/'cells.spice').read_text(),(parent/'pair.spice').read_text(),i['devices'][candidate.VARIANT])
    if expected!=((out/'cells.spice').read_text(),(out/'pair.spice').read_text()):
        raise ValueError('Single added-MIM dimension transformation changed')
    devices=candidate.source.observations(*expected)
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
