# SPDX-License-Identifier: GPL-3.0-only
"""Guarded native readiness FFs followed by strong NAND2 phase storage.

Readiness rises after two clocks. A sticky arm sets during a subsequent low
phase, then a sticky public release sets on the following high phase. REQUEST
asynchronously clears the FFs and both sticky states. The reset feedback uses
NAND2(Q, REQUEST), eliminating the redundant VPWR input of the earlier NAND3.
Native FF source guards still require fresh physical RC qualification.
"""
from native_static_cells_v2 import inline
from dcc_nand_mid_shunt_v2 import devices
import native_clock_components_v3 as components

NAME='openlvds_guarded_phase_clock_release_v2'
PORTS=['CLK','REQUEST','PREPARE','RESET_N','VPWR','VGND']
CAP='sky130_fd_pr__cap_mim_m3_1'


def readiness():
    return [('r0','dfrtp_1',dict(CLK='CLK',D='REQUEST',RESET_B='REQUEST',Q='ready0')),
            ('r1','dfrtp_1',dict(CLK='CLK',D='ready0',RESET_B='REQUEST',Q='PREPARE'))]


def phase_gates():
    return [('arm_clock','inv_8',dict(A='CLK',Y='arm_clk_n')),
            ('arm_set','nand2_8',dict(A='PREPARE',B='arm_clk_n',Y='arm_sn')),
            ('arm_q','nand2_8',dict(A='arm_sn',B='arm_qb',Y='armed')),
            ('arm_b','nand2_8',dict(A='armed',B='REQUEST',Y='arm_qb')),
            ('release_set','nand2_8',dict(A='armed',B='CLK',Y='release_sn')),
            ('release_q','nand2_8',dict(A='release_sn',B='release_qb',Y='RESET_N')),
            ('release_b','nand2_8',dict(A='RESET_N',B='REQUEST',Y='release_qb'))]


def source(library,rc,guard_nodes,size):
    if size not in [1,2] or not guard_nodes or len(set(guard_nodes))!=len(guard_nodes):
        raise ValueError('Invalid private-guard experiment')
    body=inline(readiness(),library);nodes={n for d in devices(body) for n in d['nodes']}
    expected={tag+'__'+n for tag in ['r0','r1'] for n in guard_nodes}
    if not expected<=nodes:raise ValueError('Guard target is not an actual native FF private terminal')
    rows=['.subckt '+NAME+' '+' '.join(PORTS),body.rstrip()]
    rows += [f'XGUARD{i} {node} VGND {CAP} w={size} l={size}' for i,node in enumerate(sorted(expected))]
    rows += [components.instance(tag,components.MODELS[model],dict(pins,VPWR='VPWR',VGND='VGND'),rc)
             for tag,model,pins in phase_gates()]
    return '\n'.join(rows+['.ends '+NAME,''])
