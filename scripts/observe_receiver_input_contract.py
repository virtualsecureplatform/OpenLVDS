#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure legacy replay pulse support without replacing any receiver qualification gate."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np

from diagnose_receiver_restoration import diagnose
from dll_measurements import read_wave
from receiver_static_diagnosis import capture_manifest
from simulate_link import edge_times, pwl

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def supported_intervals(t,v,threshold,start,end):
    t=np.asarray(t);v=np.asarray(v)
    if (t.shape!=v.shape or len(t)<2 or not np.isfinite(t).all() or not np.isfinite(v).all() or
            np.any(np.diff(t)<=0) or not np.isfinite(threshold) or not t[0]<=start<end<=t[-1]):
        raise ValueError('Require a finite complete increasing pulse interval')
    local=np.r_[start,t[(t>start)&(t<end)],end];values=np.interp(local,t,v)
    points=np.unique(np.r_[start,edge_times(local,values,threshold),end])
    above=np.interp((points[:-1]+points[1:])/2,local,values)>=threshold
    spans=[]
    for a,b,active in zip(points[:-1],points[1:],above):
        if active:
            if spans and spans[-1][1]==a:spans[-1][1]=float(b)
            else:spans.append([float(a),float(b)])
    return spans


def pulse_support(t,differential,transport,threshold):
    rows=[]
    for pulse in transport['pulses']:
        start=pulse['input_edge_ns']*1e-9;end=start+pulse['input_pulse_width_ps']*1e-12
        signed=differential*(1 if pulse['polarity']=='rising' else -1)
        spans=supported_intervals(t,signed,threshold,start,end)
        durations=[(b-a)*1e12 for a,b in spans]
        rows.append(dict(pulse,peak_reaches_sensitivity_threshold=pulse['input_peak_magnitude_v']>=threshold,
            above_threshold_total_ps=sum(durations),above_threshold_longest_ps=max(durations,default=0.),
            above_threshold_intervals_ns=[[a*1e9,b*1e9] for a,b in spans]))
    return rows


def verify_origin(replay):
    m=json.loads((replay/'manifest.json').read_text());parent=ROOT/m['identity']['parent']
    if not parent.is_relative_to(ROOT/'build/diagnostics/clock_restore'):
        raise ValueError('Require the original captured-pin clock replay origin')
    legacy=json.loads((parent/'manifest.json').read_text())['identity'];link=ROOT/legacy['link']
    if (not link.is_relative_to(ROOT/'build/link') or legacy['source_interval_ns']!=[50,120] or
            legacy['replay_interval_ns']!=[5,75] or legacy['interpolation_step_ps']!=5):
        raise ValueError('Unexpected original captured-pin translation')
    proofs={str((parent/'manifest.json').relative_to(ROOT)):sha(parent/'manifest.json')}
    for name,h in legacy['files'].items():
        p=link/name
        if sha(p)!=h:raise ValueError('Original link evidence changed')
        proofs[str(p.relative_to(ROOT))]=h
    original=json.loads((link/'summary.json').read_text())
    if original['config']!=legacy['config'] or original['waveform_sha256']!=sha(link/'bench.cir.prn') or original['library_sha256']!=sha(link/'library.spice'):
        raise ValueError('Original link waveform/configuration binding changed')
    wave,headers=read_wave(link/'bench.cir.prn');t=wave[:,1]
    if not np.isfinite(wave).all() or np.any(np.diff(t)<=0) or t[0]>50e-9 or t[-1]<120e-9:
        raise ValueError('Incomplete original link interval')
    captured=np.arange(50.,120.+.0025,.005)*1e-9;times=(captured-captured[0])*1e9+5
    deck=(replay/'captured/bench.cir').read_text()
    for node in ['RCP','RCN']:
        voltage=np.interp(captured,t,wave[:,headers['V('+node+')']])
        expected='V'+node+' '+node+' 0 '+pwl([(0,float(voltage[0]))]+list(zip(times,voltage)))
        actual=re.findall(r'(?m)^V'+node+r' [^\n]*$',deck)
        if actual!=[expected]:raise ValueError('Captured receiver pins differ from original link translation')
    return legacy,proofs


def observe(replay):
    restoration=diagnose(replay);receipt=restoration/'summary.json';prior=json.loads(receipt.read_text())
    legacy,origin_files=verify_origin(replay)
    proofs=dict(prior['identity']['files'],**origin_files)
    proofs[str(receipt.relative_to(ROOT))]=sha(receipt)
    for name in [Path(__file__).name,'diagnose_receiver_restoration.py','diagnose_link_clock.py','simulate_link.py','dll_measurements.py','receiver_static_diagnosis.py']:
        proofs['scripts/'+name]=sha(ROOT/'scripts'/name)
    proofs['requirements.json']=sha(ROOT/'requirements.json')
    def unchanged():
        if any(sha(ROOT/n)!=h for n,h in proofs.items()):raise ValueError('Receiver input observation context changed')
    unchanged();req=json.loads((ROOT/'requirements.json').read_text());wave,h=read_wave(replay/'captured/bench.cir.prn');t=wave[:,1]
    positive=wave[:,h['V(RCP)']];negative=wave[:,h['V(RCN)']];diff=positive-negative
    transport=next(r['receiver_transport'] for r in prior['results'] if r['case']=='captured')
    rows=pulse_support(t,diff,transport,req['rx_threshold_v']);keep=(t>=15e-9)&(t<=75e-9)
    pins=dict(min_v=float(min(positive[keep].min(),negative[keep].min())),max_v=float(max(positive[keep].max(),negative[keep].max())))
    config=legacy['config'];training_cycles=config['training_ns']*config['mhz']/1000
    groups={}
    for polarity in ['rising','falling']:
        pulses=[r for r in rows if r['polarity']==polarity]
        groups[polarity]=dict(pulses=len(pulses),peaks_below_threshold=sum(not r['peak_reaches_sensitivity_threshold'] for r in pulses),
            minimum_above_threshold_longest_ps=min(r['above_threshold_longest_ps'] for r in pulses),
            maximum_above_threshold_longest_ps=max(r['above_threshold_longest_ps'] for r in pulses),
            lost_response_periods=sum(r['output_edges_in_next_input_period']==0 for r in pulses))
    unchanged();identity=dict(replay=str(replay.relative_to(ROOT)),files=proofs)
    out=replay/'input_contract_observations'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    capture_manifest(out/'summary.json',dict(identity=identity,qualified_phy=False,native_clock_admission_changed=False,
        source_origin=dict(link=legacy['link'],bundle=legacy['bundle'],config=config,source_interval_ns=legacy['source_interval_ns'],
            replay_interval_ns=legacy['replay_interval_ns'],training_cycles_at_configured_frequency=training_cycles,
            qualified_startup_training_cycles=256,training_covers_qualified_startup=training_cycles>=256),
        sensitivity_threshold_v=req['rx_threshold_v'],pin_range=pins,pins_within_required_bounds=bool(
            pins['min_v']>=req['rx_pin_min_v'] and pins['max_v']<=req['rx_pin_max_v']),groups=groups,pulses=rows,
        scope='Read-only complete original 80 ns captured replay and bound original link translation. Input pulse support is measured with piecewise-linear interpolation between recorded samples. Peak amplitude below the static sensitivity threshold has no sensitivity guarantee; time beyond threshold is descriptive, not a new dynamic acceptance limit. Source duty/skew/jitter are not reinterpreted as receiver-pin duty requirements. Short diagnostic training cannot prove qualified startup. These observations neither excuse losses with sufficient support nor replace original native, component, coupled, startup or full PHY gates.'))
    return out/'summary.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('replay',type=Path);a=p.parse_args()
    print(observe(a.replay.resolve()),flush=True)
