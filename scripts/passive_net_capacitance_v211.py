#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Report parasitic C incident on DC-connected nets of a flat native RC view.

Native MOS and MIM capacitances are not approximated. This is a diagnostic
of extracted passive loading; resistor-shorted capacitances are not a timing
model or a replacement for distributed native transient qualification.
"""
import argparse
from collections import defaultdict
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
from native_bank_inventory_v51 import exact_number


def loading(text,targets):
    parents={};ranks={};caps=[];native=defaultdict(int);ports=None
    def root(n):
        parents.setdefault(n,n);ranks.setdefault(n,0)
        while parents[n]!=n:
            parents[n]=parents[parents[n]];n=parents[n]
        return n
    def join(a,b):
        a,b=root(a),root(b)
        if a==b:return
        if ranks[a]<ranks[b]:a,b=b,a
        parents[b]=a
        if ranks[a]==ranks[b]:ranks[a]+=1
    for line in re.sub(r'\n[ \t]*\+[ \t]*',' ',text).splitlines():
        w=line.split('$',1)[0].split()
        if not w or w[0].startswith('*'):continue
        if w[0].lower()=='.subckt':
            if ports is not None:raise ValueError('Require a single flat native RC subcircuit')
            ports=w[2:]
            for n in ports:root(n)
        elif w[0].lower()=='.ends':continue
        elif w[0][0].upper() in ('R','C'):
            if len(w)!=4:raise ValueError('Unexpected passive statement')
            value=exact_number(w[3])
            if not value.is_finite() or value<0 or (w[0][0].upper()=='R' and value==0):raise ValueError('Require positive R and nonnegative finite C')
            a,b=w[1:3];root(a);root(b)
            if w[0][0].upper()=='R':join(a,b)
            else:caps.append((a,b,value))
        elif w[0][0].upper()=='X':
            end=next((k for k,v in enumerate(w) if '=' in v),len(w));model=w[end-1]
            if not model.startswith('sky130_fd_pr__'):raise ValueError('Require flattened native devices')
            native[model]+=1
            for n in w[1:end-1]:root(n)
        else:raise ValueError('Unsupported flat RC statement')
    if ports is None or not targets or len(set(targets))!=len(targets) or any(n not in parents for n in targets):raise ValueError('Missing or duplicate diagnostic target')
    groups=defaultdict(list)
    for n in targets:groups[root(n)].append(n)
    totals=defaultdict(Decimal);couplings=defaultdict(lambda:defaultdict(Decimal));ignored=0
    for a,b,value in caps:
        a,b=root(a),root(b)
        if a==b:ignored+=1;continue
        totals[a]+=value;totals[b]+=value
        if a in groups and b in groups:
            couplings[a][b]+=value;couplings[b][a]+=value
    return dict(targets={n:dict(dc_equivalent_targets=sorted(groups[root(n)]),incident_parasitic_capacitance_ff=float(totals[root(n)]*Decimal('1e15')),
            coupling_to_other_targets_ff={','.join(sorted(groups[g])):float(v*Decimal('1e15')) for g,v in sorted(couplings[root(n)].items())}) for n in targets},
        parasitic_capacitor_statements=len(caps),self_caps_after_wire_short_ignored=ignored,native_model_counts=dict(native),
        scope='DC wire-group parasitic C incidence only; native MOS/MIM capacitance and distributed transient timing remain separate',qualified_phy=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('netlist',type=Path);p.add_argument('--targets',nargs='+',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    data=a.netlist.read_bytes();r=loading(data.decode(),a.targets);r['netlist_sha256']=hashlib.sha256(data).hexdigest();r['code_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if hashlib.sha256(a.netlist.read_bytes()).hexdigest()!=r['netlist_sha256']:raise ValueError('RC view changed during diagnosis')
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:f.write(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r['targets'],indent=2))
