#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare incident extracted routing capacitance on DLL section internal nets."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
from dll_campaign import atomic
from dll_candidate_library import audited
from reduce_rc import number
from spice_library import checked_netlist

ROOT=Path(__file__).resolve().parents[1]


def routing_caps(text):
    parents={};ranks={}
    def find(node):
        parents.setdefault(node,node);ranks.setdefault(node,0);head=node
        while parents[head]!=head: head=parents[head]
        while parents[node]!=node:
            nxt=parents[node];parents[node]=head;node=nxt
        return head
    def union(a,b):
        a,b=find(a),find(b)
        if a==b:return
        if ranks[a]<ranks[b]:a,b=b,a
        parents[b]=a
        if ranks[a]==ranks[b]:ranks[a]+=1
    rows=[line.split() for line in text.splitlines() if line.split()]
    for row in rows:
        if row[0][0].lower()=='r' and len(row)==4:union(row[1],row[2])
    caps=defaultdict(float)
    for row in rows:
        if row[0][0].lower()=='c' and len(row)==4:
            a,b=find(row[1]),find(row[2]);value=number(row[3])
            if value<0:raise ValueError('Negative extracted capacitance')
            if a!=b:caps[a]+=value;caps[b]+=value
    return {node:caps[find(node)] for node in parents}


def sections(text):
    caps=routing_caps(text);result={}
    for i in range(4):
        nets={}
        for leaf in ['N','S','B','PCTRL','X0__T','X0__F','X1__T','X1__F']:
            # Hierarchical layout can add private cell prefixes. Preserve the
            # flattened schematic label suffix, including Magic's .tN splits.
            suffix='openlvds_dll_analog__XL__X'+str(i)+'__'+leaf
            values={v for n,v in caps.items() if re.search(r'(?:^|\.)'+re.escape(suffix)+r'(?:\.t\d+)?$',n)}
            if len(values)!=1:raise ValueError('Missing or disconnected section net '+suffix)
            nets[leaf]=values.pop()*1e15
        result[str(i)]=nets
    return result


def inspect(layout):
    if not layout.is_relative_to(ROOT/'build/diagnostics/dll_layout'):raise ValueError('Use an isolated DLL layout')
    physical=json.loads((layout/'summary.json').read_text());info=json.loads((layout/'extraction.json').read_text())
    if not physical['passed'] or physical['source_sha256']!=info['source_sha256']:raise ValueError('Invalid physical candidate')
    audited(layout,info);text=checked_netlist(info)
    paths=[layout/'summary.json',layout/'extraction.json',layout/'rc_audit.json',layout/'candidate.spice',ROOT/info['netlist']]
    identity=dict(layout=str(layout.relative_to(ROOT)),files={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        code={n:hashlib.sha256((ROOT/'scripts'/n).read_bytes()).hexdigest() for n in
              ['inspect_dll_stage_caps.py','dll_candidate_library.py','spice_library.py','reduce_rc.py']})
    report=dict(identity=identity,qualified_phy=False,qualification_verdict=None,section_incident_routing_cap_ff=sections(text),
        scope='Sum of wire capacitors incident on each resistor-connected net. Includes coupling to other nets at full value; excludes device and MIM model capacitance. Not an effective AC load or a timing qualification.')
    root=ROOT/'build/diagnostics/dll_stage_loading'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True,exist_ok=True);atomic(root/'summary.json',report);print(root/'summary.json',flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('layout',type=Path);a=p.parse_args();inspect(a.layout.resolve())
