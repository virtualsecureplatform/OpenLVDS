# SPDX-License-Identifier: GPL-3.0-only
"""Identify all fine sections before any full-bank junction reconstruction.

Names and junction values are not used to choose devices. This is a local
structural diagnostic; native full-bank LVS and geometric provenance remain
mandatory. No netlist or model parameter is changed here.
"""
from collections import Counter,defaultdict
import native_bank_inventory_v51 as native
import moscap_junction_reconstruction_v86 as junctions

N='sky130_fd_pr__nfet_01v8'
P='sky130_fd_pr__pfet_01v8'
MIM='sky130_fd_pr__cap_mim_m3_1'


def dimensions(d,model,width,length='.15'):
    return junctions.geometry_key(d)==(model,native.exact_number(width),native.exact_number(length))


def identify(text,top):
    ports,devices=native.native_leaves(text,top)
    if len({d['name'] for d in devices})!=len(devices):raise ValueError('Ambiguous native device identities')
    caps=[d for d in devices if any(dimensions(d,m,'1.26') for m in (N,P))]
    if len(caps)!=62:raise ValueError('Require exactly 62 native fine capacitor MOS devices')
    groups=defaultdict(list)
    for d in caps:
        drain,gate,source,body=d['nodes']
        if drain!=source or source!=body or gate==body or gate in ports:
            raise ValueError('Fine capacitor lacks a private gate and tied D/S/body')
        groups[gate].append(d)
    if len(groups)!=31:raise ValueError('Require 31 distinct private fine CAP nodes')
    incidence=defaultdict(list)
    for d in devices:
        for node in set(d['nodes']):incidence[node].append(d)
    sections=[];used=set()
    def one(candidates,role):
        if len(candidates)!=1:raise ValueError('Fine section has missing or ambiguous '+role)
        return candidates[0]
    for cap,group in sorted(groups.items()):
        cn=one([d for d in group if d['model']==N],'N capacitor')
        cp=one([d for d in group if d['model']==P],'P capacitor')
        low=cn['nodes'][3];high=cp['nodes'][3]
        if low==high:raise ValueError('Fine capacitor supply rails are shorted')
        attached=incidence[cap]
        if len(attached)!=5 or {d['name'] for d in group}-{d['name'] for d in attached}:
            raise ValueError('Private fine CAP node must touch exactly five MOS devices')
        switches=[d for d in attached if d['name'] not in {cn['name'],cp['name']}]
        clear=one([d for d in switches if dimensions(d,N,'.42') and d['nodes'][3]==low
                   and set(d['nodes'][::2])=={cap,low}],'N clear switch')
        ns=one([d for d in switches if dimensions(d,N,'.42') and d['name']!=clear['name']],'N pass switch')
        ps=one([d for d in switches if dimensions(d,P,'.84')],'P pass switch')
        if (ns['nodes'][3]!=low or ps['nodes'][3]!=high or cap not in ns['nodes'][::2]
            or set(ns['nodes'][::2])!=set(ps['nodes'][::2])):
            raise ValueError('Fine pass-gate data/body topology changed')
        node=next(iter(set(ns['nodes'][::2])-{cap}),None)
        en=ns['nodes'][1];enb=ps['nodes'][1]
        if (node is None or len({cap,node,low,high,en,enb})!=6 or clear['nodes'][1]!=enb):
            raise ValueError('Fine data, complementary-control or clear topology changed')
        guards=[d for d in devices if dimensions(d,MIM,'2','2') and set(d['nodes'])=={enb,low}]
        guard=one(guards,'control guard MIM')
        for d in [*attached,guard]:
            if d['name'] in used:raise ValueError('Fine sections share a device')
            used.add(d['name'])
        sections.append(dict(cap_node=cap,node=node,enable=en,enable_b=enb,low=low,high=high,
                             capacitor_n=cn['name'],capacitor_p=cp['name'],pass_n=ns['name'],pass_p=ps['name'],clear=clear['name'],guard=guard['name']))
    if (len({s['node'] for s in sections})!=1 or len({s['low'] for s in sections})!=1
        or len({s['high'] for s in sections})!=1 or len({s['enable'] for s in sections})!=31
        or len({s['enable_b'] for s in sections})!=31
        or {s['enable'] for s in sections}&{s['enable_b'] for s in sections}):
        raise ValueError('Fine shared data/rails or 31 independent control pairs changed')
    return dict(sections=sections,fine_sections=31,capacitor_mos=62,programming_mos=93,guard_mims=31,
                geometry_proof_required=True,whole_bank_lvs_required=True,parameters_changed=False,qualified_phy=False)


def diagnose(text,top,measurement_rows):
    partition=identify(text,top);_,devices=native.native_leaves(text,top)
    byname={d['name']:d for d in devices};library=junctions.junction_library(measurement_rows)
    rows=[];hist=Counter()
    for section in partition['sections']:
        for role in ['capacitor_n','capacitor_p']:
            d=byname[section[role]];key=junctions.geometry_key(d)
            if key not in library:raise ValueError('Missing measured capacitor primitive')
            target=library[key]['values'];actual={f:d['params'].get(f) for f in junctions.FIELDS}
            if any(v is None for v in actual.values()):raise ValueError('Native capacitor omits junction fields')
            differences=[f for f in junctions.FIELDS if native.exact_number(actual[f])!=native.exact_number(target[f])]
            zeros=[f for f in differences if native.exact_number(actual[f])==0]
            nonzero=[f for f in differences if f not in zeros]
            hist.update(dict(devices=1,devices_with_mismatch=bool(differences),zero_field_mismatches=len(zeros),nonzero_field_mismatches=len(nonzero)))
            rows.append(dict(instance=d['name'],cap_node=section['cap_node'],role=role,primitive=library[key]['cell'],
                             original=actual,measured=target,differing_fields=differences,zero_mismatches=zeros,nonzero_mismatches=nonzero))
    return dict(partition=partition,capacitor_junctions=rows,summary=dict(hist),
                per_device_capacitor_junctions_match_geometry=not hist['devices_with_mismatch'],
                parameters_changed=False,joint_rc_qualified=False,qualified_phy=False)
