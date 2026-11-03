#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reuse completed AC calibration, reading frequency as the real scalar it is."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import numpy as np

import measure_driver_cm_impedance as original
import native_ac
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import provenance

ROOT=Path(__file__).resolve().parents[1]
sha=original.sha


def impedance(names,wave):
    # The complex binary record has padding in frequency's imaginary slot.
    # native_ac also uses frequency.real; it is not a complex voltage vector.
    f=wave[:,names.index('frequency')].real
    if (len(f)!=401 or not np.isfinite(wave).all() or
            not np.isclose(f[0],1e4,rtol=1e-9) or not np.isclose(f[-1],1e9,rtol=1e-9) or np.any(np.diff(f)<=0)):
        raise ValueError('Incomplete or invalid declared AC frequency grid')
    p,n=[wave[:,names.index('v('+node+')')] for node in ['p','n']]
    return f,(p+n)/2/2e-6,p-n


def measure(raw):
    names,w=native_ac.read_complex(raw);f,z,diff=impedance(names,w);i=int(np.argmax(abs(z)))
    return dict(peak_hz=float(f[i]),peak_common_mode_impedance_ohm=float(abs(z[i])),
        peak_phase_deg=float(np.angle(z[i],deg=True)),low_frequency_impedance_ohm=float(abs(z[0])),
        high_frequency_impedance_ohm=float(abs(z[-1])),peak_is_bracketed=bool(0<i<len(f)-1),
        differential_response_at_peak_v=float(abs(diff[i])),frequency_points=len(f),
        scope='Closed-loop impedance about one static DC state; not loop gain, phase margin or switching stability sign-off.')


def calibration(source):
    folder=source/'calibration';e=json.loads((folder/'bench.evidence.json').read_text())
    if (e.get('passed') is not True or e['simulator_provenance']!=provenance() or
            e['producer_sha256']!=sha(Path(native_ac.__file__)) or e['deck_sha256']!=sha(folder/'bench.cir') or
            e['raw_sha256']!=sha(folder/'bench.raw')):
        raise ValueError('Completed calibration evidence changed')
    names,w=native_ac.read_complex(folder/'bench.raw');f,z,_=impedance(names,w)
    exact=50/(1+2j*np.pi*f*100*2e-12);error=float(np.max(abs(z-exact)/abs(exact)))
    if error>1e-6: raise ValueError('Original completed analytic calibration failed')
    return dict(passed=True,max_relative_error=error,source_raw_sha256=sha(folder/'bench.raw'),
        reused_without_simulation=True,frequency_points=len(f),
        definition='Vcm divided by total 2 uA; two parallel 100 ohm/2 pF shunts')


def prepare(source):
    m=original.bound(source)
    if any((source/t['id']/'bench.raw').exists() for t in m['tasks']):
        raise ValueError('Only recover the calibration-only failure; retain all started driver AC runs')
    c=calibration(source)
    inputs=dict(m['identity']['inputs'])
    paths=[source/'manifest.json',source/'state.json']+[source/'calibration'/n for n in
        ['bench.cir','bench.raw','bench.log','bench.console.log','bench.evidence.json']]
    paths += [source/t['id']/n for t in m['tasks'] for n in t['files']]
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    code=dict(m['identity']['code']);code['recover_driver_cm_impedance.py']=sha(Path(__file__))
    identity=dict(source=str(source.relative_to(ROOT)),inputs=inputs,code=code,simulator=provenance(),
        scope=m['identity']['scope']+' Recovery changes only interpretation of the unused '
              'imaginary-frequency padding. Original successful passive calibration is '
              'remeasured without rerun; original producer, raw bytes and failure retained. '
              'The six driver AC cases have not previously started.')
    out=ROOT/'build/diagnostics/driver_cm_impedance_recovery'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);tasks=[]
    for task in m['tasks']:
        old=source/task['id'];folder=out/task['id'];folder.mkdir(exist_ok=True)
        deck=(old/'bench.cir').read_text();include=f'.include "{old}/source.spice"'
        if deck.count(include)!=1: raise ValueError('Unexpected original AC source include')
        for n,body in [('source.spice',(old/'source.spice').read_text()),('bench.cir',deck.replace(include,f'.include "{folder}/source.spice"'))]:
            path=folder/n
            if path.exists() and path.read_text()!=body: raise ValueError('Prepared AC recovery changed')
            if not path.exists():path.write_text(body)
        row={k:v for k,v in task.items() if k!='files'};row['files']={n:sha(folder/n) for n in task['files']};tasks.append(row)
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,calibration=c,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    expected=[(v,l) for v in original.VIEWS for l in [0.,1.8]]
    if (not out.is_relative_to(ROOT/'build/diagnostics/driver_cm_impedance_recovery') or
            out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
            [(t['view'],t['logic_v']) for t in m['tasks']]!=expected or provenance()!=i['simulator'] or
            any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items()) or
            any(sha(out/t['id']/n)!=h for t in m['tasks'] for n,h in t['files'].items())):
        raise ValueError('Common-mode AC recovery context changed')
    return m


def run(out):
    m=bound(out);stamp=sha(out/'manifest.json');previous=native_ac.slot
    try:
        native_ac.slot=lambda:lease(ROOT,priority=2,label='driver_cm_impedance_recovery')
        with (out/'.execution.lock').open('a+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            if (out/'state.json').exists() or any((out/t['id']/'bench.raw').exists() for t in m['tasks']):
                raise ValueError('Prior or partial driver AC recovery retained')
            if calibration(ROOT/m['identity']['source'])!=m['calibration']: raise ValueError('Reused AC calibration changed')
            rows=[]
            for task in m['tasks']:
                bound(out);atomic(out/'state.json',dict(status='running_'+task['id'],qualified_phy=False))
                raw=native_ac.run(out/task['id']/'bench.cir');bound(out)
                row=dict(task=task['id'],**measure(raw));capture_manifest(out/task['id']/'summary.json',row);rows.append(row)
            paths=[p for p in out.rglob('*') if p.is_file() and p.name not in ['.execution.lock','state.json','manifest.json','summary.json']]
            paths += [out/t['id']/'summary.json' for t in m['tasks']]
            capture_manifest(out/'summary.json',dict(results=rows,required=6,diagnostic_complete=True,
                calibration=m['calibration'],manifest_sha256=stamp,files={str(p.relative_to(out)):sha(p) for p in paths},
                qualified_phy=False,scope=m['identity']['scope']))
            atomic(out/'state.json',dict(status='completed_static_cm_impedance',qualified_phy=False))
    finally:native_ac.slot=previous


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
