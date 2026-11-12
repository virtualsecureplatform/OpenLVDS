#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Transistor-level validation using real SKY130 corner models."""
import argparse
import fcntl
from concurrent.futures import ThreadPoolExecutor
import hashlib
import itertools
import math
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
from evidence_scope import TOPS,scope_hash,matches as evidence_matches
from dll_case import case_name,trace_duty
from spice_slots import slot
from dll_measurements import edges as level_edges
import xyce_profile_300

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
# Asynchronous I/O macro contract (io_300.json). None keeps the legacy
# requirements.json benches and artifact locations byte-for-byte.
CONTRACT=None
PROFILE='baseline'
IO_SCHEMA='openlvds-io-300-v1'
IO_TESTS=['driver','receiver','receiver-rate','link','timing','power']
MC_TESTS=['driver-mc','receiver-mc']

def use_contract(name,root=ROOT):
    """Bind every limit, hash and artifact path to the I/O macro contract."""
    global REQ,REQ_HASH,CONTRACT,ARTIFACT_ROOT
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():raise ValueError('Missing or external contract: '+name)
    terms=json.loads(path.read_text())
    if terms.get('schema')!=IO_SCHEMA:raise ValueError('Unsupported analog contract schema')
    REQ=terms['requirements'];REQ_HASH=hashlib.sha256(path.read_bytes()).hexdigest()
    CONTRACT=name;ARTIFACT_ROOT=ROOT/'build/io_300/analog'

def contract_step_ps():
    """Step ceiling for contract Xyce runs while stimulus is applied: five
    times the pinned profile's reference step (10 ps baseline, 5 ps refined,
    2.5 ps strict). At 10 ps, edges, levels and ripple match
    truncation-error-controlled runs; the 50 ps overshoot spikes on 1.8 V
    nodes read about 15 mV low, which the stress check allows for."""
    return 5*xyce_profile_300.PROFILES[PROFILE]['maxstep_ps']

QUIET_STEP_PS=500.
def quiet_until(ns):
    """Deck marker: no stimulus before this time, so steps may be coarse."""
    return f'*QUIET_UNTIL {ns:g}\n' if CONTRACT and ns>0 else ''

def contract_ui_ns():
    """Shortest unit interval in the contract; the strictest 0.3 tui bound."""
    return 1000/(max(REQ['clock_test_mhz'])*REQ['bits_per_cycle'])

def prbs7(count,state=0x7f):
    bits=[]
    for _ in range(count):
        new=((state>>6)^(state>>5))&1;state=((state<<1)|new)&0x7f;bits.append(new)
    return bits

def header(corner,temp):
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    numerics='.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
    # Contract runs on Xyce: step size follows Newton iteration count under a
    # fixed ceiling. Truncation-error step control drives the step toward zero
    # on the 5 V devices' near-floating body nodes until Newton fails.
    if CONTRACT and engine()=='xyce':numerics=xyce_profile_300.options(PROFILE)+'.options timeint erroption=1\n'
    return f'''OpenLVDS SKY130 fixed-supply bench {corner} {temp}C
.lib "{pdk}/libs.tech/ngspice/sky130.lib.spice" {corner}
.include "{ROOT}/analog/openlvds.spice"
.options device temp={temp}
{numerics}VIO VDDIO 0 PWL(0 0 1n 3.3)
VDIG VDDD 0 PWL(0 0 1n 1.8)
VREF VREF 0 PWL(0 0 1n 1.2)
'''

def archive_previous(out):
    files=[p for p in out.iterdir() if p.is_file() and not p.name.startswith('.')]
    if not files:return
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    stamp=hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()[:16]
    history=out/'history'/stamp;history.mkdir(parents=True,exist_ok=True)
    for path in files:
        target=history/path.name
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest()!=hashes[path.name]:raise ValueError('Analog history collision')
            path.unlink()
        else:path.replace(target)
    (history/'archive.json').write_text(json.dumps(dict(files=hashes,qualified_phy=False,
        reason='Prior evidence did not match the current fixture/circuit/provenance',producer_sha256=SCRIPT_HASH),indent=2)+'\n')

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
    ceiling=MAX_STEP_PS if MAX_STEP_PS is not None else contract_step_ps() if CONTRACT and engine()=='xyce' else None
    if ceiling is not None:
        import re
        from reduce_rc import number
        match=re.search(r'(?im)^\.tran\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)',deck)
        if match:
            limit=min(ceiling,number(match[4])*1e12)
            quiet=re.search(r'(?m)^\*QUIET_UNTIL (\S+)$',deck)
            if quiet and CONTRACT and engine()=='xyce' and QUIET_STEP_PS>limit:
                # Coarse ceiling while only the supplies and bias settle, the
                # stimulus ceiling from shortly before the first edge.
                # Xyce takes a schedule only in place of the start and ceiling fields.
                if number(match[3])!=0:raise ValueError('Scheduled step ceilings need a zero start time')
                fields=f'{{schedule(0,{QUIET_STEP_PS:g}p,{quiet[1]}n,{limit:.12g}p)}}'
            else:fields=f'{match[3]} {limit:.12g}p'
            deck=deck[:match.start()]+f'.tran {match[1]} {match[2]} {fields}'+deck[match.end():]
    if CONTRACT:
        # Contract benches exercise the released macros. Extracted macros are
        # flat, bias included, so internal nodes carry the flattened prefix.
        import re
        deck=re.sub(r'\bopenlvds_driver\b','openlvds_io_tx',deck);deck=re.sub(r'\bopenlvds_receiver\b','openlvds_io_rx',deck)
        def inside(macro,wrapper):
            def rewrite(match):
                path=match[2].split(':')
                return match[1]+(f':{macro}__{wrapper}__XCORE__'+'__'.join(path) if EXTRACTED else f':{wrapper}:XCORE:'+':'.join(path))
            return rewrite
        deck=re.sub(r'\b(XD):XCORE:((?:\w+:)*\w+)',inside('openlvds_io_tx','XTX'),deck)
        deck=re.sub(r'\b(XR\d*):XCORE:((?:\w+:)*\w+)',inside('openlvds_io_rx','XRX'),deck)
    elif EXTRACTED:
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
                evidence_matches(old,snapshot,SOURCE_BYTES,name.split('_')[0],bool(CONTRACT)) and
                (out/'runner.py').exists() and old.get('runner_sha256')==hashlib.sha256((out/'runner.py').read_bytes()).hexdigest())
            if cached and old.get('waveform_sha256'):
                cached=old['waveform_sha256']==hashlib.sha256(data.read_bytes()).hexdigest()
            if cached:REUSED[out]=old
        except (OSError,ValueError,KeyError):cached=False
    if not cached:
        archive_previous(out)
        (out/'summary.json').unlink(missing_ok=True);data.unlink(missing_ok=True)
        snapshot.write_bytes(SOURCE_BYTES)
        (out/'runner.py').write_bytes(SCRIPT_BYTES)
        path.write_text(deck)
        pinned=bool(CONTRACT and engine()=='xyce')
        with slot():
            result=subprocess.run((xyce_profile_300.command if pinned else spice_command)(out/(engine()+'.log'),path),
                                   cwd=out,capture_output=True,text=True,**(dict(env=xyce_profile_300.environment()) if pinned else {}))
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

def driver_dc_metrics(wave,windows=((1800,1850,-1),(1950,1990,1))):
    """Both settled data polarities with the bench's 100 ohm termination."""
    points=[]
    for low_ns,high_ns,sign in windows:
        a=wave[(wave[:,1]>=low_ns*1e-9)&(wave[:,1]<=high_ns*1e-9)]
        if not len(a):return dict(passed=False,error='Missing settled DC polarity')
        differential=sign*(a[:,3]-a[:,4]);common=(a[:,3]+a[:,4])/2
        ok=bool(np.all(differential>=REQ['tx_differential_min_v']) and
            np.all(differential<=REQ['tx_differential_max_v']) and
            np.all(common>=REQ['tx_common_mode_min_v']) and
            np.all(common<=REQ['tx_common_mode_max_v']))
        points.append(dict(polarity=sign,passed=ok,differential_mean_v=float(differential.mean()),
            common_mode_mean_v=float(common.mean()),differential_min_v=float(differential.min()),
            differential_max_v=float(differential.max()),common_mode_min_v=float(common.min()),
            common_mode_max_v=float(common.max())))
    return dict(passed=all(x['passed'] for x in points),termination_ohm=100,points=points)

# Internal nodes that reach a 1.8 V thin-oxide device terminal.
TX_THIN_NODES=['XD:XCORE:XLS:INB','XD:XCORE:XLS:AD','XD:XCORE:XLS:AB']
RX_THIN_NODES=['PP','PN','CO','CL','CT','NBC']

def rx_thin_nodes(instance='XR'):return [f'{instance}:XCORE:{n}' for n in RX_THIN_NODES]

def probes(nodes):return ' '.join(f'V({n})' for n in nodes)

def stress_metrics(wave,first,names,pins=()):
    """Largest voltage span any 1.8 V device can see across two of its terminals.

    Every such terminal is VDDD, VSS, a listed pin, or one of these probed
    nodes, so the span is bounded by the extremes over all of them.
    """
    limit=REQ['device_terminal_span_max_v']['01v8']-REQ['stress_measurement_guard_v'];vdd=REQ['digital_supply_v'];nodes={}
    for offset,name in enumerate(names):
        column=wave[:,first+offset];nodes[name]=[float(column.min()),float(column.max())]
    for name,index in pins:nodes[name]=[float(wave[:,index].min()),float(wave[:,index].max())]
    span=max([vdd]+[v[1] for v in nodes.values()])-min([0.]+[v[0] for v in nodes.values()])
    return dict(passed=bool(span<=limit),thin_oxide_terminal_span_v=float(span),limit_v=limit,guard_v=REQ['stress_measurement_guard_v'],nodes=nodes)

def settle_ns():
    """Preamble before stimulus when supplies ramp from zero: the driver's
    common-mode loop needs about a microsecond to reach its operating point."""
    return 0. if SETTLED_START else 1500.

def driver_guesses(p='P',n='N',instance='XD'):
    """Initial guesses for the driver's common-mode loop (contract benches).

    The poly-resistor model has a non-physical high-voltage branch; without a
    guess the DC solve of an extracted macro can land on it (sense node at
    megavolts, feedback amplifier railed). NODESET only seeds Newton: it
    clamps nothing in the solution or the transient.
    """
    # Only a solved DC start needs seeding; a supply ramp starts from zero.
    if not CONTRACT or not SETTLED_START:return ''
    guesses={p:1.25,n:1.25,f'{instance}:XCORE:CM':1.2,f'{instance}:XCORE:CMS':.6,f'{instance}:XCORE:SINK':1.3,f'{instance}:XCORE:TOP':2.1}
    return ''.join(f'.nodeset V({node})={value}\n' for node,value in guesses.items())

def driver_waveform_metrics(wave,start_ns,stop_ns,ui_ns):
    """TIA/EIA-644-A 4.1.4/4.1.5 generator waveform checks at the loaded pins."""
    t=wave[:,1];d=wave[:,3]-wave[:,4];cm=(wave[:,3]+wave[:,4])/2
    def plateau(a,b):
        keep=(t>a*1e-9)&(t<b*1e-9)
        return float(np.median(d[keep])) if np.count_nonzero(keep)>1 else None
    low,high=plateau(1800,1890),plateau(1950,1990)
    if low is None or high is None or not low<0<high:return dict(passed=False,error='Missing or inverted static driver plateaus')
    span=high-low;rows=[]
    for rising in [True,False]:
        begin=low+(.2 if rising else .8)*span;finish=low+(.8 if rising else .2)*span
        first=level_edges(t,d,level=begin,rising=rising);last=level_edges(t,d,level=finish,rising=rising)
        for a in first[(first>start_ns*1e-9)&(first<(stop_ns-ui_ns)*1e-9)]:
            later=last[last>a]
            if not len(later) or later[0]-a>ui_ns*1e-9:
                rows.append(dict(rising=rising,start_ns=float(a*1e9),duration_ps=None,monotonic=False));continue
            b=later[0];samples=np.r_[begin,d[(t>a)&(t<b)],finish]
            rows.append(dict(rising=rising,start_ns=float(a*1e9),duration_ps=float((b-a)*1e12),
                monotonic=bool(np.all(np.diff(samples)*(1 if rising else -1)>=-1e-6))))
    keep=(t>start_ns*1e-9)&(t<stop_ns*1e-9)
    durations=[r['duration_ps'] for r in rows if r['duration_ps'] is not None]
    limits=[REQ['tx_transition_20_80_min_ps'],REQ['tx_transition_max_ui_fraction']*ui_ns*1000]
    complete=bool(len(rows)>=20 and len(durations)==len(rows) and {r['rising'] for r in rows}=={True,False} and np.any(keep))
    if not complete:return dict(passed=False,error='Insufficient complete 20/80 transitions',edges=len(rows))
    ring=REQ['tx_ring_fraction_max']*span
    checks=dict(transition_within_limits=bool(min(durations)>=limits[0] and max(durations)<=limits[1]),
        monotonic_20_80=bool(all(r['monotonic'] for r in rows) or not REQ['tx_monotonic_20_80']),
        common_mode_within_limit=bool(np.ptp(cm[keep])<=REQ['tx_dynamic_common_mode_pp_max_v']),
        ring_within_limit=bool(d[keep].max()<=high+ring and d[keep].min()>=low-ring))
    return dict(passed=all(checks.values()),**checks,edges=len(rows),static_low_v=low,static_high_v=high,
        transition_limits_ps=limits,transition_min_ps=min(durations),transition_max_ps=max(durations),
        rise_max_ps=max(r['duration_ps'] for r in rows if r['rising']),fall_max_ps=max(r['duration_ps'] for r in rows if not r['rising']),
        common_mode_pp_v=float(np.ptp(cm[keep])),overshoot_v=float(max(d[keep].max()-high,low-d[keep].min())))

def driver_imbalance(dc):
    """Steady-state |VT|-|VT*| and VOS-VOS* between the two binary states."""
    try:a,b=dc['points']
    except (KeyError,ValueError):return dict(passed=False,error='Missing settled DC polarity')
    vod=abs(a['differential_mean_v']-b['differential_mean_v']);vos=abs(a['common_mode_mean_v']-b['common_mode_mean_v'])
    return dict(passed=bool(vod<=REQ['tx_differential_imbalance_max_v'] and vos<=REQ['tx_common_mode_imbalance_max_v']),
        differential_imbalance_v=float(vod),common_mode_imbalance_v=float(vos))

def driver_stimulus():
    """Return (PWL points in ns, transient stop in ns, scoring start in ns)."""
    stimulus=[(0,0),(1899.95,0),(1900.05,1.8),(1999.95,1.8),(2000.05,0)]
    if not CONTRACT:
        for i in range(1,433):
            at=2000+i*1.25;previous=1.8*((i-1)%2);value=1.8*(i%2)
            stimulus.extend([(at-.05,previous),(at+.05,value)])
        return stimulus,2540,2510
    # Two PRBS7 periods at the shortest contract UI expose pattern dependence
    # that the alternating legacy stimulus cannot.
    ui=contract_ui_ns();bits=prbs7(254);previous=0
    for i,bit in enumerate(bits,1):
        if bit!=previous:stimulus.extend([(2000+i*ui-.05,1.8*previous),(2000+i*ui+.05,1.8*bit)])
        previous=bit
    return stimulus,int(2000+(len(bits)+2)*ui)+1,2000+8*ui

def driver(corner,temp):
    name=f'driver_{corner}_{temp}'
    # Hold both polarities for DC qualification before exercising edge cadence.
    stimulus,stop_ns,score_ns=driver_stimulus()
    vd='VD D 0 PWL('+ ' '.join(f'{t:.9f}n {v}' for t,v in stimulus)+')'
    deck=header(corner,temp)+'''IREF IREF 0 PWL(0 0 1n 35u)
DRIVER_STIMULUS
XD D P N VREF IREF VDDIO VDDD 0 openlvds_driver
RT P N 100
CP P 0 2p
CN N 0 2p
DRIVER_GUESSESDRIVER_QUIET.tran 5p TRAN_STOPn 0 1n
.print tran V(D) V(P) V(N) V(XD:XCORE:SINK) V(XD:XCORE:TOP) V(XD:XCORE:DP) V(XD:XCORE:DN) THIN_PROBES
.end
'''
    deck=deck.replace('DRIVER_STIMULUS',vd).replace('TRAN_STOP',str(stop_ns)).replace('DRIVER_GUESSES',driver_guesses()).replace('DRIVER_QUIET',quiet_until(1890)).replace(' THIN_PROBES',' '+probes(TX_THIN_NODES) if CONTRACT else '')
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        res=driver_metrics(wave,score_ns)
        res['dc_output']=driver_dc_metrics(wave)
        res['loaded_eye_passed']=res['passed']
        res['passed']=res['polarity_ok'] and res['transitions_ok'] and res['dc_output']['passed']
        if CONTRACT:
            # The released I/O macro must meet the loaded eye and the generator
            # waveform limits, not only DC levels.
            res['waveform']=driver_waveform_metrics(wave,score_ns,stop_ns,contract_ui_ns())
            res['imbalance']=driver_imbalance(res['dc_output'])
            res['pattern']='prbs7';res['unit_interval_ps']=contract_ui_ns()*1000
            res['stress']=stress_metrics(wave,9,TX_THIN_NODES,[('D',2)])
            res['passed']=bool(res['passed'] and res['loaded_eye_passed'] and res['waveform']['passed'] and res['imbalance']['passed'] and res['stress']['passed'])
    return name,save(out,res,deck)

def receiver(corner,temp):
    name=f'receiver_{corner}_{temp}'
    # Static threshold decision at each legal input common-mode: +/-100 mV.
    levels=REQ['rx_static_common_mode_v'] if CONTRACT else [.05,.2,.6,1.2,1.8,2.35]
    half=REQ['rx_threshold_v']/2
    lines=[]; expected=[]
    for i,cm in enumerate(levels):
        for sign in [-1,1]:
            k=len(expected); start=k*12
            for edge in [start,start+11.9]: lines.append((edge,cm+sign*half,cm-sign*half))
            expected.append((start+10,sign))
    vp=' '.join(f'{t}n {v:.6f}' for t,v,_ in lines)
    vn=' '.join(f'{t}n {v:.6f}' for t,_,v in lines)
    deck=header(corner,temp)+f'''IREF IREF 0 PWL(0 0 1n 35u)
VP P 0 PWL({vp})
VN N 0 PWL({vn})
XR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver
CQ Q 0 100f
.tran 10p {len(expected)*12}n 0 50p
.print tran V(P) V(N) V(Q) V(XR:XCORE:PP) V(XR:XCORE:PN) V(XR:XCORE:CO){' '+probes(rx_thin_nodes()[3:]) if CONTRACT else ''}
.end
'''
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        points=[]
        for t,sign in expected:
            v=float(np.interp(t*1e-9,wave[:,1],wave[:,4]))
            points.append(dict(time_ns=t,expected=sign>0,output_v=v,passed=v>1.44 if sign>0 else v<.36))
        res=dict(passed=all(x['passed'] for x in points),points=points)
        if CONTRACT:
            res['stress']=stress_metrics(wave,5,RX_THIN_NODES,[('Q',4)])
            res['passed']=bool(res['passed'] and res['stress']['passed'])
    return name,save(out,res,deck)

def folded_eye(t,v,start,ui,signs,low,high,step=5e-12):
    """Worst signed margin per sampling phase over every bit, and the open width.

    Bit i occupies [start+i*ui, start+(i+1)*ui). A positive margin at a phase
    means every bit is on the correct side of its threshold there.
    """
    phases=np.arange(0,ui,step);index=np.arange(len(signs));margins=[]
    for phase in phases:
        samples=np.interp(start+index*ui+phase,t,v)
        margins.append(float(np.min(np.where(signs>0,samples-high,low-samples))))
    margins=np.array(margins);open_=margins>=0
    # Longest run of open phases, allowing the eye to wrap across the UI edge.
    best=run=0
    for flag in np.r_[open_,open_]:
        run=run+1 if flag else 0;best=max(best,run)
    best=min(best,len(phases))
    return dict(best_margin_v=float(margins.max()),best_phase_ps=float(phases[int(margins.argmax())]*1e12),
        open_width_ps=float(best*step*1e12),phases=phases,margins=margins)

def link_metrics(wave,bits,start_ns,ui_ns):
    """Receiver-pin and receiver-output eyes for the transmitted sequence."""
    t=wave[:,1];d=wave[:,2];vr=wave[:,3]-wave[:,4];q=wave[:,5];ui=ui_ns*1e-9;vdd=REQ['digital_supply_v']
    sent=level_edges(t,d,level=vdd/2,rising=True);sent=np.sort(np.r_[sent,level_edges(t,d,level=vdd/2,rising=False)])
    def latency(signal,level):
        got=np.sort(np.r_[level_edges(t,signal,level=level,rising=True),level_edges(t,signal,level=level,rising=False)])
        got=got[got>sent[0]] if len(sent) else got
        if len(got)!=len(sent) or not len(sent):return None
        return float(np.median(got-sent))
    pin_lag,out_lag=latency(vr,0.),latency(q,vdd/2)
    if pin_lag is None or out_lag is None:
        return dict(passed=False,error='Transition count differs from the transmitted sequence',bits=len(bits))
    # Skip the first PRBS bits while the channel reaches its periodic state.
    skip=16;signs=np.where(np.array(bits[skip:])>0,1,-1);first=(start_ns*1e-9)+skip*ui
    threshold=REQ['link_rx_pin_eye_min_v']
    # Receiver-pin range is judged in operation. During power-up the driver
    # outputs sit near VDDIO until its common-mode loop settles (about 1 us).
    live=t>=start_ns*1e-9
    pin=folded_eye(t,vr,first+pin_lag,ui,signs,-threshold,threshold)
    out=folded_eye(t,q,first+out_lag,ui,signs,.2*vdd,.8*vdd)
    sampled=np.interp(first+out_lag+np.arange(len(signs))*ui+out['best_phase_ps']*1e-12,t,q)>vdd/2
    errors=int(np.count_nonzero(sampled!=(signs>0)))
    got=np.sort(np.r_[level_edges(t,q,level=vdd/2,rising=True),level_edges(t,q,level=vdd/2,rising=False)])
    jitter=(got[got>sent[0]]-sent)*1e12
    checks=dict(rx_pin_eye_open=bool(pin['best_margin_v']>=0 and pin['open_width_ps']>=REQ['link_rx_pin_eye_width_min_ui']*ui_ns*1000),
        output_valid=bool(out['open_width_ps']>=REQ['link_output_valid_min_ps']),no_bit_errors=errors==0,
        pin_range=bool(min(wave[live,3].min(),wave[live,4].min())>=REQ['rx_pin_min_v'] and max(wave[live,3].max(),wave[live,4].max())<=REQ['rx_pin_max_v']))
    startup=float(max(wave[~live,3].max(),wave[~live,4].max())) if np.any(~live) else None
    return dict(passed=all(checks.values()),**checks,bits=len(bits),scored_bits=len(signs),bit_errors=errors,startup_pin_max_v=startup,
        rx_pin_eye_height_v=pin['best_margin_v']+threshold,rx_pin_eye_width_ps=pin['open_width_ps'],
        output_valid_width_ps=out['open_width_ps'],output_delay_ps=out_lag*1e12,
        output_data_dependent_jitter_pp_ps=float(np.ptp(jitter)),unit_interval_ps=ui_ns*1000)

def channel_ladder(leg,near,far,z0,delay_ns,section_ps=50.):
    """Lossless line as an LC ladder.

    The simulators' ideal delay element makes this driver's transient lose
    convergence in both Xyce and ngspice; a ladder with a 50 ps section delay
    (cutoff above 6 GHz, far beyond the 355 ps edges) does not.
    """
    sections=max(4,math.ceil(delay_ns*1000/section_ps));lines=[];previous=near
    for i in range(sections):
        node=far if i==sections-1 else f'TL{leg}_{i}'
        lines += [f'LTL{leg}_{i} {previous} {node} {z0*delay_ns/sections:.9g}n',f'CTL{leg}_{i} {node} 0 {delay_ns/z0/sections*1000:.9g}p']
        previous=node
    return lines

def link(corner,temp,mhz,delay_ns,count):
    """PRBS7 through the driver macro, the contract channel and the receiver macro."""
    name=f'link_{corner}_{temp}_{mhz}m_{delay_ns:g}ns'
    channel=REQ['channel'];ui=1000/(mhz*REQ['bits_per_cycle']);start=20.+settle_ns();bits=prbs7(count);points=[(0,0.)];previous=0
    for i,bit in enumerate(bits):
        if bit!=previous:points += [(start+i*ui-.05,1.8*previous),(start+i*ui+.05,1.8*bit)]
        previous=bit
    stop=int(start+(count+2)*ui+delay_ns)+2
    lines=['IREF_TX IREFT 0 PWL(0 0 1n 35u)','IREF_RX IREFR 0 PWL(0 0 1n 35u)',
        'VD D 0 PWL('+' '.join(f'{t:.9f}n {v:.9g}' for t,v in points)+')',
        'XD D TP TN VREF IREFT VDDIO VDDD 0 openlvds_driver','XR RP RN Q VREF IREFR VDDIO VDDD 0 openlvds_receiver','CQ Q 0 100f']
    pad=channel['pad_capacitance_per_pin_pf'];bond=channel['package_inductance_per_pin_nh']
    for leg,(tx,rx) in enumerate([('TP','RP'),('TN','RN')]):
        lines += [f'CPT{leg} {tx} 0 {pad}p',f'LT{leg} {tx} A{leg} {bond}n',
            f'RS{leg} A{leg} B{leg} {channel["series_resistance_per_leg_ohm"]}',
            *channel_ladder(leg,f'B{leg}',f'F{leg}',channel['differential_impedance_ohm']/2,delay_ns),
            f'LR{leg} F{leg} {rx} {bond}n',f'CPR{leg} {rx} 0 {pad}p']
    lines += [f'RTERM F0 F1 {channel["termination_ohm"]}',*driver_guesses('TP','TN').splitlines(),*quiet_until(start-10).splitlines(),f'.tran 10p {stop}n 0 200p','.print tran V(D) V(RP) V(RN) V(Q) V(TP) V(TN) '+probes(TX_THIN_NODES+rx_thin_nodes()),'.end']
    deck=header(corner,temp)+'\n'.join(lines)+'\n'
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        res=link_metrics(wave,bits,start,ui)
        res.update(clock_mhz=mhz,channel_delay_ns=delay_ns,pattern=REQ['link_pattern'],channel_model='LC ladder, 50 ps per section')
        res['stress']=stress_metrics(wave,8,TX_THIN_NODES+RX_THIN_NODES,[('D',2),('Q',5)])
        res['passed']=bool(res['passed'] and res['stress']['passed'])
    return name,save(out,res,deck)

def timing_slews_ps():
    """Receiver input 20-80% transitions spanning the driver's legal edge window."""
    low=REQ['tx_transition_20_80_min_ps'];high=REQ['tx_transition_max_ui_fraction']*1e6/(min(REQ['clock_test_mhz'])*REQ['bits_per_cycle'])
    return [float(low),round((low+high)/2,3),round(high,3)]

def crossing_after(t,v,level,rising,after):
    at=level_edges(t,v,level=level,rising=rising);at=at[at>after]
    return float(at[0]) if len(at) else None

def receiver_timing(corner,temp):
    """Liberty arcs: differential zero crossing to Q, against input slew and output load."""
    name=f'receiver_timing_{corner}_{temp}'
    loads=REQ['rx_output_load_ff'];slews=timing_slews_ps();vdd=REQ['digital_supply_v']
    cm=REQ['rx_rate_common_mode_v'];half=REQ['rx_rate_differential_v']/2;events=[];points=[(0,-1)]
    # After a supply ramp the 20 kohm capacitance-measurement node needs
    # tens of nanoseconds to return from the kick the ramp gives it.
    t0=0. if SETTLED_START else 100.
    for k,slew in enumerate(slews):
        ramp=slew/600  # ns for the full swing of a linear edge whose 20-80% takes `slew` ps
        for rising,at in [(True,t0+12+k*20),(False,t0+22+k*20)]:
            points += [(at-ramp/2,-1 if rising else 1),(at+ramp/2,1 if rising else -1)];events.append((k,rising,at))
    wave_p=' '.join(f'{t:.9g}n {cm+sign*half:.6f}' for t,sign in points);wave_n=' '.join(f'{t:.9g}n {cm-sign*half:.6f}' for t,sign in points)
    lines=[f'VP P 0 PWL({wave_p})',f'VN N 0 PWL({wave_n})']
    for i,load in enumerate(loads):
        lines += [f'IREF{i} IREF{i} 0 PWL(0 0 1n 35u)',f'XR{i} P N Q{i} VREF IREF{i} VDDIO VDDD 0 openlvds_receiver',f'CQ{i} Q{i} 0 {load}f']
    # A separate instance measures the INP pin capacitance: a 100 mV step
    # around the common mode through 20 kohm, with INN held at the common mode.
    series=20000.
    lines += [f'VSC SC 0 PWL(0 {cm-.05:.6f} {t0+12:g}n {cm-.05:.6f} {t0+12.1:g}n {cm+.05:.6f})',f'RSC SC PC {series}',f'VNC NC 0 {cm}',
        'IREFC IREFC 0 PWL(0 0 1n 35u)','XRC PC NC QC VREF IREFC VDDIO VDDD 0 openlvds_receiver','CQC QC 0 100f']
    lines += [*quiet_until(t0+5 if t0 else 0).splitlines(),f'.tran 5p {t0+12+len(slews)*20:g}n 0 50p','.print tran V(P) V(N) '+' '.join(f'V(Q{i})' for i in range(len(loads)))+' V(PC)','.end']
    deck=header(corner,temp)+'\n'.join(lines)+'\n'
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        t=wave[:,1];shape=(len(slews),len(loads))
        tables={k:np.full(shape,np.nan) for k in ['cell_rise','cell_fall','rise_transition','fall_transition']}
        for k,rising,at in events:
            for i in range(len(loads)):
                q=wave[:,4+i];mid=crossing_after(t,q,vdd/2,rising,at*1e-9)
                a=crossing_after(t,q,(.2 if rising else .8)*vdd,rising,at*1e-9);b=crossing_after(t,q,(.8 if rising else .2)*vdd,rising,at*1e-9)
                if mid is None or a is None or b is None or mid-at*1e-9>8e-9:continue
                tables['cell_rise' if rising else 'cell_fall'][k,i]=(mid-at*1e-9)*1e9
                tables['rise_transition' if rising else 'fall_transition'][k,i]=(b-a)*1e9
        complete=all(np.all(np.isfinite(x)&(x>0)) for x in tables.values())
        charged=crossing_after(t,wave[:,4+len(loads)],cm,True,(t0+12)*1e-9)
        # Valid only if the node had settled to its starting level before the step.
        settled=abs(float(np.interp((t0+11.9)*1e-9,t,wave[:,4+len(loads)]))-(cm-.05))<.002
        pin=(charged-(t0+12.05)*1e-9)/(math.log(2)*series)*1e12 if charged is not None and settled else None
        complete=bool(complete and pin is not None and 0<pin<5)
        res=dict(passed=bool(complete),input_pin_capacitance_pf=pin,input_transition_20_80_ps=slews,output_load_ff=loads,unit='ns',
            thresholds='input: differential zero crossing; output: 50% delay, 20-80% transition',
            **{k:[[None if not np.isfinite(v) else float(v) for v in row] for row in x] for k,x in tables.items()})
    return name,save(out,res,deck)

def driver_timing(corner,temp):
    """Effective D input capacitance from the RC delay through a known series resistor."""
    # 20 kohm makes the RC time far longer than the 100 ps source ramp, so the
    # 50% delay from the ramp midpoint is RC ln 2 to well under one percent.
    name=f'driver_timing_{corner}_{temp}';series=20000.;vdd=REQ['digital_supply_v'];t0=settle_ns()
    deck=header(corner,temp)+f'''IREF IREF 0 PWL(0 0 1n 35u)
VS S 0 PWL(0 0 {t0+10:g}n 0 {t0+10.1:g}n {vdd} {t0+40:g}n {vdd} {t0+40.1:g}n 0)
RS S D {series}
XD D P N VREF IREF VDDIO VDDD 0 openlvds_driver
RT P N 100
CP P 0 2p
CN N 0 2p
'''+driver_guesses()+quiet_until(t0+5)+f'''.tran 2p {t0+70:g}n 0 20p
.print tran V(S) V(D) V(P) V(N)
.end
'''
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        t=wave[:,1]-t0*1e-9;d=wave[:,3];rise=crossing_after(t,d,vdd/2,True,10e-9);fall=crossing_after(t,d,vdd/2,False,40e-9)
        if rise is None or fall is None:res=dict(passed=False,error='Input node did not cross its threshold')
        else:
            values=[(rise-10.05e-9)/(math.log(2)*series),(fall-40.05e-9)/(math.log(2)*series)]
            res=dict(passed=bool(0<min(values) and max(values)<5e-12),input_capacitance_rise_pf=values[0]*1e12,
                input_capacitance_fall_pf=values[1]*1e12,input_capacitance_pf=max(values)*1e12,series_resistance_ohm=series,
                method='50% crossing of an RC charge through the series resistor')
    return name,save(out,res,deck)

def supply_metrics(wave,quiet,active):
    """Average supply and reference currents in a quiet and a toggling window (Xyce source currents)."""
    t=wave[:,1];result={}
    for label,(start,stop) in [('quiet',quiet),('active',active)]:
        keep=(t>=start*1e-9)&(t<=stop*1e-9)
        if np.count_nonzero(keep)<2:return dict(passed=False,error='Missing supply-current window')
        mean=lambda column:float(abs(np.trapz(wave[keep,column],t[keep])/(t[keep][-1]-t[keep][0])))
        vddio,vddd,vref=mean(2),mean(3),mean(4)
        result[label]=dict(vddio_ma=vddio*1e3,vddd_ma=vddd*1e3,vref_ua=vref*1e6,
            power_mw=(vddio*REQ['analog_supply_v']+vddd*REQ['digital_supply_v'])*1e3)
    sane=all(0<result[k]['vddio_ma']<50 and result[k]['vddd_ma']<50 for k in result)
    return dict(passed=bool(sane),**result,iref_ua=REQ['reference_current_a']*1e6,
        scope='Macro only: excludes the external termination, reference buffer and bias sink')

def power(macro,corner,temp):
    """Datasheet supply currents: static, then toggling at the fastest contract clock."""
    if engine()!='xyce':raise ValueError('Supply-current benches print source currents and need Xyce')
    name=f'{macro}_power_{corner}_{temp}';period=1000/max(REQ['clock_test_mhz']);t0=settle_ns() if macro=='driver' else 0.
    common='IREF IREF 0 PWL(0 0 1n 35u)\n'
    if macro=='driver':
        body=f'''VD D 0 PULSE(0 {REQ['digital_supply_v']} {t0+30:g}n 100p 100p {period/2-.1:.12g}n {period:.12g}n)
XD D P N VREF IREF VDDIO VDDD 0 openlvds_driver
RT P N 100
CP P 0 2p
CN N 0 2p
'''+driver_guesses()
    else:
        low=REQ['rx_rate_common_mode_v']-REQ['rx_rate_differential_v']/2;high=REQ['rx_rate_common_mode_v']+REQ['rx_rate_differential_v']/2
        body=f'''VP P 0 PULSE({low:.12g} {high:.12g} 30n 100p 100p {period/2-.1:.12g}n {period:.12g}n)
VN N 0 PULSE({high:.12g} {low:.12g} 30n 100p 100p {period/2-.1:.12g}n {period:.12g}n)
XR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver
CQ Q 0 100f
'''
    deck=header(corner,temp)+common+body+quiet_until(t0+5 if t0 else 0)+f'.tran 10p {t0+80:g}n 0 200p\n.print tran I(VIO) I(VDIG) I(VREF)\n.end\n'
    out,wave,res=run_deck(name,deck)
    if wave is not None:res=supply_metrics(wave,(t0+10,t0+28),(t0+45,t0+78))
    return name,save(out,res,deck)

def mismatch_header(corner,temp,seed):
    """Local-mismatch model section with a recorded, reproducible seed."""
    if engine()!='ngspice':raise ValueError('Mismatch sampling is defined only for the pinned ngspice runtime')
    return header(corner+REQ['mismatch']['model_section_suffix'],temp)+f'.options seed={seed}\n'

def driver_mc(corner,temp,seed):
    name=f'driver_mc_{corner}_{temp}_s{seed}'
    deck=mismatch_header(corner,temp,seed)+'''IREF IREF 0 PWL(0 0 1n 35u)
VD D 0 PWL(0 0 99.95n 0 100.05n 1.8)
XD D P N VREF IREF VDDIO VDDD 0 openlvds_driver
RT P N 100
CP P 0 2p
CN N 0 2p
'''+driver_guesses()+'''.tran 100p 300n 0 1n
.print tran V(D) V(P) V(N)
.end
'''
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        dc=driver_dc_metrics(wave,((60,95,-1),(250,295,1)))
        res=dict(passed='points' in dc,seed=seed,dc_output=dc)
        if res['passed']:
            a,b=dc['points']
            res['values']=dict(differential_low_v=a['differential_mean_v'],differential_high_v=b['differential_mean_v'],
                common_mode_low_v=a['common_mode_mean_v'],common_mode_high_v=b['common_mode_mean_v'],
                differential_imbalance_v=b['differential_mean_v']-a['differential_mean_v'],
                common_mode_imbalance_v=b['common_mode_mean_v']-a['common_mode_mean_v'])
    return name,save(out,res,deck)

def receiver_mc(corner,temp,seed):
    """Input-referred trip point from slow up and down differential ramps."""
    name=f'receiver_mc_{corner}_{temp}_s{seed}'
    amplitude=REQ['rx_threshold_v'];hold,ramp=20,400;segment=2*(hold+ramp);levels=REQ['rx_static_common_mode_v']
    points=[]
    for k,cm in enumerate(levels):
        start=k*segment
        points += [(start,cm,-amplitude),(start+hold,cm,-amplitude),(start+hold+ramp,cm,amplitude),
                   (start+2*hold+ramp,cm,amplitude),(start+segment-.001,cm,-amplitude)]
    vp=' '.join(f'{t:.9g}n {cm+d/2:.6f}' for t,cm,d in points);vn=' '.join(f'{t:.9g}n {cm-d/2:.6f}' for t,cm,d in points)
    deck=mismatch_header(corner,temp,seed)+f'''IREF IREF 0 PWL(0 0 1n 35u)
VP P 0 PWL({vp})
VN N 0 PWL({vn})
XR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver
CQ Q 0 100f
.tran 100p {len(levels)*segment}n 0 500p
.print tran V(P) V(N) V(Q)
.end
'''
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        t=wave[:,1];d=wave[:,2]-wave[:,3];q=wave[:,4];values={};ok=True
        for k,cm in enumerate(levels):
            start=k*segment
            def trip(a,b,rising):
                keep=(t>=a*1e-9)&(t<=b*1e-9);at=level_edges(t[keep],q[keep],level=REQ['digital_supply_v']/2,rising=rising)
                return float(np.interp(at[0],t,d)) if len(at)==1 else None
            up=trip(start+hold,start+hold+ramp,True);down=trip(start+2*hold+ramp,start+segment-.001,False)
            if up is None or down is None:ok=False;values[f'{cm:g}']=None
            else:values[f'{cm:g}']=dict(offset_v=(up+down)/2,hysteresis_and_delay_v=up-down)
        res=dict(passed=ok,seed=seed,values=values)
    return name,save(out,res,deck)

def mismatch_statistics(test,results):
    """Contract rule |mean| + sigma*std per PVT point; a failed sample fails its point."""
    rule=REQ['mismatch'];groups={}
    for name,row in results.items():groups.setdefault(name.rsplit('_s',1)[0],[]).append(row)
    report={}
    for group,rows in sorted(groups.items()):
        entry=dict(samples=len(rows),valid=bool(all(r['passed'] for r in rows) and len(rows)>1),metrics={})
        if entry['valid']:
            if test=='receiver-mc':
                series={'offset_cm_'+k:[r['values'][k]['offset_v'] for r in rows] for k in rows[0]['values']}
                bounds={k:(-rule['rx_offset_bound_v'],rule['rx_offset_bound_v']) for k in series}
            else:
                series={k:[r['values'][k] for r in rows] for k in rows[0]['values']}
                vod=(REQ['tx_differential_min_v'],REQ['tx_differential_max_v']);vos=(REQ['tx_common_mode_min_v'],REQ['tx_common_mode_max_v'])
                dv,dc=REQ['tx_differential_imbalance_max_v'],REQ['tx_common_mode_imbalance_max_v']
                bounds=dict(differential_low_v=vod,differential_high_v=vod,common_mode_low_v=vos,common_mode_high_v=vos,
                    differential_imbalance_v=(-dv,dv),common_mode_imbalance_v=(-dc,dc))
            for key,data in series.items():
                mean=float(np.mean(data));std=float(np.std(data,ddof=1));low,high=bounds[key]
                entry['metrics'][key]=dict(mean=mean,std=std,minimum=float(min(data)),maximum=float(max(data)),
                    bound=[low,high],passed=bool(std>0 and mean-rule['sigma']*std>=low and mean+rule['sigma']*std<=high))
        entry['passed']=bool(entry['valid'] and all(m['passed'] for m in entry['metrics'].values()))
        report[group]=entry
    return report

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

def receiver_rate_metrics(wave,mhz=None):
    mhz=max(REQ['clock_test_mhz']) if mhz is None else mhz
    pulse=REQ['rx_minimum_valid_pulse_ps'] if CONTRACT else 2*REQ['minimum_sampling_margin_ps']
    period=1e-6/mhz
    # The legacy 25 ns window holds ten 410 MHz cycles; contract clocks are
    # slower, so score the same number of whole cycles instead.
    end=30e-9+12.5*period if CONTRACT else 55e-9
    a=wave[(wave[:,1]>30e-9)&(wave[:,1]<end)]
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
               min(high)>=pulse and min(low)>=pulse)
    return dict(passed=valid,clock_mhz=mhz,output_load_ff=100,minimum_valid_pulse_ps=pulse,
        input_differential_v=REQ['tx_differential_min_v'],rising_edges=len(rises),falling_edges=len(falls),
        high_valid_min_ps=min(high) if high else None,low_valid_min_ps=min(low) if low else None,
        output_min_v=float(q.min()),output_max_v=float(q.max()))

def receiver_rate(corner,temp,mhz=None):
    name=f'receiver_rate_{corner}_{temp}'+(f'_{mhz}m' if mhz is not None else '')
    mhz=max(REQ['clock_test_mhz']) if mhz is None else mhz
    period=1000/mhz;low=1.2-REQ['tx_differential_min_v']/2;high=1.2+REQ['tx_differential_min_v']/2
    deck=header(corner,temp)+f'''IREF IREF 0 PWL(0 0 1n 35u)
VP P 0 PULSE({low:.12g} {high:.12g} 5n 100p 100p {period/2-.1:.12g}n {period:.12g}n)
VN N 0 PULSE({high:.12g} {low:.12g} 5n 100p 100p {period/2-.1:.12g}n {period:.12g}n)
XR P N Q VREF IREF VDDIO VDDD 0 openlvds_receiver
CQ Q 0 100f
.tran 10p {int(36+12.5*period) if CONTRACT else 60}n 0 100p
.print tran V(P) V(N) V(Q){' '+probes(rx_thin_nodes()) if CONTRACT else ''}
.end
'''
    out,wave,res=run_deck(name,deck)
    if wave is not None:
        res=receiver_rate_metrics(wave,mhz)
        if CONTRACT:
            res['stress']=stress_metrics(wave,5,RX_THIN_NODES,[('Q',4)])
            res['passed']=bool(res['passed'] and res['stress']['passed'])
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
    if CONTRACT:res.update(contract=CONTRACT,qualified_io=False,numerical_profile=PROFILE if engine()=='xyce' else 'ngspice_legacy',
        step_control=f'Newton-iteration step control, {MAX_STEP_PS if MAX_STEP_PS is not None else contract_step_ps():g} ps ceiling under stimulus' if engine()=='xyce' else 'truncation error')
    res['schematic_sha256']=previous.get('schematic_sha256') if previous else SCHEMATIC_HASH
    res['extraction_inputs']=EXTRACTION_INPUTS
    res['simulator']=engine()
    res['simulator_provenance']=SIMULATOR_STAMP
    res['simulation_scope_sha256']=scope_hash((out/'source.spice').read_bytes(),out.name.split('_')[0],bool(CONTRACT))
    wave=out/'bench.cir.prn'
    if wave.exists():res['waveform_sha256']=hashlib.sha256(wave.read_bytes()).hexdigest()
    res['startup']='solved fixed-supply DC operating point' if SETTLED_START else '1 ns supply and reference ramp'
    (out/'summary.json').write_text(json.dumps(res,indent=2)+'\n')
    CASE_LOCKS.pop(out).close()
    return res

def main():
    global EXTRACTED,SOURCE_BYTES,ARTIFACT_ROOT,EXTRACTION_INPUTS,CLOCK_MHZ,MAX_STEP_PS,SETTLED_START,RESUME,SIMULATOR_STAMP,PROFILE
    # Limits and argument choices depend on the contract, so bind it first.
    early=argparse.ArgumentParser(add_help=False);early.add_argument('--contract')
    selected=early.parse_known_args()[0].contract
    if selected:use_contract(selected)
    p=argparse.ArgumentParser()
    p.add_argument('--contract',help='Qualify the asynchronous I/O macros against this contract (io_300.json)')
    p.add_argument('--profile',choices=sorted(xyce_profile_300.PROFILES),default='baseline',help='Pinned Xyce numerical profile for contract runs')
    p.add_argument('--corners',action='store_true')
    p.add_argument('--test',choices=['all','driver','receiver','receiver-rate','link','timing','power','delay','dll',*MC_TESTS],default='all')
    p.add_argument('--samples',type=int,help='Diagnostic mismatch sample count; fewer than the contract plan cannot pass')
    p.add_argument('--jobs',type=int,default=8)
    p.add_argument('--process',help='Comma-separated process subset for diagnosis')
    p.add_argument('--temperature',type=int,choices=REQ['temperatures_c'])
    p.add_argument('--extracted',action='store_true',help='Replace cores with GDS-extracted RC networks')
    p.add_argument('--fast-rc',action='store_true',help='Use separately qualified TICER RC approximation')
    p.add_argument('--raw-rc',action='store_true',help='Use the unreduced extraction (contract runs; proves the exact reduction)')
    p.add_argument('--control-v',type=float,help='Single internal delay-control test point; supplies remain fixed')
    p.add_argument('--clock-mhz',type=int,choices=REQ['clock_test_mhz'],default=400)
    p.add_argument('--duty',type=float,default=.5,help='DLL input high fraction, from 0.45 to 0.55')
    p.add_argument('--clock-corners',action='store_true',help='DLL frequency/duty matrix at the selected PVT, including available OpenPLL trace duties')
    p.add_argument('--max-step-ps',type=float,help='Tighten the existing maximum integration timestep')
    p.add_argument('--settled-start',action='store_true',help='Solve fixed-supply DC bias before reset and clock stimuli')
    p.add_argument('--resume',action='store_true',help='Reanalyze matching completed evidence; wait for an active case instead of overwriting it')
    a=p.parse_args()
    PROFILE=a.profile
    if not CONTRACT and a.test in ['link','timing','power']:p.error('The link, timing and power benches need --contract')
    if a.test=='power' and engine()!='xyce':p.error('The power bench needs the Xyce engine')
    if CONTRACT and a.test not in ['all',*IO_TESTS,*MC_TESTS]:p.error('The I/O contract covers only '+', '.join(IO_TESTS+MC_TESTS))
    mc=a.test in MC_TESTS
    if mc and (not CONTRACT or a.extracted or a.fast_rc or not a.settled_start or engine()!='ngspice'):
        p.error('Mismatch tests need --contract, --settled-start, the ngspice engine and the schematic netlist')
    if a.samples is not None and (not mc or a.samples<2):p.error('--samples needs a mismatch test and at least two samples')
    if CONTRACT and (a.clock_corners or a.clock_mhz!=400 or a.duty!=.5 or a.control_v is not None):p.error('Clock and delay options do not apply to the I/O contract')
    if not CONTRACT and a.profile!='baseline':p.error('--profile requires --contract')
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
    if a.fast_rc or a.raw_rc:a.extracted=True
    if a.raw_rc and (a.fast_rc or not CONTRACT):p.error('--raw-rc needs --contract and excludes --fast-rc')
    if a.extracted:
        EXTRACTED=True;ARTIFACT_ROOT=ROOT/'build/analog_extracted'
        manifest=json.loads((ROOT/'build/extracted/current.json').read_text())
        if not manifest['passed']:p.error('RC extraction is not qualified')
        required={'driver':{'openlvds_driver_core','lvds_bias'},
                  'receiver':{'openlvds_receiver_core','lvds_bias'},
                  'receiver-rate':{'openlvds_receiver_core','lvds_bias'},
                  'dll':{'openlvds_dll_analog','lvds_bias'},
                  'delay':{'openlvds_delay_line'}}
        if CONTRACT:
            ARTIFACT_ROOT=ROOT/('build/io_300/analog_extracted_raw' if a.raw_rc else 'build/io_300/analog_extracted')
            required={'driver':{'openlvds_io_tx'},'receiver':{'openlvds_io_rx'},'receiver-rate':{'openlvds_io_rx'},'link':{'openlvds_io_tx','openlvds_io_rx'},'timing':{'openlvds_io_tx','openlvds_io_rx'},'power':{'openlvds_io_tx','openlvds_io_rx'}}
        needed=set().union(*required.values()) if a.test=='all' else required[a.test]
        missing=needed-set(manifest['designs'])
        if missing:p.error('Missing required extracted cores: '+', '.join(sorted(missing)))
        try:SOURCE_BYTES,EXTRACTION_INPUTS,_=library(extracted=True,fast=a.fast_rc,designs=needed,raw=a.raw_rc)
        except (ValueError,KeyError,FileNotFoundError) as error:p.error(str(error))
        if a.fast_rc:
            certificate=json.loads((ROOT/'build/rc_validation/summary.json').read_text())
            if not valid_certificate(certificate,EXTRACTION_INPUTS,subset=True):
                p.error('Fast-RC comparison failed or is stale')
            ARTIFACT_ROOT=ROOT/('build/io_300/analog_fast' if CONTRACT else 'build/analog_fast')
    ct=list(itertools.product(REQ['process_corners'],REQ['temperatures_c'])) if a.corners else [('tt',25)]
    if a.process or a.temperature is not None:
        ct=list(itertools.product(a.process.split(',') if a.process else REQ['process_corners'],
            [a.temperature] if a.temperature is not None else REQ['temperatures_c']))
        if any(c not in REQ['process_corners'] for c,t in ct): p.error('Unknown process corner')
    tag='clock_corners' if a.clock_corners else 'corners' if a.corners else 'subset' if a.process or a.temperature is not None else 'nominal'
    suffix=case_name('tt',25,CLOCK_MHZ,a.duty).removeprefix('dll_tt_25')
    if CONTRACT and PROFILE!='baseline':ARTIFACT_ROOT=ARTIFACT_ROOT.with_name(ARTIFACT_ROOT.name+'_'+PROFILE)
    # Engines never share a directory: their evidence is compared, not mixed.
    if CONTRACT and engine()!='xyce':ARTIFACT_ROOT=ARTIFACT_ROOT.with_name(ARTIFACT_ROOT.name+'_'+engine())
    summary_path=ARTIFACT_ROOT/f'summary_{a.test}_{tag}{suffix}.json'
    summary_path.parent.mkdir(parents=True,exist_ok=True);summary_path.unlink(missing_ok=True)
    jobs=[]
    for c,t in ct:
        if a.test in ['all','driver']: jobs.append((driver,(c,t)))
        if a.test in ['all','receiver']: jobs.append((receiver,(c,t)))
        if a.test in ['all','receiver-rate']:
            jobs.extend((receiver_rate,(c,t,f)) for f in REQ['clock_test_mhz']) if CONTRACT else jobs.append((receiver_rate,(c,t)))
        if CONTRACT and a.test in ['all','timing']:jobs += [(driver_timing,(c,t)),(receiver_timing,(c,t))]
        if CONTRACT and a.test in ['all','power'] and engine()=='xyce':jobs += [(power,('driver',c,t)),(power,('receiver',c,t))]
        if CONTRACT and a.test in ['all','link']:
            count=REQ['minimum_extracted_nominal_bits'] if (c,t)==('tt',25) else REQ['minimum_extracted_corner_bits']
            jobs.extend((link,(c,t,f,delay,count)) for f in REQ['link_clock_mhz'] for delay in REQ['channel']['delay_ns'])
        if mc:
            plan=REQ['mismatch']['nominal_samples'] if (c,t)==('tt',25) else REQ['mismatch']['corner_samples']
            jobs.extend((driver_mc if a.test=='driver-mc' else receiver_mc,(c,t,seed)) for seed in range(1,(a.samples or plan)+1))
        if CONTRACT:continue
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
    if CONTRACT:summary.update(contract=CONTRACT,contract_sha256=REQ_HASH,qualified_io=False,numerical_profile=PROFILE)
    if mc:
        statistics=mismatch_statistics(a.test,results)
        planned=bool(a.samples is None and len(ct)==len(REQ['process_corners'])*len(REQ['temperatures_c']))
        summary.update(statistics=statistics,sample_plan_complete=planned,mismatch=REQ['mismatch'],
            passed=bool(planned and all(x['passed'] for x in statistics.values())))
        summary['results']={k:dict(passed=v['passed'],seed=v.get('seed'),values=v.get('values')) for k,v in results.items()}
        print(json.dumps({k:dict(samples=v['samples'],passed=v['passed'],metrics={m:[round(x['mean'],5),round(x['std'],5)] for m,x in v['metrics'].items()}) for k,v in statistics.items()},indent=1))
    summary_path.write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(dict(passed=summary['passed'],cases=len(results),
        failed=[k for k,v in results.items() if not v['passed']],supply_sweep=False),indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__': sys.exit(main())
