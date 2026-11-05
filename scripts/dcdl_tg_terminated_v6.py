# SPDX-License-Identifier: GPL-3.0-only
"""Terminate the retained TG bank's otherwise unloaded balancing output.

Only one native 2x2 MIM is added. All active devices, data/control connections,
and the complete declared tap/fine topology remain those of double_direct v5.
New physical termination geometry and full native qualification remain open.
"""
import dcdl_tg_tree_v5 as previous

VERSION = 'native-double-tg-direct-bank-real-tail-mim-termination-v6.1'
PROFILE = 'double_direct'
CAP = 'sky130_fd_pr__cap_mim_m3_1'
WIDTH = LENGTH = 2


def name(coarse=16, fine_count=32):
    return previous.name(PROFILE, coarse, fine_count).removesuffix('_v5')+'_terminated_v6'


def instances(coarse=16, fine_count=32):
    return previous.instances(PROFILE, coarse, fine_count)+[
        dict(name='tail_termination', model=CAP, pins=dict(TOP='unused_tail', BOTTOM='VGND'),
             parameters=dict(w=WIDTH, l=LENGTH))]


def source(orders, coarse=16, fine_count=32):
    old = previous.source(orders, PROFILE, coarse, fine_count)
    old_name = previous.name(PROFILE, coarse, fine_count)
    new_name = name(coarse, fine_count)
    header = '.subckt '+old_name+' '
    ending = '.ends '+old_name+'\n'
    if not old.startswith(header) or old.count(ending) != 1 or not old.endswith(ending):
        raise ValueError('Retained native TG source changed')
    body = old[len(header): -len(ending)]
    return ('.subckt '+new_name+' '+body+
            f'Xtail_termination unused_tail VGND {CAP} w={WIDTH} l={LENGTH}\n'
            '.ends '+new_name+'\n')
