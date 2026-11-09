# SPDX-License-Identifier: GPL-3.0-only
"""Add every true source-DCC MOS terminal without changing circuit or clocks."""
import re
import dcc_input_waveforms_300_v2 as waveform
import dcc_chain_fanout_300_v1 as inventory
from run_native_binary_v2 import translate

PORTS=['P0','P180','RESET_N','Q','VDD','VSS']


def observations(library):
    if inventory.native.definitions(library).get('dcc_source',([],))[0]!=PORTS:
        raise ValueError('Actual source DCC interface changed')
    devices,passives=inventory.mapped_mos(library,dict(zip(PORTS,['P0','P180','RESET_N','Q','VDD','0'])),'XD')
    if (len(devices)!=136 or len(passives)!=2 or len({d['name'] for d in devices+passives})!=138):
        raise ValueError('Complete source DCC native inventory changed')
    return dict(devices=devices,passive_resistors=passives)


def fixture(out,s,library):
    obs=observations(library);text=waveform.fixture(out,s)
    if text.count('XD P0 P180 RESET_N Q VDD 0 dcc_source\n')!=1:
        raise ValueError('Actual source DCC call changed')
    matches=list(re.finditer(r'(?m)^\.print tran (.+)$',text))
    if len(matches)!=1:raise ValueError('Missing source DCC observation statement')
    match=matches[0];nodes={'RESET_N'}
    nodes.update(n for d in obs['devices']+obs['passive_resistors'] for n in d['terminals'] if n!='0')
    tokens=match[1].split()+['V('+n+')' for n in sorted(nodes)];unique=[];seen=set()
    for token in tokens:
        if not re.fullmatch(r'V\([^()\s]+\)',token):raise ValueError('Unexpected source DCC observation token')
        key=token.lower().replace(':','.')
        if key not in seen:unique.append(token);seen.add(key)
    text=text[:match.start()]+'.print tran '+' '.join(unique)+text[match.end():]
    translate(text)
    return text,obs
