#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Six fresh native-output pilots after compact driver GDS extraction and RC LVS."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np

import driver_geometric_shape as recipe
import extract_driver_compact as physical
import qualify_driver_output_shape_source as reference
from dll_campaign import atomic
from dll_measurements import read_wave, edges, average
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from spice_dispatch import lease
from spice_engine import command, engine, provenance
from spice_library import checked_netlist, replace
from spice_probes import ProbeNetwork

ROOT=Path(__file__).resolve().parents[1]
sha=physical.sha
POINTS=[('tt',25),('ss',25),('ff',40)]
CODE=['probe_driver_compact_native.py','extract_driver_compact.py','qualify_driver_output_shape_source.py',
      'probe_driver_output_shape.py','dll_measurements.py','dll_campaign.py','receiver_static_diagnosis.py',
      'spice_library.py','spice_probes.py','spice_scope.py','spice_dispatch.py','spice_engine.py','run_ngspice.py']


def fixture(deck,old,new):
    include=f'.include "{old}/source.spice"'
    if deck.count(include)!=1 or re.findall(r'(?im)^\.tran[^\n]+',deck)!=['.tran 1p 80n 0 1p']:
        raise ValueError('Require original complete 80 ns/1 ps fixture')
    prints=re.findall(r'(?im)^\.print tran[^\n]+',deck)
    if len(prints)!=1 or re.findall(r'(?im)^\.save[^\n]+',deck)!=['.save i(VIO) i(VDIG)']:
        raise ValueError('Require original voltage and real supply-current observations')
    return deck.replace(include,f'.include "{new}/source.spice"').replace(prints[0],'.print tran V(D) V(P) V(N)')


def prepare(parent):
    if engine()!='ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/driver_compact_extraction'):
        raise ValueError('Use compact-driver native extraction with pinned ngspice')
    r=json.loads((parent/'summary.json').read_text())
    if (parent.name!=hashlib.sha256(json.dumps(r['identity'],sort_keys=True).encode()).hexdigest()[:16] or
            r.get('passed') is not True or r['rc_audit']['passed'] is not True or
            any(sha(ROOT/n)!=h for n,h in r['files'].items())):
        raise ValueError('Require unchanged successful native extraction and RC audit')
    layout=ROOT/r['identity']['parent']
    # This verifies the physical producer, source proof chain, technology,
    # GDS and extraction files; it returns the existing complete receipt.
    if physical.run(layout)!=parent: raise ValueError('Extraction context changed')
    p=json.loads((layout/'summary.json').read_text())
    model=replace((layout/'candidate.spice').read_text(),physical.TOP,checked_netlist(r['extraction']))
    ready=[ROOT/n for n in p['identity']['inputs'] if Path(n).is_relative_to('build/diagnostics/driver_shape_source_verification') and Path(n).name=='summary.json']
    if len(ready)!=1: raise ValueError('Require full source readiness')
    source=ROOT/json.loads(ready[0].read_text())['campaign']
    tasks=[dict(id=f'{corner}_{temp}_{op}',process=corner,temperature=temp,op=op)
           for corner,temp in POINTS for op in reference.shape.CASES]
    inputs=dict(p['identity']['inputs'])
    inputs.update({str((layout/n).relative_to(ROOT)):h for n,h in p['files'].items()})
    inputs.update(r['files'])
    inputs.update({str((parent/'summary.json').relative_to(ROOT)):sha(parent/'summary.json'),
                   str((layout/'summary.json').relative_to(ROOT)):sha(layout/'summary.json'),
                   'requirements.json':sha(ROOT/'requirements.json')})
    for task in tasks:
        old=source/task['id']
        inputs.update({str((old/n).relative_to(ROOT)):sha(old/n) for n in ['source.spice','bench.cir']})
    code=dict(p['identity']['code'],**r['identity']['code'])
    code.update({n:sha(ROOT/'scripts'/n) for n in CODE})
    identity=dict(extraction=str(parent.relative_to(ROOT)),source=str(source.relative_to(ROOT)),
        points=[list(x) for x in POINTS],inputs=inputs,code=code,simulator=provenance(),
        scope='Six fresh native GDS-output pilots, TT25/SS25/FF40 and both initial polarities. '
              'Same full 80 ns/1 ps stimulus, fixed supplies/reference and original '
              '100 ohm plus 2 pF/pin load. Fresh DC and calibrated output edges, '
              'common-mode movement and actual supply power. Public outputs only; '
              'internal MOS stress, all-PVT native qualification, coupled PHY and '
              'generator certification remain separate gates.')
    out=ROOT/'build/diagnostics/driver_compact_native_pilot'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    with (out/'.preparation.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for task in tasks:
            folder=out/task['id'];folder.mkdir(exist_ok=True);old=source/task['id']
            deck=fixture((old/'bench.cir').read_text(),old,folder)
            ProbeNetwork(model).validate(deck,['D','P','N'])
            for name,text in [('source.spice',model),('bench.cir',deck)]:
                path=folder/name
                if path.exists() and path.read_text()!=text: raise ValueError('Native pilot preparation changed')
                if not path.exists(): path.write_text(text)
            task['files']={n:sha(folder/n) for n in ['source.spice','bench.cir']}
        capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False))
    return out


def measure(folder):
    w,h=read_wave(folder/'bench.cir.prn')
    if (len(w)<2 or not np.isfinite(w).all() or w[0,1]>1e-15 or
            w[-1,1]<80e-9-1e-12 or np.any(np.diff(w[:,1])<=0)):
        raise ValueError('Incomplete native 80 ns output trace')
    names,raw=read_raw(folder/'bench.raw')
    t=w[:,1]
    if not np.isfinite(raw).all() or not np.array_equal(raw[:,names.index('time')],t):
        raise ValueError('Native raw/export times differ')
    for pin in ['D','P','N']:
        if not np.array_equal(raw[:,names.index('v('+pin.lower()+')')],w[:,h['V('+pin+')']]):
            raise ValueError('Native public raw/export voltages differ')
    p,n=w[:,h['V(P)']],w[:,h['V(N)']]
    window=(t>=20e-9)&(t<=75e-9)
    cm=(p+n)/2
    rising=edges(t,p-n,level=0,rising=True)
    metrics=dict(common_mode_pp_v=float(np.ptp(cm[window])),
        common_mode_min_v=float(cm[window].min()),common_mode_max_v=float(cm[window].max()),
        differential_min_v=float((p-n)[window].min()),differential_max_v=float((p-n)[window].max()),
        rising_output_edges=int(np.count_nonzero((rising>=20e-9)&(rising<=75e-9))))
    at=np.r_[20e-9,t[(t>20e-9)&(t<75e-9)],75e-9]
    metrics['mean_supply_power_w']={rail:float(-voltage*average(at,np.interp(at,t,raw[:,names.index(name)])))
        for rail,voltage,name in [('io',3.3,'i(vio)'),('digital',1.8,'i(vdig)')]}
    return metrics,reference.shape.initial_dc(w,h)


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    expected=[dict(id=f'{p}_{t}_{op}',process=p,temperature=t,op=op) for p,t in POINTS for op in reference.shape.CASES]
    if (not out.is_relative_to(ROOT/'build/diagnostics/driver_compact_native_pilot') or
            out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
            i['points']!=[list(x) for x in POINTS] or
            [{k:v for k,v in t.items() if k!='files'} for t in m['tasks']]!=expected or
            provenance()!=i['simulator'] or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or
            any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
            any(sha(out/t['id']/n)!=h for t in m['tasks'] for n,h in t['files'].items())):
        raise ValueError('Native pilot context changed')
    return m


def aggregate(out,m,rows):
    req=json.loads((ROOT/'requirements.json').read_text());points=[]
    for process,temp in POINTS:
        pair=[r for r in rows if r['case'].startswith(f'{process}_{temp}_')]
        waveforms={};error=None
        try:
            if len(pair)!=2 or any(r['error'] is not None or r['metrics'] is None for r in pair):
                raise ValueError('Native pair incomplete')
            low,high=[r['initial_dc']['differential_v'] for r in pair]
            waveforms={r['task']:reference.shape.transitions(*read_wave(out/r['case']/'bench.cir.prn'),low,high) for r in pair}
        except (ValueError,OSError,KeyError) as caught: error=str(caught)
        points.append(dict(process=process,temperature=temp,calibrated_transitions=waveforms,error=error,
            passed=error is None and reference.pair_checks(pair,waveforms,req)))
    return dict(results=rows,pvt=points,required_cases=6,required_pvt=3,
        passed_pvt=sum(p['passed'] for p in points),native_output_pilot_passed=all(p['passed'] for p in points),
        manifest_sha256=sha(out/'manifest.json'),qualified_phy=False,physical_admission=False,scope=m['identity']['scope'])


def verify(out):
    m=bound(out);rows=[]
    for task in m['tasks']:
        folder=out/task['id'];row=json.loads((folder/'summary.json').read_text())
        if (row['case']!=task['id'] or row['task']!=task['op'] or row['returncode']!=0 or row['error'] is not None or
                row['manifest_sha256']!=sha(out/'manifest.json') or
                set(row['files'])!={'bench.raw','bench.cir.prn','ngspice.log','console.log'} or
                any(sha(folder/n)!=h for n,h in row['files'].items()) or
                measure(folder)!=(row['metrics'],row['initial_dc'])):
            raise ValueError('Native pilot output or remeasurement changed')
        rows.append(row)
    report=aggregate(out,m,rows)
    if report!=json.loads((out/'summary.json').read_text()): raise ValueError('Native pilot aggregate changed')
    bound(out)
    return report


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists() or any((out/t['id']/n).exists() for t in m['tasks'] for n in ['bench.raw','summary.json','ngspice.log']):
            raise ValueError('Prior or partial native pilot retained')
        atomic(out/'state.json',dict(status='running_native_output_pilot',qualified_phy=False))
        def execute(task):
            folder=out/task['id'];metrics=dc=result=None;error=None
            atomic(folder/'state.json',dict(status='waiting_for_slot'))
            try:
                with lease(ROOT,priority=2,label='compact_driver_'+task['id']):
                    bound(out)
                    atomic(folder/'state.json',dict(status='running'))
                    result=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(result.stdout+result.stderr)
                result.check_returncode();bound(out);metrics,dc=measure(folder)
            except Exception as caught: error=str(caught)
            row=dict(case=task['id'],task=task['op'],returncode=None if result is None else result.returncode,
                metrics=metrics,initial_dc=dc,error=error,manifest_sha256=stamp,qualified_phy=False,
                files={n:sha(folder/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (folder/n).exists()})
            capture_manifest(folder/'summary.json',row)
            atomic(folder/'state.json',dict(status='completed' if error is None else 'held_for_diagnosis'))
            return row
        with ThreadPoolExecutor(max_workers=2) as pool: rows=list(pool.map(execute,m['tasks']))
        bound(out);report=aggregate(out,m,rows);capture_manifest(out/'summary.json',report)
        atomic(out/'state.json',dict(status='completed_native_output_checks' if report['native_output_pilot_passed'] else 'held_native_output_checks',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','verify']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare': print(prepare(a.artifact.resolve()),flush=True)
    elif a.action=='run': run(a.artifact.resolve())
    else: print(json.dumps(verify(a.artifact.resolve())),flush=True)
