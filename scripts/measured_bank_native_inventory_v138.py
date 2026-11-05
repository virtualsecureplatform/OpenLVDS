# SPDX-License-Identifier: GPL-3.0-only
"""Strict native census and device-parameter gate for the measured balanced bank.

Connectivity needs independent native LVS; this gate never substitutes for it.
"""
from collections import Counter
import native_bank_inventory_v51 as native


def verify(reference,reference_top,extracted,extracted_top,profile):
    if profile not in ('b2','b3'):raise ValueError('Unknown measured balanced profile')
    expected_ports,expected=native.native_leaves(reference,reference_top)
    actual_ports,actual=native.native_leaves(extracted,extracted_top)
    if expected_ports!=actual_ports:raise ValueError('Native extracted public port order differs')
    wanted=(1133+320*(int(profile[1])-1),42)
    def census(devices):
        counts=Counter(d['model'] for d in devices)
        if any('fet_' not in m and 'cap_mim' not in m for m in counts):raise ValueError('Unexpected native bank primitive')
        return sum(n for m,n in counts.items() if 'fet_' in m),sum(n for m,n in counts.items() if 'cap_mim' in m)
    if census(expected)!=wanted or census(actual)!=wanted:raise ValueError('Measured balanced native MOS/MIM census differs')
    parameters=native.compare_parameters(expected,actual)
    return dict(parameters,native_mos=wanted[0],native_mims=wanted[1],exact_public_port_order_preserved=True,
                connectivity_requires_native_lvs=True,joint_rc_extracted=False,qualified_phy=False)
