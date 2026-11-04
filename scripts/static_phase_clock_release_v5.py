# SPDX-License-Identifier: GPL-3.0-only
"""Use private-guard NAND2B RC with a mirrored substrate-contact row."""
import static_phase_clock_release_v2 as previous

components=previous.components
PORTS=previous.PORTS
NAME='openlvds_stack_guard_static_phase_release_v2'
MACROS={v:f'openlvds_nand2b_4_{v}_stack_guard_bodytap_v2' for v in ['o1','o2']}


def source(rc,variant):
    if variant not in MACROS:raise ValueError('Unknown physical NAND2B shunt variant')
    old=previous.source(rc,4).splitlines();body=old[1:-1]
    for tag,prior,high,out in previous.STAGES:
        if high:continue
        matches=[row for row in body if row.split()[0]=='X'+tag+'_set']
        if len(matches)!=1 or matches[0].split()[-1]!=previous.NAND2B:raise ValueError('Previous low setter changed')
        body.remove(matches[0])
        for copy in range(2):
            body.append(components.instance(tag+'_set_'+str(copy),MACROS[variant],
                dict(A_N='CLK',B=prior,Y=tag+'_sn',VPWR='VPWR',VGND='VGND'),rc))
    return '\n'.join(['.subckt '+NAME+' '+' '.join(PORTS),*body,'.ends '+NAME,''])
