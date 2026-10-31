#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Snapshot TX training clocks without issuing a payload/qualification verdict."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from diagnose_native_dll_loop import raw_prefix
from diagnose_link_clock import pulse_transport
from dll_campaign import atomic
from dll_measurements import read_wave
from simulate_link import edge_times,input_slews

ROOT=Path(__file__).resolve().parents[1]


def digest(data):return hashlib.sha256(data).hexdigest()


def metrics(t,clock,p,n,q,start,end):
    differential=p-n;rises=edge_times(t,differential,0,True);falls=edge_times(t,differential,0,False);pulses=[]
    for at in falls[(falls>start)&(falls<end)]:
        after=rises[rises>at]
        if not len(after) or after[0]>=end:continue
        keep=(t>=at)&(t<=after[0])
        pulses.append(dict(start_ns=float(at*1e9),width_ps=float((after[0]-at)*1e12),
                           peak_magnitude_v=float(-differential[keep].min())))
    if not pulses:raise ValueError('No complete negative clock pulses')
    return dict(tx_clock_slew_ps=input_slews(t,clock,start,end),
        negative_clock_pulses=pulses,negative_clock_width_min_ps=min(p['width_ps'] for p in pulses),
        negative_clock_peak_min_v=min(p['peak_magnitude_v'] for p in pulses),
        receiver_transport=pulse_transport(t,differential,q,start,end))


def compare(root,start_ns,end_ns):
    if not root.is_relative_to(ROOT/'build/diagnostics/tx_candidate_link'):raise ValueError('Use a captured native TX experiment')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity'];baseline=ROOT/identity['link']
    for path,value in identity['inputs'].items():
        if digest((ROOT/path).read_bytes())!=value:raise ValueError('TX experiment input changed')
    for name,value in identity['code'].items():
        if digest((ROOT/'scripts'/name).read_bytes())!=value:raise ValueError('TX experiment producer changed')
    raw=(root/'bench.raw').read_bytes();names,wave,description=raw_prefix(raw);t=wave[:,names.index('time')]
    start,end=start_ns*1e-9,end_ns*1e-9
    if not t[0]<=start<end<=t[-1]:raise ValueError('Training observation interval unavailable')
    previous=json.loads((baseline/'summary.json').read_text())
    data=baseline/'bench.cir.prn'
    if digest(data.read_bytes())!=previous['waveform_sha256']:raise ValueError('Baseline waveform changed')
    before,header=read_wave(data)
    signals=['TXCLOCK','RCP','RCN','RXCLOCK']
    old=metrics(before[:,1],*[before[:,header['V('+n+')']] for n in signals],start,end)
    new=metrics(t,*[wave[:,names.index('v('+n.lower()+')')] for n in signals],start,end)
    captured=dict(experiment=str(root.relative_to(ROOT)),manifest_sha256=digest((root/'manifest.json').read_bytes()),
        baseline_waveform_sha256=previous['waveform_sha256'],snapshot_sha256=digest(raw),interval_ns=[start_ns,end_ns],
        code={n:digest((ROOT/'scripts'/n).read_bytes()) for n in
              ['compare_tx_training.py','diagnose_native_dll_loop.py','diagnose_link_clock.py','dll_measurements.py','simulate_link.py']},
        numpy_version=np.__version__)
    out=ROOT/'build/diagnostics/tx_training_compare'/digest(json.dumps(captured,sort_keys=True).encode())[:16]
    out.mkdir(parents=True,exist_ok=True);(out/'trace_snapshot.raw').write_bytes(raw)
    archive=out/'producer_archive';archive.mkdir(exist_ok=True)
    for name in captured['code']:(archive/name).write_bytes((ROOT/'scripts'/name).read_bytes())
    atomic(out/'summary.json',dict(identity=captured,qualified_phy=False,qualification_verdict=None,raw_description=description,
        scope='Training interval only, preserving the active transient. Peak pulse magnitudes are diagnostic, not a replacement for payload sampling-eye measurements.',
        baseline=old,candidate=new));print(out/'summary.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('experiment',type=Path)
    p.add_argument('--start-ns',type=float,default=20);p.add_argument('--end-ns',type=float,default=35)
    a=p.parse_args();compare(a.experiment.resolve(),a.start_ns,a.end_ns)
