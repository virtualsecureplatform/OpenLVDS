#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Transistor-level PHY link, actual extracted DDR logic and analog cores.

Clock generation is a feed-forward partition: ideal source-synchronous stress
clocks or captured OpenPLL edges. DLL acquisition/phase is checked separately.
Every run reports that boundary, network hashes, bit errors, and eye metrics.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np
from spice_library import library
from rc_certificate import valid as valid_certificate
from spice_engine import command as spice_command,engine,provenance
from evidence_scope import matches as evidence_matches
from dll_case import case_name,trace_duty
from rx_aperture_evidence import load as load_rx_aperture
from spice_slots import slot

ROOT=Path(__file__).resolve().parents[1]
REQ_BYTES=(ROOT/'requirements.json').read_bytes()
REQ=json.loads(REQ_BYTES)

def edge_times(t,v,level=.9,rising=None):
    high=v>=level
    changes=high[:-1]!=high[1:]
    if rising is not None:changes &= high[1:]==rising
    i=np.where(changes)[0]
    return t[i]+(level-v[i])*(t[i+1]-t[i])/(v[i+1]-v[i])

def input_slews(t,v,start,end):
    values=[]
    for rising in [True,False]:
        mid=edge_times(t,v,rising=rising)
        before=edge_times(t,v,.18 if rising else 1.62,rising)
        after=edge_times(t,v,1.62 if rising else .18,rising)
        for at in mid[(mid>=start)&(mid<=end)]:
            lo=before[before<=at];hi=after[after>=at]
            if len(lo) and len(hi):values.append((hi[0]-lo[-1])*1e12)
    return dict(min_ps=min(values) if values else None,max_ps=max(values) if values else None)

def pwl(points):
    return 'PWL('+ ' '.join(f'{t:.9f}n {v:.9g}' for t,v in points)+')'

def clocks(a,total):
    t=1000/a.mhz
    duty=a.duty
    rng=np.random.default_rng(130)
    if a.clock_source=='ideal':
        events=[]
        for i in range(int(total/t)+20):
            for at,value in [(5+i*t,1),(5+i*t+a.duty*t,0)]:
                events.append((at,value))
        scope='ideal source-synchronous timing stress; DLL separately qualified'
    else:
        path=ROOT/'build/openpll'/('clock.csv' if a.clock_source=='openpll-rtl' else 'physical_clock.csv')
        raw=np.loadtxt(path,delimiter=',',skiprows=1)
        summary=ROOT/'build/openpll'/('summary.json' if a.clock_source=='openpll-rtl' else 'physical_summary.json')
        status=json.loads(summary.read_text())
        if not status['passed']:raise ValueError('OpenPLL waveform is outside the clock contract')
        if status.get('clock_sha256')!=hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError('OpenPLL edge trace changed after qualification')
        # Repeat an integral rising-edge-to-rising-edge span for short physical
        # fixtures. This preserves recorded deterministic jitter, not noise.
        rises=np.where(raw[:,1]==1)[0]
        start,end=raw[rises[0],0],raw[rises[-1],0]
        segment=raw[(raw[:,0]>=start)&(raw[:,0]<end)].copy();segment[:,0]-=start
        span=end-start;events=[]
        for n in range(int(total/span)+2):
            events.extend((5+n*span+float(at),int(v)) for at,v in segment)
        t=1000/status['frequency_mhz'];scope=status['kind']
        duty=trace_duty(path)
    if a.jitter_pp_ps:
        events=[(at+float(rng.choice([-1,1]))*a.jitter_pp_ps/2000,value) for at,value in events]
    # A measured DLL phase can be replayed as the clock partition's delay.
    phase=t/4
    if a.dll_phase:
        if getattr(a,'bundle',None):
            from phy_candidate import phase as candidate_phase
            status=candidate_phase(a.bundle,a.process,a.temperature,a.mhz,duty)
            phase_stamp=status['evidence_sha256']
        else:
            case=case_name(a.process,a.temperature,a.mhz,duty)
            path=ROOT/'build/analog_extracted'/case/'summary.json'
            status=json.loads(path.read_text())
            if not status['passed']:raise ValueError('DLL phase characterization failed')
            expected,_,_=library(extracted=True,designs={'openlvds_dll_analog','lvds_bias'})
            if not evidence_matches(status,path.with_name('source.spice'),expected,'dll'):
                raise ValueError('Measured DLL phase belongs to another active circuit')
            if status.get('simulator')!=engine():raise ValueError('Measured DLL phase uses a different simulator')
            phase_stamp=hashlib.sha256(path.read_bytes()).hexdigest()
        if abs(status.get('clock_duty',.5)-duty)>5e-7:raise ValueError('Measured DLL phase uses another clock duty')
        phase=(status['quarter_phase_min_ps']+status['quarter_phase_max_ps'])/2000*(t/(1000/a.mhz))
        scope+='; full-RC DLL phase at this process, temperature, frequency and duty; characterization SHA256 '+phase_stamp
    def waveform(offset):
        p=[(0,0.)]
        for at,value in events:
            if at+offset>total+10*t:break
            p.extend([(at+offset-.05,1.8*(1-value)),(at+offset+.05,1.8*value)])
        return p
    return waveform(0),waveform(phase),np.array([at for at,v in events if v]),t,scope

def word_stream(count):
    state=0x1274dba9;words=[]
    for _ in range(count):
        for _ in range(2):
            bit=((state>>31)^(state>>21)^(state>>1)^state)&1
            state=((state<<1)&0xffffffff)|bit
        words.append(state&3)
    return words

def parallel_stimulus(launch,words,previous_rise):
    # Match tx.sdc: an upstream register publishes the next pair 250 ps
    # after the preceding rising edge. D0 traverses the serializer's XOR
    # input logic before its capture flop; a late half-nanosecond stimulus
    # would impose a different input timing contract from physical signoff.
    data0=[(0,1.8)];data1=[(0,0.)]
    for at,word in zip(launch,words):
        change=previous_rise+.25
        if change+.05>=at:raise ValueError('Parallel data has no setup interval')
        for points,bit in [(data0,word&1),(data1,(word>>1)&1)]:
            previous=points[-1][1]
            points.extend([(change-.05,previous),(change+.05,1.8*bit)])
        previous_rise=at
    return data0,data1

def instance(label,name,nodes,models):
    return 'X'+label+' '+' '.join(nodes[x] for x in models[name]['ports'])+' '+name


# Same public-output window used by the native capture characterization.
PUBLICATION_WINDOW_NS=(.80,1.05)
PUBLICATION_STEP_NS=.005


def decode_public_pairs(t,q0,q1,valid,publication):
    offsets=np.arange(PUBLICATION_WINDOW_NS[0],PUBLICATION_WINDOW_NS[1]+PUBLICATION_STEP_NS/2,PUBLICATION_STEP_NS)
    samples=publication[:,None]+offsets[None,:]*1e-9
    values=np.array([np.interp(samples.ravel(),t,v).reshape(samples.shape) for v in [q0,q1,valid]])
    low=values.min(axis=2);high=values.max(axis=2)
    legal=((high[0]<.36)|(low[0]>1.44))&((high[1]<.36)|(low[1]>1.44))&(low[2]>1.44)
    pairs=(low[0]>1.44).astype(int)+2*(low[1]>1.44).astype(int)
    return np.where(legal,pairs,-1)


def analyze(wave,words,launch,period,data_delay_ns=1.2,aperture=None):
    t=wave[:,1];qclk=wave[:,7]
    edges=edge_times(t,qclk,rising=True)
    window_end=PUBLICATION_WINDOW_NS[1]*1e-9
    publication=edges[(edges+window_end>launch[0]*1e-9)&(edges+window_end<t[-1])]
    decoded=decode_public_pairs(t,wave[:,8],wave[:,9],wave[:,10],publication)
    sync=min(16,len(words));offset=None
    for i in range(min(16,len(decoded)-sync+1)):
        if list(decoded[i:i+sync])==words[:sync]:offset=i;break
    if offset is None:return dict(passed=False,error='No correctly ordered payload preamble',
        observed=decoded[:24].tolist(),expected=words[:24],
        rx_clock_min_v=float(qclk.min()),rx_clock_max_v=float(qclk.max()),rx_clock_rising_edges=len(edges),
        publication_window_ns=list(PUBLICATION_WINDOW_NS))
    received=decoded[offset:offset+len(words)]
    errors=sum(int(a)!=int(b) for a,b in zip(received,words))+max(0,len(words)-len(received))
    # Publication exports the preceding complete pair. Include its capture
    # edges, rather than starting the margin window one word too late.
    start_publication=publication[offset]
    earlier=edges[edges<start_publication-1e-15]
    first=earlier[-1] if len(earlier) else start_publication-period*1e-9
    last=publication[min(offset+len(words)-1,len(publication)-1)]
    # Characterized setup/hold is subtracted before requiring the additional
    # 200ps link margin. Legacy estimates are restricted to diagnostics.
    aperture=aperture or dict(setup_ps=200,hold_ps=80,qualified=False)
    data_edges=edge_times(t,wave[:,6]);sampling=edge_times(t,qclk)
    sampling=sampling[(sampling>=first-1e-15)&(sampling<last-1e-15)]
    setup=[];hold=[]
    for at in sampling:
        before=data_edges[data_edges<at];after=data_edges[data_edges>at]
        if len(before):setup.append((at-before[-1])*1e12-aperture['setup_ps'])
        if len(after):hold.append((after[0]-at)*1e12-aperture['hold_ps'])
    mask=(t>=first)&(t<=last)
    vd=wave[:,2]-wave[:,3];vc=(wave[:,2]+wave[:,3])/2
    # Sensitivity belongs at the input clock crossing, before the comparator
    # delay. Correlate each digital edge with its same-polarity input edge.
    clock_diff=wave[:,4]-wave[:,5]
    pin_rise=edge_times(t,clock_diff,level=0,rising=True)
    pin_fall=edge_times(t,clock_diff,level=0,rising=False)
    pin_sampling=[]
    for at in sampling:
        rising=np.interp(at+1e-12,t,qclk)>np.interp(at-1e-12,t,qclk)
        candidates=pin_rise if rising else pin_fall
        previous=candidates[candidates<at+1e-15]
        if len(previous):pin_sampling.append(previous[-1])
    # Each published word comes from the preceding rising/falling capture pair.
    # Require one ordered pair per payload word and the expected analog sign.
    expected_sign=np.array([1 if word&(1<<bit) else -1 for word in words for bit in [0,1]])
    signed_samples=np.interp(pin_sampling,t,vd)
    capture_count_ok=len(sampling)==len(expected_sign)==len(signed_samples)
    signed_ok=bool(capture_count_ok and np.all(signed_samples*expected_sign>=REQ['rx_threshold_v']))
    clock_crossings=edge_times(t,clock_diff,level=0)
    clock_centers=(clock_crossings[:-1]+clock_crossings[1:])/2
    if pin_sampling:
        clock_centers=clock_centers[(clock_centers>=min(pin_sampling))&(clock_centers<=max(pin_sampling))]
    else:clock_centers=np.array([])
    clock_amplitudes=abs(np.interp(clock_centers,t,clock_diff))
    clock_eye_ok=bool(len(clock_amplitudes) and np.all(clock_amplitudes>=REQ['rx_threshold_v']))
    amplitudes=abs(signed_samples)
    pin_min=float(np.min(wave[mask,2:6]));pin_max=float(np.max(wave[mask,2:6]))
    transmitter=[]
    if wave.shape[1]>=16 and pin_sampling:
        for label,p,n in [('data',12,13),('clock',14,15)]:
            crossings=edge_times(t,wave[:,p]-wave[:,n],level=0)
            centers=(crossings[:-1]+crossings[1:])/2
            centers=centers[(centers>=min(pin_sampling)-data_delay_ns*1e-9)&
                            (centers<=max(pin_sampling)-data_delay_ns*1e-9)]
            swing=abs(np.interp(centers,t,wave[:,p]-wave[:,n]))
            common=np.interp(centers,t,(wave[:,p]+wave[:,n])/2)
            ok=bool(len(swing) and np.all(swing>=REQ['tx_differential_min_v']) and
                np.all(swing<=REQ['tx_differential_max_v']) and np.all(common>=REQ['tx_common_mode_min_v']) and
                np.all(common<=REQ['tx_common_mode_max_v']))
            transmitter.append(dict(lane=label,passed=ok,qualification='diagnostic_loaded_eye',differential_min_v=float(swing.min()) if len(swing) else None,
                differential_max_v=float(swing.max()) if len(swing) else None,
                common_mode_min_v=float(common.min()) if len(common) else None,
                common_mode_max_v=float(common.max()) if len(common) else None))
    capture_slews={name:input_slews(t,wave[:,col],first,last) for name,col in [('data',6),('clock',7)]}
    domain=aperture.get('input_slew_ps',[20,200])
    slew_ok=all(v['min_ps'] is not None and v['min_ps']>=domain[0] and v['max_ps']<=domain[1] for v in capture_slews.values())
    # DC output limits are qualified independently in the driver bench.
    # Loaded TX eye metrics remain diagnostic; sensitivity is measured at RX.
    electrical_ok=bool(capture_count_ok and signed_ok and clock_eye_ok and len(amplitudes) and
        np.all(amplitudes>=REQ['rx_threshold_v']) and pin_min>=REQ['rx_pin_min_v'] and
        pin_max<=REQ['rx_pin_max_v'] and len(transmitter)==2 and (not aperture.get('qualified') or slew_ok))
    return dict(passed=errors==0 and electrical_ok,checked_bits=2*len(received),word_errors=errors,
        publication_window_ns=list(PUBLICATION_WINDOW_NS),publication_step_ps=PUBLICATION_STEP_NS*1000,
        first_payload_publication_ns=float(start_publication*1e9),
        electrical_passed=electrical_ok,capture_count_passed=capture_count_ok,
        capture_input_slew_ps=capture_slews,capture_aperture_slew_passed=slew_ok,
        signed_receive_eye_passed=signed_ok,clock_receive_eye_passed=clock_eye_ok,
        clock_sampling_differential_min_v=float(clock_amplitudes.min()) if len(clock_amplitudes) else None,
        transmitter=transmitter,rx_pin_min_v=pin_min,rx_pin_max_v=pin_max,
        sampling_differential_min_v=float(np.min(amplitudes)) if len(amplitudes) else None,
        sampling_differential_max_v=float(np.max(amplitudes)) if len(amplitudes) else None,
        alignment=offset,setup_margin_ps=min(setup) if setup else None,
        hold_margin_ps=min(hold) if hold else None,
        rx_input_common_min_v=float(np.min(vc[mask])),rx_input_common_max_v=float(np.max(vc[mask])),
        rx_differential_peak_v=float(np.max(abs(vd[mask]))))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--bits',type=int,default=4096)
    p.add_argument('--process',choices=REQ['process_corners'],default='tt')
    p.add_argument('--temperature',type=int,choices=REQ['temperatures_c'],default=25)
    p.add_argument('--mhz',type=float,choices=REQ['clock_test_mhz'],default=400)
    p.add_argument('--duty',type=float,choices=REQ['clock_duty'],default=.5)
    p.add_argument('--skew-ps',type=float,default=0)
    p.add_argument('--eye-shift-ps',type=float,default=0)
    p.add_argument('--jitter-pp-ps',type=float,default=100)
    p.add_argument('--clock-source',choices=['ideal','openpll-rtl','openpll-physical'],default='ideal')
    p.add_argument('--fast-rc',action='store_true')
    p.add_argument('--bundle',help='Use an isolated staged PHY instead of active extraction pointers')
    p.add_argument('--diagnostic',action='store_true',help='Permit an unqualified approximation for bring-up; cannot release')
    p.add_argument('--aperture-table',help='Completed full-RC capture table; otherwise discover the latest current table')
    p.add_argument('--dll-phase',action='store_true')
    p.add_argument('--settled-start',action='store_true',help='Begin from solved fixed-supply DC bias; startup acquisition is checked separately')
    p.add_argument('--training-ns',type=float,help='Training before payload (default 256 cycles with settled-start, otherwise at least 800 ns)')
    a=p.parse_args()
    if a.clock_source!='ideal' and (a.mhz!=400 or a.duty!=.5):
        p.error('OpenPLL captures are the configured 400 MHz mode; duty comes from the recorded trace')
    if a.bits<32 or a.bits%2:p.error('Even bit count >= 32 required')
    certificate=None
    if a.fast_rc and not a.diagnostic:
        certificate_path=Path(a.bundle)/'rc_certificate.json' if a.bundle else ROOT/'build/rc_validation/summary.json'
        certificate=json.loads(certificate_path.read_text())
        if not certificate['passed']:p.error('Fast-RC comparison is not qualified')
    source_path=Path(a.bundle)/'full.spice' if a.bundle else ROOT/'analog/openlvds.spice'
    source_bytes=source_path.read_bytes()
    runner_bytes=Path(__file__).read_bytes()
    simulator_stamp=provenance()
    if a.bundle:
        from phy_candidate import load
        lib,inputs,models=load(a.bundle,a.fast_rc)
        a.bundle=str(Path(a.bundle).resolve().relative_to(ROOT))
    else:lib,inputs,models=library(extracted=True,digital=True,fast=a.fast_rc)
    if source_path.read_bytes()!=source_bytes:p.error('Analog source changed while assembling the circuit')
    if certificate and not valid_certificate(certificate,inputs):p.error('Fast-RC certificate is stale or incomplete')
    rx_model=models['openlvds_ddr_rx']
    try:
        aperture=load_rx_aperture(rx_model.get('exact_sha256',rx_model['netlist_sha256']),a.process,a.temperature,a.aperture_table)
    except (OSError,ValueError,KeyError,TypeError) as error:
        if not a.diagnostic or a.aperture_table:p.error(str(error))
        aperture=dict(qualified=False,setup_ps=200,hold_ps=80,qualification='legacy diagnostic estimate')
    config=dict(vars(a),simulator=engine(),rx_aperture=aperture)
    if a.bundle:config['bundle_manifest_sha256']=hashlib.sha256((Path(a.bundle)/'manifest.json').read_bytes()).hexdigest()
    nominal_period=1000/a.mhz
    minimum_training=256*nominal_period
    training=a.training_ns if a.training_ns is not None else minimum_training if a.settled_start else max(800,minimum_training)
    if training<50:p.error('At least 50 ns training is required')
    if not a.diagnostic and training<minimum_training:p.error('Qualified runs require the PHY startup training of 256 clock cycles')
    total=training+50+(a.bits/2+16)*nominal_period
    c0,c90,rises,period,scope=clocks(a,total)
    if a.training_ns is None:
        actual_training=256*period if a.settled_start else max(800,256*period)
        if actual_training!=training:
            training=actual_training
            total=training+50+(a.bits/2+16)*period
            c0,c90,rises,period,scope=clocks(a,total)
    if not a.diagnostic and training<256*period:p.error('Qualified runs require 256 cycles at the actual clock frequency')
    clock_bytes=(pwl(c0)+pwl(c90)).encode()
    fingerprint=hashlib.sha256(lib+REQ_BYTES+json.dumps(config,sort_keys=True).encode()+runner_bytes+simulator_stamp.encode()+clock_bytes+scope.encode()).hexdigest()
    name=f'{a.process}_{a.temperature}_{a.mhz:g}m_d{a.duty:g}_s{a.skew_ps:g}_e{a.eye_shift_ps:g}_{a.clock_source}_{a.bits}'
    out=ROOT/'build/link'/name/fingerprint[:12];out.mkdir(parents=True,exist_ok=True)
    lock=(out/'.run.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:p.error('This exact link case is already running')
    (out/'summary.json').unlink(missing_ok=True)
    (out/'bench.cir.prn').unlink(missing_ok=True)
    (out/'runner.py').write_bytes(runner_bytes)
    (out/'requirements.json').write_bytes(REQ_BYTES)
    (out/'analog_source.spice').write_bytes(source_bytes)
    (out/'library.spice').write_bytes(lib)
    (out/'rx_aperture.json').write_text(json.dumps(aperture,indent=2)+'\n')
    eligible=np.where(rises>=training)[0]
    if len(eligible)<a.bits/2+10:p.error('Clock waveform is too short')
    launch=rises[eligible[0]:eligible[0]+a.bits//2]
    words=word_stream(len(launch))
    data0,data1=parallel_stimulus(launch,words,rises[eligible[0]-1])
    txnodes={'VGND':'0','VPWR':'VDDD','clk_400':'CLK0','clk_90':'CLK90',
        'clock_ready':'VDDD','dll_locked':'VDDD','enable':'VDDD','reset_n':'RESET_N',
        'tx_data[0]':'D0','tx_data[1]':'D1','tx_ready':'TXREADY','tx_serial':'TXDATA','forwarded_clock':'TXCLOCK'}
    rxnodes={'VGND':'0','VPWR':'VDDD','clk':'RXCLOCK','reset_n':'RESET_N','serial':'RXDATA',
             'data[0]':'Q0','data[1]':'Q1','valid':'RXVALID'}
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
    lines=[f'OpenLVDS extracted link {name}',f'.lib "{pdk}" {a.process}',
        f'.include "{out}/library.spice"',f'.options device temp={a.temperature}',
        '.options timeint method=gear reltol=1e-4 abstol=1e-12',
        'VIO VDDIO 0 PWL(0 0 1n 3.3)','VDIG VDDD 0 PWL(0 0 1n 1.8)',
        'VREF VREF 0 PWL(0 0 1n 1.2)','VRST RESET_N 0 PWL(0 0 2n 0 2.1n 1.8)',
        'IREF_TX IREF_TX 0 PWL(0 0 1n 35u)','IREF_RX IREF_RX 0 PWL(0 0 1n 35u)',
        'VCLK0 CLK0 0 '+pwl(c0),'VCLK90 CLK90 0 '+pwl(c90),
        'VD0 D0 0 '+pwl(data0),'VD1 D1 0 '+pwl(data1),
        instance('TX','openlvds_tx_core',txnodes,models),
        'XBT IREF_TX NBT VDDIO 0 lvds_bias','XBR IREF_RX NBR VDDIO 0 lvds_bias',
        'XDT TXDATA TP TN VREF IREF_TX NBT VDDIO VDDD 0 openlvds_driver_core',
        'XCT TXCLOCK CP CN VREF IREF_TX NBT VDDIO VDDD 0 openlvds_driver_core',
        'XDR RP RN RXDATA VREF IREF_RX NBR VDDIO VDDD 0 openlvds_receiver_core',
        'XCR RCP RCN RXCLOCK VREF IREF_RX NBR VDDIO VDDD 0 openlvds_receiver_core',
        instance('RX','openlvds_ddr_rx',rxnodes,models),'CQ0 Q0 0 20f','CQ1 Q1 0 20f']
    if a.settled_start:
        replacements={
            'VIO VDDIO 0 PWL(0 0 1n 3.3)':'VIO VDDIO 0 3.3',
            'VDIG VDDD 0 PWL(0 0 1n 1.8)':'VDIG VDDD 0 1.8',
            'VREF VREF 0 PWL(0 0 1n 1.2)':'VREF VREF 0 1.2',
            'IREF_TX IREF_TX 0 PWL(0 0 1n 35u)':'IREF_TX IREF_TX 0 35u',
            'IREF_RX IREF_RX 0 PWL(0 0 1n 35u)':'IREF_RX IREF_RX 0 35u'}
        lines=[replacements.get(line,line) for line in lines]
        # Guesses help Newton find the closed-loop DC solution. NODESET does
        # not clamp any node during the transient; these are not ideal biases.
        guesses={'IREF_TX':1.35,'IREF_RX':1.35,'NBT':1.35,'NBR':1.35,
                 'RXDATA':0,'RXCLOCK':0,'TP':1.075,'TN':1.425,'CP':1.075,'CN':1.425,
                 'RP':1.075,'RN':1.425,'RCP':1.075,'RCN':1.425}
        for inst in ['XDT','XCT']:
            for node,value in [('SINK',1.36),('TOP',2.42),('DP',0),('DN',3.3)]:
                guesses[inst+':openlvds_driver_core__'+node]=value
        lines.extend('.nodeset V('+n+')='+str(v) for n,v in guesses.items())
    for tag,pins,delay in [('D',('TP','TN','RP','RN'),1.2+a.skew_ps/1000),
                           ('C',('CP','CN','RCP','RCN'),1.2+a.eye_shift_ps/1000)]:
        if delay<=0:p.error('Channel propagation delay must remain positive')
        for leg,(tx,rx) in enumerate(zip(pins[:2],pins[2:])):
            base=f'{tag}{leg}'
            lines.extend([f'CP{base} {tx} 0 2p',f'LT{base} {tx} {base}A 1n',
                f'RT{base} {base}A {base}B 1',f'T{base} {base}B 0 {base}F 0 Z0=50 TD={delay:g}n',
                f'LR{base} {base}F {rx} 1n',f'CR{base} {rx} 0 2p'])
        lines.append(f'RTERM{tag} {tag}0F {tag}1F 100')
    lines.extend([f'.tran 20p {total:g}n 0 100p',
        '.print tran V(RP) V(RN) V(RCP) V(RCN) V(RXDATA) V(RXCLOCK) V(Q0) V(Q1) V(RXVALID) V(TXREADY) V(TP) V(TN) V(CP) V(CN) V(TXDATA) V(TXCLOCK) V(CLK0) V(CLK90)',
        '.end'])
    deck=out/'bench.cir';deck.write_text('\n'.join(lines)+'\n')
    with slot():
        result=subprocess.run(spice_command(out/(engine()+'.log'),deck),cwd=out,capture_output=True,text=True)
    (out/'console.log').write_text(result.stdout+result.stderr)
    rows=[];prn=out/'bench.cir.prn'
    if prn.exists():
        for line in prn.read_text().splitlines():
            try:rows.append(list(map(float,line.split())))
            except ValueError:pass
    wave=np.array(rows)
    if result.returncode or wave.ndim!=2 or wave[-1,1]<(total-.1)*1e-9:
        summary=dict(passed=False,error=engine()+' failed or transient incomplete',returncode=result.returncode)
    else:
        summary=analyze(wave,words,launch,period,1.2+a.skew_ps/1000,aperture)
        if not a.eye_shift_ps:
            margins=[summary.get('setup_margin_ps'),summary.get('hold_margin_ps')]
            margin_ok=all(m is not None and m>=REQ['minimum_sampling_margin_ps'] for m in margins)
            summary['sampling_margin_passed']=margin_ok
            summary['passed']=summary['passed'] and margin_ok
    summary.update(config=config,rx_aperture=aperture,clock_partition=scope,network='TICER approximate RC' if a.fast_rc else 'full distributed RC',
        actual_clock_mhz=1000/period,injected_external_jitter_pp_ps=a.jitter_pp_ps,
        startup_model='solved DC operating point at fixed supplies' if a.settled_start else 'one-nanosecond supply ramp',
        simulator=engine(),simulator_provenance=simulator_stamp,training_ns=training,
        clock_waveform_sha256=hashlib.sha256(clock_bytes).hexdigest(),
        diagnostic=a.diagnostic,inputs=inputs,fingerprint=fingerprint,
        source_sha256=hashlib.sha256(source_bytes).hexdigest(),
        requirements_sha256=hashlib.sha256(REQ_BYTES).hexdigest(),
        runner_sha256=hashlib.sha256(runner_bytes).hexdigest(),
        library_sha256=hashlib.sha256(lib).hexdigest(),
        deck_sha256=hashlib.sha256(deck.read_bytes()).hexdigest(),
        waveform_sha256=hashlib.sha256(prn.read_bytes()).hexdigest() if prn.exists() else None,
        output=str(out.relative_to(ROOT)))
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    lock.close()
    print(json.dumps(summary,indent=2))
    return 0 if summary['passed'] else 1

if __name__=='__main__':sys.exit(main())
