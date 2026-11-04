# SPDX-License-Identifier: GPL-3.0-only
"""Replace three ideal shared low-setter pairs with actual routed-pair RC."""
import static_phase_clock_release_v5 as previous

components=previous.components
PORTS=previous.PORTS
NAME='openlvds_routed_pair_static_phase_release_v2'
PAIR='openlvds_nand2b_4_o1_stack_guard_pair_v2'
MACROS={'pair':PAIR}


def source(rc,variant):
    if variant!='pair':raise ValueError('Unknown physical low-setter pair')
    rows=previous.source(rc,'o1').splitlines();rows[0]='.subckt '+NAME+' '+' '.join(PORTS);rows[-1]='.ends '+NAME
    for tag,prior,high,out in previous.previous.STAGES:
        if high:continue
        for copy in range(2):
            matches=[r for r in rows if r.split()[0]=='X'+tag+'_set_'+str(copy)]
            if len(matches)!=1 or matches[0].split()[-1]!=previous.MACROS['o1']:raise ValueError('Original guarded setter topology changed')
            rows.remove(matches[0])
        rows.insert(-1,components.instance(tag+'_set_pair',PAIR,dict(A_N='CLK',B=prior,Y=tag+'_sn',VPWR='VPWR',VGND='VGND'),rc))
    return '\n'.join(rows)+'\n'
