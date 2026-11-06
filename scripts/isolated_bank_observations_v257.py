# SPDX-License-Identifier: GPL-3.0-only
"""Observe every native isolated-bank MOS and typed physical programming gate.

Only actual extraction aliases label separated RC nodes; physical/native RC
qualification remains a caller requirement. No netlist or stimulus is changed.
"""
from collections import Counter
import re
import measured_bank_observations_v145 as original
from dcdl_tg_tree_v5 import control_targets
from isolated_fine_bank_physical_v239 import TOP,DRIVER,BUFFER

native=original.native
number=original.number
TG,FINE,N,NLVT,P=original.TG,original.FINE,original.N,original.NLVT,original.P
expected_programming=original.expected_programming
aliases=original.aliases


def graph_contract(graph,plan):
    if graph['top']!=TOP or len(graph['cells'])!=180 or len(plan['cells'])!=352:
        raise ValueError('Require exact native isolated-bank graph/placement')
    byname={c['name']:c for c in graph['cells']}
    expected={
        'u_fine_isolate':(DRIVER,dict(A='selected',Y='fine_node',VGND='VGND',VPWR='VPWR')),
        'u_fine_regenerate':(BUFFER,dict(A='fine_node',X='OUT',VGND='VGND',VPWR='VPWR')),
    }
    for name,(model,pins) in expected.items():
        if name not in byname or byname[name]['model']!=model or byname[name]['pins']!=pins:
            raise ValueError('Isolated fine driver/regenerator path changed')
    for k in range(31):
        c=byname.get(f'u_fine_unit{k}')
        if c is None or c['model']!=FINE or c['pins']!=dict(A='fine_node',CTRL=f'fine{k}',CTRL_B=f'fine_b{k}',VPWR='VPWR',VGND='VGND'):
            raise ValueError('Fine load/programming/bulk interface changed')


def mapping(mag,ext,rc,graph,plan):
    graph_contract(graph,plan)
    expected=expected_programming(graph);names,labelled,body,canonical_count=aliases(mag,ext,rc,graph,plan)
    ports=graph['ports'];devices=native.mapped_mos(rc,graph['top'],{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports},'XD')
    byname={d['name'].split(':')[-1]:d for d in devices};gates=[];actual=Counter()
    kinds={(NLVT,number('1.68')):'tg',(P,number('3.36')):'tg',(N,number('.42')):'fine',(P,number('.84')):'fine'}
    for w in body:
        if not w[0].upper().startswith('X'):continue
        end=next((k for k,t in enumerate(w) if '=' in t),len(w));model=w[end-1]
        if 'fet_' not in model:continue
        params=dict(t.split('=',1) for t in w[end:]);width=number(params['w']);kind=kinds.get((model,width))
        if kind is None:continue
        label=labelled.get(w[2]);pattern=r'en(?:_b)?[01]_[0-3]' if kind=='tg' else r'fine(?:_b)?\d+'
        if label is None or re.fullmatch(pattern,label) is None:raise ValueError('Programming gate lacks its actual logical control label')
        actual[(kind,model,width,label)]+=1
        gates.append(dict(device=byname[w[0]]['name'],gate_node=byname[w[0]]['terminals'][1],control=label,kind=kind))
    if actual!=expected or len(gates)!=173 or len(devices)!=1479 or len(byname)!=1479:
        raise ValueError('Incomplete actual native MOS or typed per-control programming-gate coverage')
    targets=set(control_targets(0,0));controls=set()
    for device in devices:
        for node in device['terminals']:
            raw=node[3:] if node.startswith('XD:') else 'VPWR' if node=='VDD' else 'VGND' if node=='0' else node
            label=labelled.get(raw)
            if label in targets:controls.add((node,label))
    if {c for _,c in controls}!=targets or len(targets)!=86:raise ValueError('Missing actual terminal observations for a logical control')
    if canonical_count!=151 or len(names)!=352:raise ValueError('Isolated canonical nets or physical instance inventory changed')
    data=set()
    for device in devices:
        for node in device['terminals']:
            raw=node[3:] if node.startswith('XD:') else 'VPWR' if node=='VDD' else 'VGND' if node=='0' else node
            label=labelled.get(raw)
            if label in ('selected','fine_node'):data.add((node,label))
    if {label for _,label in data}!={'selected','fine_node'}:raise ValueError('Missing actual isolated data-path terminal observations')
    return dict(data_nodes=[dict(node=n,data_net=label) for n,label in sorted(data)],devices=devices,programming_gates=gates,controls=[dict(node=n,control=c) for n,c in sorted(controls)],
                magic_instance_names=names,observed_canonical_nets=canonical_count,logical_controls=sorted(targets),
                physical_instances=len(names),typed_per_control_gate_coverage_verified=True,rc_model_changed=False,isolated_fine_interface_verified=True)
