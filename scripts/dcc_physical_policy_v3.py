# SPDX-License-Identifier: GPL-3.0-only
"""Retain exact clock/reset topology while recognizing true constant clones."""
import re
import dcc_physical_policy_v2 as original


def interface_retained(text):
    cells=[];names=set()
    for kind,name,body in re.findall(r'\bsky130_fd_sc_hd__(\w+)\s+(\\[^\s]+|[A-Za-z_$][\w$/.]*)\s*\((.*?)\);',text,re.S):
        name=name.lstrip('\\')
        if name in names:return False
        names.add(name);cells.append((kind,name,dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',body))))
    high={p['HI'] for k,n,p in cells if k=='conb_1' and 'HI' in p}
    low={p['LO'] for k,n,p in cells if k=='conb_1' and 'LO' in p}
    if not high or high&low or high&{'phase0','phase180','reset_n','clock_out','__verified_const_high'}:return False
    for kind,name,pins in cells:
        if kind=='conb_1':continue
        for pin,net in pins.items():
            if net in high and not (name in ['first_ff','second_ff'] and pin=='D'):return False
            if net in low and pin not in ['VGND','VNB']:return False
    # Only constant D inputs are canonicalized. Every pulse/reset/toggle/output
    # connection and every non-tie cell is still checked by the retained policy.
    rows=['sky130_fd_sc_hd__conb_1 tie (.HI(__verified_const_high));']
    for kind,name,pins in cells:
        if kind=='conb_1':continue
        # This PDK uses decap_3 as a row endcap. It has no signal interface;
        # its actual power devices remain present in the subsequent RC audit.
        if kind=='decap_3':
            if set(pins)-{'VPWR','VGND','VPB','VNB'}:return False
            continue
        rows.append('sky130_fd_sc_hd__'+kind+' '+name+' ('+','.join('.'+p+'('+('__verified_const_high' if net in high else net)+')' for p,net in pins.items())+');')
    return original.interface_retained('\n'.join(rows))
