#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolated DLL candidate screens. Results are diagnostic, never release evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import numpy as np
from layout import circuits,flatten,schematic_text
from spice_library import replace
from spice_engine import command,engine,provenance
from verify_phase_detector import metrics

ROOT=Path(__file__).resolve().parents[1]
VARIANTS={'mirror2':(1,2),'input2':(2,1),'both2':(2,2),'both4':(4,4)}

def variant_source(source,variant):
    if variant.startswith('restore'):
        width={'restore4':4,'restore2':2}[variant]
        helper=f'''.subckt screen_restorer A Y VDD VSS
XP Y A VDD VDD sky130_fd_pr__pfet_01v8 w={width} l=0.15
XN Y A VSS VSS sky130_fd_pr__nfet_01v8 w=16 l=0.15
.ends screen_restorer
'''
        return source.replace('XF0 PCO FBAD_B VDDD VSS lvds_inv18_drive',
                              'XF0 PCO FBAD_B VDDD VSS screen_restorer')+'\n'+helper
    ps,ns=VARIANTS[variant]
    defs=circuits(source);ports,instances=defs['lvds_ctrl_buffer'];lines=[]
    for name,nodes,model,params in instances:
        params=dict(params)
        factor=ps if name in ['XPP','XPM'] else ns if name in ['XNL','XNR'] else 1
        for key in ['w','l']:params[key]=f'{float(params[key])*factor:g}'
        lines.append(name+' '+' '.join(nodes)+' '+model+' '+' '.join(f'{k}={v}' for k,v in params.items()))
    body='.subckt lvds_ctrl_buffer '+' '.join(ports)+'\n'+'\n'.join(lines)+'\n.ends lvds_ctrl_buffer'
    return replace(source,'lvds_ctrl_buffer',body)

def raw_wave(path):
    rows=[]
    for line in path.read_text().splitlines():
        try:rows.append([float(x) for x in line.split()])
        except ValueError:pass
    return np.array(rows)

def stimulus(t,v):return 'PWL('+' '.join(f'{at:.12g}n {value:.12g}' for at,value in zip(t,v))+')'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('variant',choices=['baseline',*VARIANTS,'restore4','restore2'])
    a=p.parse_args();original=(ROOT/'analog/openlvds.spice').read_text()
    source=original if a.variant=='baseline' else variant_source(original,a.variant)
    ports,devices=flatten(circuits(source),'openlvds_dll_analog')
    flat=schematic_text('openlvds_dll_analog',ports,devices)
    stamp=provenance();producer=Path(__file__).read_bytes()
    recipe=hashlib.sha256(source.encode()+producer+stamp.encode()).hexdigest()[:16]
    root=ROOT/'build/diagnostics/dll_candidates'/a.variant/recipe
    root.mkdir(parents=True,exist_ok=False)
    (root/'candidate.spice').write_text(source);(root/'producer.py').write_bytes(producer)
    requirements=(ROOT/'requirements.json').read_bytes();(root/'requirements.json').write_bytes(requirements)
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    results=[]
    def run(name,lib,deck,analyze,inputs):
        out=root/name;out.mkdir()
        (out/'library.spice').write_text(lib)
        deck=deck.replace('SCREEN_LIBRARY',str(out/'library.spice'))
        (out/'bench.cir').write_text(deck)
        r=subprocess.run(command(out/(engine()+'.log'),out/'bench.cir'),cwd=out,capture_output=True,text=True)
        (out/'console.log').write_text(r.stdout+r.stderr)
        result=dict(case=name,diagnostic=True,qualified=False,returncode=r.returncode,inputs=inputs)
        wavefile=out/'bench.cir.prn'
        if r.returncode==0 and wavefile.exists():
            wave=raw_wave(wavefile)
            if wave.ndim==2 and len(wave)>1 and np.isfinite(wave).all():result.update(analyze(wave))
        result['files']={n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in
                         ['library.spice','bench.cir']+(['bench.cir.prn'] if wavefile.exists() else [])}
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');results.append(result)
        print(name,result.get('passed',False),flush=True)
    if a.variant.startswith('restore'):
        base=ROOT/'build/phase_detector/extracted/a82259d7acf0'
        for corner,temp in [('tt',25),('ss',0),('ff',0)]:
            for offset in [0,50,-50,150,-150,300,-300]:
                case=base/f'tt_25_{offset}ps_r100_f100'
                lib=replace((case/'library.spice').read_text(),'openlvds_dll_analog',flat)
                deck=(case/'bench.cir').read_text()
                deck=re.sub(r'(?im)^\.include .*$', '.include "SCREEN_LIBRARY"',deck)
                deck=re.sub(r'(?m)^(\.lib .* )tt$',lambda m:m[1]+corner,deck)
                deck=deck.replace('.options device temp=25',f'.options device temp={temp}')
                run(f'{corner}_{temp}_{offset}ps',lib,deck,lambda w,o=offset:metrics(w,o,120e-9,160e-9),
                    dict(captured_case=str(case.relative_to(ROOT)),captured_library_sha256=hashlib.sha256((case/'library.spice').read_bytes()).hexdigest()))
    else:
        capture=ROOT/'build/analog_extracted/dll_ss_0/bench.cir.prn'
        wave=raw_wave(capture);selected=wave[(wave[:,1]>=1200e-9)&(wave[:,1]<1250e-9)]
        t=(selected[:,1]-selected[0,1])*1e9
        # Repeat a 20-cycle captured interval, then score the second interval.
        tt=np.concatenate([t,t+50,[100]])
        def replay(col):return stimulus(tt,np.concatenate([selected[:,col],selected[:,col],[selected[0,col]]]))
        private='openlvds_dll_analog__CTRL'
        flat=flat.replace('.subckt openlvds_dll_analog '+' '.join(ports),
                          '.subckt openlvds_dll_analog '+' '.join(ports)+' '+private,1)
        lib=replace(source,'openlvds_dll_analog',flat)
        nodes=dict(CLK='0',PD_ENABLE='VDDD',PH0='P0',PH90='P90',PH180='P180',PH270='P270',FB='FB',
                   PD_REF='PDREF',PHASE_BAD='BAD',UP='UP',DN='DN',ERR='0',PB='PB',VDDIO='VDDIO',VDDD='VDDD',VSS='0',
                   QREF='QR',QFB='QF',QWIN='QW',SENSE_REF='0',SENSE_FB='0',SENSE_WINDOW='0')
        deck=f'''Loaded follower candidate, SS/0C recorded control and pump pulses
.lib "{pdk}" ss
.include "SCREEN_LIBRARY"
VA VDDIO 0 3.3
VD VDDD 0 1.8
IB PB 0 35u
XB PB NB VDDIO 0 lvds_bias
VC CTRL 0 {replay(7)}
VU UP 0 {replay(9)}
VN DN 0 {replay(10)}
XA {' '.join(nodes[x] for x in ports)} CTRL openlvds_dll_analog
.options device temp=0
.options timeint method=gear reltol=1e-4 abstol=1e-12
.tran 5p 100n 0 20p
.print tran V(CTRL) V(XA:openlvds_dll_analog__VCOPY) V(UP) V(DN)
.end
'''
        def analyze(w):
            complete=w[-1,1]>=100e-9-1e-12
            b=w[(w[:,1]>=50e-9)&(w[:,1]<=100e-9)];error=b[:,2]-b[:,3]
            mean=float(np.sum((error[:-1]+error[1:])*.5*np.diff(b[:,1]))/(b[-1,1]-b[0,1]))
            peak=float(np.max(abs(error)))
            return dict(passed=bool(complete and peak<.05),complete=bool(complete),
                        mean_copy_error_mv=mean*1000,peak_copy_error_mv=peak*1000)
        run('ss_0_loaded_replay',lib,deck,analyze,dict(captured_waveform=str(capture.relative_to(ROOT)),
            captured_waveform_sha256=hashlib.sha256(capture.read_bytes()).hexdigest()))
    summary=dict(diagnostic=True,qualified=False,variant=a.variant,simulator=engine(),simulator_provenance=stamp,
        source_sha256=hashlib.sha256(original.encode()).hexdigest(),candidate_sha256=hashlib.sha256(source.encode()).hexdigest(),
        producer_sha256=hashlib.sha256(producer).hexdigest(),requirements_sha256=hashlib.sha256(requirements).hexdigest(),
        passed=bool(results and all(r.get('passed',False) for r in results)),results=results)
    (root/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(root,flush=True)
    return 0 if summary['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
