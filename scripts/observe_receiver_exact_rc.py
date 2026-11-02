#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Calculate and independently witness further exact receiver wire-R reduction, preserving native probes."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from dll_candidate_library import audited
from dll_campaign import text_block
from exact_rc_candidate import parse,render,static_signature,witness,math_runtime
from receiver_static_diagnosis import capture_manifest
from reduce_rc import eliminate
from spice_library import checked_netlist

ROOT=Path(__file__).resolve().parents[1]
TOP='openlvds_receiver_core'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()


def retain_probes(network,decks):
    names=set(network['graph'])|network['protected']
    lookup={n.upper():n for n in names}
    if len(lookup)!=len(names):raise ValueError('Ambiguous case-folded native node names')
    observed=set()
    for deck in decks:
        prints=re.findall(r'(?im)^\.print tran[^\n]*',deck)
        if len(prints)!=1:raise ValueError('Require one original native print statement')
        for node in re.findall(r'V\(XRC:([^\)]+)\)',prints[0],re.I):
            if node.upper() not in lookup:raise ValueError('Native observation terminal missing from receiver network')
            observed.add(lookup[node.upper()])
    if not observed:raise ValueError('Require bound native receiver observations')
    network['protected'].update(observed)
    return observed


def reduced(source,decks,degree):
    if degree not in [6,8,12]:raise ValueError('Select a bounded exact elimination degree')
    original=parse(source);observed=retain_probes(original,decks);candidate=deepcopy(original)
    removed=eliminate(candidate['graph'],candidate['protected'],degree)
    text=render(candidate,degree);serialized=parse(text)
    # Named probe vertices can be resistor-only algebraic nodes. Keep them
    # explicitly in both sides of the independent boundary-current witness.
    if not observed<=set(serialized['graph'])|serialized['protected']:
        raise ValueError('Exact reduction removed a native observation node')
    serialized['protected'].update(observed)
    if static_signature(original)!=static_signature(serialized) or original['protected']!=serialized['protected']:
        raise ValueError('Exact reduction changed a capacitor, device, port or protected terminal')
    return original,serialized,text,removed,observed


def prepare(layout,replay,degree=8):
    if not layout.is_relative_to(ROOT/'build/diagnostics/receiver_layout') or not replay.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):
        raise ValueError('Require an audited receiver layout and its prepared native replay')
    physical=json.loads((layout/'summary.json').read_text());info=json.loads((layout/'extraction.json').read_text());audit=audited(layout,info)
    gds=ROOT/physical['designs'][TOP]['gds']
    if not physical['passed'] or sha(layout/'candidate.spice')!=info['source_sha256'] or sha(gds)!=info['gds_sha256']:
        raise ValueError('Receiver source/GDS changed or failed')
    m=json.loads((replay/'manifest.json').read_text())
    if m['identity']['layout']!=str(layout.relative_to(ROOT)) or len(m['tasks'])!=2 or {t['id'] for t in m['tasks']}!={'captured','sharp_control'}:
        raise ValueError('Require the exact original two native controls for this geometry')
    model=checked_netlist(info);library=(replay/'library.spice').read_text()
    if sha(replay/'library.spice')!=m['library_sha256'] or text_block(library,TOP)!=text_block(model,TOP):
        raise ValueError('Replay uses a different receiver network')
    decks=[];paths=[layout/n for n in ['summary.json','candidate.spice','extraction.json','rc_audit.json']]
    paths += [gds,ROOT/info['netlist'],ROOT/audit['report'],replay/'manifest.json',replay/'library.spice']
    for task in m['tasks']:
        p=replay/task['id']/'bench.cir'
        if sha(p)!=task['deck_sha256']:raise ValueError('Native fixture changed')
        paths.append(p);decks.append(p.read_text())
    paths += [ROOT/'scripts'/n for n in [Path(__file__).name,'exact_rc_candidate.py','reduce_rc.py','dll_candidate_library.py','spice_library.py','dll_campaign.py','receiver_static_diagnosis.py']]
    runtime=math_runtime()
    identity=dict(layout=str(layout.relative_to(ROOT)),replay=str(replay.relative_to(ROOT)),degree=degree,
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},math_runtime=runtime)
    def unchanged():
        if any(sha(ROOT/n)!=h for n,h in dict(identity['inputs'],**runtime['binaries']).items()):raise ValueError('Exact receiver observation context changed')
    unchanged();before,after,text,removed,observed=reduced(model,decks,degree);proof=witness(before,after)
    if proof['passed'] is not True:raise ValueError('Independent terminal-current witnesses failed')
    out=layout/'exact_reduction_observation'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=True)
    target=out/'receiver.exact.spice'
    if target.exists() and target.read_text()!=text:raise ValueError('Retain changed exact receiver candidate')
    if not target.exists():target.write_text(text)
    unchanged()
    capture_manifest(out/'summary.json',dict(identity=identity,resistors_before=before['resistors'],resistors_after=after['resistors'],
        algebraic_nodes_removed=removed,observed_nodes=sorted(observed),source_sha256=info['netlist_sha256'],exact_sha256=sha(target),
        non_resistor_sha256=static_signature(after),witness=proof,qualified_phy=False,native_clock_passed=None,transient_equivalence_pending=True,
        scope='Exact positive-conductance resistor elimination only; every capacitor/device/port/directive and all original native probe nodes retained. Four independent sparse terminal-current witnesses. Original native model, GDS, fixtures and live simulations unchanged. Native transient comparison and full qualification remain required before use; no speed or positive transport admission.'))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('layout',type=Path);p.add_argument('replay',type=Path);p.add_argument('--degree',type=int,choices=[6,8,12],default=8);a=p.parse_args()
    print(prepare(a.layout.resolve(),a.replay.resolve(),a.degree)/'summary.json',flush=True)
