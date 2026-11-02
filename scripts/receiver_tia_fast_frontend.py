# SPDX-License-Identifier: GPL-3.0-only
"""Bounded frontend-conductance experiment around the real feedback inverter."""
import receiver_tia_restore as tia
from dll_campaign import text_block
from layout import circuits
from spice_library import replace

TOP=tia.TOP
RES=tia.RES
AMPLIFIER=[]
VARIANTS=['control','fast_tia_r2','fast_tia_r4']
LOADS=[f'XRL{node}{suffix}' for node in ['PP','PN'] for suffix in 'ABCDE']
LOADS += [f'XRBC{node}{i}' for node in ['PP','PN'] for i in range(2)]


def source_variant(canonical,variant):
    source=tia.baseline.baseline.transform(tia.baseline.original.source_variant(canonical,True),'control')
    return transform(source,variant)


def transform(source,variant):
    if variant not in VARIANTS:raise ValueError('Select a declared fast-frontend feedback receiver')
    candidate=tia.transform(source,'control' if variant=='control' else variant.removeprefix('fast_'))
    if variant=='control':return candidate
    rows={r[0]:r for r in circuits(candidate)[TOP][1]}
    if any(name.startswith('XFAST_') for name in rows):raise ValueError('Frontend loads already duplicated')
    actual={name for name in rows if name.startswith(('XRLPP','XRLPN','XRBC'))}
    if actual!=set(LOADS):raise ValueError('Require every original two-unit frontend load and boost resistor')
    block=text_block(candidate,TOP);additions=[]
    for name in LOADS:
        _,nodes,model,params=rows[name]
        if model!=RES or params!=dict(w='0.35',l='1.25') or len(nodes)!=3 or nodes[-1]!='VSS':
            raise ValueError('Unexpected original precision-poly frontend load')
        lines=[line for line in block.splitlines() if line.split() and line.split()[0]==name]
        if len(lines)!=1:raise ValueError('Ambiguous frontend load statement')
        additions.append(lines[0].replace(name,'XFAST_'+name[1:],1))
    # Double every branch, including both series boost units: unloaded bias
    # ratios are preserved and the resistive Thevenin impedance halves. Real
    # resistor/device capacitances remain; settling improvement is unproven.
    anchor='.ends '+TOP
    if block.splitlines().count(anchor)!=1:raise ValueError('Unexpected receiver terminator')
    return replace(candidate,TOP,block.replace(anchor,'\n'.join(additions)+'\n'+anchor))
