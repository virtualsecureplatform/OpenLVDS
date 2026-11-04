# SPDX-License-Identifier: GPL-3.0-only
"""Expand routed bank connections to native primitives without resizing devices.

Each compound uses its own schematic scope. This avoids confusing local tap
definitions with similarly named standard-cell library definitions. Geometry,
power continuity, and extracted topology need their own independent checks.
"""
import re

PREFIX='__openlvds_bank_reference_internal__'


def definitions(text):
    lines=[]
    for line in text.splitlines():
        line=line.split('$',1)[0].strip()
        if line.startswith('+'):
            if not lines:raise ValueError('Orphan SPICE continuation')
            lines[-1]+=' '+line[1:].strip()
        else:lines.append(line)
    headers=re.findall(r'(?im)^\.subckt\s+(\S+)', '\n'.join(lines))
    if len(set(headers))!=len(headers):raise ValueError('Duplicate schematic definition')
    result={};current=None
    for line in lines:
        w=line.split()
        if not w or w[0].startswith('*'):continue
        if w[0].lower()=='.subckt':
            if current is not None:raise ValueError('Nested schematic definition')
            current=w[1];result[current]=(w[2:],[])
        elif w[0].lower()=='.ends':current=None
        elif current is not None:
            if not w[0].lower().startswith('x'):raise ValueError('Unsupported native schematic element')
            end=next((i for i,v in enumerate(w) if '=' in v),len(w))
            if end<3:raise ValueError('Malformed native schematic instance')
            params=dict(v.split('=',1) for v in w[end:])
            result[current][1].append((w[0],w[1:end-1],w[end-1],params))
    if current is not None:raise ValueError('Unterminated native schematic')
    for _,instances in result.values():
        for _,nodes,model,_ in instances:
            if model in result and len(nodes)!=len(result[model][0]):raise ValueError('Native child pin count mismatch')
    return result


def expand(defs,model,pins,prefix):
    """Retain the exact primitive parameters, including native SPICE unit suffixes."""
    leaves=[]
    def visit(model,mapping,path,ancestors):
        if model in ancestors:raise ValueError('Recursive native schematic')
        for instance,nodes,child,params in defs[model][1]:
            translated=[mapping.get(n,path+'__'+n) for n in nodes]
            tag=path+'__'+instance
            if child in defs:
                visit(child,dict(zip(defs[child][0],translated)),tag,ancestors|{model})
            elif child.startswith('sky130_fd_pr__'):
                leaves.append((tag,translated,child,dict(params)))
            else:raise ValueError('Missing native primitive definition: '+child)
    if model not in defs or set(pins)!=set(defs[model][0]):raise ValueError('Native cell pin set mismatch: '+model)
    visit(model,pins,prefix,set())
    return leaves


def reference(top,ports,rows,sc_text,macro_texts):
    """Rows are actual final OpenDB (instance, master, pin, net) records."""
    cells={};allnets=set()
    for name,model,pin,net in rows:
        if not net or net.startswith(PREFIX):raise ValueError('Disconnected or reserved native net')
        cell=cells.setdefault(name,dict(model=model,pins={}))
        if cell['model']!=model or pin in cell['pins']:raise ValueError('Conflicting native instance records')
        cell['pins'][pin]=net;allnets.add(net)
    if len(set(ports))!=len(ports) or not set(ports)<=allnets:raise ValueError('Invalid bank formal ports')
    sc=definitions(sc_text);macros={m:definitions(t) for m,t in macro_texts.items()}
    leaves=[];counts={}
    for name,cell in sorted(cells.items()):
        model=cell['model'];defs=macros.get(model,sc)
        group=expand(defs,model,cell['pins'],PREFIX+name)
        counts[name]=len(group);leaves+=group
    if not leaves:raise ValueError('Empty native bank reference')
    names=[d[0] for d in leaves]
    if len(set(names))!=len(names):raise ValueError('Duplicate primitive path')
    lines=['* Native routed-bank reference; exact device parameters, no resizing.',
           '.subckt '+top+' '+' '.join(ports)]
    for tag,nodes,model,params in leaves:
        lines.append('X'+tag+' '+' '.join(nodes)+' '+model+' '+
                     ' '.join(k+'='+v for k,v in params.items()))
    return '\n'.join(lines+['.ends '+top,'']),counts
