#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Transistor-level validation using real SKY130 corner models."""
import argparse
import fcntl
from concurrent.futures import ThreadPoolExecutor
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from spice_library import library
from rc_certificate import valid as valid_certificate
from spice_engine import command as spice_command,engine,provenance
from spice_scope import closure_hash
from evidence_scope import TOPS,matches as evidence_matches
from dll_case import case_name,trace_duty

ROOT=Path(__file__).resolve().parents[1]
REQ=json.loads((ROOT/'requirements.json').read_text())
SCRIPT_HASH=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
SCRIPT_BYTES=Path(__file__).read_bytes()
REQ_HASH=hashlib.sha256((ROOT/'requirements.json').read_bytes()).hexdigest()
SOURCE_BYTES=(ROOT/'analog/openlvds.spice').read_bytes()
SCHEMATIC_HASH=hashlib.sha256(SOURCE_BYTES).hexdigest()
ARTIFACT_ROOT=ROOT/'build/analog'
EXTRACTED=False
EXTRACTION_INPUTS={}
CLOCK_MHZ=400
MAX_STEP_PS=None
SETTLED_START=False
CASE_LOCKS={}
RESUME=False
REUSED={}
SIMULATOR_STAMP=None

def header(corner,temp):
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    return f'''OpenLVDS SKY130 fixed-supply bench {corner} {temp}C
.lib "{pdk}/libs.tech/ngspice/sky130.lib.spice" {corner}
.include "{ROOT}/analog/openlvds.spice"
.options device temp={temp}
.options timeint method=gear reltol=1e-4 abstol=1e-12
VIO VDDIO 0 PWL(0 0 1n 3.3)
VDIG VDDD 0 PWL(0 0 1n 1.8)
VREF VREF 0 PWL(0 0 1n 1.2)
'''

def run_deck(name,deck):
    out=ARTIFACT_ROOT/name
    out.mkdir(parents=True,exist_ok=True)
    lock=(out/'.run.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX if RESUME else fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise RuntimeError(f'{name} is already running; its evidence cannot be overwritten')
    CASE_LOCKS[out]=lock
    snapshot=out/'source.spice'
    if SETTLED_START:
        import re
        # Supplies and external references are already stable in the lab.
        # Solve their DC bias before applying reset and clock stimuli.
        deck=re.sub(r'PWL\(0 0 1n (3\.3|1\.8|1\.2|35u)\)',r'\1',deck)
    if MAX_STEP_PS is not None:
        import re
        from reduce_rc import number
        match=re.search(r'(?im)^\.tran\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)',deck)
        if match:
            limit=min(MAX_STEP_PS,number(match[4])*1e12)
            deck=deck[:match.start()]+f'.tran {match[1]} {match[2]} {match[3]} {limit:.12g}p'+deck[match.end():]
    if EXTRACTED:
        for parent,core,nodes in [('XD','openlvds_driver_core',['SINK','TOP','DP','DN']),
                                  ('XR','openlvds_receiver_core',['PP','PN','CO'])]:
            for node in nodes:
                deck=deck.replace(f'{parent}:XCORE:{node}',f'{parent}:XCORE:{core}__{node}')
        deck=deck.replace('XL:XCORE:XA:CTRL','XL:XCORE:XA:openlvds_dll_analog__CTRL')
        deck=deck.replace('XL:XCORE:XA:VCOPY','XL:XCORE:XA:openlvds_dll_analog__VCOPY')
    deck=deck.replace(str(ROOT/'analog/openlvds.spice'),str(snapshot))
    path=out/'bench.cir'
    data=out/'bench.cir.prn'
    cached=False
    if RESUME and (out/'summary.json').exists() and path.exists() and data.exists():
        try:
            old=json.loads((out/'summary.json').read_text())
            cached=bool(not old.get('error') and path.read_text()==deck and old.get('deck_sha256')==hashlib.sha256(deck.encode()).hexdigest() and
                old.get('requirements_sha256')==REQ_HASH and old.get('simulator')==engine() and
                old.get('simulator_provenance')==SIMULATOR_STAMP and old.get('extraction_inputs',{})==EXTRACTION_INPUTS and
                evidence_matches(old,snapshot,SOURCE_BYTES,name.split('_')[0]) and
                (out/'runner.py').exists() and old.get('runner_sha256')==hashlib.sha256((out/'runner.py').read_bytes()).hexdigest())
            if cached and old.get('waveform_sha256'):
                cached=old['waveform_sha256']==hashlib.sha256(data.read_bytes()).hexdigest()
            if cached:REUSED[out]=old
        except (OSError,ValueError,KeyError):cached=False
    if not cached:
        (out/'summary.json').unlink(missing_ok=True);data.unlink(missing_ok=True)
        snapshot.write_bytes(SOURCE_BYTES)
        (out/'runner.py').write_bytes(SCRIPT_BYTES)
        path.write_text(deck)
        result=subprocess.run(spice_command(out/(engine()+'.log'),path),
                               cwd=out,capture_output=True,text=True)
        (out/'console.log').write_text(result.stdout+result.stderr)
        if result.returncode or not data.exists():
            return out,None,dict(passed=False,error=engine()+' failed',returncode=result.returncode)
    else:(out/'analysis_runner.py').write_bytes(SCRIPT_BYTES)
    try:
        rows=[]
        for line in data.read_text().splitlines():
            try: rows.append([float(x) for x in line.split()])
            except ValueError: pass
        wave=np.array(rows)
        if wave.ndim!=2 or wave.shape[0]<2: raise ValueError('No waveform samples')
        import re
        from reduce_rc import number
        stop=re.search(r'(?im)^\.tran\s+\S+\s+(\S+)',deck)
        if stop and wave[-1,1]<number(stop[1])*(1-1e-8):raise ValueError('Incomplete transient')
        return out,wave,{}
    except (OSError,ValueError) as e: return out,None,dict(passed=False,error=str(e))

def driver_metrics(wave,window_start_ns=2510):
    t=wave[:,1];inp=wave[:,2];vod=wave[:,3]-wave[:,4];vcm=(wave[:,3]+wave[:,4])/2
    window=t>window_start_ns*1e-9
    def crossings(y,level):
        high=y>=level;i=np.flatnonzero(high[1:]!=high[:-1])
        times=t[i]+(level-y[i])*(t[i+1]-t[i])/(y[i+1]-y[i])
        return times,high[i+1]
    ie,idir=crossings(inp,.9);oe,odir=crossings(vod,0)
    # Pair transitions from the first driven edge, preserving their order.
    # The most recent input edge aliases a valid delay longer than one UI
    # into an apparent inversion. The initial DC polarity distinguishes a
    # delayed noninverting driver from a genuinely inverting driver.
    baseline=False
    if len(ie):
        before=ie[0]-.1e-9
        baseline=bool((np.interp(before,t,inp)>.9)==(np.interp(before,t,vod)>0))
        keep=oe>=ie[0];oe=oe[keep];odir=odir[keep]
    count=min(len(ie),len(oe));lag=oe[:count]-ie[:count]
    correct=bool(baseline and count and np.all(idir[:count]==odir[:count]) and np.all(lag>=0))
    cadence=bool(count>1 and np.all(abs(np.diff(oe[:count])-np.diff(ie[:count]))<.5*np.min(np.diff(ie[:count]))))
    scored=oe>window_start_ns*1e-9;ve=oe[scored];directions=odir[scored]
    centers=(ve[:-1]+ve[1:])/2;samples=np.interp(centers,t,vod)
    polarity=np.where(directions[:-1],1.,-1.)
    delays=lag[oe[:count]>window_start_ns*1e-9]*1e12
    transitions_ok=bool(cadence and len(ve)>=20 and abs(len(ie[ie>window_start_ns*1e-9])-len(ve))<=1)
    return dict(passed=bool(correct and transitions_ok and len(samples) and np.any(window) and
        np.all(samples*polarity>=REQ['tx_differential_min_v']) and
        np.all(np.abs(samples)<=REQ['tx_differential_max_v']) and
        np.all(vcm[window]>=REQ['tx_common_mode_min_v']) and np.all(vcm[window]<=REQ['tx_common_mode_max_v'])),
        transitions_ok=transitions_ok,polarity_ok=correct,initial_polarity_ok=baseline,edge_cadence_ok=cadence,
        propagation_min_ps=float(delays.min()) if len(delays) else None,
        propagation_max_ps=float(delays.max()) if len(delays) else None,
        differential_min_v=float(np.min(samples*polarity)) if len(samples) else None,
        differential_max_v=float(np.max(np.abs(samples))) if len(samples) else None,
        common_mode_min_v=float(np.min(vcm[window])) if np.any(window) else None,
        common_mode_max_v=float(np.max(vcm[window])) if np.any(window) else None,
        sink_bias_v=float(np.mean(wave[window,5])) if np.any(window) else None)

def driver_dc_metrics(wave):
    """Both settled data polarities with the bench's 100 ohm termination."""
    points=[]
    for low_ns,high_ns,sign in [(1800,1850,-1),(1950,1990,1)]:
        a=wave[(wave[:,1]>=low_ns*1e-9)&(wave[:,1]<=high_ns*1e-9)]
        if not len(a):return dict(passed=False,error='Missing settled DC polarity')
        differential=sign*(a[:,3]-a[:,4]);common=(a[:,3]+a[:,4])/2
        ok=bool(np.all(differential>=REQ['tx_differential_min_v']) and
            np.all(differential<=REQ['tx_differential_max_v']) and
            np.all(common>=REQ['tx_common_mode_min_v']) and
            np.all(common<=REQ['tx_common_mode_max_v']))
        points.append(dict(polarity=sign,passed=ok,differential_min_v=float(differential.min()),
            differential_max_v=float(differential.max()),common_mode_min_v=float(common.min()),
            common_mode_max_v=float(common.max())))
    return dict(passed=all(x['passed'] for x in points),termination_ohm=100,points=points)


def driver(corner,temp):
    name=f'driver_{corner}_{temp}'
    # Hold both polarities for DC qualification before exercising edge cadence.
    stimulus=[(0,0),(1899.95,0),(1900.05,1.8),(1999.95,1.8),(2000.05,0)]
    for i in range(1,433):
        at=2000+i*1.25;previous=1.8*((i-1)%2);value=1.8*(i%2)
        stimulus.extend([(at-.05,previous),(at+.05,value)])
    vd='VD D 0 PWL('+ ' '.join(f'{t:.9f}n {v}' for t,v in stimulus)+')'
    deck=header(corner,temp)+'''IREF IREF 0 PWL(0 0 1n 35u)
DRIVER_STIMULUS
XD D P N VREF IREF VDDIO VDDD 0 openlvds_driver
RT P N 100
CP P 0 2p
CN N 0 2p
.tran 5p 2540n 0 1n
.print tran V(D) V(P) V(N) V(XD:XCORE:SINK) V(XD:XCORE:TOP) V(XD:XCORE:DP) V(XD:XCORE:DN)
.end
'''
    deck=deck.replace('DRIVER_STIMULUS',vd)
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        res=driver_metrics(wave)
        res['dc_output']=driver_dc_metrics(wave)
        res['loaded_eye_passed']=res['passed']
        res['passed']=res['polarity_ok'] and res['transitions_ok'] and res['dc_output']['passed']
    return name,save(out,res,deck)

def receiver(corner,temp):
    name=f'receiver_{corner}_{temp}'
    # Static threshold decision at each legal input common-mode: +/-100 mV.
    levels=[.05,.2,.6,1.2,1.8,2.35]
    lines=[]; expected=[]
    for i,cm in enumerate(levels):
        for sign in [-1,1]:
            k=len(expected); start=k*12
            for edge in [start,start+11.9]: lines.append((edge,cm+sign*.05,cm-sign*.05))
            expected.append((start+10,sign))
    vp=' '.join(f'{t}n {v:.6f}' for t,v,_ in lines)
    vn=' '.join(f'{t}n {v:.6f}' for t,_,v in lines)
    deck=header(corner,temp)+f'''IREF IREF 0 PWL(0 0 1n 35u)
VP P 0 PWL({vp})
VN N 0 PWL({vn})
XR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver
CQ Q 0 100f
.tran 10p {len(expected)*12}n 0 50p
.print tran V(P) V(N) V(Q) V(XR:XCORE:PP) V(XR:XCORE:PN) V(XR:XCORE:CO)
.end
'''
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        points=[]
        for t,sign in expected:
            v=float(np.interp(t*1e-9,wave[:,1],wave[:,4]))
            points.append(dict(time_ns=t,expected=sign>0,output_v=v,passed=v>1.44 if sign>0 else v<.36))
        res=dict(passed=all(x['passed'] for x in points),points=points)
    return name,save(out,res,deck)

def delay_line(corner,temp,ctrl):
    name=f'delay_{corner}_{temp}_{ctrl:.2f}'
    deck=header(corner,temp)+f'''VC CTRL 0 {ctrl}
VD D 0 PULSE(0 1.8 10n 20p 20p 5n 20n)
XL D P90 P180 P270 P360 CTRL VDDD 0 openlvds_delay_line
.tran 5p 28n 0 10p
.print tran V(D) V(P90) V(P180) V(P270) V(P360)
.end
'''
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        def crossing(col):
            t=wave[:,1]; y=wave[:,col]; ids=np.where((y[:-1]<.9)&(y[1:]>=.9)&(t[1:]>9e-9))[0]
            if not len(ids): return None
            i=ids[0]; return float(t[i]+(.9-y[i])*(t[i+1]-t[i])/(y[i+1]-y[i]))
        ref=crossing(2); edges=[crossing(i) for i in range(3,7)]
        res=dict(passed=ref is not None and all(x is not None for x in edges),
                 control_v=ctrl,delays_ns=[(x-ref)*1e9 if x is not None and ref else None for x in edges])
    return name,save(out,res,deck)

def receiver_rate_metrics(wave):
    period=1e-6/max(REQ['clock_test_mhz'])
    a=wave[(wave[:,1]>30e-9)&(wave[:,1]<55e-9)]
    t=a[:,1];q=a[:,4]
    def crossings(level):
        i=np.where((q[:-1]-level)*(q[1:]-level)<0)[0]
        at=t[i]+(level-q[i])*(t[i+1]-t[i])/(q[i+1]-q[i])
        return at[q[i+1]>q[i]],at[q[i+1]<q[i]]
    rises,falls=crossings(.9)
    def widths(level,high):
        up,down=crossings(level)
        start,end=(up,down) if high else (down,up)
        return [float((end[end>x][0]-x)*1e12) for x in start if len(end[end>x])]
    high=widths(1.44,True);low=widths(.36,False)
    periods=np.diff(rises)
    valid=bool(len(rises)>=9 and len(falls)>=9 and len(periods) and
               np.min(periods)>.9*period and np.max(periods)<1.1*period and high and low and
               min(high)>=2*REQ['minimum_sampling_margin_ps'] and
               min(low)>=2*REQ['minimum_sampling_margin_ps'])
    return dict(passed=valid,clock_mhz=max(REQ['clock_test_mhz']),output_load_ff=100,
        input_differential_v=REQ['tx_differential_min_v'],rising_edges=len(rises),falling_edges=len(falls),
        high_valid_min_ps=min(high) if high else None,low_valid_min_ps=min(low) if low else None,
        output_min_v=float(q.min()),output_max_v=float(q.max()))

def receiver_rate(corner,temp):
    name=f'receiver_rate_{corner}_{temp}'
    period=1000/max(REQ['clock_test_mhz']);low=1.2-REQ['tx_differential_min_v']/2;high=1.2+REQ['tx_differential_min_v']/2
    deck=header(corner,temp)+f'''IREF IREF 0 PWL(0 0 1n 35u)
VP P 0 PULSE({low:.12g} {high:.12g} 5n 100p 100p {period/2-.1:.12g}n {period:.12g}n)
VN N 0 PULSE({high:.12g} {low:.12g} 5n 100p 100p {period/2-.1:.12g}n {period:.12g}n)
XR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver
CQ Q 0 100f
.tran 10p 60n 0 100p
.print tran V(P) V(N) V(Q)
.end
'''
    out,wave,res=run_deck(name,deck)
    if wave is not None:res=receiver_rate_metrics(wave)
    return name,save(out,res,deck)

def dll(corner,temp,mhz=None,duty=.5):
    mhz=CLOCK_MHZ if mhz is None else mhz
    name=case_name(corner,temp,mhz,duty)
    period=1000/mhz
    # Enable follows the 32-cycle hold with nonzero control propagation.
    # At 380/420 MHz, coincident PULSE/PWL times rounded independently can
    # differ by sub-femtoseconds and stall the ideal enable-source branch.
    pd_start=5+32*period+.2
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    deck=header(corner,temp)+f'''.include "{pdk}/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice"
IREF IREF 0 PWL(0 0 1n 35u)
VCLK CLK 0 PULSE(0 1.8 5n 100p 100p {period*duty-.1:.12g}n {period:.12g}n)
VRST RST 0 PWL(0 0 2n 0 2.02n 1.8)
VEN ENABLE 0 PWL(0 0 {pd_start:.12g}n 0 {pd_start+.02:.12g}n 1.8)
XL CLK RST ENABLE PH0 PH90 PH180 PH270 FB BAD UP DN VREF IREF VDDIO VDDD 0 openlvds_dll
C0 PH0 0 40f
C90 PH90 0 40f
C180 PH180 0 20f
C270 PH270 0 20f
C360 FB 0 20f
.tran 5p 1500n 0 100p
.print tran V(PH0) V(PH90) V(PH180) V(PH270) V(FB) V(XL:XCORE:XA:CTRL) V(BAD) V(UP) V(DN) V(XL:XCORE:XA:VCOPY) V(XL:XCORE:PD_REF)
.end
'''
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        def edges(col):
            t=wave[:,1];v=wave[:,col]
            i=np.where((v[:-1]<.9)&(v[1:]>=.9))[0]
            return t[i]+(.9-v[i])*(t[i+1]-t[i])/(v[i+1]-v[i])
        ref=edges(2); shifted=edges(3);fb=edges(4);detector_ref=edges(12)
        phases=[];errors=[]
        # Leave complete neighboring cycles at both boundaries, including a
        # feedback edge that leads the first reference in the scoring window.
        ref=ref[(ref>(1200+period)*1e-9)&(ref<(1500-2*period)*1e-9)]
        for t in ref:
            upcoming=shifted[shifted>t]
            if len(upcoming): phases.append((upcoming[0]-t)*1e12)
        for t in detector_ref[(detector_ref>(1200+period)*1e-9)&(detector_ref<(1500-2*period)*1e-9)]:
            if len(fb):errors.append(float(np.min(abs(fb-t)))*1e12)
        bad_max=float(np.max(wave[wave[:,1]>1200e-9,8]))
        copy_error=float(np.max(abs(wave[wave[:,1]>1200e-9,11]-wave[wave[:,1]>1200e-9,7])))
        res=dict(passed=bool(phases and errors and max(abs(x-period*250) for x in phases)<100 and max(errors)<100 and bad_max<.36 and copy_error<.05),
                 clock_mhz=mhz,clock_duty=duty,
                 quarter_phase_min_ps=min(phases) if phases else None,
                 quarter_phase_max_ps=max(phases) if phases else None,
                 feedback_error_max_ps=max(errors) if errors else None,
                 phase_bad_max_v=bad_max,
                 control_buffer_error_max_mv=copy_error*1000,
                 control_v=float(np.mean(wave[wave[:,1]>1200e-9,7])))
    return name,save(out,res,deck)

def save(out,res,deck):
    previous=REUSED.pop(out,None)
    res['deck_sha256']=hashlib.sha256((out/'bench.cir').read_bytes()).hexdigest()
    res['source_sha256']=hashlib.sha256((out/'source.spice').read_bytes()).hexdigest()
    res['runner_sha256']=hashlib.sha256((out/'runner.py').read_bytes()).hexdigest()
    res['analysis_runner_sha256']=SCRIPT_HASH
    res['reused_waveform']=previous is not None
    res['requirements_sha256']=REQ_HASH
    res['schematic_sha256']=previous.get('schematic_sha256') if previous else SCHEMATIC_HASH
    res['extraction_inputs']=EXTRACTION_INPUTS
    res['simulator']=engine()
    res['simulator_provenance']=SIMULATOR_STAMP
    res['simulation_scope_sha256']=closure_hash((out/'source.spice').read_bytes(),TOPS[out.name.split('_')[0]])
    wave=out/'bench.cir.prn'
    if wave.exists():res['waveform_sha256']=hashlib.sha256(wave.read_bytes()).hexdigest()
    res['startup']='solved fixed-supply DC operating point' if SETTLED_START else '1 ns supply and reference ramp'
    (out/'summary.json').write_text(json.dumps(res,indent=2)+'\n')
    CASE_LOCKS.pop(out).close()
    return res

def main():
    global EXTRACTED,SOURCE_BYTES,ARTIFACT_ROOT,EXTRACTION_INPUTS,CLOCK_MHZ,MAX_STEP_PS,SETTLED_START,RESUME,SIMULATOR_STAMP
    p=argparse.ArgumentParser()
    p.add_argument('--corners',action='store_true')
    p.add_argument('--test',choices=['all','driver','receiver','receiver-rate','delay','dll'],default='all')
    p.add_argument('--jobs',type=int,default=8)
    p.add_argument('--process',help='Comma-separated process subset for diagnosis')
    p.add_argument('--temperature',type=int,choices=REQ['temperatures_c'])
    p.add_argument('--extracted',action='store_true',help='Replace cores with GDS-extracted RC networks')
    p.add_argument('--fast-rc',action='store_true',help='Use separately qualified TICER RC approximation')
    p.add_argument('--control-v',type=float,help='Single internal delay-control test point; supplies remain fixed')
    p.add_argument('--clock-mhz',type=int,choices=REQ['clock_test_mhz'],default=400)
    p.add_argument('--duty',type=float,default=.5,help='DLL input high fraction, from 0.45 to 0.55')
    p.add_argument('--clock-corners',action='store_true',help='DLL frequency/duty matrix at the selected PVT, including available OpenPLL trace duties')
    p.add_argument('--max-step-ps',type=float,help='Tighten the existing maximum integration timestep')
    p.add_argument('--settled-start',action='store_true',help='Solve fixed-supply DC bias before reset and clock stimuli')
    p.add_argument('--resume',action='store_true',help='Reanalyze matching completed evidence; wait for an active case instead of overwriting it')
    a=p.parse_args()
    from layout import circuits
    circuits((ROOT/'analog/openlvds.spice').read_text())
    CLOCK_MHZ=a.clock_mhz
    SETTLED_START=a.settled_start
    RESUME=a.resume
    SIMULATOR_STAMP=provenance()
    MAX_STEP_PS=a.max_step_ps
    if MAX_STEP_PS is not None and (not np.isfinite(MAX_STEP_PS) or MAX_STEP_PS<=0):p.error('Maximum timestep must be positive and finite')
    if CLOCK_MHZ!=400 and a.test!='dll':p.error('Non-nominal --clock-mhz requires --test dll')
    if not .45<=a.duty<=.55:p.error('DLL duty must be between 0.45 and 0.55')
    if (a.duty!=.5 or a.clock_corners) and a.test!='dll':p.error('Clock duty options require --test dll')
    if a.control_v is not None and (a.test!='delay' or not 0<=a.control_v<=REQ['digital_supply_v']):
        p.error('--control-v requires --test delay and a control between 0 and 1.8 V')
    if a.fast_rc:a.extracted=True
    if a.extracted:
        EXTRACTED=True;ARTIFACT_ROOT=ROOT/'build/analog_extracted'
        manifest=json.loads((ROOT/'build/extracted/current.json').read_text())
        if not manifest['passed']:p.error('RC extraction is not qualified')
        required={'driver':{'openlvds_driver_core','lvds_bias'},
                  'receiver':{'openlvds_receiver_core','lvds_bias'},
                  'receiver-rate':{'openlvds_receiver_core','lvds_bias'},
                  'dll':{'openlvds_dll_analog','lvds_bias'},
                  'delay':{'openlvds_delay_line'}}
        needed=set().union(*required.values()) if a.test=='all' else required[a.test]
        missing=needed-set(manifest['designs'])
        if missing:p.error('Missing required extracted cores: '+', '.join(sorted(missing)))
        try:SOURCE_BYTES,EXTRACTION_INPUTS,_=library(extracted=True,fast=a.fast_rc,designs=needed)
        except (ValueError,KeyError,FileNotFoundError) as error:p.error(str(error))
        if a.fast_rc:
            certificate=json.loads((ROOT/'build/rc_validation/summary.json').read_text())
            if not valid_certificate(certificate,EXTRACTION_INPUTS,subset=True):
                p.error('Fast-RC comparison failed or is stale')
            ARTIFACT_ROOT=ROOT/'build/analog_fast'
    ct=list(itertools.product(REQ['process_corners'],REQ['temperatures_c'])) if a.corners else [('tt',25)]
    if a.process or a.temperature is not None:
        ct=list(itertools.product(a.process.split(',') if a.process else REQ['process_corners'],
            [a.temperature] if a.temperature is not None else REQ['temperatures_c']))
        if any(c not in REQ['process_corners'] for c,t in ct): p.error('Unknown process corner')
    tag='clock_corners' if a.clock_corners else 'corners' if a.corners else 'subset' if a.process or a.temperature is not None else 'nominal'
    suffix=case_name('tt',25,CLOCK_MHZ,a.duty).removeprefix('dll_tt_25')
    summary_path=ARTIFACT_ROOT/f'summary_{a.test}_{tag}{suffix}.json'
    summary_path.parent.mkdir(parents=True,exist_ok=True);summary_path.unlink(missing_ok=True)
    jobs=[]
    for c,t in ct:
        if a.test in ['all','driver']: jobs.append((driver,(c,t)))
        if a.test in ['all','receiver']: jobs.append((receiver,(c,t)))
        if a.test in ['all','receiver-rate']:jobs.append((receiver_rate,(c,t)))
        if a.test in ['all','dll']:
            clocks=list(itertools.product(REQ['clock_test_mhz'],REQ['clock_duty'])) if a.clock_corners else [(CLOCK_MHZ,a.duty)]
            if a.clock_corners:
                for prefix in ['', 'physical_']:
                    trace=ROOT/'build/openpll'/('physical_clock.csv' if prefix else 'clock.csv')
                    report=ROOT/'build/openpll'/('physical_summary.json' if prefix else 'summary.json')
                    if trace.exists() and report.exists():
                        evidence=json.loads(report.read_text())
                        if evidence.get('passed') and evidence.get('clock_sha256')==hashlib.sha256(trace.read_bytes()).hexdigest():
                            clocks.append((400,trace_duty(trace)))
            jobs.extend((dll,(c,t,f,d)) for f,d in dict.fromkeys(clocks))
        if a.test in ['all','delay']:
            for ctrl in [a.control_v] if a.control_v is not None else [1.,1.1,1.2,1.3,1.4,1.5]: jobs.append((delay_line,(c,t,ctrl)))
    with ThreadPoolExecutor(max_workers=a.jobs) as pool:
        results=dict(pool.map(lambda item:item[0](*item[1]),jobs))
    out=ARTIFACT_ROOT; out.mkdir(parents=True,exist_ok=True)
    summary=dict(passed=all(x['passed'] for x in results.values()),corners=a.corners,
                 supply_sweep=False,results=results)
    summary_path.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(passed=summary['passed'],cases=len(results),
        failed=[k for k,v in results.items() if not v['passed']],supply_sweep=False),indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__': sys.exit(main())
