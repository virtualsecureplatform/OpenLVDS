# SPDX-License-Identifier: GPL-3.0-only
"""Isolate complementary storage with four matched native buf8 drivers."""
import dcc_tg_combiner_v2 as direct
from native_static_cells_v2 import inline

NAME='openlvds_dcc_tg_buffered_v2'
PORTS=direct.PORTS
storage=direct.storage
devices=direct.devices
CAP=direct.CAP
N=direct.N
P=direct.P
VARIANTS={v:dict(s,isolation_buffer='buf_8') for v,s in direct.VARIANTS.items()}


def source(variant,library):
    if variant not in VARIANTS:raise ValueError('Undeclared isolated TG combiner')
    spec=VARIANTS[variant];cells=[c for c in storage.gates(spec['ff_drive']) if not c[0].startswith('xor_')]
    mapping={n:n+'_iso' for n in ['a','a_qb','b','b_qb']}
    cells += [('isolate_'+n,'buf_8',dict(A=n,X=target)) for n,target in mapping.items()]
    body=inline(cells,library);private=sorted({n for d in devices(body) for n in d['nodes'] if '__' in n})
    outputs=sorted({p.get('Y',p.get('X')) for _,_,p in cells}|{'xor_out'})
    rows=['.subckt '+NAME+' '+' '.join(PORTS),body.rstrip()]
    for tag,data,en,enb in direct.switches():
        rows += [f'Xtg_{tag}_n xor_out {mapping[en]} {mapping[data]} VGND {N} w={spec["n_width_um"]} l=0.15',
                 f'Xtg_{tag}_p xor_out {mapping[enb]} {mapping[data]} VPWR {P} w={spec["p_width_um"]} l=0.15']
    for i,node in enumerate(private):
        size=4 if node.startswith('output_reset__') else 2
        rows.append(f'XSTACKCAP{i} {node} VGND {CAP} w={size} l={size}')
    rows += [f'XOUTCAP{i} {node} VGND {CAP} w=2 l=2' for i,node in enumerate(outputs)]
    return '\n'.join(rows+['.ends '+NAME,'']),dict(private_nodes=private,output_nodes=outputs,hardware=spec,isolation_nodes=mapping)
