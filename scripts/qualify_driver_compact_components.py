#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Original thirty long driver fixtures with native bias and actual MOS voltages."""
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

import assemble_driver_compact_native as assembly
import driver_native_stress as stress
import qualify_driver_compact_native as qualification
import qualify_driver_restore_components as original
import observe_driver_waveform as dynamic
from dll_campaign import atomic
from dll_measurements import read_wave, average
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_library import library
from spice_probes import ProbeNetwork
from verify_component_evidence import check_case

ROOT=Path(__file__).resolve().parents[1]
sha=assembly.sha
CODE=['qualify_driver_compact_components.py','assemble_driver_compact_native.py','driver_native_stress.py',
      'qualify_driver_compact_native.py','qualify_driver_restore_components.py','observe_driver_waveform.py',
      'verify_analog.py','verify_component_evidence.py','evidence_scope.py','spice_probes.py']


def fixture(deck,old,new,model,view,observations):
    include=f'.include "{old}/source.spice"'
    transients=re.findall(r'(?im)^\.tran[^\n]+',deck)
    # The captured schematic SF0 fixture already uses the stricter 20 ps
    # maximum step. Preserve it exactly alongside the other 1 ns fixtures.
    if deck.count(include)!=1 or transients not in [['.tran 5p 2540n 0 1n'],['.tran 5p 2540n 0 20p']]:
        raise ValueError('Require the original complete 2540 ns long component fixture')
    prints=re.findall(r'(?im)^\.print tran[^\n]+',deck)
    if len(prints)!=1 or re.search(r'(?im)^\.save\b',deck): raise ValueError('Unexpected long fixture observations')
    voltages=re.findall(r'V\(([^)]+)\)',prints[0],re.I)
    if voltages[:3]!=['D','P','N'] or len(voltages)!=7: raise ValueError('Original long print order changed')
    leaves=['SINK','TOP','DP','DN']
    for node,leaf in zip(voltages[3:],leaves):
        if not re.fullmatch(r'XD:XCORE:(?:openlvds_driver_core__)?'+leaf+r'(?:\.t\d+)?',node):
            raise ValueError('Original internal component observation changed')
    if view not in ['schematic','native']: raise ValueError('Unknown component view')
    targets=['XD:XCORE:'+(observations[n]['native_node'] if view=='native' else n) for n in leaves]
    result=deck.replace(include,f'.include "{new}/source.spice"').replace(prints[0],
        '.print tran '+' '.join('V('+n+')' for n in voltages[:3]+targets))
    rows=stress.terminal_observations(model,result) if view=='native' else []
    if view=='native' and (len(rows)!=305 or sum(r['device'].startswith('XD:XCORE:') for r in rows)!=302 or
                           sum(r['device'].startswith('XD:XB:') for r in rows)!=3):
        raise ValueError('Require all 302 core and three native bias MOS devices')
    probes=stress.voltage_probes(rows)
    saved='.save i(VIO) i(VDIG)'+(' '+' '.join('V('+n+')' for n in probes) if probes else '')
    if result.splitlines().count('.end')!=1: raise ValueError('Unexpected component terminator')
    result=result.replace('.end',saved+'\n.end')
    ProbeNetwork(model).validate(result,voltages[:3]+targets+probes)
    return result,rows


def prepare(pilot,assembled):
    qualification.pilot_ready(pilot)
    pm=qualification.pilot.bound(pilot)
    a=json.loads((assembled/'summary.json').read_text())
    if (a.get('assembly_complete') is not True or a.get('component_reference_count')!=1 or
            a.get('two_core_endpoint_reference_count')!=1 or
            any(sha(assembled/n)!=h for n,h in a['files'].items()) or
            assembly.assemble(ROOT/a['identity']['extraction'])!=assembled):
        raise ValueError('Require unchanged native core/bias assembly')
    if pm['identity']['extraction']!=a['identity']['extraction']:
        raise ValueError('Native pilot and long component driver differ')
    req=json.loads((ROOT/'requirements.json').read_text())
    source=(ROOT/'analog/openlvds.spice').read_bytes()
    baseline,baseline_inputs,_=library(extracted=True,designs={assembly.TOP,'lvds_bias'})
    inputs=dict(pm['identity']['inputs'],**a['identity']['inputs'])
    inputs.update({str((assembled/n).relative_to(ROOT)):h for n,h in a['files'].items()})
    paths=[assembled/'summary.json',pilot/'manifest.json',pilot/'summary.json']
    for task in pm['tasks']:
        folder=pilot/task['id'];r=json.loads((folder/'summary.json').read_text())
        paths += [folder/n for n in set(task['files'])|set(r['files'])|{'summary.json'}]
    points=list(itertools.product(req['process_corners'],req['temperatures_c']))
    points.remove(('tt',25));points.insert(0,('tt',25))
    tasks=[]
    for corner,temp in points:
        for view in ['schematic','native']:
            old=ROOT/'build'/('analog' if view=='schematic' else 'analog_extracted')/f'driver_{corner}_{temp}'
            proof=check_case(old,'driver',source if view=='schematic' else baseline,
                {} if view=='schematic' else baseline_inputs,sha(ROOT/'scripts/verify_analog.py'),
                sha(ROOT/'requirements.json'),qualification.pilot.engine(),provenance())
            if proof.get('passed') is not True: raise ValueError('Original long driver evidence is stale or failed')
            paths += [old/n for n in ['bench.cir','source.spice','summary.json','bench.cir.prn','runner.py']]
            tasks.append(dict(id=f'{view}_driver_{corner}_{temp}',view=view,process=corner,temperature=temp,
                              original=str(old.relative_to(ROOT)),stop_seconds=2540e-9))
    original.check_coverage(tasks,req)
    inputs.update({str(n.relative_to(ROOT)):sha(n) for n in paths})
    code=dict(pm['identity']['code'],**a['identity']['code'])
    code.update({n:sha(ROOT/'scripts'/n) for n in CODE})
    identity=dict(pilot=str(pilot.relative_to(ROOT)),assembly=str(assembled.relative_to(ROOT)),inputs=inputs,
        code=code,simulator=provenance(),scope='Original thirty long component fixtures, source '
        'and native core plus native bias, five processes x 0/25/40 C. Unchanged '
        '2540 ns stimulus, original integration settings, 100 ohm and 2 pF/pin '
        'load, fixed supplies/reference. Original DC/eye checks plus long '
        'output-waveform reference observations. All 305 native MOS terminal '
        'voltages and real supply power recorded. Stress is sampled observation, '
        'not a reliability certificate. Separate 1 ps native output matrix '
        'remains required; no generator certification or PHY admission.')
    out=ROOT/'build/diagnostics/driver_compact_components'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for task in tasks:
            folder=out/task['id'];folder.mkdir(exist_ok=True)
            model=(assembled/('schematic.spice' if task['view']=='schematic' else 'native.spice')).read_text()
            old=ROOT/task['original'];deck,rows=fixture((old/'bench.cir').read_text(),old,folder,model,task['view'],a['observations'])
            for name,text in [('source.spice',model),('bench.cir',deck),('mos_observations.json',json.dumps(rows,sort_keys=True,indent=2)+'\n')]:
                path=folder/name
                if path.exists() and path.read_text()!=text: raise ValueError('Prepared long component changed')
                if not path.exists(): path.write_text(text)
            task['files']={n:sha(folder/n) for n in ['source.spice','bench.cir','mos_observations.json']}
        capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,required=30,qualified_phy=False))
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    original.check_coverage(m['tasks'],json.loads((ROOT/'requirements.json').read_text()))
    if (not out.is_relative_to(ROOT/'build/diagnostics/driver_compact_components') or
            out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
            provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or
            any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
            any(sha(out/t['id']/n)!=h for t in m['tasks'] for n,h in t['files'].items())):
        raise ValueError('Long component evidence or coverage changed')
    return m


def measure(folder,task):
    wave,h=read_wave(folder/'bench.cir.prn');names,raw=read_raw(folder/'bench.raw')
    metrics=original.measurements(wave,h,task['stop_seconds'])
    if (not np.isfinite(raw).all() or not np.array_equal(raw[:,names.index('time')],wave[:,1]) or
            not np.array_equal(wave[:,0],np.arange(len(raw)))):
        raise ValueError('Long raw/export samples differ')
    for name,col in h.items():
        if name.startswith('V(') and not np.array_equal(raw[:,names.index(name.replace(':','.').lower())],wave[:,col]):
            raise ValueError('Long raw/export voltages differ')
    observed=dynamic.measure(wave,h)
    metrics['waveform_reference']=observed
    metrics['original_component_passed']=metrics['passed']
    metrics['passed']=bool(metrics['passed'] and observed['transition_within_reference_limits'] and observed['common_mode_within_reference_limit'])
    t=wave[:,1];window=(t>2010e-9)&(t<2500e-9);at=np.r_[2010e-9,t[window],2500e-9]
    metrics['mean_supply_power_w']={rail:float(-voltage*average(at,np.interp(at,t,raw[:,names.index(n)])))
        for rail,voltage,n in [('io',3.3,'i(vio)'),('digital',1.8,'i(vdig)')]}
    rows=json.loads((folder/'mos_observations.json').read_text())
    if task['view']=='native': metrics['native_mos_stress']=stress.measure(names,raw,rows)
    elif rows: raise ValueError('Unexpected native MOS observations in source view')
    return metrics


def verify(out):
    m=bound(out);rows=[];stamp=sha(out/'manifest.json')
    for task in m['tasks']:
        folder=out/task['id'];row=json.loads((folder/'summary.json').read_text())
        if (row['task']!=task['id'] or row['returncode']!=0 or row['error'] is not None or
                row['manifest_sha256']!=stamp or set(row['files'])!={'bench.raw','bench.cir.prn','ngspice.log','console.log'} or
                any(sha(folder/n)!=h for n,h in row['files'].items()) or measure(folder,task)!=row['metrics']):
            raise ValueError('Long component output or independent remeasurement changed')
        rows.append(row)
    report=aggregate(m,stamp,rows)
    if report!=json.loads((out/'summary.json').read_text()): raise ValueError('Long component aggregate changed')
    bound(out);return report


def aggregate(m,stamp,rows):
    return dict(results=rows,required=30,passed_cases=sum(r['passed'] for r in rows),
        passed=len(rows)==30 and all(r['passed'] for r in rows),manifest_sha256=stamp,
        qualified_phy=False,physical_admission=False,scope=m['identity']['scope'])


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists() or any((out/t['id']/n).exists() for t in m['tasks'] for n in ['bench.raw','summary.json','ngspice.log']):
            raise ValueError('Prior or partial long component run retained')
        atomic(out/'state.json',dict(status='running_long_components',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];metrics=result=None;error=None
            atomic(folder/'state.json',dict(status='waiting_for_slot'))
            try:
                with lease(ROOT,priority=1,label='compact_component_'+task['id']):
                    bound(out);atomic(folder/'state.json',dict(status='running'))
                    result=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(result.stdout+result.stderr)
                result.check_returncode();bound(out);metrics=measure(folder,task)
            except Exception as caught: error=str(caught)
            row=dict(task=task['id'],returncode=None if result is None else result.returncode,metrics=metrics,
                error=error,passed=error is None and metrics is not None and metrics['passed'],manifest_sha256=stamp,qualified_phy=False,
                files={n:sha(folder/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (folder/n).exists()})
            capture_manifest(folder/'summary.json',row)
            atomic(folder/'state.json',dict(status='completed' if error is None else 'held_for_diagnosis'))
            return row
        with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(execute,m['tasks']))
        bound(out);report=aggregate(m,stamp,rows);capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='completed_long_components' if report['passed'] else 'held_long_components',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path);p.add_argument('--assembly',type=Path);a=p.parse_args()
    if a.action=='prepare':
        if a.assembly is None:p.error('--assembly required')
        print(prepare(a.artifact.resolve(),a.assembly.resolve()),flush=True)
    elif a.action=='run':run(a.artifact.resolve())
    else:print(json.dumps(verify(a.artifact.resolve())),flush=True)
