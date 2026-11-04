# SPDX-License-Identifier: GPL-3.0-only
"""Reset-qualified static NAND master/slave toggles and symmetric NAND XOR.

Synchronous internal initialization requires raw clocks while reset is LOW.
The final NAND holds the public output HIGH throughout reset. This candidate
uses only native static NAND/inverter cells, with every transistor unchanged.
Paired XOR NANDs require real single-output compound macros before PNR.
"""
from build_compound_drivers_v3 import cell_definition

NAME='openlvds_dcc_nand_latch_v2'
PORTS=['VGND','VPWR','clock_out','phase0','phase180','reset_n']


def gates(drive):
    if drive not in [1,2]:raise ValueError('Undeclared static-latch drive')
    cells=[]
    def nand(n,a,b,y,level=drive):cells.append((n,'nand2_'+str(level),dict(A=a,B=b,Y=y)))
    def inv(n,a,y):cells.append((n,'inv_1',dict(A=a,Y=y)))
    for tag,phase in [('a','phase0'),('b','phase180')]:
        # D = RESET_N & Q_B. Both latches receive valid complementary data;
        # reset initializes them through clock edges, not an async FF pin.
        nand(tag+'_data_n','reset_n',tag+'_qb',tag+'_dn')
        inv(tag+'_data',tag+'_dn',tag+'_d')
        inv(tag+'_clock',phase,tag+'_clk_n')
        nand(tag+'_master_s',tag+'_d',tag+'_clk_n',tag+'_ms')
        nand(tag+'_master_r',tag+'_dn',tag+'_clk_n',tag+'_mr')
        nand(tag+'_master_q',tag+'_ms',tag+'_mb',tag+'_m')
        nand(tag+'_master_b',tag+'_mr',tag+'_m',tag+'_mb')
        nand(tag+'_slave_s',tag+'_m',phase,tag+'_ss')
        nand(tag+'_slave_r',tag+'_mb',phase,tag+'_sr')
        nand(tag+'_slave_q',tag+'_ss',tag+'_qb',tag)
        nand(tag+'_slave_b',tag+'_sr',tag,tag+'_qb')
    def symmetric(n,a,b,y):
        nand(n+'_0',a,b,y,1);nand(n+'_1',b,a,y,1)
    symmetric('xor_n','a','b','xor_n')
    symmetric('xor_a','a','xor_n','xor_a')
    symmetric('xor_b','b','xor_n','xor_b')
    symmetric('xor_out','xor_a','xor_b','xor_out')
    nand('output_reset','reset_n','xor_out','clock_out',8)
    return cells


def source(drive,library):
    cells=gates(drive);definitions={}
    for short in sorted({short for _,short,_ in cells}):
        model='sky130_fd_sc_hd__'+short;block=cell_definition(library,model)
        definitions[short]=(block.splitlines()[0].split()[2:],block.splitlines()[1:-1])
    lines=['.subckt '+NAME+' '+' '.join(PORTS)]
    for tag,short,pins in cells:
        ports,body=definitions[short]
        pins=dict(VGND='VGND',VNB='VGND',VPWR='VPWR',VPB='VPWR',**pins)
        if set(pins)!=set(ports):raise ValueError('Native NAND/inverter interface changed')
        for line in body:
            words=line.split()
            if not words or words[0].startswith('*'):continue
            if not words[0].startswith('X') or len(words)<6 or not words[5].startswith('sky130_fd_pr__'):
                raise ValueError('Unexpected native static-gate transistor')
            nodes=[pins.get(n,tag+'__'+n) for n in words[1:5]]
            lines.append('X'+tag+'__'+words[0]+' '+' '.join([*nodes,*words[5:]]))
    return '\n'.join(lines+['.ends '+NAME,''])
