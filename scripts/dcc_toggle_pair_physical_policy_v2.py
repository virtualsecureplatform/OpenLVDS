# SPDX-License-Identifier: GPL-3.0-only
"""Check both reset-qualified toggle loops and their exact XNOR output."""
import re


def interface_retained(text):
    text=re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)
    cells={}
    for kind,name,body in re.findall(r'\bsky130_fd_sc_hd__(\w+)\s+(\\[^\s]+|[A-Za-z_$][\w$/.]*)\s*\((.*?)\);',text,re.S):
        name=name.lstrip('\\')
        if name in cells:return False
        pairs=re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',body)
        if len(dict(pairs))!=len(pairs):return False
        pins=dict(pairs)
        for p,n in pins.items():
            if p in ['VPWR','VPB'] and n!='VPWR':return False
            if p in ['VGND','VNB'] and n!='VGND':return False
        pins={p:n for p,n in pins.items() if p not in ['VPWR','VPB','VGND','VNB']}
        if kind=='decap_3' or re.fullmatch(r'(fill|tapvpwrvgnd)_\w+',kind):
            if pins:return False
            continue
        cells[name]=(kind,pins)
    if set(cells)!={'first_feedback','second_feedback','first_ff','second_ff','combine'}:return False
    outputs=[]
    for prefix,clock in [('first','phase0'),('second','phase180')]:
        kind,ff=cells[prefix+'_ff'];gkind,feedback=cells[prefix+'_feedback']
        if (kind!='dfrtp_2' or gkind!='and2b_1' or set(ff)!={'CLK','D','RESET_B','Q'}
            or set(feedback)!={'A_N','B','X'} or ff['CLK']!=clock or ff['RESET_B']!='reset_n'
            or feedback['B']!='reset_n' or feedback['A_N']!=ff['Q'] or feedback['X']!=ff['D']):return False
        outputs.append(ff['Q'])
    kind,combine=cells['combine']
    nets=[cells['first_ff'][1]['Q'],cells['second_ff'][1]['Q'],cells['first_ff'][1]['D'],cells['second_ff'][1]['D']]
    return (kind=='xnor2_4' and combine==dict(A=outputs[0],B=outputs[1],Y='clock_out') and len(set(nets))==4
        and not set(nets)&{'phase0','phase180','reset_n','clock_out','VPWR','VGND'})
