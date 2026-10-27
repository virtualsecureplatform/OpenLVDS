#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Positive-RC quick-node reduction, requiring separate waveform validation.

TICER quick-node equations: g_ab += g_ai*g_bi/sum(g_i),
c_ab += c_ai*g_bi/sum(g_i). Never eliminate a port or a device terminal.
Reference: Sheehan, TICER (ICCAD 1999); derivation in the KLayout-PEX docs:
https://iic-jku.github.io/klayout-pex-website/doc/doc.html#quick-nodes
This approximation preserves the DC conductance network, not all RC poles.
"""
import argparse
from collections import defaultdict
import hashlib
import heapq
import itertools
import json
from pathlib import Path
from reduce_rc import number

ROOT=Path(__file__).resolve().parents[1]

def reduce_quick(g,c,protected,max_tau=1e-14,max_neighbors=12):
    queue=[];version=defaultdict(int);removed=0;largest_tau=0.
    def enqueue(n):
        version[n]+=1
        if n in protected or n not in g or not g[n]:return
        tau=sum(c.get(n,{}).values())/sum(g[n].values())
        if tau<=max_tau and len(set(g[n])|set(c.get(n,{})))<=max_neighbors:
            heapq.heappush(queue,(tau,n,version[n]))
    for n in list(g):enqueue(n)
    while queue:
        tau,n,ver=heapq.heappop(queue)
        if n not in g or version[n]!=ver:continue
        neighbors=dict(g[n]);caps=dict(c.get(n,{}));total=sum(neighbors.values())
        actual=sum(caps.values())/total
        if actual>max_tau:continue
        affected=set(neighbors)|set(caps)
        for (a,ga),(b,gb) in itertools.combinations(neighbors.items(),2):
            value=ga*gb/total
            g[a][b]=g[a].get(b,0)+value;g[b][a]=g[b].get(a,0)+value
        for a,ca in caps.items():
            for b,gb in neighbors.items():
                if a==b:continue
                value=ca*gb/total
                c[a][b]=c[a].get(b,0)+value;c[b][a]=c[b].get(a,0)+value
        for a in neighbors:del g[a][n]
        for a in caps:del c[a][n]
        del g[n];c.pop(n,None);removed+=1;largest_tau=max(largest_tau,actual)
        for a in affected:enqueue(a)
    return removed,largest_tau

def fast(source,destination,max_tau_ps=.01):
    text=source.read_text();g=defaultdict(dict);c=defaultdict(dict)
    kept=[];protected={'0'};header=False;count_r=0;count_c=0
    for line in text.splitlines():
        w=line.split()
        if not w or w[0].startswith('*'):kept.append(line);continue
        tag=w[0].lower()
        if tag=='.subckt':protected.update(w[2:]);header=True
        elif tag=='+':
            if header:protected.update(w[1:])
        else:header=False
        if tag.startswith(('r','c')) and len(w)==4:
            a,b=w[1:3];value=number(w[3]);count_r+=tag.startswith('r');count_c+=tag.startswith('c')
            if value<=0:
                if value<0:raise ValueError('Negative extracted passive element')
                kept.append(line);protected.update([a,b]);continue
            if a==b:continue
            target=g if tag.startswith('r') else c;v=1/value if target is g else value
            target[a][b]=target[a].get(b,0)+v;target[b][a]=target[b].get(a,0)+v
        else:
            kept.append(line)
            if tag.startswith('x'):
                end=next((i for i,x in enumerate(w) if '=' in x),len(w));protected.update(w[1:end-1])
            elif tag.startswith(('v','i','l','b','d','m','r','c')):protected.update(w[1:5])
    removed,largest=reduce_quick(g,c,protected,max_tau_ps*1e-12)
    passives=[];nr=nc=0
    for a in sorted(g):
        for b,v in sorted(g[a].items()):
            if a<b and v>0:passives.append(f'RFAST{nr} {a} {b} {1/v:.15g}');nr+=1
    for a in sorted(c):
        for b,v in sorted(c[a].items()):
            if a<b and v>0:passives.append(f'CFAST{nc} {a} {b} {v:.15g}');nc+=1
    ends=[i for i,x in enumerate(kept) if x.lower().startswith('.ends')]
    if len(ends)!=1:raise ValueError('Expected one flattened subcircuit')
    kept[ends[0]:ends[0]]=['* TICER quick-node APPROXIMATION; see companion JSON',*passives]
    destination.write_text('\n'.join(kept)+'\n')
    info=dict(source_sha256=hashlib.sha256(text.encode()).hexdigest(),
        fast_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
        model='TICER quick-node positive RC',approximate_transient=True,exact_dc=True,
        qualified=False,max_tau_ps=max_tau_ps,largest_eliminated_tau_ps=largest*1e12,
        nodes_eliminated=removed,resistors_before=count_r,resistors_after=nr,
        capacitors_before=count_c,capacitors_after=nc)
    destination.with_suffix('.json').write_text(json.dumps(info,indent=2)+'\n')
    return info

def main():
    p=argparse.ArgumentParser();p.add_argument('--max-tau-ps',type=float,default=.01)
    a=p.parse_args();results={}
    for kind in ['current','digital']:
        manifest=json.loads((ROOT/f'build/extracted/{kind}.json').read_text())
        if not manifest['passed']:raise SystemExit(f'{kind} extraction failed')
        for name,info in manifest['designs'].items():
            src=ROOT/info['netlist'];dest=src.with_name(name+f'.fast_{a.max_tau_ps:g}ps.spice')
            reduction=fast(src,dest,a.max_tau_ps)
            results[name]=dict(info,exact_netlist=info['netlist'],exact_sha256=info['netlist_sha256'],
                netlist=str(dest.relative_to(ROOT)),netlist_sha256=reduction['fast_sha256'],fast_reduction=reduction)
            print(name,f"R {reduction['resistors_before']} -> {reduction['resistors_after']}, "
                       f"C {reduction['capacitors_before']} -> {reduction['capacitors_after']}",flush=True)
    (ROOT/'build/extracted/fast.json').write_text(json.dumps(dict(qualified=False,designs=results),indent=2)+'\n')

if __name__=='__main__':main()
