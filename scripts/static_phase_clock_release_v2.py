# SPDX-License-Identifier: GPL-3.0-only
"""Alternating sticky phases using only existing native passive-RC macros.

After REQUEST: low0 -> high1 -> low1 -> high2 -> low2 -> public high3.
The initial low state prevents a request asserted in a high phase from counting
that partial phase. PREPARE is high2 and armed is low2. All sticky feedback
resets from the same buffered REQUEST, including when CLK stops. Actual
transition ordering, reset dominance/settling and voltage require simulation.
"""
import native_clock_components_v3 as components
NAND2B='openlvds_nand2b_4_pair_v2'

NAME='openlvds_static_phase_clock_release_v2'
PORTS=['CLK','REQUEST','PREPARE','RESET_N','VPWR','VGND']
STAGES=[('low0','request_i',False,'low0'),('high1','low0',True,'high1'),
        ('low1','high1',False,'low1'),('high2','low1',True,'PREPARE'),
        ('low2','PREPARE',False,'armed'),('release','armed',True,'RESET_N')]


def source(rc,drive):
    if drive not in [4,8]:raise ValueError('Unknown static-phase storage drive')
    nand=components.MODELS['nand2_'+str(drive)]
    rows=['.subckt '+NAME+' '+' '.join(PORTS),
          components.instance('request_driver',components.CLOCK_BUFFER,
              dict(A='REQUEST',X='request_i',VPWR='VPWR',VGND='VGND'),rc)]
    def add(tag,model,**pins):
        rows.append(components.instance(tag,model,dict(pins,VPWR='VPWR',VGND='VGND'),rc))
    for tag,prior,high,out in STAGES:
        setter=components.MODELS['nand2_8'] if tag=='release' else nand
        if high:add(tag+'_set',setter,A=prior,B='CLK',Y=tag+'_sn')
        else:add(tag+'_set',NAND2B,A_N='CLK',B=prior,Y=tag+'_sn')
        add(tag+'_q',components.MODELS['nand2_8'] if tag=='release' else nand,
            A=tag+'_sn',B=tag+'_qb',Y=out)
        add(tag+'_b',nand,A=out,B='request_i',Y=tag+'_qb')
    return '\n'.join(rows+['.ends '+NAME,''])
