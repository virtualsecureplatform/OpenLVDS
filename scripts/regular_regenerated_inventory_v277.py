# SPDX-License-Identifier: GPL-3.0-only
"""Strict 1529-MOS/43-MIM census for the native isolated fine-stage bank."""
from collections import Counter
import native_bank_inventory_v51 as native


def verify(reference,reference_top,extracted,extracted_top):
    a,expected=native.native_leaves(reference,reference_top);b,actual=native.native_leaves(extracted,extracted_top)
    if a!=b:raise ValueError('Native extracted public port order differs')
    for devices in (expected,actual):
        counts=Counter(d['model'] for d in devices)
        if (any('fet_' not in m and m!='sky130_fd_pr__cap_mim_m3_1' for m in counts)
            or sum(n for m,n in counts.items() if 'fet_' in m)!=1529
            or counts['sky130_fd_pr__cap_mim_m3_1']!=43):raise ValueError('Isolated fine-stage native MOS/MIM census differs')
    parameters=native.compare_parameters(expected,actual)
    return dict(parameters,native_mos=1529,native_mims=43,exact_public_port_order_preserved=True,
                connectivity_requires_native_lvs=True,joint_rc_extracted=False,qualified_phy=False)
