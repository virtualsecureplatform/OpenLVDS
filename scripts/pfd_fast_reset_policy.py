# SPDX-License-Identifier: GPL-3.0-only
"""Require the single-AOI reset path in the experimental pulse-area PFD."""
import re
from physical_policy import delay_cells_absent


def pins(body):
    return dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)', body))


def cell(netlist, kind, name):
    matches = list(re.finditer(r'\bsky130_fd_sc_hd__' + kind + r'\s+' + name + r'\s*\((.*?)\);', netlist, re.S))
    return pins(matches[0][1]) if len(matches) == 1 else {}


def pfd_fast_reset_paths_retained(netlist):
    header = re.search(r'\bmodule\s+lvds_pfd\s*\((.*?)\);', netlist, re.S)
    if not header or re.search(r'\b(ERR|QREF|QFB|QWIN)\b', header[1]):
        return False
    ports = ['REF', 'FB', 'RESET_N', 'PD_ENABLE', 'UP', 'DN']
    if not all(re.search(r'\b' + p + r'\b', header[1]) for p in ports):
        return False
    high = {pins(body).get('HI') for body in re.findall(
        r'\bsky130_fd_sc_hd__conb_1\s+[^\s(]+\s*\((.*?)\);', netlist, re.S)} - {None}
    raw = []; resets = []
    for name, clock, driver, out in [('ref_ff', 'REF', 'up_drive', 'UP'), ('fb_ff', 'FB', 'dn_drive', 'DN')]:
        ff = cell(netlist, 'dfrtp_4', name); buf = cell(netlist, 'buf_8', driver)
        if not ff or not buf or ff.get('CLK') != clock or ff.get('D') not in high:
            return False
        if not ff.get('Q') or buf.get('A') != ff['Q'] or buf.get('X') != out:
            return False
        raw.append(ff['Q']); resets.append(ff.get('RESET_B'))
    if len(set(raw)) != 2 or set(raw) & set(ports):
        return False
    disable = cell(netlist, 'nand2_1', 'reset_disable'); clear = cell(netlist, 'a22oi_4', 'clear')
    if not disable.get('Y') or {disable.get('A'), disable.get('B')} != {'RESET_N', 'PD_ENABLE'}:
        return False
    if {clear.get('A1'), clear.get('A2')} != set(raw) or clear.get('B1') != disable['Y']:
        return False
    if clear.get('B2') not in high or not clear.get('Y') or resets != [clear['Y'], clear['Y']]:
        return False
    if clear['Y'] in set(raw) | set(ports) | high or disable['Y'] == clear['Y']:
        return False
    return delay_cells_absent(netlist) and not re.search(r'\bqual_\w+', netlist)
