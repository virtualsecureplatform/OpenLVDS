# SPDX-License-Identifier: GPL-3.0-only
"""Native MIM loads on stack nodes and distinct logical gate outputs.

One output shunt is shared by each swapped-input NAND pair; its internal stack
nodes remain distinct. All native transistor dimensions/parameters are retained.
"""
import dcc_nand_mid_shunt_v2 as mid

unshunted=mid.unshunted
NAME='openlvds_dcc_nand_node_shunt_v2'
PORTS=mid.PORTS
CAP=mid.CAP
devices=mid.devices


def source(drive,library):
    text,stack_nodes=mid.source(drive,library)
    lines=text.splitlines()
    if lines[-1]!='.ends '+mid.NAME:raise ValueError('Unexpected mid-shunted DCC boundary')
    lines=lines[:-1];lines[0]='.subckt '+NAME+' '+' '.join(PORTS)
    outputs=sorted({pins['Y'] for _,_,pins in unshunted.gates(drive)})
    lines += [f'XOUTCAP{i} {node} VGND {CAP} w=2 l=2' for i,node in enumerate(outputs)]
    return '\n'.join(lines+['.ends '+NAME,'']),dict(stack_nodes=stack_nodes,output_nodes=outputs)
