#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise phase-error indication with the actual DLL and PFD electrical loads."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import numpy as np
from spice_engine import command,engine,provenance
from spice_library import library

ROOT=Path(__file__).resolve().parents[1]
REQ=json.loads((ROOT/'requirements.json').read_text())
OFFSETS_PS=(0,50,-50,150,-150,300,-300)


def pulse_metrics(time,reference,bad,window_start_s=20e-9,window_end_s=40e-9):
    def crossings(values,level,rising):
        high=values>=level
        i=np.flatnonzero((~high[:-1]&high[1:]) if rising else (high[:-1]&~high[1:]))
        return time[i]+(level-values[i])*(time[i+1]-time[i])/(values[i+1]-values[i])
    ref=crossings(reference,.9,True)
    if len(ref)<3:return dict(passed=False,error='Missing reference cycles')
    period=float(np.median(np.diff(ref)))
    anchors=ref[(ref>window_start_s+period/2)&(ref<window_end_s-period/2)]
    starts=list(crossings(bad,1.44,True));ends=list(crossings(bad,1.44,False))
    if bad[0]>=1.44:starts.insert(0,float(time[0]))
    if bad[-1]>=1.44:ends.append(float(time[-1]))
    segments=list(zip(starts,ends));events=crossings(bad,.9,True)
    counts=[];valid=[];widths=[]
    for at in anchors:
        lo,hi=at-period/2,at+period/2
        counts.append(int(((events>=lo)&(events<hi)).sum()))
        overlapping=[(end-start)*1e12 for start,end in segments if start<hi and end>lo]
        valid.append(bool(overlapping) and min(overlapping)>=200)
        widths.extend(overlapping)
    return dict(passed=bool(len(anchors) and all(valid) and max(counts)<=1),
        reference_cycles=len(anchors),events_per_cycle_max=max(counts) if counts else None,
        valid_high_min_ps=min(widths) if widths else None)


def metrics(wave,offset_ps,window_start_s=20e-9,window_end_s=40e-9):
    """A <=50 ps error is accepted; >=150 ps must produce a valid BAD high."""
    if (wave.ndim!=2 or wave.shape[1]!=8 or len(wave)<2 or
            not np.isfinite(wave).all() or not np.isfinite([window_start_s,window_end_s]).all() or
            window_start_s<0 or window_end_s<=window_start_s or
            wave[0,1]>window_start_s or wave[-1,1]<window_end_s-1e-12 or
            not np.all(np.diff(wave[:,1])>0)):
        return dict(passed=False,error='Incomplete or invalid phase-detector transient')
    a=wave[(wave[:,1]>window_start_s)&(wave[:,1]<window_end_s)]
    def rises(col):
        v=a[:,col];t=a[:,1]
        i=np.flatnonzero((v[:-1]<.9)&(v[1:]>=.9))
        return t[i]+(.9-v[i])*(t[i+1]-t[i])/(v[i+1]-v[i])
    ref=rises(2);fb=rises(3)
    if len(ref)<7 or len(fb)<7:
        return dict(passed=False,error='Missing detector input cycles')
    observed=np.array([fb[np.argmin(abs(fb-t))]-t for t in ref[1:-1]])
    if np.max(abs(observed-offset_ps*1e-12))>5e-12:
        return dict(passed=False,error='Detector input phase differs from the requested case')
    bad=a[:,7];expect_bad=abs(offset_ps)>=150
    low=float(bad.min());high=float(bad.max())
    pulses=pulse_metrics(wave[:,1],wave[:,2],wave[:,7],window_start_s,window_end_s) if expect_bad else None
    return dict(passed=bool(high>1.44 and pulses['passed'] if expect_bad else high<.36),
        pulse_response=pulses,
        expected_bad=expect_bad,bad_min_v=low,bad_max_v=high,
        up_max_v=float(a[:,4].max()),dn_max_v=float(a[:,5].max()),
        error_max_v=float(a[:,6].max()))



def response_cases(corners=False,slew_corners=False):
    if slew_corners:
        return [(c,t,o,sr,sf) for c,t in [('tt',25),('ss',40),('ff',0),('fs',0),('sf',40)]
                for sr,sf in [(20,200),(200,20)] for o in OFFSETS_PS]
    return [(c,t,o,100,100) for c in (REQ['process_corners'] if corners else ['tt'])
            for t in (REQ['temperatures_c'] if corners else [25]) for o in OFFSETS_PS]


def library_ports(lib,name):
    match=re.search(r'(?im)^\.subckt[ \t]+'+re.escape(name)+r'[ \t]+([^\n]*(?:\n\+[^\n]*)*)',lib.decode())
    if not match:raise ValueError('Missing subcircuit '+name)
    return match[1].replace('\n+',' ').split()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--extracted',action='store_true')
    group=p.add_mutually_exclusive_group()
    group.add_argument('--corners',action='store_true')
    group.add_argument('--slew-corners',action='store_true')
    p.add_argument('--settle-ns',type=float,default=120)
    p.add_argument('--measure-ns',type=float,default=40)
    p.add_argument('--jobs',type=int,default=2)
    a=p.parse_args()
    if a.jobs<1:p.error('--jobs must be positive')
    if not np.isfinite([a.settle_ns,a.measure_ns]).all() or a.settle_ns<0 or a.measure_ns<20:
        p.error('Settling must be nonnegative and measurement at least 20 ns')
    stop_ns=a.settle_ns+a.measure_ns
    lib,inputs,models=library(extracted=a.extracted,fast=False,designs={'openlvds_dll_analog','lvds_bias'})
    runner=Path(__file__).read_bytes();stamp=provenance()
    requirements=(ROOT/'requirements.json').read_bytes()
    recipe=hashlib.sha256(lib+runner+requirements+stamp.encode()+json.dumps(dict(settle_ns=a.settle_ns,measure_ns=a.measure_ns,slew_corners=a.slew_corners),sort_keys=True).encode()).hexdigest()[:12]
    base=ROOT/'build/phase_detector'/('extracted' if a.extracted else 'schematic')/recipe
    base.mkdir(parents=True,exist_ok=True)
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    def run(case):
        corner,temp,offset,sr,sf=case
        out=base/f'{corner}_{temp}_{offset}ps_r{sr}_f{sf}';out.mkdir(exist_ok=True)
        lock=(out/'.run.lock').open('a')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError(f'{out} is already running')
        (out/'library.spice').write_bytes(lib);(out/'producer.py').write_bytes(runner)
        cells='' if a.extracted else f'.include "{pdk}/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"\n'
        nodes=dict(CLK='0',PD_ENABLE='VDDD',PH0='PH0',PH90='PH90',PH180='PH180',PH270='PH270',
            FB='FB',PD_REF='PDREF',PHASE_BAD='BAD',UP='UP',DN='DN',ERR='ERR',PB='PB',VDDIO='VDDIO',VDDD='VDDD',VSS='0',QREF='QREF',QFB='QFB',QWIN='QWIN',SENSE_REF='REF',SENSE_FB='FDB',SENSE_WINDOW='WINDOW')
        ports=library_ports(lib,'openlvds_dll_analog')
        analog='XA '+' '.join(nodes[x] for x in ports)+' openlvds_dll_analog'
        pdnodes=dict(REF='REF',FB='FDB',RESET_N='RST',PD_ENABLE='VDDD',UP='UP',DN='DN',ERR='ERR',VDDD='VDDD',VSS='0',VGND='0',VPWR='VDDD',QREF='QREF',QFB='QFB',QWIN='QWIN')
        pdports=library_ports(lib,'lvds_pfd')
        detector='XP '+' '.join(pdnodes[x] for x in pdports)+' lvds_pfd'
        deck=f'''OpenLVDS phase-error response {corner} {temp}C {offset}ps
.lib "{pdk}/libs.tech/ngspice/sky130.lib.spice" {corner}
.include "{out}/library.spice"
{cells}VD VDDD 0 1.8
VA VDDIO 0 3.3
IB PB 0 35u
XB PB NB VDDIO 0 lvds_bias
VRST RST 0 PWL(0 0 2n 0 2.1n 1.8)
VR REF 0 PULSE(0 1.8 5n {sr}p {sr}p {1.25-sr/1000:.9g}n 2.5n)
VF FDB 0 PULSE(0 1.8 {5+offset/1000+(sr-sf)/2000:.9g}n {sf}p {sf}p {1.25-sf/1000:.9g}n 2.5n)
VW WINDOW 0 PULSE(0 1.8 4.2n {sr}p {sr}p {1.25-sr/1000:.9g}n 2.5n)
{analog}
{detector}
CB BAD 0 20f
.options device temp={temp}
.options timeint method=gear reltol=1e-4 abstol=1e-12
.tran 5p {stop_ns:.9g}n 0 20p
.print tran V(REF) V(FDB) V(UP) V(DN) V(ERR) V(BAD)
.end
'''
        path=out/'bench.cir';path.write_text(deck)
        r=subprocess.run(command(out/(engine()+'.log'),path),cwd=out,capture_output=True,text=True)
        (out/'console.log').write_text(r.stdout+r.stderr)
        result=dict(passed=False,error='Simulator failed',returncode=r.returncode)
        waveform=out/'bench.cir.prn'
        if not r.returncode and waveform.exists():
            rows=[]
            for line in waveform.read_text().splitlines():
                try:rows.append(list(map(float,line.split())))
                except ValueError:pass
            result=metrics(np.array(rows),offset,a.settle_ns*1e-9,stop_ns*1e-9)
        result.update(corner=corner,temperature_c=temp,offset_ps=offset,reference_slew_ps=sr,feedback_slew_ps=sf,measurement_window_ns=[a.settle_ns,stop_ns],extraction_inputs=inputs,
            simulator=engine(),simulator_provenance=stamp,requirements_sha256=hashlib.sha256(requirements).hexdigest(),
            files={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in
                ['library.spice','producer.py','bench.cir']+(['bench.cir.prn'] if waveform.exists() else [])})
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        lock.close()
        print(out.name,result['passed'],flush=True)
        return out.name,result
    cases=response_cases(a.corners,a.slew_corners)
    with ThreadPoolExecutor(a.jobs) as pool:results=dict(pool.map(run,cases))
    unchanged=provenance()==stamp and Path(__file__).read_bytes()==runner
    summary=dict(passed=unchanged and all(x['passed'] for x in results.values()),extracted=a.extracted,
        corners=a.corners,slew_corners=a.slew_corners,cases=results,artifact=str(base.relative_to(ROOT)))
    (base/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    raise SystemExit(0 if summary['passed'] else 1)


if __name__=='__main__':main()
