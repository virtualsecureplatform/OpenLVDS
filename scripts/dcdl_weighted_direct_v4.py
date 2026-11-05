# SPDX-License-Identifier: GPL-3.0-only
"""Unchanged full bank topology selecting repaired fine and wide-power pair RC."""
import dcdl_weighted_direct_v3 as previous
NAME='openlvds_dcdl_weighted_direct_v4'
PORTS=previous.PORTS
MODES=previous.MODES
direct=previous.direct
weighted=previous.weighted
parsing=previous.parsing
controls=previous.controls
pair=previous.pair
GUARD=previous.GUARD
core_instances=previous.core_instances


def source(mode,orders):
    text=previous.source(mode,orders)
    if text.count(previous.NAME)!=2:raise ValueError('Unexpected full-bank top identity')
    return text.replace(previous.NAME,NAME)


def devices(text):
    header='.subckt '+NAME+' ';end='.ends '+NAME
    if text.count(header)!=1 or text.count(end)!=1:raise ValueError('Missing/duplicate repaired bank')
    return previous.devices(text.replace(header,'.subckt '+previous.NAME+' ').replace(end,'.ends '+previous.NAME))
