# SPDX-License-Identifier: GPL-3.0-only
"""Candidate signed-cubic compatibility for the pinned high-poly model.

Retain original PDK license, parameters, resistors, temperature coefficients
and substrate capacitors. Expand a potentially negative integer cube explicitly
instead of relying on engine-specific POW semantics. Deterministic pilot only.
"""
NAME='openlvds_res_high_po_0p35_compat_300_v2'


def adapt(original):
    old='sky130_fd_pr__res_high_po_0p35'
    if original.count('.subckt  '+old)!=1 or original.count('.ends '+old)!=1:
        raise ValueError('Pinned high-poly subcircuit changed')
    text=original.replace('.subckt  '+old,'.subckt '+NAME).replace('.ends '+old,'.ends '+NAME)
    base='min(abs(v(r0,r1))-1.7,0.3)'
    cube='pow('+base+',3)'
    if text.count(cube)!=1:
        raise ValueError('Pinned potentially negative cubic changed')
    return text.replace(cube,'('+base+'*'+base+'*'+base+')')
