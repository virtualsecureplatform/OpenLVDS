# SPDX-License-Identifier: GPL-3.0-only
"""Strict 1453-MOS/40-MIM census for the output-only b2 revision."""
from collections import Counter
import native_bank_inventory_v51 as native


def verify(reference,reference_top,extracted,extracted_top,profile):
    if profile!='b2':raise ValueError('Only the qualified output-only b2 revision is supported')
    a,expected=native.native_leaves(reference,reference_top);b,actual=native.native_leaves(extracted,extracted_top)
    if a!=b:raise ValueError('Native extracted public port order differs')
    for devices in (expected,actual):
        counts=Counter(d['model'] for d in devices)
        if (any('fet_' not in m and m!='sky130_fd_pr__cap_mim_m3_1' for m in counts)
            or sum(n for m,n in counts.items() if 'fet_' in m)!=1453
            or counts['sky130_fd_pr__cap_mim_m3_1']!=40):raise ValueError('Unguarded b2 native MOS/MIM census differs')
    parameters=native.compare_parameters(expected,actual)
    return dict(parameters,native_mos=1453,native_mims=40,exact_public_port_order_preserved=True,
                connectivity_requires_native_lvs=True,joint_rc_extracted=False,qualified_phy=False)


def metadata(source):
    """Derive actual observation metadata from unchanged placement coordinates."""
    import copy
    import unguarded_bank_variant_v164 as variant
    result=copy.deepcopy(source)
    for key in ('graph','plan'):
        result[key]=copy.deepcopy(source[key])
        cells=result[key]['cells'];selected=[c for c in cells if c['name']=='u_fine_compound']
        if len(selected)!=1 or selected[0]['model']!=variant.PAIR:
            raise ValueError('Require exactly the original final-output metadata')
        selected[0]['model']=variant.NEW_PAIR
    orders=result['graph'].get('orders',{})
    if variant.PAIR in orders:orders[variant.NEW_PAIR]=copy.deepcopy(orders[variant.PAIR])
    if result['graph']['top']!=variant.NEW_TOP:raise ValueError('Require revised whole-bank top')
    return result
