# SPDX-License-Identifier: GPL-3.0-only
"""Physical hierarchy for the unchanged v3 full-bank candidate, not admission."""
from collections import Counter
import dcdl_weighted_direct_v3 as candidate
import mim_base_4x4_v2 as shared
import native_clock_components_v2 as native

NAME='openlvds_weighted_bank_physical_v2'
PORTS=[*candidate.PORTS[:-2],'VPWR','VGND']


def instances():
    cells=candidate.core_instances('guarded')
    for bit in range(5):
        cells += [dict(name=f'fine_buffer{bit}',model=candidate.controls.native.CLOCK_BUFFER,
                       pins=dict(A=f'B{bit}',X=f'fine{bit}',VPWR='VPWR',VGND='VGND')),
                  dict(name=f'fine_inverse{bit}',model=candidate.controls.native.MODELS['inv_8'],
                       pins=dict(A=f'fine{bit}',Y=f'fine_b{bit}',VPWR='VPWR',VGND='VGND')),
                  dict(name=f'fine{bit}',model=candidate.controls.unit.name(bit),
                       pins=dict(NODE='OUT',EN=f'fine{bit}',ENB=f'fine_b{bit}',VDD='VPWR',VSS='VGND'))]
    cells.append(dict(name='shared_base',model=shared.NAME,pins=dict(NODE='OUT',VSS='VGND')))
    if len(cells)!=94 or len({c['name'] for c in cells})!=94:raise ValueError('Full bank instance coverage changed')
    return cells


def pins(cell,orders):
    mapping=dict(dict(VPWR='VPWR',VGND='VGND',VPB='VPWR',VNB='VGND'),**cell['pins'])
    order=orders[cell['model']]
    if not set(order)<=set(mapping):raise ValueError('Incomplete physical bank pin mapping')
    return {p:mapping[p] for p in order}


def spice(orders):
    rows=['.subckt '+NAME+' '+' '.join(PORTS)]
    for cell in instances():
        mapping=pins(cell,orders)
        rows.append('X'+cell['name']+' '+' '.join(mapping[p] for p in orders[cell['model']])+' '+cell['model'])
    return '\n'.join(rows+['.ends '+NAME,''])


def verilog(orders):
    cells=instances();inputs=[p for p in PORTS if p not in ['OUT','VPWR','VGND']]
    nets=sorted({n for c in cells for n in pins(c,orders).values()}-set(PORTS))
    rows=['// SPDX-License-Identifier: GPL-3.0-only','// Unqualified physical hierarchy; no timing model or code ROM selected.',
          '`default_nettype none',f'module {NAME}(input wire '+','.join(inputs)+', output wire OUT, inout wire VPWR,VGND);',
          'wire '+','.join(nets)+';']
    for c in cells:
        rows.append('(* keep="true", dont_touch="true" *) '+c['model']+' '+c['name']+' ('+
                    ','.join('.'+p+'('+n+')' for p,n in pins(c,orders).items())+');')
    return '\n'.join(rows+['endmodule','`default_nettype wire',''])


def leaves(text,top):
    """Canonical complete leaf multiset, retaining all R/C/MOS/MIM statements.

    Only instance labels are omitted. Internal node paths, connections,
    primitive models, parameters and multiplicities remain exact. Root power
    names normalize VPWR/VGND to VDD/VSS for the physical interface adapter.
    """
    definitions=native.definitions(text);result=Counter()
    def walk(model,mapping,path,seen):
        if model in seen:raise ValueError('Recursive physical bank hierarchy')
        ports,body=definitions[model]
        if set(ports)!=set(mapping):raise ValueError('Physical bank source interface mismatch')
        def node(n):return '0' if n=='0' else mapping.get(n,path+':'+n)
        for tokens in body:
            w=' '.join(tokens).split('$',1)[0].split();kind=w[0][0].upper()
            if kind in ['R','C']:
                if len(w)!=4:raise ValueError('Unknown passive source statement')
                result[(kind,w[3],tuple(node(n) for n in w[1:3]),())]+=1
            elif kind=='X':
                first=next((i for i,v in enumerate(w) if '=' in v),len(w));child=w[first-1];nodes=[node(n) for n in w[1:first-1]]
                if child in definitions:
                    order=definitions[child][0]
                    if len(order)!=len(nodes):raise ValueError('Physical bank child port count changed')
                    walk(child,dict(zip(order,nodes)),path+':'+w[0],seen|{model})
                else:
                    if not child.startswith('sky130_fd_pr__'):raise ValueError('Non-native physical bank leaf')
                    result[('X',child,tuple(nodes),tuple(sorted(w[first:])))]+=1
            else:raise ValueError('Unsupported physical bank electrical statement')
    order=definitions[top][0];aliases=dict(VPWR='VDD',VGND='VSS')
    walk(top,{p:aliases.get(p,p) for p in order},'X',set());return result
