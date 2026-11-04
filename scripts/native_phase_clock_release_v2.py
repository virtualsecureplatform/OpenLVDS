# SPDX-License-Identifier: GPL-3.0-only
"""Two-clock readiness followed by low-phase arm and sticky PH0 release.

The native readiness registers remain asynchronously clearable. Added static
NAND storage arms while CLK is low and holds release after a subsequent high
phase; REQUEST clears both added states even with a stopped clock. Actual RC
setup/hold, release latency and first DCC event remain simulation requirements.
"""
import native_clock_release_v3 as previous

NAME='openlvds_clock_release_phase_armed_v2'
PORTS=previous.PORTS


def phase_gates():
    return [
        ('arm_clock','inv_8',dict(A='CLK',Y='arm_clk_n')),
        ('arm_set','nand3_2',dict(A='r1_q',B='arm_clk_n',C='REQUEST',Y='arm_sn')),
        ('arm_q','nand2_4',dict(A='arm_sn',B='arm_qb',Y='armed')),
        ('arm_b','nand3_2',dict(A='armed',B='VPWR',C='REQUEST',Y='arm_qb')),
        ('release_set','nand3_2',dict(A='armed',B='CLK',C='REQUEST',Y='release_sn')),
        ('release_q','nand2_8',dict(A='release_sn',B='release_qb',Y='RESET_N')),
        ('release_b','nand3_2',dict(A='RESET_N',B='VPWR',C='REQUEST',Y='release_qb')),
    ]


def gates():
    cells=[(tag,{'nand2_2':'nand2_4','inv_1':'inv_8'}.get(model,model),pins)
           for tag,model,pins in previous.gates() if tag not in ['qualify','output']]
    return cells+phase_gates()
