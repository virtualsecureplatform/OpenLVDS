#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Bounded source controls separating complementary gate drive from bridge/CMFB behavior."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from dll_campaign import atomic,text_block
from dll_measurements import read_wave,edges
from receiver_static_diagnosis import capture_manifest
from spice_library import replace
from spice_dispatch import lease
from spice_engine import command,engine,provenance

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_driver_core'
CASES=['baseline','balanced_100ps','balanced_400ps']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def stimulus(ramp_ps,complement=False,rail=1.8):
    points=[(0,rail if complement else 0)]
    for i in range(56):
        at=10+i*1.25;before=bool(i%2);after=not before
        if complement:before,after=not before,not after
        points += [(at-ramp_ps/2000,rail*before),(at+ramp_ps/2000,rail*after)]
    return 'PWL('+' '.join(f'{t:.12g}n {v:.12g}' for t,v in points)+')'


def model(source,case):
    if case not in CASES:raise ValueError('Use a bounded gate-drive control')
    if case=='baseline':return source
    block=text_block(source,TOP)
    expected='XLS D DP DN NB VDDIO VDDD VSS lvds_shift18_33_restore_64_24'
    if block.splitlines().count(expected)!=1:raise ValueError('Original restoration converter changed')
    ramp=100 if case=='balanced_100ps' else 400
    replacement='VCONTROL_DP DP VSS '+stimulus(ramp,rail=3.3)+'\nVCONTROL_DN DN VSS '+stimulus(ramp,complement=True,rail=3.3)
    return replace(source,TOP,block.replace(expected,replacement))


def fixture(original,old,new):
    include=f'.include "{old}/source.spice"'
    if original.count(include)!=1:raise ValueError('Expected original component source binding')
    result=original.replace(include,f'.include "{new}/source.spice"')
    rows=re.findall(r'(?m)^VD D 0 [^\n]+',result)
    if len(rows)!=1:raise ValueError('Expected original driver logic source')
    result=result.replace(rows[0],'VD D 0 '+stimulus(100))
    if re.findall(r'(?im)^\.tran[^\n]+',result)!=['.tran 5p 2540n 0 1n']:raise ValueError('Original component transient changed')
    result=result.replace('.tran 5p 2540n 0 1n','.tran 1p 80n 0 1p')
    prints=re.findall(r'(?im)^\.print tran[^\n]+',result)
    if len(prints)!=1:raise ValueError('Expected one original voltage print')
    result=result.replace(prints[0],'.print tran V(D) V(P) V(N) V(XD:XCORE:DP) V(XD:XCORE:DN) V(XD:XCORE:TOP) V(XD:XCORE:BOT) V(XD:XCORE:SINK)')
    return result


def measure(w,h):
    t=w[:,1]
    if t[0]>1e-15 or t[-1]<80e-9-1e-12:raise ValueError('Incomplete balance control')
    v=lambda n:w[:,h['V('+n+')']]
    keep=(t>=20e-9)&(t<=75e-9);cm=(v('P')+v('N'))/2;diff=v('P')-v('N')
    gate_sum=v('XD:XCORE:DP')+v('XD:XCORE:DN')
    crossings=edges(t,diff,level=0,rising=True);crossings=crossings[(crossings>=20e-9)&(crossings<=75e-9)]
    records=[]
    for label,index in [('minimum',np.flatnonzero(keep)[np.argmin(cm[keep])]),('maximum',np.flatnonzero(keep)[np.argmax(cm[keep])])]:
        records.append(dict(extreme=label,time_ns=float(t[index]*1e9),common_mode_v=float(cm[index]),
            nodes={n:float(v(n)[index]) for n in ['P','N','XD:XCORE:DP','XD:XCORE:DN','XD:XCORE:TOP','XD:XCORE:BOT','XD:XCORE:SINK']}))
    return dict(common_mode_pp_v=float(np.ptp(cm[keep])),common_mode_min_v=float(cm[keep].min()),common_mode_max_v=float(cm[keep].max()),
        differential_min_v=float(diff[keep].min()),differential_max_v=float(diff[keep].max()),rising_output_edges=len(crossings),
        complement_sum_error_max_v=float(np.max(abs(gate_sum[keep]-3.3))),extrema=records,qualified_phy=False)


def prepare(observation):
    if engine()!='ngspice' or not observation.is_relative_to(ROOT/'build/diagnostics/driver_waveform_observation'):raise ValueError('Use completed loaded waveform observation in pinned ngspice')
    om=json.loads((observation/'manifest.json').read_text());oi=om['identity'];summary=json.loads((observation/'summary.json').read_text())
    if summary.get('observed')!=30 or summary.get('manifest_sha256')!=sha(observation/'manifest.json'):raise ValueError('Require complete waveform observation')
    if any(sha(ROOT/n)!=h for n,h in oi['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in oi['code'].items()):raise ValueError('Waveform observation changed')
    campaign=ROOT/oi['campaign'];old=campaign/'schematic_driver_tt_25';m=json.loads((campaign/'manifest.json').read_text())
    task=next(t for t in m['tasks'] if t['id']=='schematic_driver_tt_25')
    if any(sha(old/n)!=h for n,h in task['files'].items()):raise ValueError('Original source fixture changed')
    source=(old/'source.spice').read_text()
    # Confirm the selected current correction before using its source-level controls.
    if 'XIT10 TOP PB VDDIO VDDIO sky130_fd_pr__pfet_g5v0d10v5 w=20 l=1' not in text_block(source,TOP):raise ValueError('Require corrected 110:1 driver')
    paths=[observation/'manifest.json',observation/'summary.json',campaign/'manifest.json',old/'source.spice',old/'bench.cir']
    names=['isolate_driver_balance.py','dll_campaign.py','dll_measurements.py','receiver_static_diagnosis.py','spice_library.py','spice_dispatch.py','spice_engine.py','run_ngspice.py']
    identity=dict(observation=str(observation.relative_to(ROOT)),inputs={**oi['inputs'],**{str(p.relative_to(ROOT)):sha(p) for p in paths}},
        code={n:sha(ROOT/'scripts'/n) for n in names},simulator=provenance(),scope='TT25 source-level causal controls only. Same corrected 110:1 bridge, CMFB, fixed rails/reference, 100 ohm plus 2 pF/pin load, reset-free DC start and 80 ns/1 ps fixture. Baseline retains original converter; ideal 100/400 ps complementary 3.3 V gates replace XLS only in diagnostic controls. No extracted-layout, gate-current, compliance or PHY admission.')
    out=ROOT/'build/diagnostics/driver_balance_isolation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True);tasks=[]
    for case in CASES:
        folder=out/case;folder.mkdir(exist_ok=True)
        for n,body in [('source.spice',model(source,case)),('bench.cir',fixture((old/'bench.cir').read_text(),old,folder))]:
            p=folder/n
            if p.exists() and p.read_text()!=body:raise ValueError('Prepared control changed')
            if not p.exists():p.write_text(body)
        tasks.append(dict(id=case,files={n:sha(folder/n) for n in ['source.spice','bench.cir']}))
    capture_manifest(out/'manifest.json',dict(identity=identity,tasks=tasks,qualified_phy=False));return out


def run(out):
    if not out.is_relative_to(ROOT/'build/diagnostics/driver_balance_isolation'):raise ValueError('Use prepared driver balance controls')
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];stamp=sha(out/'manifest.json')
    def unchanged():
        if (sha(out/'manifest.json')!=stamp or provenance()!=i['simulator'] or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16] or
                any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(ROOT/'scripts'/n)!=h for n,h in i['code'].items())):raise ValueError('Driver balance context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        if [t['id'] for t in m['tasks']]!=CASES:raise ValueError('Incomplete control coverage')
        if (out/'state.json').exists():raise ValueError('Prior balance campaign retained')
        results=[]
        for task in m['tasks']:
            folder=out/task['id']
            if any(sha(folder/n)!=h for n,h in task['files'].items()):raise ValueError('Control fixture changed')
            if any((folder/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log','summary.json']):raise ValueError('Partial balance control retained')
            atomic(out/'state.json',dict(status='waiting_'+task['id'],qualified_phy=False))
            with lease(ROOT,priority=2,label='driver_balance_'+task['id']):
                unchanged();atomic(out/'state.json',dict(status='running_'+task['id'],qualified_phy=False))
                p=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
            (folder/'console.log').write_text(p.stdout+p.stderr);unchanged();metrics=None
            if p.returncode==0:metrics=measure(*read_wave(folder/'bench.cir.prn'))
            result=dict(task=task['id'],returncode=p.returncode,metrics=metrics,qualified_phy=False,manifest_sha256=stamp,
                files={n:sha(folder/n) for n in ['bench.raw','bench.cir.prn','ngspice.log','console.log'] if (folder/n).exists()})
            capture_manifest(folder/'summary.json',result);results.append(result)
            if metrics is None:break
        capture_manifest(out/'summary.json',dict(results=results,diagnostic_complete=len(results)==3 and all(r['metrics'] is not None for r in results),manifest_sha256=stamp,qualified_phy=False,scope=i['scope']))
        atomic(out/'state.json',dict(status='completed_diagnostic' if len(results)==3 and results[-1]['metrics'] is not None else 'held_numerical_failure',qualified_phy=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.artifact.resolve()),flush=True)
    else:run(a.artifact.resolve())
