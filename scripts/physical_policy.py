# SPDX-License-Identifier: GPL-3.0-only
"""Physical clock and pulse paths must retain the intended detector interface."""
import re


def delay_cells_absent(netlist):
    return not re.search(r'\bsky130_fd_sc_hd__clkdlybuf\w*\b',netlist)


def pfd_ports_direct(netlist):
    for instance,clock,output in [('ref_ff','REF','UP'),('fb_ff','FB','DN')]:
        match=re.search(r'\bsky130_fd_sc_hd__dfrtp_4\s+'+instance+r'\s*\((.*?)\);',netlist,re.S)
        if not match:return False
        pins=dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)',match[1]))
        if pins.get('CLK')!=clock or pins.get('Q')!=output:return False
    return True
