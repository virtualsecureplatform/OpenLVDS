# SPDX-License-Identifier: GPL-3.0-only
"""One physical output for two native XNORs with opposite input assignments."""
import dcdl_mim_bank_v2 as native

NAME='openlvds_xnor2_2_balanced_v2'
MODEL=native.SC+'xnor2_2'
COMPOUNDS={MODEL:NAME}
SIGNALS={MODEL:(['A','B'],'Y')}


def swapped_pin(copy,pin):
    if copy not in [0,1] or pin not in ['A','B','Y','VPWR','VGND','VPB','VNB']:
        raise ValueError('Unknown balanced-XNOR copy/pin')
    return {'A':'B','B':'A'}.get(pin,pin) if copy==1 else pin
