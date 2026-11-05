# SPDX-License-Identifier: GPL-3.0-only
"""Expand actual native SPICE without resizing or losing unit suffixes."""
import layout
from collections import Counter
from decimal import Decimal
import re


def exact_number(value):
    match=re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(meg|[tgkmunpf]?)',str(value),re.I)
    if match is None:raise ValueError('Unsupported native numeric parameter')
    scale={'':'1','t':'1e12','g':'1e9','meg':'1e6','k':'1e3','m':'1e-3','u':'1e-6','n':'1e-9','p':'1e-12','f':'1e-15'}
    return Decimal(match[1])*Decimal(scale[match[2].lower()])


def native_leaves(source,name):
    # The synthesis-oriented layout.flatten() splits wide MOS and accepts
    # plain floats only. Here native SPICE suffixes and every actual device
    # must remain unchanged; connectivity itself is checked by strict LVS.
    defs=layout.circuits(source);leaves=[]
    def walk(model,mapping,path,seen):
        if model in seen:raise ValueError('Recursive native bank definition')
        for instance,nodes,child,params in defs[model][1]:
            translated=['0' if n=='0' else mapping.get(n,path+'__'+n) for n in nodes]
            if child in defs:
                order=defs[child][0]
                if params or len(order)!=len(translated):raise ValueError('Parameterized or invalid native hierarchy')
                walk(child,dict(zip(order,translated)),path+instance+'__',seen|{model})
            elif child.startswith('sky130_fd_pr__'):
                leaves.append(dict(name=path+instance,nodes=translated,model=child,params=params))
            else:raise ValueError('Unknown primitive in native parameter inventory')
    walk(name,{p:p for p in defs[name][0]},'native__',set());return defs[name][0],leaves


def compare_parameters(expected,actual):
    def key(d):return d['model'],exact_number(d['params']['w']),exact_number(d['params']['l'])
    if Counter(map(key,expected))!=Counter(map(key,actual)):
        raise ValueError('Native model or dimensions changed')
    full={'w','l','ad','as','pd','ps'};partial={'w','l'}
    for d in expected:
        allowed=partial if 'cap_mim' in d['model'] else full if set(d['params'])==full else partial
        if set(d['params'])!=allowed:raise ValueError('Unexpected reference native parameters')
    for d in actual:
        if set(d['params'])!=(partial if 'cap_mim' in d['model'] else full):
            raise ValueError('Extracted MOS lacks actual junction geometry')
    supplied={key(d) for d in expected if set(d['params'])==full}
    absent={key(d) for d in expected if 'fet_' in d['model'] and set(d['params'])==partial}
    if supplied&absent:raise ValueError('Ambiguous partial-junction native class')
    def junctions(devices):
        result=Counter()
        for d in devices:
            if key(d) not in supplied:continue
            p={k:exact_number(v) for k,v in d['params'].items()}
            result[(key(d),tuple(sorted(((p['ad'],p['pd']),(p['as'],p['ps'])))))]+=1
        return result
    if junctions(expected)!=junctions(actual):raise ValueError('Reference native junction geometry changed')
    counts=Counter(d['model'] for d in actual)
    return dict(native_parameters_preserved=True,all_native_model_dimensions_preserved=True,
                all_reference_supplied_junctions_preserved=True,
                newly_characterized_junction_devices=sum(key(d) in absent for d in actual),
                native_model_counts=dict(counts),native_primitives=len(actual))

