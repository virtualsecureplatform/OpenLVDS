# SPDX-License-Identifier: GPL-3.0-only
"""Strengthen only the post-mux root branches using full measured TG cells.

Leaf muxes and coarse tap loads stay unchanged. The measured output compound
and fine cell are retained. New root gang wiring remains unextracted.
"""
from collections import Counter
from copy import deepcopy
import re
import post_mux_output_rc_bank_v112 as base
from parallel_root_bank_v97 import rename

ROOT=base.ROOT
source=base.source
checked_cell=base.checked_cell
driver_inputs=base.driver_inputs
TG=base.base.TG


def name(profile):
    base.name(profile)
    return 'openlvds_parallel_post_mux_roots_'+profile+'_v116'


def root_calls(bank,top):
    defs=source.native.definitions(bank);body=defs[top][1];result=[]
    for k in range(4):
        calls=[w for w in body if w[0]==f'Xswitch1_0_{k}']
        if len(calls)!=1:raise ValueError('Missing or duplicate post-mux root')
        w=calls[0]
        if w[-1]!=TG or dict(zip(defs[TG][0],w[1:-1]))!=dict(A=f'tree0_{k}',Z='selected',EN=f'en1_{k}',ENB=f'en_b1_{k}',VPWR='VPWR',VGND='VGND'):
            raise ValueError('Post-mux root data/control/body wiring changed')
        result.append(w)
    return result


def strengthen(bank,top,target):
    calls=root_calls(bank,top)
    if re.search(r'(?m)^Xroot_parallel\d+\b',bank):raise ValueError('Post-mux roots already strengthened')
    before=base.cell_definition(bank,top)
    added='\n'.join(' '.join([f'Xroot_parallel{k}',*w[1:]]) for k,w in enumerate(calls))+'\n'
    after,n=re.subn(r'(?im)^\.ends\b',added+'.ends',before)
    if n!=1:raise ValueError('Ambiguous post-mux bank boundary')
    return rename(bank.replace(before,after,1),top,target)


def projection(bank,profile):
    top=name(profile);calls=root_calls(bank,top);body=source.native.definitions(bank)[top][1]
    if [w for w in body if w[0].startswith('Xroot_parallel')]!=[[f'Xroot_parallel{k}',*w[1:]] for k,w in enumerate(calls)]:
        raise ValueError('Parallel post-mux roots missing, duplicated or rewired')
    result,n=re.subn(r'(?m)^Xroot_parallel[0-3][ \t][^\n]*\n','',bank)
    if n!=4:raise ValueError('Parallel root source layout changed')
    return rename(result,top,base.name(profile))


def transform(text,profile,fine_rc):
    original=base.transform(text,profile,fine_rc)
    bank=strengthen(original,base.name(profile),name(profile))
    if projection(bank,profile)!=original:raise ValueError('Unrelated measured post-mux circuitry changed')
    counts=source.primitive_counts(bank,name(profile))
    if sum(v for k,v in counts.items() if 'fet_' in k)!=989 or counts.get('sky130_fd_pr__cap_mim_m3_1')!=35:
        raise ValueError('Strengthened post-mux native inventory changed')
    return bank


def observations(bank,profile,previous):
    result=base.observations(projection(bank,profile),profile,previous)
    top=name(profile);ports=source.native.definitions(bank)[top][0]
    devices=source.native.mapped_mos(bank,top,{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports},'XD')
    byname={d['name']:d for d in devices};gates=deepcopy(result['programming_gates']);extras=[]
    for k in range(4):
        prefix=f'XD:Xswitch1_0_{k}:';duplicate=f'XD:Xroot_parallel{k}:'
        original=[g for g in gates if g['device'].startswith(prefix)]
        if len(original)!=2 or any(g['kind']!='tg' for g in original):raise ValueError('Root gate identity changed')
        for g in original:
            device=duplicate+g['device'][len(prefix):]
            extras.append(dict(g,device=device,gate_node=byname[device]['terminals'][1]))
    gates+=extras
    if len(devices)!=989 or len(byname)!=989 or len(gates)!=141 or Counter(g['kind'] for g in gates)!=Counter(fine=93,tg=48):
        raise ValueError('Incomplete strengthened post-mux native/gate coverage')
    return dict(result,devices=devices,programming_gates=gates)
