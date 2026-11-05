# SPDX-License-Identifier: GPL-3.0-only
"""Retain measured local wiring inside all paired balanced-bank inverters.

No bank candidate is admitted here. The first/root TG gangs and all common
bank wiring still require routing/extraction and native timing qualification.
"""
import re
import strong_coarse_bank_v122 as base
from post_mux_output_rc_bank_v112 import checked_driver,driver_inputs,DRIVER
from parallel_root_bank_v97 import rename
from build_compound_drivers_v3 import cell_definition

ROOT=base.ROOT
source=base.source
INV='openlvds_inv_8_nlvt_o2_v34'


def name(profile):
    base.name(profile)
    return 'openlvds_measured_gangs_'+profile+'_v125'


def pairs():
    return [(f'Xgroup_inverse{k}',f'Xgroup_parallel{k}',f'Xgroup_compound{k}',f'tree0_{k}',f'regenerated{k}') for k in range(4)]+[
        ('Xfine_driver','Xfine_parallel','Xfine_compound','selected','OUT')]


def collapse_pairs(bank,top,driver):
    defs=source.native.definitions(bank);body=defs[top][1];before=cell_definition(bank,top);after=before
    if DRIVER in defs:raise ValueError('Measured inverter gangs already present')
    if [w[0] for w in body[-4:]]!=[f'Xgroup_parallel{k}' for k in range(4)]:
        raise ValueError('Original group gang order changed')
    fine=[k for k,w in enumerate(body) if w[0]=='Xfine_parallel']
    if len(fine)!=1 or fine[0]+1>=len(body) or body[fine[0]+1][0]!='Xleaf_parallel0_0':
        raise ValueError('Original final gang order changed')
    for first,second,compound,a,y in pairs():
        for tag in [first,second]:
            calls=[w for w in body if w[0]==tag]
            if (len(calls)!=1 or calls[0][-1]!=INV
                or dict(zip(defs[INV][0],calls[0][1:-1]))!=dict(A=a,Y=y,VPWR='VPWR',VGND='VGND')):
                raise ValueError('Expected paired inverter data/body wiring')
            line=' '.join(calls[0])+'\n'
            if after.count(line)!=1:raise ValueError('Ambiguous inverter source')
            after=after.replace(line,compound+' '+a+' '+y+' VPWR VGND '+DRIVER+'\n' if tag==first else '',1)
    return bank.replace(before,after,1)+'\n'+cell_definition(driver,DRIVER)


def projection(bank,profile):
    top=name(profile);defs=source.native.definitions(bank);block=cell_definition(bank,DRIVER)
    if not bank.endswith('\n'+block):raise ValueError('Measured gang definition moved')
    result=bank[:-len('\n'+block)];before=cell_definition(result,top);after=before
    for first,second,compound,a,y in pairs():
        calls=[w for w in defs[top][1] if w[0]==compound]
        expected=[compound,a,y,'VPWR','VGND',DRIVER]
        if calls!=[expected]:raise ValueError('Measured gang missing, duplicated or rewired')
        pins=dict(A=a,Y=y,VPWR='VPWR',VGND='VGND')
        after=after.replace(' '.join(expected)+'\n',first+' '+' '.join(pins[p] for p in defs[INV][0])+' '+INV+'\n',1)
    fine=pairs()[-1];pins=dict(A=fine[3],Y=fine[4],VPWR='VPWR',VGND='VGND')
    line=fine[1]+' '+' '.join(pins[p] for p in defs[INV][0])+' '+INV+'\n'
    marker=next((' '.join(w)+'\n' for w in defs[top][1] if w[0]=='Xleaf_parallel0_0'),None)
    if marker is None or after.count(marker)!=1:raise ValueError('Leaf insertion anchor changed')
    after=after.replace(marker,line+marker,1)
    added=[]
    for first,second,compound,a,y in pairs()[:4]:
        pins=dict(A=a,Y=y,VPWR='VPWR',VGND='VGND')
        added.append(second+' '+' '.join(pins[p] for p in defs[INV][0])+' '+INV)
    after,count=re.subn(r'(?im)^\.ends\b','\n'.join(added)+'\n.ends',after)
    if count!=1:raise ValueError('Ambiguous bank boundary')
    return rename(result.replace(before,after,1),top,base.name(profile))


def transform_existing(parent,profile):
    bank=rename(collapse_pairs(parent,base.name(profile),checked_driver()),base.name(profile),name(profile))
    if projection(bank,profile)!=parent:raise ValueError('Unrelated measured coarse-bank circuitry changed')
    counts=source.primitive_counts(bank,name(profile))
    if sum(v for k,v in counts.items() if 'fet_' in k)!=base.native_count(profile) or counts.get('sky130_fd_pr__cap_mim_m3_1')!=42:
        raise ValueError('Measured inverter gang native inventory changed')
    return bank


def observations(bank,profile,previous):
    result=base.observations(projection(bank,profile),profile,previous);top=name(profile)
    ports=source.native.definitions(bank)[top][0]
    devices=source.native.mapped_mos(bank,top,{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports},'XD');byname={d['name']:d for d in devices}
    gates=[dict(g,gate_node=byname[g['device']]['terminals'][1]) for g in result['programming_gates']]
    if len(devices)!=base.native_count(profile) or len(byname)!=len(devices) or len(gates)!=173:
        raise ValueError('Measured inverter gang native/control observations incomplete')
    return dict(result,devices=devices,programming_gates=gates)
