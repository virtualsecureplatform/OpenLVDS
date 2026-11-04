# SPDX-License-Identifier: GPL-3.0-only
"""Isolate five real weighted fine loads and compare native control drivers."""
import dcdl_weighted_fine_v2 as fine
import native_clock_components_v3 as native

NAME='openlvds_weighted_fine_control_v2'
PORTS=['DATA',*[f'B{i}' for i in range(5)],*[n+str(i) for i in range(5) for n in ['EN','ENB']],'VDD','VSS']
MODES=['guarded','source']


def source(mode,orders):
    if mode not in MODES:raise ValueError('Unknown fine-control driver candidate')
    rows=[fine.fine_cells('root').rstrip(),'.subckt '+NAME+' '+' '.join(PORTS)]
    pg=dict(VPWR='VDD',VPB='VDD',VGND='VSS',VNB='VSS')
    for bit in range(5):
        buf=native.CLOCK_BUFFER if mode=='guarded' else fine.old.native.SC+'buf_1'
        inv=native.MODELS['inv_8'] if mode=='guarded' else fine.old.native.SC+'inv_1'
        for tag,model,pins in [('buffer',buf,dict(A=f'B{bit}',X=f'EN{bit}')),('inverse',inv,dict(A=f'EN{bit}',Y=f'ENB{bit}'))]:
            pins=dict(pg,**pins)
            if model not in orders or not set(orders[model])<=set(pins):raise ValueError('Missing actual native control port order')
            rows.append('X'+tag+str(bit)+' '+' '.join(pins[p] for p in orders[model])+' '+model)
        rows.append(f'Xfine{bit} DATA EN{bit} ENB{bit} VDD VSS weighted_root_{bit}')
    return '\n'.join(rows+['.ends '+NAME,''])


def devices(text):
    return native.mapped_mos(text,NAME,{p:'0' if p=='VSS' else p for p in PORTS},'XD')
