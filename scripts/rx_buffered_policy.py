# SPDX-License-Identifier: GPL-3.0-only
"""Retain explicit RX public drivers without changing sampler clock topology."""
import re
from physical_policy import delay_cells_absent


def policy_parameters(label):
    policies={'half-cycle-publish-buf4':dict(strength=4,early_publish=True),
              'public-data-buf4':dict(strength=4,publication4=False),
              'public-data-buf8-publish4':dict(strength=8,publication4=True),
              'public-data-buf8-publish1':dict(strength=8,publication4=False,publication1=True)}
    if label not in policies:raise ValueError('Unknown RX topology policy')
    return policies[label]


def retained(text,strength=4,publication4=False,publication1=False,early_publish=False):
    if early_publish and (strength!=4 or publication4 or publication1):return False
    if (strength,publication4,publication1) not in [(4,False,False),(8,True,False),(8,False,True)]:return False
    cells={name:(kind,dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',body)))
        for kind,name,body in re.findall(r'\bsky130_fd_sc_hd__(\w+)\s+([^\s(]+)\s*\((.*?)\);',text,re.S)}
    for name,kind,output in [('data0_drive',f'buf_{strength}','data[0]'),('data1_drive',f'buf_{strength}','data[1]'),('valid_drive','buf_4' if early_publish else 'buf_1','valid')]:
        cell,pins=cells.get(name,(None,{}))
        if cell!=kind or pins.get('X')!=output or not pins.get('A') or pins['A']==output:return False
        if sum(v.get('X')==output or v.get('Q')==output or v.get('Y')==output for _,v in cells.values())!=1:return False
    if not (publication4 or publication1) and any(n in cells for n in ['data0_publish','data1_publish']):return False
    if publication4 or publication1:
        publication_strength=4 if publication4 else 1
        outputs=[]
        for index in [0,1]:
            cell,pins=cells.get(f'data{index}_publish',(None,{}))
            driver=cells[f'data{index}_drive'][1]
            if (cell!=f'dfrtp_{publication_strength}' or pins.get('CLK')!='clk' or pins.get('RESET_B')!='reset_n' or
                not pins.get('D') or pins['D']==pins.get('Q') or pins.get('Q')!=driver['A']):return False
            outputs.append(pins.get('Q'))
        if len(set(outputs))!=2:return False
    inv,ip=cells.get('falling_clock',(None,{}));ff,fp=cells.get('falling_sample',(None,{}))
    if inv!=('inv_4' if early_publish else 'inv_1') or ip.get('A')!='clk' or ff!='dfrtp_1' or fp.get('CLK')!=ip.get('Y'):return False
    if fp.get('D')!='serial' or fp.get('RESET_B')!='reset_n' or not delay_cells_absent(text):return False
    if not early_publish:return True
    def ff(name,clock):
        kind,pins=cells.get(name,(None,{}))
        return pins if kind=='dfrtp_1' and pins.get('CLK')==clock and pins.get('RESET_B')=='reset_n' and pins.get('D') and pins.get('Q') else None
    rise=ff('rising_sample','clk');start=ff('pair_start','clk')
    held=ff('held_rise',ip.get('Y'));valid=ff('valid_sample',ip.get('Y'))
    if not all([rise,start,held,valid]) or rise['D']!='serial':return False
    run=start['D']
    for name,sample,target in [('rise_enable',rise['Q'],held['D']),
            ('fall_enable',fp['Q'],cells['data1_drive'][1]['A']),
            ('valid_enable',start['Q'],valid['D'])]:
        kind,pins=cells.get(name,(None,{}))
        if kind!='and2_1' or {pins.get('A'),pins.get('B')}!={sample,run} or pins.get('X')!=target:return False
    return (held['Q']==cells['data0_drive'][1]['A'] and valid['Q']==cells['valid_drive'][1]['A'] and
            len({rise['Q'],fp['Q'],held['Q'],valid['Q'],start['Q']})==5)
