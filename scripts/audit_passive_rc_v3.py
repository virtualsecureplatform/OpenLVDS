#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Audit extracted R/C signs and exact negative capacitor-matrix diagonals.

Positive two-terminal R/C elements suffice for passivity. A negative diagonal
is a direct negative-energy basis-vector witness. Negative elements without
that witness are rejected conservatively; no full PSD claim is made for them.
No element is removed, clipped, relocated or otherwise repaired here.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
from reduce_rc import number

ROOT=Path(__file__).resolve().parents[1]


def audit(text):
    models={};current=None
    for line in text.splitlines():
        w=line.split('$',1)[0].split()
        if not w or w[0].startswith('*'):continue
        if w[0].lower()=='.subckt':
            current=w[1]
            if current in models:raise ValueError('Duplicate RC model')
            models[current]=dict(caps=[],resistors=[],device_nodes=set())
        elif w[0].lower()=='.ends':current=None
        elif current:
            if w[0][0].upper() in ['C','R']:
                if len(w)!=4:raise ValueError('Unexpected extracted RC element')
                value=number(w[3]);kind='caps' if w[0][0].upper()=='C' else 'resistors'
                models[current][kind].append(dict(name=w[0],nodes=w[1:3],value=value))
            elif w[0][0].upper()=='X':
                first=next((i for i,v in enumerate(w) if '=' in v),len(w));models[current]['device_nodes'].update(w[1:first-1])
    if not models:raise ValueError('Missing extracted RC models')
    rows=[]
    for name,data in models.items():
        diagonals=defaultdict(float)
        for c in data['caps']:
            a,b=c['nodes']
            if a==b:continue
            for n in [a,b]:
                if n!='0':diagonals[n]+=c['value']
        bad_c=[c for c in data['caps'] if c['value']<0];bad_r=[r for r in data['resistors'] if r['value']<=0]
        negative=[dict(node=n,diagonal_ff=v*1e15,device_terminal=n in data['device_nodes']) for n,v in sorted(diagonals.items()) if v < -1e-27]
        rows.append(dict(model=name,resistors=len(data['resistors']),capacitors=len(data['caps']),negative_capacitors=bad_c,
            nonpositive_resistors=bad_r,negative_diagonal_vertices=negative,negative_energy_witness=bool(negative),
            elementwise_passive_passed=not bad_c and not bad_r))
    return dict(rows=rows,elementwise_passive_passed=all(r['elementwise_passive_passed'] for r in rows),
        negative_energy_witness=any(r['negative_energy_witness'] for r in rows),qualified_phy=False)


def run(libraries,evidence):
    files=libraries+evidence
    def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
    code=[Path(__file__),ROOT/'scripts/reduce_rc.py'];identity=dict(version='extracted-rc-sign-and-negative-diagonal-audit-v2.2',
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files},code={str(p.relative_to(ROOT)):sha(p) for p in code})
    rows=[dict(library=str(p.relative_to(ROOT)),**audit(p.read_text())) for p in libraries]
    out=ROOT/'build/diagnostics/rc_passivity_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    body=json.dumps(dict(identity=identity,libraries=rows,elementwise_passive_passed=all(r['elementwise_passive_passed'] for r in rows),
        negative_energy_witness=any(r['negative_energy_witness'] for r in rows),qualified_phy=False,
        scope='Unmodified extracted parasitic R/C signs and exact capacitor-matrix negative-diagonal witnesses; excludes intrinsic MOS/MIM model capacitance, no numerical fix or electrical admission'),indent=2)+'\n'
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('RC audit witness changed')
    out.mkdir(parents=True,exist_ok=True);path=out/'summary.json'
    if path.exists() and path.read_text()!=body:raise ValueError('Retain prior RC audit')
    if not path.exists():path.write_text(body)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('libraries',nargs='+',type=Path);p.add_argument('--evidence',nargs='*',type=Path,default=[]);a=p.parse_args()
    print(run([v.resolve() for v in a.libraries],[v.resolve() for v in a.evidence]),flush=True)
