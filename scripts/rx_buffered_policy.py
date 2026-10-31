# SPDX-License-Identifier: GPL-3.0-only
"""Retain explicit RX public drivers without changing sampler clock topology."""
import re
from physical_policy import delay_cells_absent


def retained(text):
    cells={name:(kind,dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',body)))
        for kind,name,body in re.findall(r'\bsky130_fd_sc_hd__(\w+)\s+([^\s(]+)\s*\((.*?)\);',text,re.S)}
    for name,kind,output in [('data0_drive','buf_4','data[0]'),('data1_drive','buf_4','data[1]'),('valid_drive','buf_1','valid')]:
        cell,pins=cells.get(name,(None,{}))
        if cell!=kind or pins.get('X')!=output or not pins.get('A') or pins['A']==output:return False
        if sum(v.get('X')==output or v.get('Q')==output or v.get('Y')==output for _,v in cells.values())!=1:return False
    inv,ip=cells.get('falling_clock',(None,{}));ff,fp=cells.get('falling_sample',(None,{}))
    if inv!='inv_1' or ip.get('A')!='clk' or ff!='dfrtp_1' or fp.get('CLK')!=ip.get('Y'):return False
    return fp.get('D')=='serial' and fp.get('RESET_B')=='reset_n' and delay_cells_absent(text)
