#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Source-bound native RX burst diagnostic for half-cycle publication paths."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess

import numpy as np
from dll_measurements import read_wave, column, complete
from rx_candidate_aperture import audited_model, extra_code
from characterize_rx_aperture import atomic, pwl
from spice_engine import command, engine, provenance
from spice_library import checked_netlist
from spice_slots import slot

ROOT=Path(__file__).resolve().parents[1]
WORDS=32
WARMUP=8


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def conditions():
    return [dict(process='ss',temperature=40,mhz=410,duty=duty,skew_ps=skew,
        jitter_ps=50,clock_slew_ps=200,data_slew_ps=200)
        for duty in [.45,.55] for skew in [-100,100]]


def fixture(spec,ports):
    period=1000/spec['mhz'];count=WORDS+WARMUP+2
    # Deterministic independent rising/falling edge displacement. Jitter is
    # measured from each nominal edge, rather than accumulating a random walk.
    rng=random.Random(193);j=spec['jitter_ps']/1000
    rising=[5+n*period+rng.uniform(-j,j) for n in range(count)]
    falling=[5+(n+spec['duty'])*period+rng.uniform(-j,j) for n in range(count)]
    ramp=spec['clock_slew_ps']/800
    clock=[(0,0)]
    for rise,fall in zip(rising,falling):
        clock += [(rise-ramp/2,0),(rise+ramp/2,1.8),(fall-ramp/2,1.8),(fall+ramp/2,0)]
    bits=random.Random(927)
    words=[(bits.randrange(2),bits.randrange(2)) for _ in range(count)]
    # Include long runs, all four symbols, and consecutive alternating bits.
    words[WARMUP:WARMUP+12]=[(0,0),(1,1),(0,1),(1,0)]*3
    serial=[(0,0)];events=[];ramp_data=spec['data_slew_ps']/800;skew=spec['skew_ps']/1000
    old=0
    for n,(rb,fb) in enumerate(words):
        for at,value in [((falling[n-1]+rising[n])/2 if n else 3,rb),((rising[n]+falling[n])/2,fb)]:
            at+=skew
            events.append(dict(time_ns=at,value=value))
            if value!=old:
                serial += [(at-ramp_data/2,1.8*old),(at+ramp_data/2,1.8*value)];old=value
    nodes={'VGND':'0','VPWR':'VDDD','clk':'CLK','reset_n':'RST','serial':'D',
        'data[0]':'Q0','data[1]':'Q1','valid':'VALID'}
    if set(ports)!=set(nodes):raise ValueError('RX public terminals changed')
    body='VD VDDD 0 1.8\nVR RST 0 PWL(0 0 2n 0 2.05n 1.8)\n'
    body+=f'VC CLK 0 {pwl(clock)}\nVS D 0 {pwl(serial)}\n'
    body+='XR '+' '.join(nodes[p] for p in ports)+' openlvds_ddr_rx\nC0 Q0 0 20f\nC1 Q1 0 20f\nCV VALID 0 20f\n'
    witnesses=[dict(publication_ns=rising[n+1],expected=list(words[n])) for n in range(WARMUP,WARMUP+WORDS)]
    return body,dict(stop_ns=rising[WARMUP+WORDS]+period,witnesses=witnesses,
        rising_ns=rising,falling_ns=falling,serial_events=events)


def measure(wave,header,timing):
    if not complete(wave,timing['stop_ns']):raise ValueError('Incomplete native burst transient')
    t=wave[:,1];outputs=[column(wave,header,n) for n in ['Q0','Q1','VALID']]
    results=[]
    for witness in timing['witnesses']:
        samples=(witness['publication_ns']+np.arange(.80,1.051,.005))*1e-9
        limits=[(float(v.min()),float(v.max())) for v in [np.interp(samples,t,y) for y in outputs]]
        correct=all(lo>1.44 if bit else hi<.36 for (lo,hi),bit in zip(limits,witness['expected']+[1]))
        legal=all(lo>=-.1 and hi<=1.95 for lo,hi in limits)
        results.append(dict(**witness,passed=bool(correct and legal),output_limits_v=limits))
    return dict(passed=all(r['passed'] for r in results),words=len(results),bits=2*len(results),results=results)


def identity(physical):
    info,reports=audited_model(physical)
    code={name:sha(ROOT/'scripts'/name) for name in ['probe_rx_burst.py','dll_measurements.py',
        'spice_library.py','spice_scope.py','spice_engine.py','run_ngspice.py','characterize_rx_aperture.py']}
    code.update(extra_code())
    return dict(physical=str(physical.relative_to(ROOT)),model=info,reports=reports,code=code,
        simulator_provenance=provenance(),requirements_sha256=sha(ROOT/'requirements.json'),
        conditions=conditions(),words=WORDS,warmup=WARMUP)


def prepare(physical):
    physical=physical.resolve()
    if engine()!='ngspice':raise ValueError('Use the pinned --ngspice environment')
    captured=identity(physical)
    root=ROOT/'build/diagnostics/rx_burst'/hashlib.sha256(json.dumps(captured,sort_keys=True).encode()).hexdigest()[:16]
    if (root/'manifest.json').exists():
        if json.loads((root/'manifest.json').read_text())['identity']!=captured:raise ValueError('Burst manifest changed')
        return root
    root.mkdir(parents=True,exist_ok=True)
    (root/'library.spice').write_text(checked_netlist(captured['model']))
    for name in captured['code']:(root/name).write_bytes((ROOT/'scripts'/name).read_bytes())
    atomic(root/'manifest.json',dict(identity=captured,library_sha256=sha(root/'library.spice'),qualified_phy=False))
    return root


def validate(root,manifest):
    captured=manifest['identity']
    if identity(ROOT/captured['physical'])!=captured or sha(root/'library.spice')!=manifest['library_sha256']:
        raise ValueError('Native burst circuit, source or simulator changed')
    if any(sha(root/n)!=v for n,v in captured['code'].items()):raise ValueError('Captured burst producer changed')


def run(root):
    root=root.resolve()
    if not root.is_relative_to(ROOT/'build/diagnostics/rx_burst'):raise ValueError('Use a captured burst artifact')
    manifest=json.loads((root/'manifest.json').read_text());validate(root,manifest)
    results=[]
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for index,spec in enumerate(manifest['identity']['conditions']):
            validate(root,manifest);folder=root/str(index);folder.mkdir(exist_ok=True)
            body,timing=fixture(spec,manifest['identity']['model']['ports'])
            pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
            deck=(f'OpenLVDS native RX continuous burst {index}\n.lib "{pdk}" {spec["process"]}\n'
                f'.include "{root}/library.spice"\n.options device temp={spec["temperature"]}\n'
                '.options timeint method=gear reltol=1e-4 abstol=1e-12\n'+body+
                f'.tran 5p {timing["stop_ns"]:.12g}n 0 5p\n.print tran V(CLK) V(D) V(Q0) V(Q1) V(VALID)\n.end\n')
            path=folder/'bench.cir';previous=folder/'summary.json'
            if previous.exists():
                recorded=json.loads(previous.read_text())
                if (sha(path)!=hashlib.sha256(deck.encode()).hexdigest() or recorded['deck_sha256']!=sha(path) or
                        recorded['waveform_sha256']!=sha(folder/'bench.cir.prn')):raise ValueError('Burst trace changed')
            else:
                path.write_text(deck)
                with slot():result=subprocess.run(command(folder/'ngspice.log',path),cwd=folder,capture_output=True,text=True)
                (folder/'console.log').write_text(result.stdout+result.stderr);result.check_returncode()
            wave,header=read_wave(folder/'bench.cir.prn');measurement=measure(wave,header,timing)
            report=dict(spec=spec,measurement=measurement,deck_sha256=sha(path),waveform_sha256=sha(folder/'bench.cir.prn'))
            if previous.exists() and recorded!=report:raise ValueError('Burst reanalysis changed')
            atomic(previous,report);results.append(dict(case=index,passed=measurement['passed'],summary_sha256=sha(previous)))
            validate(root,manifest)
            atomic(root/'summary.json',dict(passed=len(results)==len(conditions()) and all(r['passed'] for r in results),
                completed=len(results),required=len(conditions()),results=results,manifest_sha256=sha(root/'manifest.json'),
                qualified_phy=False,scope='Supplementary native continuous-data diagnostic; does not replace aperture or link qualification'))
            if not measurement['passed']:return 1
    return 0


def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('physical',type=Path)
    a=s.add_parser('run');a.add_argument('artifact',type=Path)
    a=p.parse_args()
    if a.action=='prepare':print(prepare(a.physical),flush=True);return 0
    return run(a.artifact)


if __name__=='__main__':raise SystemExit(main())
