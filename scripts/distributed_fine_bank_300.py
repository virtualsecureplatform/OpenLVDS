#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""One-factor controls for distributing qualified fine capacitance over two stages."""
from copy import deepcopy
import mim_fine_bank_300 as mim
SOURCE=mim.SOURCE
VARIANTS={'strong_pre_c4':(4,False),'strong_pre_c2':(2,False),'split_c1_c1':(2,True),'split_c2_c2':(4,True)}


def transform(original,observations,variant):
    if variant not in VARIANTS:raise ValueError('Unknown distributed-fine architecture control')
    copies,split=VARIANTS[variant]
    text,previous,base_revision=mim.transform(original,observations,mim.qualified_cell(),copies=copies,driver='p80')
    defs=SOURCE.native.definitions(text);old_top=base_revision['macro_top'];ports,body=defs[old_top]
    old_pre=['Xfine_pre','selected','pre_out','VGND','VPWR',SOURCE.SMALL]
    new_pre=old_pre[:-1]+[mim.single.parent.FINE]
    if (body.count(old_pre)!=1 or defs[mim.single.parent.FINE][0]!=['A','Y','VGND','VPWR']
            or len(previous['controls'])!=86):raise ValueError('Require qualified original pre-driver interface')
    expected_moves={f'Xfine_mim{k}_c{copy}':[f'Xfine_mim{k}_c{copy}','fine_node',f'fine{k}',f'fine_b{k}','VPWR','VGND',mim.MODEL]
                    for k in range(31) for copy in range(1,copies,2)} if split else {}
    if any(body.count(w)!=1 for w in expected_moves.values()):raise ValueError('Require exact original second fine-capacitor calls')
    changed=[]
    for w in body:
        if w==old_pre:changed.append(new_pre)
        elif w[0] in expected_moves:
            if w!=expected_moves[w[0]]:raise ValueError('Fine capacitor wiring changed')
            changed.append([w[0],'pre_out',*w[2:]])
        else:changed.append(w)
    top='openlvds_distributed_fine_300_'+variant
    block='\n'.join(['.subckt '+top+' '+' '.join(ports),*[' '.join(w) for w in changed],'.ends '+top,''])
    result=text.replace(SOURCE.definition(text,old_top),block,1)
    if any(SOURCE.definition(result,n)!=SOURCE.definition(text,n) for n in defs if n!=old_top):
        raise ValueError('Unrelated qualified numerical component changed')
    pins={p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports}
    devices=SOURCE.native.mapped_mos(result,top,pins,'XD');before={d['name']:d for d in previous['devices']};after={d['name']:d for d in devices}
    moved=tuple('XD:'+name+':' for name in expected_moves)
    changed_prefixes=('XD:Xfine_pre:',*moved)
    old_pre_mos=sum(n.startswith('XD:Xfine_pre:') for n in before)
    new_pre_mos=sum(n.startswith('XD:Xfine_pre:') for n in after)
    qualified=SOURCE.native.mapped_mos(text,mim.single.parent.FINE,
        dict(A='XD:selected',Y='XD:pre_out',VGND='0',VPWR='VDD'),'XD:Xfine_pre')
    if (len(after)!=len(devices) or len(after)!=len(before)-old_pre_mos+len(qualified)
            or new_pre_mos!=len(qualified) or any(after.get(d['name'])!=d for d in qualified)
            or any(after.get(n)!=d for n,d in before.items() if not n.startswith(changed_prefixes))
            or set(after)!=(set(before)-{n for n in before if n.startswith('XD:Xfine_pre:')})|{d['name'] for d in qualified}):
        raise ValueError('Actual native maps changed beyond the declared pre-driver/capacitor controls')
    gates=deepcopy(previous['programming_gates'])
    if any(after[g['device']]['terminals'][1]!=g['gate_node'] for g in gates):
        raise ValueError('Actual fine/coarse programming-gate observation changed')
    _,leaves=SOURCE.inventory.native_leaves(SOURCE.collapse(result),top)
    actual_mos=sum('fet_' in d['model'] for d in leaves);actual_mims=sum('cap_mim' in d['model'] for d in leaves)
    if actual_mos!=len(devices):raise ValueError('Actual reachable transistor census changed')
    pre_calls=[w for w in changed if w[-1]==mim.MODEL and w[1]=='pre_out']
    fine_calls=[w for w in changed if w[-1]==mim.MODEL and w[1]=='fine_node']
    if (len(pre_calls)!=(31*copies//2 if split else 0) or len(fine_calls)!=(31*copies//2 if split else 31*copies)
            or len(gates)!=80+93*copies):raise ValueError('Incomplete split fine capacitance or programming coverage')
    return result,dict(devices=devices,controls=deepcopy(previous['controls']),programming_gates=gates),dict(
        macro_top=top,variant=variant,native_mos=actual_mos,native_mims=actual_mims,
        pre_driver='two_parallel_qualified_p40n16',fine_driver='two_parallel_qualified_p40n16',
        fine_copies_pre_node=copies//2 if split else 0,fine_copies_fine_node=copies//2 if split else copies,
        controls=86,programming_gates=len(gates),pre_mos_before=old_pre_mos,pre_mos_after=new_pre_mos,
        shared_wire_rc_qualified=False,qualified_phy=False)
