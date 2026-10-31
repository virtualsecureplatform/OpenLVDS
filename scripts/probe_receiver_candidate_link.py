#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test an audited receiver in the saved native link after both pin replays recover."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import numpy as np
from dll_campaign import atomic
from dll_candidate_library import audited
from dll_measurements import read_wave
from simulate_link import analyze,edge_times,word_stream,REQ
from spice_engine import command,engine,provenance
from spice_library import checked_netlist
from layout_receiver_gain_candidate import source_variant
from spice_slots import slot
from stage_phy_candidate import overlay

ROOT=Path(__file__).resolve().parents[1]
CODE=['probe_receiver_candidate_link.py','probe_receiver_gain_candidate.py','layout_receiver_gain_candidate.py',
      'probe_receiver_clamp_candidate.py','layout_receiver_clamp_candidate.py','receiver_clamp_experiment.py',
      'probe_receiver_strong_clamp_candidate.py','layout_receiver_strong_clamp_candidate.py','receiver_strong_clamp_experiment.py',
      'probe_receiver_wide_input_candidate.py','layout_receiver_wide_input_candidate.py','receiver_wide_input_experiment.py',
      'probe_receiver_light_clamp_candidate.py','layout_receiver_light_clamp_candidate.py','receiver_light_clamp_experiment.py','receiver_light_decision_experiment.py',
      'layout_receiver_variant.py','layout_receiver_tail_candidate.py','receiver_candidate_rc.py',
      'probe_link_clock_restore.py','diagnose_link_clock.py','spice_scope.py','spice_probes.py','dll_candidate_library.py',
      'dll_campaign.py','dll_measurements.py','physical_policy.py','simulate_link.py',
      'spice_engine.py','spice_library.py','spice_slots.py','stage_phy_candidate.py','run_ngspice.py']


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def recheck_replay(root):
    identity=json.loads((root/'manifest.json').read_text())['identity']
    if identity.get('clamp_variant')=='light_decision_1k_clamp':
        from probe_receiver_light_clamp_candidate import run
    elif identity.get('clamp_variant')=='strong_wide_input':
        from probe_receiver_wide_input_candidate import run
    elif identity.get('clamp_variant')=='strong':
        from probe_receiver_strong_clamp_candidate import run
    elif identity.get('decision_clamped'):
        from probe_receiver_clamp_candidate import run
    else:
        from probe_receiver_gain_candidate import run
    return run(root)


def rebind(deck,old,new):
    include=f'.include "{old}/library.spice"'
    if deck.count(include)!=1:raise ValueError('Expected one captured library inclusion')
    return deck.replace(include,f'.include "{new}/library.spice"')


def replay_ready(replay):
    if not (replay/'summary.json').exists():raise ValueError('Both receiver replay cases must complete first')
    summary=json.loads((replay/'summary.json').read_text())
    if not summary.get('diagnostic_complete') or any(
            not (replay/name/'summary.json').exists() for name in ['captured','sharp_control']):
        raise ValueError('Both receiver replay cases must complete first')
    # Completed cached replay remeasures the actual waveforms and verifies all
    # source/deck/model/runtime hashes before its results can gate integration.
    recheck_replay(replay)
    summary=json.loads((replay/'summary.json').read_text())
    results=summary['results']
    if len(results)!=2 or {r['task'] for r in results}!={'captured','sharp_control'}:
        raise ValueError('Receiver replay coverage is incomplete')
    if any(r['receiver_transport']['missing_output_edges'] or not r['receiver_transport']['pulses'] or
           any(p['output_edges_in_next_input_period']!=1 for p in r['receiver_transport']['pulses']) for r in results):
        raise ValueError('Receiver replay loses or repeats clock edges')


def receiver_overlay(baseline,model,ports):
    header=re.search(r'(?im)^\.subckt[ \t]+openlvds_receiver_core[^\n]*(?:\n\+[^\n]*)*',baseline)
    if not header or header[0].replace('\n+',' ').split()[2:]!=ports:
        raise ValueError('Receiver candidate changes captured fixture terminal order')
    return overlay(baseline,model,'openlvds_receiver_core',
        ('openlvds_driver','lvds_bias','openlvds_dll','openlvds_delay_line','openlvds_tx_core','openlvds_ddr_rx'))


def prepare(link,replay):
    if engine()!='ngspice' or not link.is_relative_to(ROOT/'build/link') or not replay.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):
        raise ValueError('Use isolated inputs in the pinned ngspice environment')
    previous=json.loads((link/'summary.json').read_text());config=previous['config']
    if config['fast_rc'] or not config['diagnostic'] or config['dll_phase']:
        raise ValueError('Use a full-RC ideal-phase diagnostic reference')
    for name,key in [('bench.cir','deck_sha256'),('bench.cir.prn','waveform_sha256'),('library.spice','library_sha256')]:
        if digest(link/name)!=previous[key]:raise ValueError('Saved link reference changed')
    capture=json.loads((replay/'manifest.json').read_text());layout=ROOT/capture['identity']['layout']
    if not layout.is_relative_to(ROOT/'build/diagnostics/receiver_layout'):
        raise ValueError('Use an isolated receiver layout')
    physical=json.loads((layout/'summary.json').read_text())
    if not physical['passed'] or (layout/'rejected_candidate.json').exists():raise ValueError('Physical receiver did not pass')
    clamped=capture['identity'].get('decision_clamped',False)
    if clamped!=physical['identity'].get('decision_clamped',False):raise ValueError('Receiver replay architecture differs from layout')
    if capture['identity'].get('clamp_variant')!=physical['identity'].get('clamp_variant'):
        raise ValueError('Receiver replay clamp variant differs from layout')
    if capture['identity'].get('clamp_variant')=='light_decision_1k_clamp':
        from receiver_light_clamp_experiment import source_variant as selected_source
    elif capture['identity'].get('clamp_variant')=='strong_wide_input':
        from receiver_wide_input_experiment import source_variant as selected_source
    elif capture['identity'].get('clamp_variant')=='strong':
        from receiver_strong_clamp_experiment import source_variant as selected_source
    elif clamped:
        from receiver_clamp_experiment import source_variant as selected_source
    else:selected_source=source_variant
    if (layout/'candidate.spice').read_text()!=selected_source((ROOT/'analog/openlvds.spice').read_text()):
        raise ValueError('Unexpected receiver source variant')
    for name,h in physical['identity']['code'].items():
        if digest(ROOT/'scripts'/name)!=h:raise ValueError('Receiver physical producer changed')
    info=json.loads((layout/'extraction.json').read_text());audited(layout,info)
    gds=ROOT/physical['designs']['openlvds_receiver_core']['gds']
    if digest(gds)!=info['gds_sha256'] or info['source_sha256']!=digest(layout/'candidate.spice'):
        raise ValueError('Receiver extraction is stale')
    library=receiver_overlay((link/'library.spice').read_text(),checked_netlist(info),info['ports'])
    paths=[link/n for n in ['summary.json','bench.cir','bench.cir.prn','library.spice']]
    paths += [layout/n for n in ['summary.json','extraction.json','rc_audit.json','candidate.spice']]+[gds,ROOT/info['netlist'],replay/'manifest.json']
    identity=dict(link=str(link.relative_to(ROOT)),receiver=str(layout.relative_to(ROOT)),replay=str(replay.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):digest(p) for p in paths},
        code={n:digest(ROOT/'scripts'/n) for n in set(CODE)|set(capture['identity']['code'])},
        simulator_provenance=provenance(),parent_config=config)
    root=ROOT/'build/diagnostics/receiver_candidate_link'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if (root/'manifest.json').exists():return root
    root.mkdir(parents=True);(root/'library.spice').write_text(library)
    (root/'bench.cir').write_text(rebind((link/'bench.cir').read_text(),link,root))
    (root/'producer.py').write_bytes(Path(__file__).read_bytes())
    atomic(root/'manifest.json',dict(identity=identity,qualified_phy=False,deck_sha256=digest(root/'bench.cir'),
                                    library_sha256=digest(root/'library.spice')))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/receiver_candidate_link'):raise ValueError('Use a captured receiver link diagnostic')
    manifest=json.loads((root/'manifest.json').read_text());identity=manifest['identity']
    def unchanged():
        if provenance()!=identity['simulator_provenance'] or any(digest(ROOT/'scripts'/n)!=h for n,h in identity['code'].items()):
            raise ValueError('Receiver link diagnostic producer changed')
        if any(digest(ROOT/p)!=h for p,h in identity['inputs'].items()):raise ValueError('Receiver link diagnostic input changed')
        for name,key in [('bench.cir','deck_sha256'),('library.spice','library_sha256')]:
            if digest(root/name)!=manifest[key]:raise ValueError('Receiver link fixture changed')
        if digest(root/'producer.py')!=identity['code']['probe_receiver_candidate_link.py']:raise ValueError('Producer snapshot changed')
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);unchanged()
        replay_ready(ROOT/identity['replay'])
        cached=None
        if (root/'summary.json').exists():
            cached=json.loads((root/'summary.json').read_text())
            if cached['waveform_sha256']!=digest(root/'bench.cir.prn') or cached['manifest_sha256']!=digest(root/'manifest.json'):
                raise ValueError('Receiver link waveform or manifest changed')
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
        result.update(qualified_phy=False,diagnostic=True,receiver=identity['receiver'],
            clock_rising_crossings_60_120ns=counts,manifest_sha256=digest(root/'manifest.json'),
            waveform_sha256=digest(root/'bench.cir.prn'),deck_sha256=manifest['deck_sha256'],
            scope='Only analog receiver native network changed from captured exact-RC diagnostic; complete PHY qualification remains required')
        unchanged()
        if cached is not None and cached!=result:raise ValueError('Receiver link saved analysis differs from its waveform')
        atomic(root/'summary.json',result)
        atomic(root/'execution.json',dict(status='completed',passed=result['passed'],qualified_phy=False))
    print(root/'summary.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    a=s.add_parser('prepare');a.add_argument('link',type=Path);a.add_argument('replay',type=Path)
    a=s.add_parser('run');a.add_argument('artifact',type=Path);a=p.parse_args()
    if a.action=='prepare':print(prepare(a.link.resolve(),a.replay.resolve()),flush=True)
    else:run(a.artifact.resolve())
