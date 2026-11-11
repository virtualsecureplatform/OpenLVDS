# SPDX-License-Identifier: GPL-3.0-only
"""Candidate explicit temperature factor for pinned ngspice-42 high-poly R.

Derive from the pinned Apache-2.0 PDK model at runtime, retaining its license,
all parameters, end resistance and substrate capacitors. Noise/mismatch are
not admitted by deterministic comparisons.
"""
import re
NAME='openlvds_res_high_po_0p35_compat_300_v1'


def adapt(original):
    old='sky130_fd_pr__res_high_po_0p35'
    if original.count('.subckt  '+old)!=1 or original.count('.ends '+old)!=1:
        raise ValueError('Pinned high-poly subcircuit changed')
    text=original.replace('.subckt  '+old,'.subckt '+NAME).replace('.ends '+old,'.ends '+NAME)
    pattern=r'(?m)^rhrpoly_0p35 ra r1 r = \{([^\n]+)\}\n\+ tc1 = 0\.514e-3\n\+ tc2 = 0\.122e-5$'
    matches=list(re.finditer(pattern,text))
    if len(matches)!=1:
        raise ValueError('Pinned high-poly body/temperature law changed')
    match=matches[0]
    replacement='BHR ra r1 I={V(ra,r1)/(('+match[1]+')*(1+0.514e-3*(temper-27)+0.122e-5*(temper-27)*(temper-27)))}'
    return text[:match.start()]+replacement+text[match.end():]
