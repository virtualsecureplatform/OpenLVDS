# SPDX-License-Identifier: GPL-3.0-only
"""Redistribute fixed total gate width in the driver's 3.3 V restoration buffers."""
from dll_campaign import text_block
from layout import circuits
from spice_library import replace

TOP = 'openlvds_driver_core'


def source_variant(source, modified=True):
    if not modified:
        return source
    definitions = circuits(source)
    private = 'lvds_inv33_restore_64_24'
    shift = 'lvds_shift18_33_restore_64_24'
    if private in definitions or shift in definitions:
        raise ValueError('Driver restoration variant already exists')
    expected = [('XP', ['Y', 'A', 'VDD', 'VDD'], 'sky130_fd_pr__pfet_g5v0d10v5', dict(w='48', l='0.5')),
                ('XN', ['Y', 'A', 'VSS', 'VSS'], 'sky130_fd_pr__nfet_g5v0d10v5', dict(w='40', l='0.5'))]
    if definitions['lvds_inv33'] != (['A', 'Y', 'VDD', 'VSS'], expected):
        raise ValueError('Unexpected original 3.3 V restoration helper')
    helper = text_block(source, 'lvds_inv33').replace('lvds_inv33', private)
    helper = helper.replace('w=48 l=0.5', 'w=64 l=0.5').replace('w=40 l=0.5', 'w=24 l=0.5')
    block = text_block(source, 'lvds_shift18_33')
    rows = {row[0]: row for row in definitions['lvds_shift18_33'][1]}
    for name, nodes in [('XB0', ['L', 'Q', 'VDDIO', 'VSS']), ('XB1', ['R', 'QB', 'VDDIO', 'VSS'])]:
        if rows[name][1:] != (nodes, 'lvds_inv33', {}):
            raise ValueError('Unexpected level-converter restoration binding')
        old = name + ' ' + ' '.join(nodes) + ' lvds_inv33'
        if block.count(old) != 1:
            raise ValueError('Ambiguous level-converter restoration instance')
        block = block.replace(old, old.rsplit(' ', 1)[0] + ' ' + private)
    block = block.replace('lvds_shift18_33', shift)
    driver = text_block(source, TOP)
    rows = {row[0]: row for row in definitions[TOP][1]}
    if rows['XLS'][1:] != (['D', 'DP', 'DN', 'NB', 'VDDIO', 'VDDD', 'VSS'], 'lvds_shift18_33', {}):
        raise ValueError('Unexpected driver level-converter binding')
    old = 'XLS D DP DN NB VDDIO VDDD VSS lvds_shift18_33'
    if driver.count(old) != 1:
        raise ValueError('Ambiguous driver level-converter instance')
    driver = driver.replace(old, old.rsplit(' ', 1)[0] + ' ' + shift)
    return replace(source, TOP, driver) + '\n' + helper + '\n' + block + '\n'
