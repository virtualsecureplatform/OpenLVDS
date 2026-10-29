#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fixed-supply OTA transfer/headroom characterization; signal inputs vary, rails do not."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from dll_design import native_block
from dll_campaign import closure,atomic
from dll_measurements import read_wave,average,column
from run_ngspice import read_raw
from screen_dll import stimulus
from spice_engine import command,provenance,engine

ROOT=Path(__file__).resolve().parents[1]

def prepare(source_path):
    source=source_path.read_bytes();lib=closure(source.decode(),['lvds_phase_ota','lvds_bias'])
    # Use the same <=8 um native fingers as physical generation.
    lib=native_block(lib,'lvds_phase_ota')+'\n'+native_block(lib,'lvds_bias')
    requirements=(ROOT/'requirements.json').read_bytes();req=json.loads(requirements)
    identity=source+lib.encode()+Path(__file__).read_bytes()+requirements+provenance().encode()
    out=ROOT/'build/diagnostics/ota_characterization'/hashlib.sha256(identity).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);(out/'candidate.spice').write_bytes(source);(out/'producer.py').write_bytes(Path(__file__).read_bytes())
    grid=[(cm,ctrl,delta) for cm in [.4,.6,.9] for ctrl in [.7,.9,1.1,1.3,1.4] for delta in [-.005,0,.005]]
    ramps=[]
    for col in range(3):
        pts=[]
        for i,(cm,ctrl,delta) in enumerate(grid):
            value=[cm+delta/2,cm-delta/2,ctrl][col]
            pts.extend([(i*10,value),(i*10+9.9,value)])
        pts.append((len(grid)*10,pts[-1][1]));ramps.append(stimulus(*zip(*pts)))
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    cases=[]
    for corner in req['process_corners']:
        for temp in req['temperatures_c']:
            name=f'{corner}_{temp}';case=out/name;case.mkdir(exist_ok=True);(case/'library.spice').write_text(lib)
            text=f'''OpenLVDS OTA signal characterization, fixed supply DIAGNOSTIC
.lib "{pdk}" {corner}
.include "{case}/library.spice"
.options device temp={temp}
.options timeint method=gear reltol=1e-4 abstol=1e-12
VA VDDIO 0 3.3
VD VDDD 0 1.8
IB PB 0 35u
XB PB NB VDDIO 0 lvds_bias
VU U 0 {ramps[0]}
VDIFF D 0 {ramps[1]}
VFORCE OUT 0 {ramps[2]}
XO U D OUT PB VDDIO VDDD 0 lvds_phase_ota
.save i(VFORCE) i(VA) i(VD)
.tran 5p {len(grid)*10}n 0 20p
.print tran V(U) V(D) V(OUT) V(PB) V(XO:lvds_phase_ota__T) V(XO:lvds_phase_ota__NL) V(XO:lvds_phase_ota__NR) V(XO:lvds_phase_ota__PLATE)
.end
'''
            (case/'bench.cir').write_text(text);cases.append(name)
    atomic(out/'manifest.json',dict(diagnostic=True,qualified=False,cases=cases,grid=grid,
        simulator=engine(),simulator_provenance=provenance(),candidate_sha256=hashlib.sha256(source).hexdigest(),
        producer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    return out

def run(root):
    # Share the campaign lease: characterization never adds a fifth transient.
    lease=ROOT/'build/diagnostics/dll_architecture/.supervisor.lock';lease.parent.mkdir(parents=True,exist_ok=True)
    atomic(root/'state.json',dict(status='waiting_for_simulator_lease'))
    with lease.open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        m=json.loads((root/'manifest.json').read_text());results=[]
        if m['producer_sha256']!=hashlib.sha256(Path(__file__).read_bytes()).hexdigest() or m['simulator_provenance']!=provenance():raise ValueError('Characterization producer changed')
        for name in m['cases']:
            out=root/name;atomic(root/'state.json',dict(status='running',case=name,completed=len(results)))
            r=subprocess.run(command(out/(engine()+'.log'),out/'bench.cir'),cwd=out,capture_output=True,text=True)
            (out/'console.log').write_text(r.stdout+r.stderr);result=dict(case=name,passed=False,returncode=r.returncode)
            if r.returncode==0:
                names,w=read_raw(out/'bench.raw');ix={v:i for i,v in enumerate(names)};t=w[:,ix['time']]
                currents=[]
                for i,point in enumerate(m['grid']):
                    keep=(t>=(i*10+8)*1e-9)&(t<=(i*10+9.8)*1e-9)
                    currents.append(average(t[keep],w[keep,ix['i(vforce)']]))
                points=[]
                for i in range(0,len(currents),3):
                    gm=(currents[i+2]-currents[i])/.01
                    points.append(dict(common_mode_v=m['grid'][i][0],control_v=m['grid'][i][1],gm_s=gm,
                        zero_error_output_current_a=currents[i+1],input_offset_v=-currents[i+1]/gm if gm else None))
                offset=max(abs(p['input_offset_v']) if p['input_offset_v'] is not None else 1e9 for p in points)
                thin=max(float(np.max(abs(w[:,ix[n]]))) for n in ['v(out)','v(xo.lvds_phase_ota__nl)','v(xo.lvds_phase_ota__nr)','v(xo.lvds_phase_ota__plate)'])
                result.update(points=points,gm_min_s=min(p['gm_s'] for p in points),gm_max_s=max(p['gm_s'] for p in points),
                    input_offset_max_v=offset,thin_terminal_absolute_max_v=thin,
                    passed=bool(t[-1]>=len(m['grid'])*10e-9-1e-12 and all(p['gm_s']>1e-6 for p in points) and offset<.01 and thin<=1.95))
            result['files']={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ['library.spice','bench.cir']+(['bench.raw'] if (out/'bench.raw').exists() else [])}
            atomic(out/'summary.json',result);results.append(result);print(name,result['passed'],flush=True)
        atomic(root/'summary.json',dict(diagnostic=True,qualified=False,passed=all(r['passed'] for r in results),results=results))
        atomic(root/'state.json',dict(status='complete',passed=all(r['passed'] for r in results)))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('--run',action='store_true');a=p.parse_args()
    out=prepare(a.source.resolve());print(out,flush=True)
    if a.run:run(out)

if __name__=='__main__':main()
