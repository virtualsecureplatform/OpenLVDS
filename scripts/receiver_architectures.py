# SPDX-License-Identifier: GPL-3.0-only
"""Bounded receiver alternatives; preserve the public interface and input frontend."""
import re
from dll_campaign import text_block
from layout import circuits
from receiver_lvt_pair_experiment import replace_decision_inputs
from spice_library import replace

TOP='openlvds_receiver_core'
DOWN='lvds_rx_downshift_33_18'
VARIANTS=('lvt','lvt_bias2','lvt_bias4')+tuple(f'pmos_p{p}_t{t}' for p in [8,16] for t in [2,4,8])


def transform(source,variant):
    if variant not in VARIANTS:raise ValueError('Unknown receiver architecture')
    validated=replace_decision_inputs(source)  # Refuse changed baseline pair/tail/mirror or clamps.
    rows={r[0]:r for r in circuits(source)[TOP][1]}
    expected=('XNCB',['NBC','NBC','VSS','VSS'],'sky130_fd_pr__nfet_01v8',dict(w='2',l='0.5'))
    if rows.get('XNCB')!=expected:raise ValueError('Expected original decision bias diode')
    def substitute(text,name,nodes,model,params):
        row=name+' '+' '.join(nodes)+' '+model+' '+' '.join(f'{k}={v}' for k,v in params.items())
        text,count=re.subn(r'(?m)^'+re.escape(name)+r'\s+[^\n]*$',lambda _:row,text)
        if count!=1:raise ValueError('Ambiguous architecture device '+name)
        return text
    if variant.startswith('lvt'):
        if variant=='lvt':return validated
        scale=int(variant[-1]);block=text_block(validated,TOP)
        for name,width in [('XNCB',2*scale),('XCT',16*scale)]:
            _,nodes,model,params=rows[name]
            block=substitute(block,name,nodes,model,dict(params,w=str(width)))
        return replace(validated,TOP,block)
    if DOWN in circuits(source):raise ValueError('Downshift helper already exists')
    if rows.get('XIB0')!=('XIB0',['CO','RESTORE0','VDDD','VSS'],'lvds_rx_restore_mid',{}):
        raise ValueError('Expected original first restoration stage')
    match=re.fullmatch(r'pmos_p(8|16)_t(2|4|8)',variant);pair,tail=match.groups()
    changes=[('XCT',['CT','PB','VDDIO','VDDIO'],'sky130_fd_pr__pfet_g5v0d10v5',dict(w=tail,l='1')),
        ('XC0',['CL','PN','CT','VDDIO'],'sky130_fd_pr__pfet_g5v0d10v5',dict(w=pair,l='0.5')),
        ('XC1',['CO','PP','CT','VDDIO'],'sky130_fd_pr__pfet_g5v0d10v5',dict(w=pair,l='0.5')),
        ('XCD',['CL','CL','VSS','VSS'],'sky130_fd_pr__nfet_g5v0d10v5',dict(w='8',l='0.5')),
        ('XCM',['CO','CL','VSS','VSS'],'sky130_fd_pr__nfet_g5v0d10v5',dict(w='8',l='0.5')),
        ('XIB0',['CO','RESTORE0','VDDD','VSS'],DOWN,{})]
    block=text_block(source,TOP)
    for name,nodes,model,params in changes:block=substitute(block,name,nodes,model,params)
    helper=f'''.subckt {DOWN} A Y VDDD VSS
* Thick-oxide gates accept the 3.3 V decision signal; output is powered at 1.8 V.
XP Y A VDDD VDDD sky130_fd_pr__pfet_g5v0d10v5 w=8 l=0.5
XN Y A VSS VSS sky130_fd_pr__nfet_g5v0d10v5 w=4 l=0.5
.ends {DOWN}
'''
    return replace(source,TOP,block)+'\n'+helper
