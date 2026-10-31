#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Change only an audited TX network in a saved link fixture; never qualify a PHY."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from digital_candidate_rc import captured_inputs
from dll_campaign import atomic
from dll_candidate_library import audited
from dll_measurements import read_wave
from physical_policy import delay_cells_absent,tx_buffered_paths_retained
from simulate_link import analyze,edge_times,word_stream,REQ
from spice_engine import command,engine,provenance
from spice_library import checked_netlist
from spice_slots import slot
from stage_phy_candidate import overlay

ROOT=Path(__file__).resolve().parents[1]
CODE=['probe_tx_candidate_link.py','digital_candidate_rc.py','dll_candidate_library.py',
      'dll_campaign.py','dll_measurements.py','physical_policy.py','simulate_link.py',
      'spice_engine.py','spice_library.py','spice_slots.py','stage_phy_candidate.py','run_ngspice.py']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def rebind(deck,old,new):
    include=f'.include "{old}/library.spice"'
    if deck.count(include)!=1:raise ValueError('Expected one captured library inclusion')
    return deck.replace(include,f'.include "{new}/library.spice"')


def prepare(link,tx):
    if engine()!='ngspice' or not link.is_relative_to(ROOT/'build/link') or not tx.is_relative_to(ROOT/'build/diagnostics'):
        raise ValueError('Use isolated inputs in the pinned ngspice environment')
    previous=json.loads((link/'summary.json').read_text());config=previous['config']
    if config['fast_rc'] or not config['diagnostic'] or config['dll_phase']:
        raise ValueError('Use a full-RC ideal-phase diagnostic reference')
    for name,key in [('bench.cir','deck_sha256'),('bench.cir.prn','waveform_sha256'),('library.spice','library_sha256')]:
        if digest(link/name)!=previous[key]:raise ValueError('Saved link reference changed')
    physical=json.loads((tx/'summary.json').read_text())
    if captured_inputs(tx,physical)!='openlvds_tx_core':raise ValueError('Expected an audited TX')
    strength=physical['tx_buffer_strength']
    netlist=ROOT/physical['run']/'final/nl/openlvds_tx_core.nl.v'
    if not delay_cells_absent(netlist.read_text()) or not tx_buffered_paths_retained(netlist.read_text(),strength):
        raise ValueError('TX no longer has its declared matched output buffers')
    info=json.loads((tx/'extraction.json').read_text());audited(tx,info)
    gds=ROOT/physical['run']/'final/gds/openlvds_tx_core.gds'
    if digest(gds)!=info['gds_sha256'] or info['source_sha256']!=physical['source_sha256']:
        raise ValueError('TX extraction is stale')
    baseline=(link/'library.spice').read_text()
    header=re.search(r'(?im)^\.subckt[ \t]+openlvds_tx_core[^\n]*(?:\n\+[^\n]*)*',baseline)
    if not header or header[0].replace('\n+',' ').split()[2:]!=info['ports']:
        raise ValueError('TX candidate changes captured fixture terminal order')
    library=overlay(baseline,checked_netlist(info),'openlvds_tx_core',
        ('openlvds_driver','openlvds_receiver','openlvds_dll','openlvds_delay_line','openlvds_ddr_rx'))
    paths=[link/n for n in ['summary.json','bench.cir','bench.cir.prn','library.spice']]
    paths += [tx/n for n in ['summary.json','extraction.json','rc_audit.json']]+[netlist,gds,ROOT/info['netlist']]
    identity=dict(link=str(link.relative_to(ROOT)),tx=str(tx.relative_to(ROOT)),buffer_strength=strength,
        inputs={str(p.relative_to(ROOT)):digest(p) for p in paths},
        code={n:digest(ROOT/'scripts'/n) for n in CODE},simulator_provenance=provenance(),parent_config=config)
    root=ROOT/'build/diagnostics/tx_candidate_link'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if (root/'manifest.json').exists():return root
    root.mkdir(parents=True);(root/'library.spice').write_text(library)
    (root/'bench.cir').write_text(rebind((link/'bench.cir').read_text(),link,root))
    (root/'producer.py').write_bytes(Path(__file__).read_bytes())
    atomic(root/'manifest.json',dict(identity=identity,qualified_phy=False,deck_sha256=digest(root/'bench.cir'),
                                    library_sha256=digest(root/'library.spice')))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/tx_candidate_link'):raise ValueError('Use a captured TX link diagnostic')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity']
    def unchanged():
        if provenance()!=identity['simulator_provenance'] or any(digest(ROOT/'scripts'/n)!=h for n,h in identity['code'].items()):
            raise ValueError('TX link diagnostic producer changed')
        if any(digest(ROOT/p)!=h for p,h in identity['inputs'].items()):raise ValueError('TX link diagnostic input changed')
        for name,key in [('bench.cir','deck_sha256'),('library.spice','library_sha256')]:
            if digest(root/name)!=manifest[key]:raise ValueError('TX link fixture changed')
        if digest(root/'producer.py')!=identity['code']['probe_tx_candidate_link.py']:raise ValueError('Producer snapshot changed')
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        cached=None
        if (root/'summary.json').exists():
            cached=json.loads((root/'summary.json').read_text())
            if cached['waveform_sha256']!=digest(root/'bench.cir.prn') or cached['manifest_sha256']!=digest(root/'manifest.json'):
                raise ValueError('TX link waveform or manifest changed')
        else:
            atomic(root/'execution.json',dict(status='waiting_for_slot',qualified_phy=False))
            with slot():
                unchanged();atomic(root/'execution.json',dict(status='running',qualified_phy=False))
                process=subprocess.run(command(root/'ngspice.log',root/'bench.cir'),cwd=root,capture_output=True,text=True)
            (root/'console.log').write_text(process.stdout+process.stderr);process.check_returncode();unchanged()
        wave,header=read_wave(root/'bench.cir.prn');t=wave[:,1];config=identity['parent_config']
        rises=edge_times(t,wave[:,header['V(CLK0)']],.9,True)
        launch=rises[rises>=config['training_ns']*1e-9][:config['bits']//2]*1e9
        if len(launch)!=config['bits']//2:raise ValueError('Incomplete captured payload clocks')
        result=analyze(wave,word_stream(len(launch)),launch,1000/config['mhz'])
        margins=[result.get('setup_margin_ps'),result.get('hold_margin_ps')]
        result['sampling_margin_passed']=all(m is not None and m>=REQ['minimum_sampling_margin_ps'] for m in margins)
        result['passed']=result['passed'] and result['sampling_margin_passed']
        counts={}
        for label,signal,level in [('rx_pins',wave[:,4]-wave[:,5],0),('rx_clock',wave[:,7],.9)]:
            events=edge_times(t,signal,level,True);counts[label]=int(np.count_nonzero((events>60e-9)&(events<120e-9)))
        result.update(qualified_phy=False,diagnostic=True,buffer_strength=identity['buffer_strength'],
            clock_rising_crossings_60_120ns=counts,manifest_sha256=digest(root/'manifest.json'),
            waveform_sha256=digest(root/'bench.cir.prn'),deck_sha256=manifest['deck_sha256'],
            scope='Only TX native network changed from captured exact-RC diagnostic; complete PHY qualification remains required')
        unchanged()
        if cached is not None and cached!=result:raise ValueError('TX link saved analysis differs from its waveform')
        atomic(root/'summary.json',result)
        atomic(root/'execution.json',dict(status='completed',passed=result['passed'],qualified_phy=False))
    print(root/'summary.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('link',type=Path);a.add_argument('tx',type=Path)
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.link.resolve(),a.tx.resolve()),flush=True)
    else:run(a.artifact.resolve())
