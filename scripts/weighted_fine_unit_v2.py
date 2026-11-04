# SPDX-License-Identifier: GPL-3.0-only
"""Exact physical-cell schematics for the five unchanged root fine weights."""
import dcdl_weighted_fine_v2 as fine
from build_compound_drivers_v3 import cell_definition

PORTS=['NODE','EN','ENB','VDD','VSS']


def name(bit):
    if bit not in range(5):raise ValueError('Unknown weighted fine bit')
    return f'openlvds_weighted_fine_root_b{bit}_v2'


def schematic(bit):
    original=f'weighted_root_{bit}';text=cell_definition(fine.fine_cells('root'),original)
    return text.replace('.subckt '+original+' ','.subckt '+name(bit)+' ').replace('.ends '+original,'.ends '+name(bit))
