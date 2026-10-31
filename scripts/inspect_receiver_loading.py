#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Report incident receiver routing capacitors from independently audited RC."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from dll_campaign import atomic
from dll_candidate_library import audited
from inspect_dll_stage_caps import routing_caps
from spice_library import checked_netlist

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(layout):
    if not layout.is_relative_to(ROOT/'build/diagnostics/receiver_layout'):
        raise ValueError('Use an isolated receiver layout')
    physical=json.loads((layout/'summary.json').read_text());info=json.loads((layout/'extraction.json').read_text())
    if not physical['passed'] or physical['source_sha256']!=info['source_sha256']:
        raise ValueError('Receiver source/physical proof changed')
    audited(layout,info);caps,components=routing_caps(checked_netlist(info),with_components=True);values={}
    for leaf in ['PP','PN','CO','CL','CT','RESTORE0','RESTORE1']:
        matches=[n for n in caps if re.search(r'openlvds_receiver_core__'+leaf+r'(?:\.t\d+)?$',n)]
        if not matches and leaf.startswith('RESTORE'):continue
        if len({components[n] for n in matches})!=1:raise ValueError('Missing/disconnected receiver net '+leaf)
        values[leaf]=caps[matches[0]]*1e15
    paths=[layout/n for n in ['summary.json','extraction.json','rc_audit.json','candidate.spice']]+[ROOT/info['netlist']]
    identity=dict(layout=str(layout.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):digest(p) for p in paths},
                  code={n:digest(ROOT/'scripts'/n) for n in ['inspect_receiver_loading.py','inspect_dll_stage_caps.py',
                        'dll_candidate_library.py','spice_library.py','reduce_rc.py']})
    out=ROOT/'build/diagnostics/receiver_loading'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=True)
    atomic(out/'summary.json',dict(identity=identity,qualified_phy=False,qualification_verdict=None,
        incident_routing_cap_ff=values,
        scope='Incident wire capacitance, full coupling value, excluding device/MIM capacitance; not effective AC load or timing qualification'))
    print(out/'summary.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('layout',type=Path);a=p.parse_args();inspect(a.layout.resolve())
