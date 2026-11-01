#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare receiver architectures with complete recorded selected-TX pin stimuli."""
import argparse,fcntl,hashlib,json,re,subprocess
from pathlib import Path
import numpy as np
import selected_analog_pilot as pilot
import receiver_architecture_observations as observed
from receiver_architectures import transform
from layout import circuits,flatten,schematic_text
from stage_phy_candidate import overlay
from spice_scope import closure_hash
from spice_engine import engine,provenance,command
from spice_probes import ProbeNetwork
from rx_candidate_aperture import lease
from receiver_static_diagnosis import capture_manifest
from dll_campaign import atomic
from dll_measurements import read_wave
from simulate_link import analyze,edge_times,word_stream
from diagnose_link_clock import pulse_transport
from reduce_rc import number
ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'
NAMES='RP RN RCP RCN RXDATA RXCLOCK Q0 Q1 RXVALID TXREADY TP TN CP CN TXDATA TXCLOCK CLK0 CLK90'.split()
RECORDED=[n for n in NAMES if n not in ['RXDATA','RXCLOCK','Q0','Q1','RXVALID']]
CODE={'replay_selected_receiver.py','selected_analog_pilot.py','receiver_architecture_observations.py','receiver_architectures.py',
      'layout.py','stage_phy_candidate.py','spice_scope.py','spice_engine.py','spice_probes.py','rx_candidate_aperture.py',
      'spice_slots.py','receiver_static_diagnosis.py','dll_campaign.py','dll_measurements.py','simulate_link.py','diagnose_link_clock.py','reduce_rc.py','run_ngspice.py'}


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def recorded_sources(wave,headers):
    # Keep every original timestamp and voltage. No resampling/compression.
    return '\n'.join('VREC_'+n+' '+n+' 0 PWL('+ ' '.join(f'{t:.17g} {v:.17g}' for t,v in zip(wave[:,1],wave[:,headers['V('+n+')']]))+')' for n in RECORDED)+'\n'


def fixture(parent,out,stop):
    lines=['Selected-TX fixed-pin receiver architecture replay',f'.include "{out}/library.spice"',f'.include "{out}/pins.spice"']
    patterns=[r'\.lib\s+.*',r'\.options device temp=.*',r'\.options timeint .*',r'VIO VDDIO 0 3\.3',r'VDIG VDDD 0 1\.8',
        r'VREF VREF 0 1\.2',r'VRST RESET_N 0 .*',r'IREF_RX IREF_RX 0 35u',r'XBR .* lvds_bias',
        r'XDR .* openlvds_receiver_core',r'XCR .* openlvds_receiver_core',r'XRX .* openlvds_ddr_rx',r'CQ0 Q0 0 20f',r'CQ1 Q1 0 20f']
    for pattern in patterns:
        rows=re.findall(r'(?m)^'+pattern+r'$',parent)
        if len(rows)!=1:raise ValueError('Unexpected recorded fixture row '+pattern)
        lines+=rows
    lines += [f'.tran 5p {stop:.17g} 0 5p','.print tran '+' '.join('V('+n+')' for n in NAMES),'.end']
    return '\n'.join(lines)+'\n'


def control_proofs(control,parent):
    if control is None:return {}
    report=json.loads((control/'summary.json').read_text());manifest=json.loads((control/'manifest.json').read_text())
    if (manifest['identity']['variant']!='lvt' or manifest['identity']['parent']!=str(parent.relative_to(ROOT)) or report.get('control_calibrated') is not True or
            report['manifest_sha256']!=digest(control/'manifest.json') or report['waveform_sha256']!=digest(control/'bench.cir.prn')):
        raise ValueError('Complete and calibrate the LVT replay control first')
    # Scientific cached remeasurement; both completed files already exist.
    run(control)
    return {str((control/n).relative_to(ROOT)):digest(control/n) for n in ['manifest.json','summary.json','bench.cir.prn']}


def prepare(parent,sanity,control=None):
    if engine()!='ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/analog_link_pilot') or not sanity.is_relative_to(ROOT/'build/diagnostics/receiver_architecture_static'):
        raise ValueError('Use completed selected-driver and architecture source diagnostics')
    if not (parent/'summary.json').exists() or not (sanity/'summary.json').exists():raise ValueError('Complete both diagnostics before replay preparation')
    pilot.run(parent);result=observed.run(sanity)
    source_manifest=json.loads((sanity/'manifest.json').read_text());variant=source_manifest['identity']['architecture_variant']
    if not result['architecture']['metrics']['passed'] or not result['architecture']['observations']['observed_thin_guard_passed']:
        raise ValueError('Architecture nominal DC/current screen failed')
    if variant!='lvt' and control is None:raise ValueError('Calibrate the original LVT replay before changed architectures')
    if variant=='lvt' and control is not None:raise ValueError('The original LVT replay is its own calibration control')
    proofs=control_proofs(control,parent)
    original=json.loads((parent/'manifest.json').read_text());config=original['identity']['config'];wave,headers=read_wave(parent/'bench.cir.prn')
    stop=number(re.search(r'(?im)^\.tran\s+\S+\s+(\S+)',(parent/'bench.cir').read_text())[1])
    if any(headers.get('V('+n+')')!=i+2 for i,n in enumerate(NAMES)):raise ValueError('Unexpected captured waveform columns')
    if not np.isfinite(wave).all() or wave[0,1]>1e-15 or wave[-1,1]<stop-1e-12 or np.any(np.diff(wave[:,1])<=0):raise ValueError('Incomplete recorded pin waveform')
    source=transform(observed.experiment.source_variant((ROOT/'analog/openlvds.spice').read_text(),False),variant)
    pins,devices=flatten(circuits(source),TOP);model=schematic_text(TOP,pins,devices);baseline=(parent/'library.spice').read_text()
    if variant=='lvt' and closure_hash(baseline,TOP)!=closure_hash(model,TOP):raise ValueError('LVT control changes the parent receiver source')
    library=overlay(baseline,model,TOP,('lvds_bias','openlvds_ddr_rx','openlvds_driver_core','openlvds_dll'))
    paths=[parent/n for n in ['manifest.json','summary.json','bench.cir','bench.cir.prn','library.spice']]
    paths += [sanity/n for n in ['manifest.json','summary.json','source.spice','bench.cir','bench.cir.prn']]+[ROOT/'requirements.json']
    names=CODE|set(original['identity']['code'])|set(source_manifest['identity']['code'])
    identity=dict(parent=str(parent.relative_to(ROOT)),sanity=str(sanity.relative_to(ROOT)),variant=variant,config=config,stop_s=stop,
        control=str(control.relative_to(ROOT)) if control else None,control_proofs=proofs,
        simulator_provenance=provenance(),inputs=dict(proofs,**{str(p.relative_to(ROOT)):digest(p) for p in paths}),
        code={n:digest(ROOT/'scripts'/n) for n in sorted(names)},maximum_step_ps=5,
        scope='Recorded selected-TX pin voltages, fingered schematic receiver pair, unchanged native RX and shared bias. Fixed pin sources suppress loading feedback to TX/channel; not matched-link or native RX-core qualification.')
    out=ROOT/'build/diagnostics/selected_receiver_replay'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True);sources=recorded_sources(wave,headers);deck=fixture((parent/'bench.cir').read_text(),out,stop)
    ProbeNetwork(library).validate(deck+sources,NAMES)
    files={}
    for name,text in [('library.spice',library),('pins.spice',sources),('bench.cir',deck)]:
        path=out/name
        if path.exists() and path.read_text()!=text:raise ValueError('Prepared replay file changed')
        if not path.exists():path.write_text(text)
        files[name]=digest(path)
    capture_manifest(out/'manifest.json',dict(identity=identity,files=files,diagnostic=True,qualified_phy=False))
    return out


def timing(wave,start,end):
    t=wave[:,1];clock=edge_times(t,wave[:,7]);data=edge_times(t,wave[:,6]);setup=[];hold=[]
    for at in clock[(clock>=start)&(clock<=end)]:
        before=data[data<at];after=data[data>at]
        if len(before):setup.append((at-before[-1])*1e12)
        if len(after):hold.append((after[0]-at)*1e12)
    return dict(raw_setup_min_ps=min(setup) if setup else None,raw_hold_min_ps=min(hold) if hold else None)


def agreement(parent,wave,start,end):
    errors={};t=wave[:,1];pt=parent[:,1]
    for name,col in [('data',6),('clock',7)]:
        for rising in [True,False]:
            a=edge_times(pt,parent[:,col],rising=rising);b=edge_times(t,wave[:,col],rising=rising)
            a=a[(a>=start)&(a<=end)];b=b[(b>=start)&(b<=end)]
            key=name+('_rising' if rising else '_falling')
            errors[key]=dict(parent_edges=len(a),replay_edges=len(b),max_edge_error_ps=float(np.max(abs(a-b))*1e12) if len(a)==len(b) and len(a) else None)
    return dict(edges=errors,edge_tolerance_ps=20,passed=all(v['max_edge_error_ps'] is not None and v['max_edge_error_ps']<=20 for v in errors.values()))


def run(out,wait_slot=None):
    if not out.is_relative_to(ROOT/'build/diagnostics/selected_receiver_replay'):raise ValueError('Use a prepared selected-pin receiver replay')
    manifest=json.loads((out/'manifest.json').read_text());identity=manifest['identity'];stamp=digest(out/'manifest.json')
    def unchanged():
        if (digest(out/'manifest.json')!=stamp or provenance()!=identity['simulator_provenance'] or
            any(digest(ROOT/'scripts'/n)!=h for n,h in identity['code'].items()) or any(digest(ROOT/n)!=h for n,h in identity['inputs'].items()) or
            any(digest(out/n)!=h for n,h in manifest['files'].items())):raise ValueError('Selected-pin receiver context changed')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        cached=json.loads((out/'summary.json').read_text()) if (out/'summary.json').exists() else None
        if cached is None:
            if any((out/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log']):raise ValueError('Partial receiver replay retained; use a fresh context')
            atomic(out/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
            with lease(wait_slot):
                unchanged();atomic(out/'execution.json',dict(status='running',qualified_phy=False))
                process=subprocess.run(command(out/'ngspice.log',out/'bench.cir'),cwd=out,capture_output=True,text=True)
            (out/'console.log').write_text(process.stdout+process.stderr);process.check_returncode()
        elif digest(out/'bench.cir.prn')!=cached['waveform_sha256']:raise ValueError('Receiver replay waveform changed')
        unchanged();wave,headers=read_wave(out/'bench.cir.prn');t=wave[:,1]
        if (len(wave)<2 or not np.isfinite(wave).all() or t[0]>1e-15 or t[-1]<identity['stop_s']-1e-12 or np.any(np.diff(t)<=0) or
                any(headers.get('V('+n+')')!=i+2 for i,n in enumerate(NAMES))):raise ValueError('Incomplete full receiver replay waveform')
        parent=ROOT/identity['parent'];pw,_=read_wave(parent/'bench.cir.prn');config=identity['config'];launch=edge_times(pw[:,1],pw[:,18],rising=True)
        launch=launch[launch>=config['training_ns']*1e-9][:config['bits']//2]
        if len(launch)!=config['bits']//2:raise ValueError('Incomplete parent payload launch clocks')
        start,end=launch[0]+1.2e-9,launch[-1]+(1000/config['mhz'])*1e-9+1.2e-9
        metrics=analyze(wave,word_stream(len(launch)),launch*1e9,1000/config['mhz'])
        raw=timing(wave,start,end);transport=pulse_transport(t,wave[:,4]-wave[:,5],wave[:,7],start,end)
        calibration=agreement(pw,wave,50e-9,125e-9) if identity['variant']=='lvt' else None
        report=dict(diagnostic_complete=True,qualified_phy=False,variant=identity['variant'],metrics=metrics,
            timing=raw,clock_transport=transport,control_agreement=calibration,control_calibrated=calibration['passed'] if calibration else None,
            manifest_sha256=stamp,waveform_sha256=digest(out/'bench.cir.prn'),scope=identity['scope'])
        unchanged()
        if cached is not None and cached!=report:raise ValueError('Replay analysis differs from completed waveform')
        capture_manifest(out/'summary.json',report);atomic(out/'execution.json',dict(status='completed',qualified_phy=False,logic_passed=metrics['passed']))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('artifact',type=Path)
    p.add_argument('--sanity',type=Path);p.add_argument('--control',type=Path);p.add_argument('--wait-slot',type=int,choices=range(6));a=p.parse_args()
    if a.action=='prepare':
        if a.sanity is None:p.error('--sanity is required')
        print(prepare(a.artifact.resolve(),a.sanity.resolve(),a.control.resolve() if a.control else None),flush=True)
    else:print(json.dumps(run(a.artifact.resolve(),a.wait_slot)),flush=True)
