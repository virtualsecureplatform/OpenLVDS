#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Exact resistor-network elimination; no capacitance or device is removed.

Nodes touching a capacitor, transistor/subcircuit, or public port are protected.
Only internal algebraic resistor nodes are eliminated by a Schur complement.
This is frequency-independent reduction, not an ideal-power-grid approximation.
"""
import argparse
from collections import defaultdict
import hashlib
import heapq
import itertools
import json
from pathlib import Path
import re
import sys

def number(word):
    m=re.fullmatch(r'([+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-z]*)',word)
    if not m:raise ValueError(f'Not a constant resistor: {word}')
    scale={'':1,'t':1e12,'g':1e9,'meg':1e6,'k':1e3,'m':1e-3,'u':1e-6,'n':1e-9,'p':1e-12,'f':1e-15}
    return float(m[1])*scale[m[2].lower()]

def eliminate(graph,protected,max_degree=4):
    queue=[(len(edges),n) for n,edges in graph.items() if n not in protected]
    heapq.heapify(queue);removed=0
    while queue:
        degree,node=heapq.heappop(queue)
        if node not in graph or node in protected:continue
        neighbors=graph[node]
        if len(neighbors)!=degree or degree>max_degree:continue
        total=sum(neighbors.values())
        if total>0:
            for (a,ga),(b,gb) in itertools.combinations(list(neighbors.items()),2):
                conductance=ga*gb/total
                graph[a][b]=graph[a].get(b,0)+conductance
                graph[b][a]=graph[b].get(a,0)+conductance
        for other in list(neighbors):
            del graph[other][node]
            if other not in protected:heapq.heappush(queue,(len(graph[other]),other))
        del graph[node];removed+=1
    return removed

def reduce_netlist(source,destination):
    text=source.read_text();graph=defaultdict(dict);protected={'0'};kept=[];resistors=0;in_header=False
    for line in text.splitlines():
        fields=line.split()
        if not fields or fields[0].startswith('*'):kept.append(line);continue
        token=fields[0].lower()
        if token=='.subckt':protected.update(fields[2:]);in_header=True
        elif token=='+':
            if in_header:protected.update(fields[1:])
        else:in_header=False
        if token.startswith('r') and len(fields)==4:
            a,b=fields[1:3];r=number(fields[3]);resistors+=1
            if r<=0:
                protected.update([a,b]);kept.append(line);continue
            if a==b:continue
            g=1/r;graph[a][b]=graph[a].get(b,0)+g;graph[b][a]=graph[b].get(a,0)+g
        else:
            kept.append(line)
            if token.startswith(('c','r')):protected.update(fields[1:3])
            elif token.startswith('x'):
                end=next((i for i,w in enumerate(fields) if '=' in w),len(fields))
                protected.update(fields[1:end-1])
            elif token.startswith(('v','i','l','b','d','m')):protected.update(fields[1:5])
    removed=eliminate(graph,protected)
    new=[]
    for a in sorted(graph):
        for b,g in sorted(graph[a].items()):
            if a<b and g>0:new.append(f'RR{len(new)} {a} {b} {1/g:.15g}')
    # Keep the resistors INSIDE the subcircuit, before its .ends statement.
    ends=[i for i,line in enumerate(kept) if line.lower().startswith('.ends')]
    if len(ends)!=1:raise ValueError('Expected one flattened subcircuit')
    kept[ends[0]:ends[0]]=['* Exact internal resistor-node Schur reduction',*new]
    destination.write_text('\n'.join(kept)+'\n')
    summary=dict(source_sha256=hashlib.sha256(text.encode()).hexdigest(),
                 reduced_sha256=hashlib.sha256(destination.read_bytes()).hexdigest(),
                 resistor_count_before=resistors,resistor_count_after=len(new),
                 algebraic_nodes_eliminated=removed,protected_nodes=len(protected),
                 method='exact positive-conductance star-mesh, degree <= 4')
    destination.with_suffix('.json').write_text(json.dumps(summary,indent=2)+'\n')
    return summary

def main():
    p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('destination',type=Path)
    a=p.parse_args();print(json.dumps(reduce_netlist(a.source,a.destination),indent=2))

if __name__=='__main__':main()
