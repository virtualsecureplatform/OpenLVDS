#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare complete native decision-node responses without changing qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np
from diagnose_link_clock import pulse_transport
from diagnose_receiver_restoration import falling_windows
from dll_measurements import read_wave
from receiver_static_diagnosis import capture_manifest
from spice_scope import closure_hash

ROOT=Path(__file__).resolve().parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def normalized_deck(text):
    includes=re.findall(r'(?im)^\.include[^\n]+',text)
    if len(includes)!=1:raise ValueError('Require one native library inclusion')
    return re.sub(r'(?im)^\.print tran[^\n]*\n?', '',text.replace(includes[0],'.include "matched_library"'))


def compare(replays):
    if len(replays)<2 or len(set(replays))!=len(replays):raise ValueError('Compare at least two distinct completed replays')
    files={};results=[];reference_decks={};reference_closures=None
    for replay in replays:
        if not replay.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):raise ValueError('Require isolated complete native replays')
        manifest=json.loads((replay/'manifest.json').read_text());identity=manifest['identity'];report=json.loads((replay/'summary.json').read_text())
        if report.get('diagnostic_complete') is not True or report.get('manifest_sha256')!=sha(replay/'manifest.json'):
            raise ValueError('Native replay is incomplete or changed')
        if {t['id'] for t in manifest['tasks']}!={'captured','sharp_control'} or len(manifest['tasks'])!=2:
            raise ValueError('Require exactly the two original native controls')
        library=(replay/'library.spice').read_text()
        if sha(replay/'library.spice')!=manifest['library_sha256']:raise ValueError('Native library changed')
        closures={name:closure_hash(library,name) for name in ['lvds_bias','openlvds_ddr_rx']}
        if reference_closures is not None and closures!=reference_closures:raise ValueError('Bias or digital load differs')
        reference_closures=closures
        proofs=dict(identity['inputs']);proofs.update({'scripts/'+n:h for n,h in identity['code'].items()})
        for n in ['manifest.json','summary.json','library.spice']:proofs[str((replay/n).relative_to(ROOT))]=sha(replay/n)
        for task in manifest['tasks']:
            folder=replay/task['id'];saved=json.loads((folder/'summary.json').read_text());deck=folder/'bench.cir'
            if saved not in report['results'] or saved.get('manifest_sha256')!=sha(replay/'manifest.json') or sha(deck)!=task['deck_sha256'] or saved.get('waveform_sha256')!=sha(folder/'bench.cir.prn'):
                raise ValueError('Completed child report/fixture/waveform changed')
            for n in ['summary.json','bench.cir','bench.cir.prn']:proofs[str((folder/n).relative_to(ROOT))]=sha(folder/n)
            normalized=normalized_deck(deck.read_text())
            if task['id'] in reference_decks and normalized!=reference_decks[task['id']]:raise ValueError('Native stimuli or numerical policy differ')
            reference_decks[task['id']]=normalized
            w,h=read_wave(folder/'bench.cir.prn');t=w[:,1]
            if not np.isfinite(w).all() or np.any(np.diff(t)<=0) or t[0]>1e-15 or t[-1]<80e-9-1e-12:raise ValueError('Require complete finite original 80 ns traces')
            col=lambda name:w[:,h['V('+name.upper()+')']]
            differential=col('RCP')-col('RCN');output=col('RXCLOCK')
            transport=pulse_transport(t,differential,output,15e-9,75e-9)
            if transport!=saved['receiver_transport']:raise ValueError('Native transport remeasurement changed')
            nodes={name:col(identity['observation_nodes'][name]) for name in ['CO','CL','RESTORE0','RESTORE1']};nodes['RXCLOCK']=output
            windows=falling_windows(t,differential,nodes,transport)
            for row in windows:
                keep=(t>=row['input_edge_ns']*1e-9)&(t<row['response_window_end_ns']*1e-9)
                delta=nodes['CO'][keep]-nodes['CL'][keep]
                row['co_minus_cl_peak_v']=float(delta.max());row['co_minus_cl_minimum_v']=float(delta.min())
            missing=[r for r in windows if r['output_edges_in_next_input_period']==0]
            results.append(dict(replay=str(replay.relative_to(ROOT)),case=task['id'],transport=transport,falling_windows=windows,
                missing_falling_windows=len(missing),missing_without_positive_decision_difference=sum(r['co_minus_cl_peak_v']<=0 for r in missing),
                missing_without_restore0_crossing=sum(r['first_restorer_falling_crossings']==0 for r in missing)))
        if any(sha(ROOT/n)!=h for n,h in proofs.items()):raise ValueError('Native evidence changed during comparison')
        for n,h in proofs.items():
            if n in files and files[n]!=h:raise ValueError('Compared replays bind inconsistent shared evidence')
            files[n]=h
    for n in [Path(__file__).name,'diagnose_receiver_restoration.py','diagnose_link_clock.py','dll_measurements.py','spice_scope.py','receiver_static_diagnosis.py']:
        files['scripts/'+n]=sha(ROOT/'scripts'/n)
    if any(sha(ROOT/n)!=h for n,h in files.items()):raise ValueError('Comparison evidence changed')
    identity=dict(replays=[str(r.relative_to(ROOT)) for r in replays],files=files)
    out=ROOT/'build/diagnostics/receiver_decision_comparison'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    capture_manifest(out/'summary.json',dict(identity=identity,results=results,qualified_phy=False,
        scope='Read-only complete original 80 ns native remeasurement; identical stimuli/numerical policies and shared bias/digital RX. Entire falling-to-falling response periods within original 15–75 ns transport window. Bus voltages are wire observations, not actual MOS terminal VDSAT or static inverter trip. Source sizing and geometry can both differ between replays. No positive source/native/component/PHY admission or model change.'))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('replays',nargs='+',type=Path);a=p.parse_args()
    print(compare([r.resolve() for r in a.replays])/'summary.json',flush=True)
