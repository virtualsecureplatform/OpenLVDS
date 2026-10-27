#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare the fast RC networks to full RC on the real nonlinear circuits."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from spice_library import library
from rc_certificate import REQUIRED
from spice_engine import command as spice_command,engine,provenance
from spice_scope import closure_hash

ROOT=Path(__file__).resolve().parents[1]
TOPS=dict(driver='openlvds_driver',receiver='openlvds_receiver',dll='openlvds_dll',
          delay='openlvds_delay_line',tx='openlvds_tx_core',rx='openlvds_ddr_rx')
MODELS=dict(driver={'openlvds_driver_core','lvds_bias'},receiver={'openlvds_receiver_core','lvds_bias'},
            dll={'openlvds_dll_analog','lvds_bias','lvds_pfd'},delay={'openlvds_delay_line'},
            tx={'openlvds_tx_core'},rx={'openlvds_ddr_rx'})

def instance(name,nodes,models):
    return 'X'+name+' '+' '.join(nodes[p] for p in models[name]['ports'])+' '+name

def fixture(kind,models):
    common='''VIO VDDIO 0 PWL(0 0 1n 3.3)
VDIG VDDD 0 PWL(0 0 1n 1.8)
VREF VREF 0 PWL(0 0 1n 1.2)
VRESET RESET_N 0 PWL(0 0 2n 0 2.1n 1.8)
'''
    print_nodes=[]
    if kind=='driver':
        body='''IREF IREF 0 PWL(0 0 1n 35u)
VD D 0 PULSE(0 1.8 2000n 100p 100p 1.15n 2.5n)
XD D P N VREF IREF VDDIO VDDD 0 openlvds_driver
RT P N 100
CP P 0 2p
CN N 0 2p
''';print_nodes=['P','N']
    elif kind=='receiver':
        body='''IREF IREF 0 PWL(0 0 1n 35u)
VP P 0 PULSE(1.075 1.425 5n 100p 100p 1.15n 2.5n)
VN N 0 PULSE(1.425 1.075 5n 100p 100p 1.15n 2.5n)
XR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver
CQ Q 0 100f
''';print_nodes=['Q']
    elif kind=='dll':
        body='''IREF IREF 0 PWL(0 0 1n 35u)
VCLK CLK 0 PULSE(0 1.8 5n 100p 100p 1.15n 2.5n)
VEN ENABLE 0 PWL(0 0 85n 0 85.1n 1.8)
XL CLK RESET_N ENABLE PH0 PH90 PH180 PH270 FB BAD UP DN VREF IREF VDDIO VDDD 0 openlvds_dll
C90 PH90 0 20f
C180 PH180 0 20f
C270 PH270 0 20f
C360 FB 0 20f
''';print_nodes=['PH0','PH90','FB','XL:XCORE:PD_REF']
    elif kind=='delay':
        body='''VCLK CLK 0 PULSE(0 1.8 5n 100p 100p 1.15n 2.5n)
VC CTRL 0 1.27
XL CLK PH90 PH180 PH270 FB CTRL VDDD 0 openlvds_delay_line
C90 PH90 0 20f
C180 PH180 0 20f
C270 PH270 0 20f
C360 FB 0 20f
''';print_nodes=['PH90','PH180','PH270','FB']
    else:
        body='''VCLK CLK 0 PULSE(0 1.8 5n 100p 100p 1.15n 2.5n)
'''
        if kind=='tx':
            body+='''VC90 CLK90 0 PULSE(0 1.8 5.625n 100p 100p 1.15n 2.5n)
VD0 D0 0 PULSE(0 1.8 3n 100p 100p 2.4n 5n)
VD1 D1 0 PULSE(1.8 0 3n 100p 100p 4.9n 10n)
'''
            nodes={'VGND':'0','VPWR':'VDDD','clk_400':'CLK','clk_90':'CLK90',
                'clock_ready':'VDDD','dll_locked':'VDDD','enable':'VDDD','reset_n':'RESET_N',
                'tx_data[0]':'D0','tx_data[1]':'D1','tx_ready':'READY','tx_serial':'DATA','forwarded_clock':'CLOCK'}
            body+=instance('openlvds_tx_core',nodes,models)+'\nCD DATA 0 20f\nCC CLOCK 0 20f\n'
            print_nodes=['DATA','CLOCK']
        elif kind=='rx':
            body+='''VS SERIAL 0 PULSE(0 1.8 4.375n 100p 100p 2.4n 5n)
'''
            nodes={'VGND':'0','VPWR':'VDDD','clk':'CLK','reset_n':'RESET_N','serial':'SERIAL',
                   'data[0]':'D0','data[1]':'D1','valid':'VALID'}
            body+=instance('openlvds_ddr_rx',nodes,models)+'\nC0 D0 0 20f\nC1 D1 0 20f\n'
            print_nodes=['D0','D1','VALID']
        else:raise ValueError(kind)
    return common+body,print_nodes

def simulate(kind,fast,reuse_full=False,analyze_only=False,resume=False):
    mode='fast' if fast else 'full'
    lib,inputs,models=library(extracted=True,digital=True,fast=fast)
    scope=closure_hash(lib,TOPS[kind]);inputs={k:v for k,v in inputs.items() if k in MODELS[kind]}
    parent=ROOT/f'build/rc_validation/{engine()}/{kind}'
    tag=mode+'_'+scope[:10]
    out=parent/tag
    if resume or analyze_only or (not fast and reuse_full):
        for candidate in sorted(parent.glob(mode+'*')):
            old=candidate/'library.spice'
            if old.exists() and (candidate/'bench.cir.prn').exists() and closure_hash(old.read_bytes(),TOPS[kind])==scope:
                out=candidate;break
    out.mkdir(parents=True,exist_ok=True)
    cached=(out/'library.spice').read_bytes() if (out/'library.spice').exists() else None
    body,nodes=fixture(kind,models)
    stop='2560n' if kind=='driver' else '1500n' if kind=='dll' else '60n'
    maximum='1n' if kind=='driver' else '100p'
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    deck=f'''OpenLVDS RC approximation reference comparison {kind} {mode} {engine()}
.lib "{pdk}" tt
.include "{out}/library.spice"
.options device temp=25
.options timeint method=gear reltol=1e-4 abstol=1e-12
{body}
.tran 20p {stop} 0 {maximum}
.print tran {' '.join('V('+n+')' for n in nodes)}
.end
'''
    path=out/'bench.cir'
    old_deck=path.read_text() if path.exists() else None
    prn=out/'bench.cir.prn'
    matching=cached is not None and closure_hash(cached,TOPS[kind])==scope and old_deck==deck and prn.exists()
    reuse=(analyze_only or (not fast and reuse_full) or resume) and matching
    if (analyze_only or (not fast and reuse_full)) and not matching:
        return kind,mode,None,inputs,dict(error='No matching circuit reference')
    if not reuse:
        (out/'library.spice').write_bytes(lib);path.write_text(deck)
        prn.unlink(missing_ok=True)
        result=subprocess.run(spice_command(out/(engine()+'.log'),path),cwd=out,
                              capture_output=True,text=True)
        (out/'console.log').write_text(result.stdout+result.stderr)
        if result.returncode or not prn.exists():return kind,mode,None,inputs,dict(error=engine()+' failed',returncode=result.returncode)
    rows=[]
    for line in prn.read_text().splitlines():
        try:rows.append(list(map(float,line.split())))
        except ValueError:pass
    wave=np.array(rows)
    minimum=2559.9e-9 if kind=='driver' else 1499.9e-9 if kind=='dll' else 59.9e-9
    if not len(wave) or wave[-1,1]<minimum:return kind,mode,None,inputs,dict(error='Incomplete transient')
    return kind,mode,wave,inputs,dict(scope_sha256=scope,artifact=str(out.relative_to(ROOT)))

def compare(kind,full,fast):
    f,_,a,_,error=full;_,_,b,_,error_b=fast
    if a is None or b is None:return dict(passed=False,full=error,fast=error_b)
    columns=a.shape[1]-2;errors=[]
    start,end=(2510e-9,2550e-9) if kind=='driver' else (1200e-9,1490e-9) if kind=='dll' else (15e-9,55e-9)
    if kind=='driver':
        a=a.copy();b=b.copy()
        for wave in [a,b]:
            p,n=wave[:,2].copy(),wave[:,3].copy()
            wave[:,2]=p-n;wave[:,3]=(p+n)/2
    for col in range(2,columns+2):
        threshold=0 if kind=='driver' and col==2 else 1.25 if kind=='driver' else .9
        def edges(wave):
            v=wave[:,col]-threshold;t=wave[:,1]
            i=np.where(v[:-1]*v[1:]<0)[0]
            times=t[i]-v[i]*(t[i+1]-t[i])/(v[i+1]-v[i])
            mask=(times>start)&(times<end)
            return times[mask]
        ea,eb=edges(a),edges(b)
        # Common mode is an analog voltage, so crossing 1.25 V is not a logic
        # event. Compare its complete waveform rather than timing tiny ripples.
        common_mode=kind=='driver' and col==3
        if common_mode:ea=eb=np.array([])
        equal=len(ea)==len(eb)
        edge_error=float(np.max(abs(ea-eb))*1e12) if equal and len(ea) else 0. if equal else None
        sample=np.linspace(start,end,8001)
        av=np.interp(sample,a[:,1],a[:,col]);bv=np.interp(sample,b[:,1],b[:,col])
        mask=np.ones(len(sample),bool)
        for t in ea:mask &= abs(sample-t)>300e-12
        voltage_error=float(np.max(abs(av[mask]-bv[mask]))) if np.any(mask) else None
        require_edges=not ((kind=='driver' and col==3) or (kind=='rx' and col==4))
        active=len(ea)>=8 and len(eb)>=8 if require_edges else True
        if kind=='rx' and col==4:active=bool(np.all(av>1.44) and np.all(bv>1.44))
        errors.append(dict(edges_full=len(ea),edges_fast=len(eb),edge_error_ps=edge_error,
            active=active,plateau_error_v=voltage_error,passed=active and equal and edge_error is not None and edge_error<=20 and
                voltage_error is not None and voltage_error<=.02))
    return dict(passed=all(x['passed'] for x in errors),outputs=errors,
                reference=error,approximation=error_b)

def main():
    p=argparse.ArgumentParser();p.add_argument('--tests',default='driver,receiver,dll,delay,tx,rx');p.add_argument('--jobs',type=int,default=8)
    p.add_argument('--reuse-full',action='store_true',help='Reuse completed references with identical circuit snapshots')
    p.add_argument('--analyze-only',action='store_true',help='Recheck completed full/fast snapshots without resimulation')
    p.add_argument('--resume',action='store_true',help='Reuse completed, identical instantiated circuit closures')
    a=p.parse_args();kinds=a.tests.split(',')
    (ROOT/'build/rc_validation/summary.json').unlink(missing_ok=True)
    jobs=[(k,f) for k in kinds for f in [False,True]]
    if any(k not in REQUIRED for k in kinds):p.error('Unknown fixture')
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:r=list(pool.map(lambda j:simulate(*j,reuse_full=a.reuse_full,analyze_only=a.analyze_only,resume=a.resume),jobs))
    data={(x[0],x[1]):x for x in r}
    cases={k:compare(k,data[k,'full'],data[k,'fast']) for k in kinds}
    inputs_full={};inputs_fast={};consistent=True
    for k in kinds:
        for mode,target in [('full',inputs_full),('fast',inputs_fast)]:
            for name,digest in data[k,mode][3].items():
                if name in target and target[name]!=digest:consistent=False
                target[name]=digest
    complete=set(kinds)==REQUIRED and len(kinds)==len(REQUIRED)
    summary=dict(passed=complete and consistent and all(x['passed'] for x in cases.values()),complete_suite=complete,cases=cases,
        simulator=engine(),simulator_provenance=provenance(),
        reference_inputs=inputs_full,fast_inputs=inputs_fast,
        source_sha256=hashlib.sha256((ROOT/'analog/openlvds.spice').read_bytes()).hexdigest(),
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        qualification='Nonlinear operating-window full-RC comparison after settling; active outputs required; 20ps edges, 20mV plateaus')
    path=ROOT/'build/rc_validation/summary.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
