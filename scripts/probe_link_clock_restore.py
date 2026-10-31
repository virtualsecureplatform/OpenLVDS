#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay saved receiver pins into the actual loaded RX; diagnostic only."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import numpy as np
from dll_campaign import atomic, closure
from dll_measurements import read_wave
from phy_candidate import load
from simulate_link import edge_times, instance, pwl
from spice_engine import command, engine, provenance
from spice_slots import slot

ROOT=Path(__file__).resolve().parents[1]
CODE=['probe_link_clock_restore.py','phy_candidate.py','stage_phy_candidate.py',
      'dll_campaign.py','dll_measurements.py','simulate_link.py','spice_engine.py','run_ngspice.py','spice_slots.py']


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(link):
    if engine()!='ngspice' or not link.is_relative_to(ROOT/'build/link'):
        raise ValueError('Use a saved link in the pinned ngspice environment')
    report=json.loads((link/'summary.json').read_text()); config=report['config']
    files={n:digest(link/n) for n in ['summary.json','bench.cir.prn','library.spice']}
    if files['bench.cir.prn']!=report['waveform_sha256'] or files['library.spice']!=report['library_sha256']:
        raise ValueError('Saved link evidence changed')
    bundle=ROOT/config['bundle']; data,_,models=load(bundle)
    if data!=(link/'library.spice').read_bytes(): raise ValueError('Replay bundle differs from the saved link')
    wave,header=read_wave(link/'bench.cir.prn');t=wave[:,1]
    # Preserve the measured analog waveform, including its common mode, skew,
    # jitter and pulse narrowing. Move 50–120 ns to 5–75 ns after a DC solve.
    captured=np.arange(50.,120.+.0025,.005)*1e-9
    if t[-1]<captured[-1]: raise ValueError('Saved input trace too short')
    values={n:np.interp(captured,t,wave[:,header['V('+n+')']]) for n in ['RP','RN','RCP','RCN']}
    identity=dict(link=str(link.relative_to(ROOT)),files=files,bundle=str(bundle.relative_to(ROOT)),
        bundle_manifest_sha256=digest(bundle/'manifest.json'),simulator_provenance=provenance(),
        code={n:digest(ROOT/'scripts'/n) for n in CODE},config=config,
        source_interval_ns=[50,120],replay_interval_ns=[5,75],interpolation_step_ps=5)
    root=ROOT/'build/diagnostics/clock_restore'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if (root/'manifest.json').exists(): return root
    root.mkdir(parents=True)
    library=closure(data.decode(),['lvds_bias','openlvds_receiver_core','openlvds_ddr_rx'])
    (root/'library.spice').write_text(library)
    times=(captured-captured[0])*1e9+5
    clock_diff=values['RCP']-values['RCN'];tasks=[]
    for mode in ['captured','sharp_control']:
        folder=root/mode;folder.mkdir();v={k:x.copy() for k,x in values.items()}
        if mode=='sharp_control':
            # A control stimulus, not an architecture fix: retain zero crossings
            # and measured duty, but use 100 ps edges and ±125 mV differential.
            events=[]
            for rising in [True,False]:
                events.extend((at,1 if rising else -1) for at in edge_times(times*1e-9,clock_diff,0,rising))
            points=[(0.,.25 if clock_diff[0]>0 else -.25)]
            for at,sign in sorted(events): points.extend([(at*1e9-.05,-sign*.25),(at*1e9+.05,sign*.25)])
            differential=np.interp(times,[p[0] for p in points],[p[1] for p in points])
            common=(v['RCP']+v['RCN'])/2;v['RCP']=common+differential/2;v['RCN']=common-differential/2
        pdk=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'
        rows=[f'OpenLVDS loaded receiver clock replay {mode} diagnostic only',f'.lib "{pdk}" {config["process"]}',
            f'.include "{root}/library.spice"',f'.options device temp={config["temperature"]}',
            '.options timeint method=gear reltol=1e-4 abstol=1e-12',
            'VD VDDD 0 1.8','VA VDDIO 0 3.3','VR VREF 0 1.2','IB PB 0 35u',
            'XB PB NB VDDIO 0 lvds_bias','VRST RESET_N 0 PWL(0 0 2n 0 2.1n 1.8)']
        for name,voltage in v.items(): rows.append('V'+name+' '+name+' 0 '+pwl([(0,float(voltage[0]))]+list(zip(times,voltage))))
        rows+=['XRC RCP RCN RXCLOCK VREF PB NB VDDIO VDDD 0 openlvds_receiver_core',
            'XRD RP RN RXDATA VREF PB NB VDDIO VDDD 0 openlvds_receiver_core',
            instance('RX','openlvds_ddr_rx',dict(VGND='0',VPWR='VDDD',clk='RXCLOCK',reset_n='RESET_N',
                serial='RXDATA',**{'data[0]':'Q0','data[1]':'Q1','valid':'VALID'}),models),
            'CQ0 Q0 0 20f','CQ1 Q1 0 20f','.tran 5p 80n 0 5p',
            '.print tran V(RCP) V(RCN) V(RXCLOCK) V(RXDATA) V(Q0) V(Q1) V(VALID)','.end']
        (folder/'bench.cir').write_text('\n'.join(rows)+'\n');tasks.append(dict(id=mode,deck_sha256=digest(folder/'bench.cir')))
    atomic(root/'manifest.json',dict(identity=identity,tasks=tasks,library_sha256=digest(root/'library.spice'),qualified_phy=False))
    return root


def run(root):
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity']
    def unchanged():
        if provenance()!=identity['simulator_provenance'] or any(digest(ROOT/'scripts'/n)!=h for n,h in identity['code'].items()):
            raise ValueError('Clock restoration producer changed')
        if any(digest(ROOT/identity['link']/n)!=h for n,h in identity['files'].items()): raise ValueError('Saved link changed')
        if digest(root/'library.spice')!=manifest['library_sha256']: raise ValueError('Replay library changed')
        load(ROOT/identity['bundle'])
        if digest(ROOT/identity['bundle']/'manifest.json')!=identity['bundle_manifest_sha256']: raise ValueError('Replay bundle changed')
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); unchanged();results=[]
        for task in manifest['tasks']:
            folder=root/task['id'];deck=folder/'bench.cir';summary=folder/'summary.json'
            if digest(deck)!=task['deck_sha256']: raise ValueError('Replay fixture changed')
            if summary.exists():
                result=json.loads(summary.read_text())
                if result['deck_sha256']!=task['deck_sha256'] or digest(folder/'bench.cir.prn')!=result['waveform_sha256']:
                    raise ValueError('Replay result changed')
                results.append(result);continue
            atomic(folder/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
            with slot():
                unchanged();atomic(folder/'execution.json',dict(status='running',qualified_phy=False))
                process=subprocess.run(command(folder/'ngspice.log',deck),cwd=folder,capture_output=True,text=True)
            (folder/'console.log').write_text(process.stdout+process.stderr);process.check_returncode()
            wave,head=read_wave(folder/'bench.cir.prn');t=wave[:,1];diff=wave[:,head['V(RCP)']]-wave[:,head['V(RCN)']]
            counts={}
            for name,signal,level in [('input',diff,0),('output',wave[:,head['V(RXCLOCK)']],.9)]:
                counts[name]={}
                for rising in [True,False]:
                    events=edge_times(t,signal,level,rising);events=events[(events>15e-9)&(events<75e-9)]
                    counts[name]['rising' if rising else 'falling']=len(events)
            result=dict(task=task['id'],qualified_phy=False,counts=counts,
                scope='Loaded clock restoration diagnostic only; no payload, aperture, PVT or release qualification',
                deck_sha256=task['deck_sha256'],waveform_sha256=digest(folder/'bench.cir.prn'))
            unchanged();atomic(summary,result);results.append(result)
        atomic(root/'summary.json',dict(diagnostic_complete=True,qualified_phy=False,results=results,
            manifest_sha256=digest(root/'manifest.json')))
    print(root/'summary.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run']);p.add_argument('path',type=Path)
    a=p.parse_args()
    if a.action=='prepare': print(prepare(a.path.resolve()),flush=True)
    else: run(a.path.resolve())
