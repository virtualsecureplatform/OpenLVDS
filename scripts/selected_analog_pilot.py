#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Early selected-driver/LVT-receiver diagnostic, independent of release admission."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import re
from spice_probes import ProbeNetwork
import numpy as np
from dll_campaign import atomic
from dll_measurements import read_wave
from layout import circuits, flatten, schematic_text
import probe_native_driver_restore as driver
import receiver_lvt_pair_experiment as receiver
from receiver_static_diagnosis import capture_manifest
from spice_engine import command, engine, provenance
from spice_slots import slot
from stage_phy_candidate import overlay
from probe_receiver_candidate_link import rebind, analyze, edge_times, word_stream, REQ

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name
PROTECTED=('lvds_bias','openlvds_dll','openlvds_delay_line','openlvds_tx_core','openlvds_ddr_rx')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def assemble(base, driver_model, receiver_source):
    pins,devices=flatten(circuits(receiver_source),'openlvds_receiver_core')
    model=schematic_text('openlvds_receiver_core',pins,devices)
    text=overlay(base,driver_model,'openlvds_driver_core',PROTECTED)
    return overlay(text,model,'openlvds_receiver_core',PROTECTED+('openlvds_driver_core',))


def prepare(reference, comparison, source, variant='restore_64_24'):
    if engine()!='ngspice':raise ValueError('Use the pinned ngspice environment')
    for path,kind in [(reference,'link'),(comparison,'diagnostics/driver_native_restore'),(source,'diagnostics/receiver_lvt_pair_static')]:
        if not path.is_relative_to(ROOT/'build'/kind):raise ValueError('Unexpected pilot input path')
    if variant not in driver.CASES:raise ValueError('Unknown matched driver variant')
    if not (source/'summary.json').is_file():raise ValueError('Complete the receiver DC pilot first')
    measured=receiver.run(source)  # Cached source-only verification; cannot start a missing transient.
    if measured['lvt_decision_pair']['metrics']['passed'] is not True:raise ValueError('Receiver DC pilot failed')
    previous=json.loads((reference/'summary.json').read_text());config=previous['config']
    if config['fast_rc'] or not config['diagnostic'] or config['dll_phase']:raise ValueError('Use the saved full-RC ideal-phase diagnostic')
    for name,key in [('bench.cir','deck_sha256'),('bench.cir.prn','waveform_sha256'),('library.spice','library_sha256')]:
        if digest(reference/name)!=previous[key]:raise ValueError('Reference link changed')
    original=json.loads((comparison/'manifest.json').read_text())['identity']
    models,physical,code=driver.physical_models({k:(ROOT/v).resolve() for k,v in original['layouts'].items()})
    source_manifest=json.loads((source/'manifest.json').read_text())['identity']
    paths=[reference/n for n in ['summary.json','bench.cir','bench.cir.prn','library.spice']]+physical
    paths += [source/n for n in ['manifest.json','summary.json','source.spice','bench.cir','bench.cir.prn']]
    paths += [comparison/'manifest.json',ROOT/'requirements.json']
    names=set(code)|set(driver.CODE)|set(original['code'])|set(source_manifest['code'])|{NAME,'probe_receiver_candidate_link.py'}
    identity=dict(inputs=dict(source_manifest['inputs'],**{str(p.relative_to(ROOT)):digest(p) for p in paths}),code={n:digest(ROOT/'scripts'/n) for n in names},
        reference=str(reference.relative_to(ROOT)),receiver_source=str(source.relative_to(ROOT)),driver_variant=variant,
        receiver_view='fingered_schematic',driver_view='audited_native',config=config,simulator_provenance=provenance())
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out=ROOT/'build/diagnostics/analog_link_pilot'/key;out.mkdir(parents=True,exist_ok=True)
    library=assemble((reference/'library.spice').read_text(),models[variant],(source/'source.spice').read_text())
    deck=rebind((reference/'bench.cir').read_text(),reference,out)
    probes=re.search(r'(?im)^\.print tran[^\n]*',deck)
    ProbeNetwork(library).validate(deck,re.findall(r'V\(([^)]+)\)',probes[0],re.I))
    for name,text in [('library.spice',library),('bench.cir',deck)]:
        target=out/name
        if target.exists() and target.read_text()!=text:raise ValueError('Prepared pilot fixture changed')
        if not target.exists():target.write_text(text)
    capture_manifest(out/'manifest.json',dict(identity=identity,diagnostic=True,qualified_phy=False,
        files={n:digest(out/n) for n in ['library.spice','bench.cir']}))
    return out


def run(folder):
    if not folder.is_relative_to(ROOT/'build/diagnostics/analog_link_pilot'):raise ValueError('Use a prepared analog pilot')
    m=json.loads((folder/'manifest.json').read_text());i=m['identity'];stamp=digest(folder/'manifest.json')
    def unchanged():
        if (digest(folder/'manifest.json')!=stamp or provenance()!=i['simulator_provenance'] or
            any(digest(ROOT/n)!=s for n,s in i['inputs'].items()) or
            any(digest(ROOT/'scripts'/n)!=s for n,s in i['code'].items()) or
            any(digest(folder/n)!=s for n,s in m['files'].items())):raise ValueError('Analog pilot context changed')
    with (folder/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        cached=json.loads((folder/'summary.json').read_text()) if (folder/'summary.json').exists() else None
        if cached is None:
            if any((folder/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log']):raise ValueError('Partial pilot retained; use a fresh retry context')
            atomic(folder/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
            with slot():
                unchanged();atomic(folder/'execution.json',dict(status='running',qualified_phy=False))
                result=subprocess.run(command(folder/'ngspice.log',folder/'bench.cir'),cwd=folder,capture_output=True,text=True)
            (folder/'console.log').write_text(result.stdout+result.stderr);result.check_returncode()
        wave,h=read_wave(folder/'bench.cir.prn');t=wave[:,1];config=i['config']
        from reduce_rc import number
        import re
        stop=number(re.search(r'(?im)^\.tran\s+\S+\s+(\S+)',(folder/'bench.cir').read_text())[1])
        if len(t)<2 or not np.isfinite(wave).all() or t[0]>1e-15 or np.any(np.diff(t)<=0) or t[-1]<stop-1e-12:raise ValueError('Incomplete pilot waveform')
        rises=edge_times(t,wave[:,h['V(CLK0)']],.9,True)
        launch=rises[rises>=config['training_ns']*1e-9][:config['bits']//2]*1e9
        if len(launch)!=config['bits']//2:raise ValueError('Incomplete pilot payload clocks')
        metrics=analyze(wave,word_stream(len(launch)),launch,1000/config['mhz'])
        metrics['sampling_margin_passed']=all(metrics.get(k) is not None and metrics[k]>=REQ['minimum_sampling_margin_ps'] for k in ['setup_margin_ps','hold_margin_ps'])
        report=dict(diagnostic_complete=True,diagnostic=True,qualified_phy=False,metrics=metrics,
            manifest_sha256=stamp,waveform_sha256=digest(folder/'bench.cir.prn'),
            scope='Audited native selected driver plus fingered schematic LVT receiver; saved short-training ideal-phase diagnostic only. No native receiver, startup, component or release admission.')
        unchanged()
        if cached is not None and cached!=report:raise ValueError('Pilot reanalysis differs from cached evidence')
        capture_manifest(folder/'summary.json',report)
        atomic(folder/'execution.json',dict(status='completed',qualified_phy=False))
    return folder/'summary.json'


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('reference',type=Path);a.add_argument('comparison',type=Path);a.add_argument('source',type=Path);a.add_argument('--variant',choices=driver.CASES,default='restore_64_24')
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a=p.parse_args()
    print(prepare(a.reference.resolve(),a.comparison.resolve(),a.source.resolve(),a.variant) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
