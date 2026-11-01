# SPDX-License-Identifier: GPL-3.0-only
"""One bounded steering-current correction for the extracted SF40 eye shortfall."""
from dll_campaign import text_block
from driver_restore_variant import source_variant as restored, TOP
from layout import circuits
from spice_library import replace

VARIANT = 'restore_64_24_current110'


def source_variant(source):
    source = restored(source)
    rows = {r[0]: r for r in circuits(source)[TOP][1]}
    fingers = {n for n in rows if n.startswith('XIT')}
    if fingers != {f'XIT{i}' for i in range(10)}:
        raise ValueError('Expected exactly ten original steering-current fingers')
    for name in fingers:
        if rows[name][1:] != (['TOP', 'PB', 'VDDIO', 'VDDIO'],
                'sky130_fd_pr__pfet_g5v0d10v5', dict(w='20', l='1')):
            raise ValueError('Original steering-current finger changed')
    block = text_block(source, TOP)
    # Retain the 35 uA reference and all existing devices. One additional
    # 20 um finger changes the ideal mirror ratio from 100:1 to 110:1.
    # Actual loaded current and all electrical limits still require testing.
    extra = 'XIT10 TOP PB VDDIO VDDIO sky130_fd_pr__pfet_g5v0d10v5 w=20 l=1\n'
    block = block.replace('.ends '+TOP, extra+'.ends '+TOP)
    block = block.replace('100:1 PMOS mirror establishes approximately 3.5 mA',
                          '110:1 PMOS mirror targets approximately 3.85 mA')
    return replace(source, TOP, block)
