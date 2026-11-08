#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Attach two actual source DCCs to four-section phases; ideal shared wires."""
import re
import native_clock_components_v2 as native
from run_native_binary_v2 import translate

PORTS=['P0','P180','RESET_N','Q','VDD','VSS']


def namespace(library):
    """Rename source subcircuits only, avoiding bank standard-cell collisions."""
    defs=native.definitions(library)
    names={n:n if n=='dcc_source' else 'openlvds_chain_dcc_'+n for n in defs}
    lines=[]
    for name,(ports,body) in defs.items():
        lines.append('.subckt '+names[name]+' '+' '.join(ports))
        for original in body:
            words=list(original)
            if words[0][0].upper()!='X':raise ValueError('Unexpected source DCC element')
            stop=next((k for k,w in enumerate(words) if '=' in w),len(words))
            words[stop-1]=names.get(words[stop-1],words[stop-1])
            lines.append(' '.join(words))
        lines.append('.ends '+names[name])
    return '\n'.join(lines)+'\n'


def mapped_mos(library,mapping,prefix):
    """Flatten source cells including explicit SKY130 passive resistor leaves.

    Resistors remain in the simulation library unchanged. Only known passive
    resistor leaves are omitted from the MOS stress list, with their terminals
    retained as voltage observations by the caller.
    """
    defs=native.definitions(library);devices=[];passives=[]
    def walk(model,pins,path,ancestors):
        if model in ancestors:raise ValueError('Recursive source DCC hierarchy')
        ports,body=defs[model]
        if set(pins)!=set(ports):raise ValueError('Source DCC port mismatch')
        def net(n):return '0' if n=='0' else pins.get(n,path+':'+n)
        for words in body:
            if words[0][0].upper()!='X':raise ValueError('Unexpected source DCC element')
            stop=next((k for k,w in enumerate(words) if '=' in w),len(words))
            child=words[stop-1];nodes=[net(n) for n in words[1:stop-1]];name=path+':'+words[0]
            if child in defs:
                if len(nodes)!=len(defs[child][0]):raise ValueError('Source DCC child pin mismatch')
                walk(child,dict(zip(defs[child][0],nodes)),name,ancestors|{model})
            elif child=='sky130_fd_pr__res_generic_po' and len(nodes)==2:
                passives.append(dict(name=name,model=child,terminals=nodes))
            elif child.startswith('sky130_fd_pr__') and ('nfet_' in child or 'pfet_' in child) and '01v8' in child and len(nodes)==4:
                devices.append(dict(name=name,model=child,limit_v=1.95,terminals=nodes))
            else:raise ValueError('Unsupported source DCC leaf '+child)
    walk('dcc_source',mapping,prefix,set())
    return devices,passives


def fixture(chain_deck,bank_library,dcc_library,dcc_include):
    defs=native.definitions(dcc_library)
    if defs.get('dcc_source',([],))[0]!=PORTS:raise ValueError('Source DCC interface changed')
    if set(native.definitions(bank_library))&set(defs):raise ValueError('Bank and DCC definition collision')
    if (chain_deck.count('CCHAIN_LOAD B3_OUT 0 20f')!=1 or
            any(chain_deck.count(f'\nXB{k} ')!=1 for k in (1,2,3)) or
            re.search(r'(?im)^XDC[01]\s|^VDCC_RESET\s',chain_deck)):
        raise ValueError('Require untouched four-section native fixture')
    lines=[f'.include "{dcc_include}"','VDCC_RESET DCC_RESET_N 0 PWL(0 0 1n 0 1.02n 1.8 40n 1.8)']
    observations={};probes={'DCC_RESET_N'}
    for k,(a,b) in enumerate((('IN','B1_OUT'),('OUT','B2_OUT'))):
        out=f'DCC{k}_OUT';mapping=dict(P0=a,P180=b,RESET_N='DCC_RESET_N',Q=out,VDD='VDD',VSS='0')
        devices,passives=mapped_mos(dcc_library,mapping,f'XDC{k}')
        lines += [f'XDC{k} '+' '.join(mapping[p] for p in PORTS)+' dcc_source',f'CDCC{k}_LOAD {out} 0 20f']
        observations[str(k)]=dict(devices=devices,passive_resistors=passives,input_nodes=[a,b],output_node=out,
            source_cell_only=True,shared_wire_rc_qualified=False,qualified_phy=False)
        probes.update(n for d in devices+passives for n in d['terminals'] if n!='0');probes.add(out)
    match=re.search(r'(?m)^\.print tran (.*)$',chain_deck)
    if match is None:raise ValueError('Missing native observations')
    tokens=match[1].split()+['V('+n+')' for n in sorted(probes)]
    unique=[];seen=set()
    for token in tokens:
        key=token.lower().replace(':','.')
        if key not in seen:unique.append(token);seen.add(key)
    result=chain_deck[:match.start()]+'\n'.join(lines)+'\n.print tran '+' '.join(unique)+chain_deck[match.end():]
    translate(result)
    return result,observations
