#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exercise phase-error indication with the actual DLL and PFD electrical loads."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import numpy as np
from spice_engine import command,engine,provenance
from spice_library import library

ROOT=Path(__file__).resolve().parents[1]
REQ=json.loads((ROOT/'requirements.json').read_text())
OFFSETS_PS=(0,50,-50,150,-150,300,-300)


def metrics(wave,offset_ps):
    """A <=50 ps error is accepted; >=150 ps must produce a valid BAD high."""
    if (wave.ndim!=2 or wave.shape[1]!=8 or len(wave)<2 or
            not np.isfinite(wave).all() or wave[-1,1]<39.999e-9 or
            not np.all(np.diff(wave[:,1])>0)):
        return dict(passed=False,error='Incomplete or invalid phase-detector transient')
    a=wave[(wave[:,1]>20e-9)&(wave[:,1]<40e-9)]
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
    return dict(passed=bool(high>1.44 if expect_bad else high<.36),
        expected_bad=expect_bad,bad_min_v=low,bad_max_v=high,
        up_max_v=float(a[:,4].max()),dn_max_v=float(a[:,5].max()),
        error_max_v=float(a[:,6].max()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--extracted',action='store_true')
    p.add_argument('--corners',action='store_true')
    p.add_argument('--jobs',type=int,default=2)
    a=p.parse_args()
    if a.jobs<1:p.error('--jobs must be positive')
    lib,inputs,models=library(extracted=a.extracted,fast=False,designs={'openlvds_dll_analog','lvds_bias'})
    runner=Path(__file__).read_bytes();stamp=provenance()
    requirements=(ROOT/'requirements.json').read_bytes()
    recipe=hashlib.sha256(lib+runner+requirements+stamp.encode()).hexdigest()[:12]
    base=ROOT/'build/phase_detector'/('extracted' if a.extracted else 'schematic')/recipe
    base.mkdir(parents=True,exist_ok=True)
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    def run(case):
        corner,temp,offset=case
        out=base/f'{corner}_{temp}_{offset}ps';out.mkdir(exist_ok=True)
        lock=(out/'.run.lock').open('a')
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise RuntimeError(f'{out} is already running')
        (out/'library.spice').write_bytes(lib);(out/'producer.py').write_bytes(runner)
        cells='' if a.extracted else f'.include "{pdk}/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"\n'
        nodes=dict(CLK='0',PD_ENABLE='VDDD',PH0='PH0',PH90='PH90',PH180='PH180',PH270='PH270',
            FB='FB',PD_REF='PDREF',PHASE_BAD='BAD',UP='UP',DN='DN',ERR='ERR',PB='PB',VDDIO='VDDIO',VDDD='VDDD',VSS='0')
        ports=['CLK','PD_ENABLE','PH0','PH90','PH180','PH270','FB','PD_REF','PHASE_BAD','UP','DN','ERR','PB','VDDIO','VDDD','VSS']
        analog='XA '+' '.join(nodes[x] for x in ports)+' openlvds_dll_analog'
        pdnodes=dict(REF='REF',FB='FDB',RESET_N='RST',PD_ENABLE='VDDD',UP='UP',DN='DN',ERR='ERR',VDDD='VDDD',VSS='0',VGND='0',VPWR='VDDD')
        pdports=['REF','FB','RESET_N','PD_ENABLE','UP','DN','ERR','VDDD','VSS']
        detector='XP '+' '.join(pdnodes[x] for x in pdports)+' lvds_pfd'
        deck=f'''OpenLVDS phase-error response {corner} {temp}C {offset}ps
.lib "{pdk}/libs.tech/ngspice/sky130.lib.spice" {corner}
.include "{out}/library.spice"
{cells}VD VDDD 0 1.8
VA VDDIO 0 3.3
IB PB 0 35u
XB PB NB VDDIO 0 lvds_bias
VRST RST 0 PWL(0 0 2n 0 2.1n 1.8)
VR REF 0 PULSE(0 1.8 5n 100p 100p 1.15n 2.5n)
VF FDB 0 PULSE(0 1.8 {5+offset/1000:.9g}n 100p 100p 1.15n 2.5n)
{analog}
{detector}
CB BAD 0 20f
.options device temp={temp}
.options timeint method=gear reltol=1e-4 abstol=1e-12
.tran 5p 40n 0 20p
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
            result=metrics(np.array(rows),offset)
        result.update(corner=corner,temperature_c=temp,offset_ps=offset,extraction_inputs=inputs,
            simulator=engine(),simulator_provenance=stamp,requirements_sha256=hashlib.sha256(requirements).hexdigest(),
            files={name:hashlib.sha256((out/name).read_bytes()).hexdigest() for name in
                ['library.spice','producer.py','bench.cir']+(['bench.cir.prn'] if waveform.exists() else [])})
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        lock.close()
        print(out.name,result['passed'],flush=True)
        return out.name,result
    cases=[(c,t,o) for c in (REQ['process_corners'] if a.corners else ['tt'])
        for t in (REQ['temperatures_c'] if a.corners else [25]) for o in OFFSETS_PS]
    with ThreadPoolExecutor(a.jobs) as pool:results=dict(pool.map(run,cases))
    unchanged=provenance()==stamp and Path(__file__).read_bytes()==runner
    summary=dict(passed=unchanged and all(x['passed'] for x in results.values()),extracted=a.extracted,
        corners=a.corners,cases=results,artifact=str(base.relative_to(ROOT)))
    (base/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    raise SystemExit(0 if summary['passed'] else 1)


if __name__=='__main__':main()
