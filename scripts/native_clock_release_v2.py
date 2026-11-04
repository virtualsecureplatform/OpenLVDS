# SPDX-License-Identifier: GPL-3.0-only
"""Native static-gate, two-register reset release with asynchronous clear.

Both master and slave complementary latches have real reset NANDs. Qualifying
the output with REQUEST clears DCC reset even if its clock has stopped; clearing
the internal state prevents an old run from bypassing the next two clock edges.
"""
from native_static_cells_v2 import inline
from dcc_nand_mid_shunt_v2 import devices,CAP

NAME='openlvds_clock_release_static_v2'
PORTS=['CLK','REQUEST','RESET_N','VPWR','VGND']


def gates():
    cells=[]
    def nand(name,a,b,y,size=2):cells.append((name,'nand2_'+str(size),dict(A=a,B=b,Y=y)))
    def reset_nand(name,a,b,y):cells.append((name,'nand3_2',dict(A=a,B=b,C='REQUEST',Y=y)))
    def inv(name,a,y,size=1):cells.append((name,'inv_'+str(size),dict(A=a,Y=y)))
    for tag,data in [('r0','REQUEST'),('r1','r0_q')]:
        nand(tag+'_data_n','REQUEST',data,tag+'_dn');inv(tag+'_data',tag+'_dn',tag+'_d')
        inv(tag+'_clock','CLK',tag+'_clk_n')
        nand(tag+'_master_s',tag+'_d',tag+'_clk_n',tag+'_ms')
        nand(tag+'_master_r',tag+'_dn',tag+'_clk_n',tag+'_mr')
        nand(tag+'_master_q',tag+'_ms',tag+'_mb',tag+'_m')
        reset_nand(tag+'_master_b',tag+'_mr',tag+'_m',tag+'_mb')
        nand(tag+'_slave_s',tag+'_m','CLK',tag+'_ss')
        nand(tag+'_slave_r',tag+'_mb','CLK',tag+'_sr')
        nand(tag+'_slave_q',tag+'_ss',tag+'_qb',tag+'_q')
        reset_nand(tag+'_slave_b',tag+'_sr',tag+'_q',tag+'_qb')
    nand('qualify','REQUEST','r1_q','qualified_n',4);inv('output','qualified_n','RESET_N',8)
    return cells


def source(library):
    cells=gates();body=inline(cells,library);private=sorted({n for d in devices(body) for n in d['nodes'] if '__' in n})
    outputs=sorted({p['Y'] for _,_,p in cells});rows=['.subckt '+NAME+' '+' '.join(PORTS),body.rstrip()]
    rows += [f'XSTACKCAP{i} {n} VGND {CAP} w=2 l=2' for i,n in enumerate(private)]
    for i,n in enumerate(outputs):
        size=4 if n=='RESET_N' else 2
        rows.append(f'XOUTCAP{i} {n} VGND {CAP} w={size} l={size}')
    return '\n'.join(rows+['.ends '+NAME,''])
