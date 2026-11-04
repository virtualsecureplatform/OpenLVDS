# SPDX-License-Identifier: GPL-3.0-only
"""Guard native FF private nodes and separate prepare from public release.

The first two FFs establish readiness; PREPARE enables internal DCC data before
the third FF releases its public output mask. All three FFs asynchronously clear
from REQUEST. Added guards are real MIM devices, with new physical proofs still
required; no native MOS is resized, removed or aliased.
"""
from native_static_cells_v2 import inline
import native_clock_components_v3 as components
from dcc_nand_mid_shunt_v2 import devices

NAME='openlvds_guarded_clock_prepare_v2'
PORTS=['CLK','REQUEST','PREPARE','RESET_N','VPWR','VGND']
DCC_NAME='openlvds_dcc_separate_prepare_v2'
DCC_PORTS=[*components.dcc.PORTS,'prepare_n']
CAP='sky130_fd_pr__cap_mim_m3_1'


def gates():
    return [('r0','dfrtp_1',dict(CLK='CLK',D='REQUEST',RESET_B='REQUEST',Q='ready0')),
            ('r1','dfrtp_1',dict(CLK='CLK',D='ready0',RESET_B='REQUEST',Q='PREPARE')),
            ('r2','dfrtp_1',dict(CLK='CLK',D='PREPARE',RESET_B='REQUEST',Q='ready2'))]


def source(library,rc,guard_nodes,size):
    if size not in [1,2] or not guard_nodes or len(set(guard_nodes))!=len(guard_nodes):raise ValueError('Invalid private-guard experiment')
    body=inline(gates(),library);nodes={n for d in devices(body) for n in d['nodes']}
    expected={tag+'__'+n for tag in ['r0','r1','r2'] for n in guard_nodes}
    if not expected<=nodes:raise ValueError('Guard target is not an actual native FF private terminal')
    rows=['.subckt '+NAME+' '+' '.join(PORTS),body.rstrip()]
    rows += [f'XGUARD{i} {node} VGND {CAP} w={size} l={size}' for i,node in enumerate(sorted(expected))]
    rows.append(components.instance('ready_buffer',components.CLOCK_BUFFER,
        dict(A='ready2',X='RESET_N',VPWR='VPWR',VGND='VGND'),rc))
    return '\n'.join(rows+['.ends '+NAME,''])


def dcc_gates():
    cells=[c for c in components.dcc.storage.gates(2) if not c[0].startswith('xor_')]
    result=[]
    for tag,model,pins in components.strengthen(cells):
        pins=dict(pins)
        if tag in ['a_data_n','b_data_n']:pins['A']='prepare_n'
        result.append((tag,model,pins))
    result += [('isolate_'+n,'buf_8',dict(A=n,X=n+'_iso')) for n in ['a','a_qb','b','b_qb']]
    return result


def dcc_source(rc):
    text=components.base.logic(DCC_NAME,DCC_PORTS,dcc_gates(),rc);rows=text.splitlines()[:-1]
    rows.append(components.instance('xor','openlvds_tg_xor_p3_v2',
        dict(a_iso='a_iso',a_qb_iso='a_qb_iso',b_iso='b_iso',b_qb_iso='b_qb_iso',xor_out='xor_out',VDDD='VPWR',VSS='VGND'),rc))
    return '\n'.join(rows+['.ends '+DCC_NAME,''])
