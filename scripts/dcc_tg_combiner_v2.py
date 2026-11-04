# SPDX-License-Identifier: GPL-3.0-only
"""Static NAND storage and two symmetric real transmission-gate XOR muxes.

Use both complementary latch outputs directly. A real reset NAND inverts XOR
and holds the public output HIGH in reset; the internal latches initialize
through raw clocks. All shunts are native MIM devices, never ideal capacitors.
"""
import dcc_nand_latch_v2 as storage
from dcc_nand_mid_shunt_v2 import devices,CAP
from native_static_cells_v2 import inline

NAME='openlvds_dcc_tg_combiner_v2'
PORTS=storage.PORTS
VARIANTS={'tg1':dict(ff_drive=2,n_width_um=1,p_width_um=2),'tg2':dict(ff_drive=2,n_width_um=2,p_width_um=4)}
N='sky130_fd_pr__nfet_01v8'
P='sky130_fd_pr__pfet_01v8'


def switches():
    # XOR = a ? b_bar : b, in parallel with b ? a_bar : a.
    return [('ab0','b','a_qb','a'),('ab1','b_qb','a','a_qb'),
            ('ba0','a','b_qb','b'),('ba1','a_qb','b','b_qb')]


def source(variant,library):
    if variant not in VARIANTS:raise ValueError('Undeclared native TG combiner')
    spec=VARIANTS[variant];cells=[c for c in storage.gates(spec['ff_drive']) if not c[0].startswith('xor_')]
    body=inline(cells,library);private=sorted({n for d in devices(body) for n in d['nodes'] if '__' in n})
    outputs=sorted({p['Y'] for _,_,p in cells}|{'xor_out'})
    rows=['.subckt '+NAME+' '+' '.join(PORTS),body.rstrip()]
    for tag,data,en,enb in switches():
        rows += [f'Xtg_{tag}_n xor_out {en} {data} VGND {N} w={spec["n_width_um"]} l=0.15',
                 f'Xtg_{tag}_p xor_out {enb} {data} VPWR {P} w={spec["p_width_um"]} l=0.15']
    for i,node in enumerate(private):
        size=4 if node.startswith('output_reset__') else 2
        rows.append(f'XSTACKCAP{i} {node} VGND {CAP} w={size} l={size}')
    rows += [f'XOUTCAP{i} {node} VGND {CAP} w=2 l=2' for i,node in enumerate(outputs)]
    return '\n'.join(rows+['.ends '+NAME,'']),dict(private_nodes=private,output_nodes=outputs,hardware=spec)
