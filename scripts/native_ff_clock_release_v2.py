# SPDX-License-Identifier: GPL-3.0-only
"""Native asynchronous-clear FF readiness chain with a real RC output buffer.

FF transistors are unmodified source cells; their physical RC and private-node
stress remain qualification gates. This is not the former continuously toggled
FF/XNOR DCC: both readiness data states saturate after two clock edges.
"""
from native_static_cells_v2 import inline
import native_clock_components_v3 as components

NAME='openlvds_clock_release_native_ff_v2'
PORTS=['CLK','REQUEST','RESET_N','VPWR','VGND']


def gates(drive):
    if drive not in [1,2]:raise ValueError('Unknown native readiness FF drive')
    return [('r0','dfrtp_'+str(drive),dict(CLK='CLK',D='REQUEST',RESET_B='REQUEST',Q='ready0')),
            ('r1','dfrtp_'+str(drive),dict(CLK='CLK',D='ready0',RESET_B='REQUEST',Q='ready1'))]


def source(drive,library,rc):
    body=inline(gates(drive),library)
    buffer=components.base.instance('ready_buffer',components.CLOCK_BUFFER,
        dict(A='ready1',X='RESET_N',VPWR='VPWR',VGND='VGND'),rc)
    return '\n'.join(['.subckt '+NAME+' '+' '.join(PORTS),body.rstrip(),buffer,'.ends '+NAME,''])
