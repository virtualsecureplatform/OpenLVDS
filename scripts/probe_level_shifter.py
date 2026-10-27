#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Short, explicitly diagnostic check of both controls inside the extracted driver."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from spice_library import library
from spice_engine import command,engine

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--full-rc',action='store_true')
    parser.add_argument('--settled-start',action='store_true');args=parser.parse_args()
    lib,inputs,_=library(extracted=True,fast=not args.full_rc,designs={'openlvds_driver_core','lvds_bias'})
    out=ROOT/'build/diagnostics/level_shifter'/(hashlib.sha256(lib).hexdigest()[:12]+('_dc' if args.settled_start else ''))
    out.mkdir(parents=True,exist_ok=True);(out/'library.spice').write_bytes(lib)
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    nodes=['D','XD:XCORE:openlvds_driver_core__DP','XD:XCORE:openlvds_driver_core__DN',
           'XD:XCORE:openlvds_driver_core__XLS__L','XD:XCORE:openlvds_driver_core__XLS__R',
           *['XD:XCORE:openlvds_driver_core__XLS__'+n for n in ['AD','AB','INB']]]
    deck=out/'bench.cir';deck.write_text(f'''OpenLVDS extracted level-shifter DIAGNOSTIC
.lib "{pdk}" tt
.include "{out}/library.spice"
.options device temp=25
.options timeint method=gear reltol=1e-4 abstol=1e-12
VIO VDDIO 0 PWL(0 0 1n 3.3)
VDIG VDDD 0 PWL(0 0 1n 1.8)
VREF VREF 0 PWL(0 0 1n 1.2)
IREF IREF 0 PWL(0 0 1n 35u)
VD D 0 PULSE(0 1.8 5n 100p 100p 1.15n 2.5n)
XD D P N VREF IREF VDDIO VDDD 0 openlvds_driver
RT P N 100
CP P 0 2p
CN N 0 2p
.tran 10p 60n 0 100p
.print tran {' '.join('V('+n+')' for n in nodes)}
.end
''')
    if args.settled_start:
        import re
        deck.write_text(re.sub(r'PWL\(0 0 1n (3\.3|1\.8|1\.2|35u)\)',r'\1',deck.read_text()))
    result=subprocess.run(command(out/(engine()+'.log'),deck),cwd=out,capture_output=True,text=True)
    (out/'console.log').write_text(result.stdout+result.stderr)
    summary=dict(passed=False,diagnostic=True,inputs=inputs,simulator=engine(),returncode=result.returncode,
                 network='full distributed RC' if args.full_rc else 'unqualified TICER candidate',
                 startup='solved fixed-supply DC operating point' if args.settled_start else '1 ns supply and reference ramp')
    if not result.returncode:
        rows=[]
        for line in Path(str(deck)+'.prn').read_text().splitlines():
            try:rows.append(list(map(float,line.split())))
            except ValueError:pass
        wave=np.array(rows);window=wave[:,1]>20e-9;metrics=[]
        for col,name in enumerate(nodes[1:],3):
            v=wave[window,col];t=wave[window,1]
            threshold=.9 if name.rsplit('__',1)[-1] in ['AD','AB','INB'] else 1.65
            i=np.where((v[:-1]-threshold)*(v[1:]-threshold)<0)[0]
            crossings=t[i]+(threshold-v[i])*(t[i+1]-t[i])/(v[i+1]-v[i])
            rise=crossings[v[i+1]>v[i]];fall=crossings[v[i+1]<v[i]];width=[]
            for at in rise:
                following=fall[fall>at]
                if len(following):width.append((following[0]-at)*1e9)
            metrics.append(dict(node=name,min_v=float(v.min()),max_v=float(v.max()),edges=len(i),
                high_width_min_ns=min(width) if width else None,high_width_max_ns=max(width) if width else None))
        summary['nodes']=metrics
        # Full voltage swing alone is insufficient: a restoring inverter can
        # emit narrow pulses with a long interval when both bridge controls
        # are off. Measure the intervals between interpolated threshold events.
        t=wave[window,1];controls=wave[window,3:5];events=[]
        state=list(controls[0]>1.65)
        for channel in range(2):
            v=controls[:,channel]
            for i in np.where((v[:-1]-1.65)*(v[1:]-1.65)<0)[0]:
                at=t[i]+(1.65-v[i])*(t[i+1]-t[i])/(v[i+1]-v[i])
                events.append((float(at),channel,bool(v[i+1]>1.65)))
        previous=float(t[0]);dead=overlap=0.
        for at,channel,high in sorted(events)+[(float(t[-1]),0,state[0])]:
            if not any(state):dead=max(dead,at-previous)
            if all(state):overlap=max(overlap,at-previous)
            state[channel]=high;previous=at
        summary['control_dead_time_max_ps']=dead*1e12
        summary['control_overlap_max_ps']=overlap*1e12
        summary['passed']=all(m['min_v']<.3 and m['max_v']>2.5 and m['edges']>=20 for m in metrics[:2]) and max(dead,overlap)<=200e-12
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
