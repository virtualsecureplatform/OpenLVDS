# SPDX-License-Identifier: GPL-3.0-only
"""Structural policy for the experimental internal-Q-reset pulse-area PFD."""
import re
from physical_policy import pfd_area_paths_retained


def pins(body):
    return dict(re.findall(r'\.(\w+)\s*\(\s*([^()\s]+)\s*\)', body))


def pfd_qreset_paths_retained(netlist):
    raw = []; data = []
    for name in ['ref_ff', 'fb_ff']:
        matches = list(re.finditer(r'\bsky130_fd_sc_hd__dfrtp_4\s+' + name + r'\s*\((.*?)\);', netlist, re.S))
        if len(matches) != 1:
            return False
        ff = pins(matches[0][1]); raw.append(ff.get('Q')); data.append(ff.get('D'))
    if None in raw or len(set(raw)) != 2 or set(raw) & {'UP', 'DN'}:
        return False
    constants = {pins(body).get('HI') for body in re.findall(
        r'\bsky130_fd_sc_hd__conb_1\s+[^\s(]+\s*\((.*?)\);', netlist, re.S)} - {None}
    if not all(node in constants for node in data):
        return False
    matches = list(re.finditer(r'\bsky130_fd_sc_hd__and2_4\s+coincidence\s*\((.*?)\);', netlist, re.S))
    if len(matches) != 1:
        return False
    both = matches[0]; inputs = pins(both[1])
    if {inputs.get('A'), inputs.get('B')} != set(raw):
        return False
    # After proving the new reset tap, reuse the existing checks for direct
    # clocks, output buffers, enable/reset wiring and forbidden clock-delay cells.
    checked = re.sub(r'\.A\s*\(\s*[^()]+\)', '.A(UP)', both[0])
    checked = re.sub(r'\.B\s*\(\s*[^()]+\)', '.B(DN)', checked)
    return pfd_area_paths_retained(netlist[:both.start()] + checked + netlist[both.end():])
