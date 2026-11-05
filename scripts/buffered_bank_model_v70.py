# SPDX-License-Identifier: GPL-3.0-only
"""Preserve actual bank RC and append a native standard-cell buffer prototype."""
from copy import deepcopy
import regenerated_bank_v56 as native_source
from build_compound_drivers_v3 import cell_definition

NAME='openlvds_dcdl_c16_f32_buffered_prototype_v70'
MODELS=dict(buf1='sky130_fd_sc_hd__buf_1',buf4='sky130_fd_sc_hd__buf_4')


def model(bank,components,profile):
    if profile not in MODELS:raise ValueError('Unknown native output-buffer prototype')
    defs=native_source.native.definitions(bank)
    if len(defs)!=1:raise ValueError('Require one actual flat joint-RC bank')
    top=next(iter(defs));ports=defs[top][0]
    if ports[:2]!=['IN','OUT'] or ports[-2:]!=['VPWR','VGND'] or 'fine_raw' in ports:
        raise ValueError('Actual bank public interface changed')
    cell=cell_definition(components,MODELS[profile])
    order=native_source.native.definitions(cell)[MODELS[profile]][0]
    if order!=['A','VGND','VNB','VPB','VPWR','X']:raise ValueError('Native output-buffer body/supply interface changed')
    return bank+'\n'+cell+'\n.subckt '+NAME+' '+' '.join(ports)+'\n'+\
        'Xbank '+' '.join('fine_raw' if p=='OUT' else p for p in ports)+' '+top+'\n'+\
        'Xoutput_buffer fine_raw VGND VGND VPWR VPWR OUT '+MODELS[profile]+'\n.ends '+NAME+'\n'


def observations(bank,original):
    ports=native_source.native.definitions(bank)[NAME][0]
    devices=native_source.native.mapped_mos(bank,NAME,{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports},'XD')
    def renamed(n):return 'XD:Xbank:'+n[3:] if n.startswith('XD:') else n
    gates=deepcopy(original['programming_gates']);controls=deepcopy(original['controls'])
    for g in gates:g['device']=renamed(g['device']);g['gate_node']=renamed(g['gate_node'])
    for c in controls:c['node']=renamed(c['node'])
    byname={d['name']:d for d in devices}
    if len(gates)!=133 or any(byname[g['device']]['terminals'][1]!=g['gate_node'] for g in gates):
        raise ValueError('Original native programming-gate mapping was not retained')
    if len([d for d in devices if d['name'].startswith('XD:Xbank:')])!=951:
        raise ValueError('Original actual native bank inventory changed')
    return dict(devices=devices,programming_gates=gates,controls=controls)
