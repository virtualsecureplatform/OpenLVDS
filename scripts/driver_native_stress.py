# SPDX-License-Identifier: GPL-3.0-only
"""Observe actual MOS terminals through hierarchy, including mapped supply ports."""
import re
import numpy as np


def terminal_observations(library,deck,instance='XD'):
    definitions={}
    for match in re.finditer(r'(?ims)^\.subckt\s+(\S+)\s.*?^\.ends[^\n]*',library):
        lines=match[0].splitlines();header=lines.pop(0).split()
        while lines and lines[0].startswith('+'): header+=lines.pop(0).split()[1:]
        definitions[match[1].lower()]=(header[2:],lines)
    rows=[]
    def walk(lines,mapping,prefix,stack):
        for line in lines:
            words=line.split()
            if not words or not words[0].lower().startswith('x'): continue
            end=next((i for i,w in enumerate(words) if '=' in w),len(words))
            name,child=words[0],words[end-1]
            if not prefix and name.lower()!=instance.lower(): continue
            full=prefix+':'+name if prefix else name
            def node(n):
                if n=='0': return '0'
                return mapping.get(n.lower(),prefix+':'+n if prefix else n)
            nodes=[node(n) for n in words[1:end-1]]
            if child.lower() in definitions:
                if child.lower() in stack: raise ValueError('Recursive MOS observation hierarchy')
                ports,body=definitions[child.lower()]
                if len(ports)!=len(nodes): raise ValueError('Wrong observation hierarchy port count')
                walk(body,{p.lower():n for p,n in zip(ports,nodes)},full,stack+(child.lower(),))
            elif 'nfet' in child.lower() or 'pfet' in child.lower():
                if len(nodes)!=4: raise ValueError('Require four actual MOS terminals')
                rows.append(dict(device=full,model=child,terminals=dict(zip(['D','G','S','B'],nodes)),
                    parameters=dict(w.split('=',1) for w in words[end:])))
    walk(deck.splitlines(),{},'',())
    if not rows: raise ValueError('No actual MOS devices under requested instance')
    return rows


def voltage_probes(rows):
    return sorted({n for row in rows for n in row['terminals'].values() if n!='0'},key=str.lower)


def measure(names,raw,rows):
    if raw.ndim!=2 or len(raw)<2 or raw.shape[1]!=len(names) or not np.isfinite(raw).all():
        raise ValueError('Invalid native stress trace')
    indices={n.lower():i for i,n in enumerate(names)}
    zero=np.zeros(len(raw))
    def voltage(node):
        if node=='0': return zero
        name='v('+node.replace(':','.').lower()+')'
        if name not in indices: raise ValueError('Missing actual native MOS terminal '+node)
        return raw[:,indices[name]]
    result=[]
    for row in rows:
        d,g,s,b=[voltage(row['terminals'][n]) for n in ['D','G','S','B']]
        metrics={}
        for name,value in [('vgs',g-s),('vgd',g-d),('vds',d-s),('vbs',b-s)]:
            metrics[name]=dict(min_v=float(value.min()),max_v=float(value.max()),max_abs_v=float(np.max(abs(value))))
        result.append(dict(row,voltages=metrics))
    return dict(devices=len(result),results=result,
        scope='Signed sampled voltages at actual native MOS terminals; no synthetic rail substitution or reliability admission.')
