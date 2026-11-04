# SPDX-License-Identifier: GPL-3.0-only
"""Shorten low-phase arming using the actual compound NAND2B4-pair RC.

Replace the separate shunted clock inverter and arm setter with the native
inverting-input NAND. Keep buffered REQUEST, all native FF guards, both sticky
feedback paths and the public release setter/output unchanged. Component RC is
real; guarded FF and whole-controller interconnect RC still need qualification.
"""
import guarded_phase_clock_release_v3 as previous

components=previous.components
PORTS=previous.PORTS
NAME='openlvds_nand2b_buffered_phase_release_v2'
NAND2B='openlvds_nand2b_4_pair_v2'


def source(library,rc,guard_nodes,size):
    old=previous.source(library,rc,guard_nodes,size).splitlines()
    removed=[row for row in old[1:-1] if row.split()[0] in ['Xarm_clock','Xarm_set']]
    if len(removed)!=2:raise ValueError('Require exact previous clock inverter and arm setter')
    body=[row for row in old[1:-1] if row not in removed]
    if any('arm_clk_n' in row.split() for row in body):raise ValueError('Old arm-clock load remains')
    setter=components.instance('arm_set',NAND2B,
        dict(A_N='CLK',B='PREPARE',Y='arm_sn',VPWR='VPWR',VGND='VGND'),rc)
    return '\n'.join(['.subckt '+NAME+' '+' '.join(PORTS),*body,setter,'.ends '+NAME,''])
