# SPDX-License-Identifier: GPL-3.0-only
"""Shorten each coarse increment with a native inverting return mux.

Retain gated forward NANDs, all sixteen coarse choices and thirty-one actual
fine units. r_i = coarse_i ? !r_(i+1) : f_i is implemented as
MUX2I(!f_i, r_(i+1), coarse_i). Two native inversions restore the last return,
retaining a two-stage turnaround at the final coarse choice as well.
Parallel source mux/turn gates require new compound geometry and whole-bank RC.
"""
import dcdl_mim_bank_physical_v2 as old
import mim_switch_2x3_v2 as fine

SC=old.native.SC
NAME='openlvds_dcdl_mux_return_c16_f32_v2'
PORTS=['IN','OUT',*[f'C{i}' for i in range(15)],*[f'E{i}' for i in range(31)],'VPWR','VGND']
CAP='sky130_fd_pr__cap_mim_m3_1'


def core_instances():
    cells=[]
    def add(name,model,**pins):cells.append(dict(name=name,model=model,pins=pins))
    def f(i):return 'IN' if i==0 else f'f{i}'
    def r(i):return 'OUT' if i==0 else f'r{i}'
    for i in range(15):
        add(f'coarse_buffer{i}',SC+'buf_4',A=f'C{i}',X=f'coarse{i}')
        add(f'forward{i}',old.COMPOUNDS[SC+'nand2_4'],A=f(i),B=f'coarse{i}',Y=f(i+1),VPWR='VPWR',VGND='VGND')
        for copy in range(2):add(f'turn{i}_{copy}',SC+'inv_4',A=f(i),Y=f'invf{i}')
        for copy in range(4 if i==0 else 2):
            add(f'return{i}_{copy}',SC+'mux2i_4',A0=f'invf{i}',A1=r(i+1),S=f'coarse{i}',Y=r(i))
    for stage,a,y in [(0,'f15','tail_n'),(1,'tail_n','r15')]:
        for copy in range(2):add(f'tail{stage}_{copy}',SC+'inv_4',A=a,Y=y)
    return cells


def instances():
    cells=core_instances()
    for i in range(31):
        cells += [dict(name=f'fine_buffer{i}',model=SC+'buf_1',pins=dict(A=f'E{i}',X=f'fine{i}')),
                  dict(name=f'fine_inverse{i}',model=SC+'inv_1',pins=dict(A=f'fine{i}',Y=f'fine_b{i}')),
                  dict(name=f'fine_unit{i}',model=fine.NAME,pins=dict(NODE='OUT',EN=f'fine{i}',ENB=f'fine_b{i}',VDD='VPWR',VSS='VGND'))]
    return cells


def source(orders):
    rows=['.subckt '+NAME+' '+' '.join(PORTS)]
    pg=dict(VPWR='VPWR',VPB='VPWR',VGND='VGND',VNB='VGND')
    for cell in instances():
        model=cell['model'];pins=dict(pg,**cell['pins'])
        if model not in orders or not set(orders[model])<=set(pins):raise ValueError('Missing native mux-bank pin interface')
        rows.append('X'+cell['name']+' '+' '.join(pins[p] for p in orders[model])+' '+model)
    rows += [f'XBASE OUT VGND {CAP} w=4 l=4','.ends '+NAME,'']
    return '\n'.join(rows)
