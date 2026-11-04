# SPDX-License-Identifier: GPL-3.0-only
"""Bounded custom fine bank: transmission-gate switched native MIM units.

Off capacitors discharge through a small NMOS. This removes floating-node
history and most of the always-connected input-gate loading of einvp loads.
No analog control voltage, supply sweep, or ideal timing element is introduced.
"""
import re
import probe_digital_dcdl_v2 as original

VERSION='dcdl-mos-switched-mim-bank-v2.1'
VARIANTS={'mim2x2':(2.,2.),'mim2x3':(2.,3.)}
N='sky130_fd_pr__nfet_01v8'
P='sky130_fd_pr__pfet_01v8'
CAP='sky130_fd_pr__cap_mim_m3_1'


def circuit(variant,coarse,fine,coarse_count=16,fine_count=32):
    if variant not in VARIANTS:raise ValueError('Undeclared fine-bank geometry')
    text=original.circuit(coarse_count,fine_count,coarse,fine)
    text,count=re.subn(r'(?m)^Xload\d+[^\n]*\n','',text)
    if count!=fine_count-1:raise ValueError('Original fine bank changed')
    w,l=VARIANTS[variant];lines=[];devices=[]
    for i in range(fine_count-1):
        enabled=i<fine;en='VDD' if enabled else 'VSS';enb='VSS' if enabled else 'VDD';node=f'cap{i}'
        entries=[(f'XSWN{i}',['r0',en,node,'VSS'],N,.42),
                 (f'XSWP{i}',[node,enb,'r0','VDD'],P,.84),
                 (f'XCLR{i}',[node,enb,'VSS','VSS'],N,.42)]
        for name,terminals,model,width in entries:
            lines.append(f'{name} '+ ' '.join(terminals)+f' {model} w={width:g} l=0.15')
            devices.append(dict(name=name,terminals=terminals,model=model,width_um=width,length_um=.15))
        lines.append(f'XC{i} {node} VSS {CAP} w={w:g} l={l:g}')
    text=text.replace('.ends dcdl_source','\n'.join(lines)+'\n.ends dcdl_source')
    return text,devices
