#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Complete two-bank fixtures for independent fast-entry interventions."""
import re
from pathlib import Path
import fast_entry_damping_bank_300_v1 as architecture
import next_bank_fixture_300_v2 as next_bank
from run_native_binary_v2 import translate


def fixture(original,library,observations,kind,include):
    top=architecture.source.TOP
    if set(observations)!={'first','next'} or any(observations['next'][k]!=0 for k in ('next_coarse','next_fine')):
        raise ValueError('Require exact two-bank zero-code observation maps')
    new_library,new_top,first,revision=architecture.transform(library,top,observations['first'],kind)
    _,_,second=next_bank.harness(new_library,new_top,dict(ports=next_bank.PORTS,observations=first),0,0)
    text=original
    includes=re.findall(r'(?m)^\.include "[^"\n]*/bank\.spice"$',text)
    if len(includes)!=1 or text.count('.tran 2p 40n 0 2p')!=1:
        raise ValueError('Require complete original native two-bank fixture')
    text=text.replace(includes[0],f'.include "{Path(include)}"',1)
    for instance in ('XD','XL'):
        pattern=r'(?m)^'+instance+r' (.+) '+re.escape(top)+r'$'
        if len(re.findall(pattern,text))!=1:raise ValueError('Actual bank instance changed')
        text=re.sub(pattern,lambda m:instance+' '+m[1]+' '+new_top,text,count=1)
    match=re.search(r'(?m)^\.print tran (.*)$',text)
    if match is None:raise ValueError('Missing original observation statement')
    required={'IN','OUT','NEXT_OUT','VDD'}
    for o in (first,second):
        required.update(n for d in o['devices'] for n in d['terminals'] if n!='0')
        required.update(c['node'] for c in o['controls']);required.update(g['gate_node'] for g in o['programming_gates'])
    if revision['coarse_shunt_units']:
        required.update(f'{prefix}:{instance}:mid' for prefix in ('XD','XL')
                        for instance in [*[f'Xdelay{k}' for k in range(1,16)],'Xtail_load'])
    unique=[];seen=set()
    for token in match[1].split()+['V('+n+')' for n in sorted(required)]:
        key=token.lower().replace(':','.')
        if key not in seen:unique.append(token);seen.add(key)
    text=text[:match.start()]+'.print tran '+' '.join(unique)+text[match.end():]
    translate(text)
    return text,new_library,dict(first=first,next=second),revision
