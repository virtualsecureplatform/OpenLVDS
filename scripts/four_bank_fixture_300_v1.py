#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Four actual native delay sections; preparation only, no fanout/RC admission."""
from copy import deepcopy
import re
import next_bank_fixture_300 as single
import native_clock_components_v2 as native
from run_native_binary_v2 import translate


def fixture(original, library, top, identity, *, codes=((0,0),(0,0),(0,0))):
    """Retain the first section and add three complete independently coded banks.

    Intermediate outputs drive the next actual input. Only the far output has
    the original 20 fF capacitor. Detector/DCC fanout is deliberately unmodelled.
    """
    if len(codes)!=3:
        raise ValueError('Require exactly three downstream section codes')
    # Validate the untouched source fixture and original full observation map.
    single.fixture(original,library,top,identity,next_coarse=0,next_fine=0)
    observations={'section0':deepcopy(identity['observations'])}
    lines=[];probes=set();previous='OUT'
    for index,(coarse,fine) in enumerate(codes,1):
        source,_,obs=single.harness(library,top,identity,coarse,fine)
        instance=f'XB{index}';prefix=f'B{index}_';output=prefix+'OUT'
        def rename(node):
            if node.startswith('XL:'):return instance+node[2:]
            if node.startswith('NEXT_'):return prefix+node[5:]
            if node=='OUT':return previous
            return node
        devices=[]
        for d in obs['devices']:
            d=deepcopy(d);d['name']=rename(d['name'])
            d['terminals']=[rename(n) for n in d['terminals']];devices.append(d)
        controls=[dict(c,node=rename(c['node'])) for c in obs['controls']]
        gates=[dict(g,device=rename(g['device']),gate_node=rename(g['gate_node'])) for g in obs['programming_gates']]
        pinmap={p:previous if p=='IN' else output if p=='OUT' else 'VDD' if p=='VPWR'
                else '0' if p=='VGND' else prefix+p for p in single.PORTS}
        if native.mapped_mos(library,top,pinmap,instance)!=devices:
            raise ValueError('Four-section native device mapping changed')
        for line in source:
            if line.startswith('CNEXT_LOAD'):continue
            tokens=line.split()
            if tokens[0]=='XL':tokens[0]=instance
            elif tokens[0].startswith('VNEXT_'):tokens[0]='V'+prefix+tokens[0][6:]
            tokens[1:]=[rename(t) for t in tokens[1:]]
            lines.append(' '.join(tokens))
        observations[f'section{index}']=dict(devices=devices,controls=controls,programming_gates=gates,
            input_node=previous,output_node=output,coarse=coarse,fine=fine)
        probes.update(n for d in devices for n in d['terminals'] if n!='0')
        probes.update(c['node'] for c in controls);probes.update(g['gate_node'] for g in gates)
        previous=output
    lines.append(f'CCHAIN_LOAD {previous} 0 20f')
    result=original.replace('CLOAD OUT 0 20f\n','\n'.join(lines)+'\n',1)
    match=re.search(r'(?m)^\.print tran (.*)$',result)
    tokens=match[1].split()+['V('+n+')' for n in sorted(probes)]
    seen=set();unique=[]
    for token in tokens:
        key=token.lower().replace(':','.')
        if key not in seen:unique.append(token);seen.add(key)
    result=result[:match.start()]+'.print tran '+' '.join(unique)+result[match.end():]
    translate(result)
    return result,observations
