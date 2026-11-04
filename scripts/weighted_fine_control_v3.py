# SPDX-License-Identifier: GPL-3.0-only
"""Compare control drivers with all five actual distributed fine-cell models."""
from collections import defaultdict
import weighted_fine_control_v2 as base
import weighted_fine_unit_v2 as unit
from reduce_rc import number

fine=base.fine
native=base.native
PORTS=base.PORTS
MODES=base.MODES
NAME='openlvds_weighted_fine_control_v3'


def source(mode,orders):
    if mode not in MODES:raise ValueError('Unknown fine-control driver candidate')
    rows=['.subckt '+NAME+' '+' '.join(PORTS)]
    pg=dict(VPWR='VDD',VPB='VDD',VGND='VSS',VNB='VSS')
    for bit in range(5):
        buf=native.CLOCK_BUFFER if mode=='guarded' else fine.old.native.SC+'buf_1'
        inv=native.MODELS['inv_8'] if mode=='guarded' else fine.old.native.SC+'inv_1'
        for tag,model,pins in [('buffer',buf,dict(A=f'B{bit}',X=f'EN{bit}')),('inverse',inv,dict(A=f'EN{bit}',Y=f'ENB{bit}'))]:
            pins=dict(pg,**pins)
            if model not in orders or not set(orders[model])<=set(pins):raise ValueError('Missing actual native control port order')
            rows.append('X'+tag+str(bit)+' '+' '.join(pins[p] for p in orders[model])+' '+model)
        model=unit.name(bit);pins=dict(NODE='DATA',EN=f'EN{bit}',ENB=f'ENB{bit}',VDD='VDD',VSS='VSS')
        if model not in orders or set(orders[model])!=set(pins):raise ValueError('Missing exact native fine-cell port order')
        rows.append(f'Xfine{bit} '+' '.join(pins[p] for p in orders[model])+' '+model)
    return '\n'.join(rows+['.ends '+NAME,''])


def cap_nodes(text,bit):
    """Observe every resistor-connected node on the switched MIM top plate.

    Select the plate by its exact model/dimensions, then follow resistors only.
    This retains separate physical MOS and MIM terminals without an ideal
    CAP alias, a new electrical observation port, or a favorable chosen finger.
    """
    name=unit.name(bit);ports,body=native.definitions(text)[name]
    graph=defaultdict(set);plates=[];mos=[]
    width,length=fine.GEOMETRIES[bit]
    for tokens in body:
        w=' '.join(tokens).split('$',1)[0].split()
        if w[0][0].upper()=='R':
            if len(w)!=4 or number(w[3])<=0:raise ValueError('Invalid physical fine resistance')
            graph[w[1]].add(w[2]);graph[w[2]].add(w[1])
        elif w[0][0].upper()=='X':
            first=next((i for i,v in enumerate(w) if '=' in v),len(w));model=w[first-1]
            params=dict(v.split('=',1) for v in w[first:])
            if model==fine.CAP and float(params['w'])==width and float(params['l'])==length:
                plates.append(w[1])
            elif model in [fine.N,fine.P]:mos.append(w[1:5])
    if len(plates)!=1 or len(mos)!=3:raise ValueError('Require exactly one weighted plate and three native MOS')
    reached=set(plates);pending=list(plates)
    while pending:
        for n in graph[pending.pop()]-reached:reached.add(n);pending.append(n)
    if reached.intersection([*ports,'0']) or sum(n in reached for terminals in mos for n in terminals)!=3:
        raise ValueError('Switched fine plate is shorted or missing physical MOS terminals')
    return [f'XD:Xfine{bit}:'+n for n in sorted(reached)]


def devices(text):
    return dict(mos=native.mapped_mos(text,NAME,{p:'0' if p=='VSS' else p for p in PORTS},'XD'),
                cap_nodes={str(bit):cap_nodes(text,bit) for bit in range(5)})
