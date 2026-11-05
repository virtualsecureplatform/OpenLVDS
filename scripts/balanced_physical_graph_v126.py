# SPDX-License-Identifier: GPL-3.0-only
"""Map measured balanced-bank gangs to canonical physical masters.

Named-pin/native-reference preparation only. This does not admit a timing
candidate, choose a gang size or qualify whole-bank routing/junction RC.
"""
from copy import deepcopy
import re
import tg_bank_physical_netlist_v45 as old
from build_compound_drivers_v3 import cell_definition
from post_mux_bank_physical_v118 import dimension_inventory
from audit_rc_comments_v2 import collapse

FINE='openlvds_fine_moscap_w126_middle_v124'
PAIR='openlvds_parallel_inv8_registered_v114'
PAIR_SOURCE='openlvds_parallel_inv8_v110'


def coarse(profile):
    if profile not in ('b2','b3'):raise ValueError('Unknown measured coarse profile')
    return 'openlvds_coarse_'+profile+'_registered_v124'


def graph(before,profile):
    buffer=coarse(profile);g=deepcopy(before);g['top']='openlvds_balanced_'+profile+'_physical_v126'
    if len(g['cells'])!=156:raise ValueError('Require complete original physical graph')
    removed=[c for c in g['cells'] if c['name']=='u_input_inverse']
    if len(removed)!=1 or removed[0]['model']!=old.INV:raise ValueError('Original input inverter missing')
    g['cells']=[c for c in g['cells'] if c['name']!='u_input_inverse'];fine=set();drivers=0;buffers=0
    for c in g['cells']:
        c['pins']={p:'IN' if n=='tap0' else n for p,n in c['pins'].items()}
        if c['model']==old.FINE:
            match=re.fullmatch(r'u_fine_unit(\d+)',c['name'])
            if match is None:raise ValueError('Unexpected fine component')
            k=int(match[1]);fine.add(k)
            if c['pins']!=dict(A='OUT',CTRL=f'fine{k}',CTRL_B=f'fine_b{k}',VPWR='VPWR',VGND='VGND'):
                raise ValueError('Original fine programming/body connection changed')
            c['model']=FINE;c['pins']['A']='selected'
        elif c['name']=='u_fine_driver':
            if c['model']!=old.INV or c['pins']!=dict(A='selected',Y='OUT',VGND='VGND',VPWR='VPWR'):
                raise ValueError('Original final driver changed')
            c.update(name='u_fine_compound',native_name='Xfine_compound',model=PAIR);drivers+=1
        elif c['model']==old.BUFFER:
            c['model']=buffer;buffers+=1
    if fine!=set(range(31)) or drivers!=1 or buffers!=16:raise ValueError('Incomplete measured balanced graph')
    byname={c['name']:c for c in g['cells']}
    for group in range(4):
        root=byname[f'u_switch1_0_{group}']
        if root['model']!=old.TG or root['pins']!=dict(A=f'tree0_{group}',Z='selected',EN=f'en1_{group}',ENB=f'en_b1_{group}',VPWR='VPWR',VGND='VGND'):
            raise ValueError('Original root mux changed')
        root['pins']['A']=f'regenerated{group}'
        g['cells'].append(dict(name=f'u_group_compound{group}',native_name=f'Xgroup_compound{group}',model=PAIR,
                              pins=dict(A=f'tree0_{group}',Y=f'regenerated{group}',VPWR='VPWR',VGND='VGND')))
        extra=deepcopy(root);extra.update(name=f'u_root_parallel{group}',native_name=f'Xroot_parallel{group}');g['cells'].append(extra)
        for leaf in range(4):
            original=byname[f'u_switch0_{group}_{leaf}'];k=group*4+leaf
            if original['model']!=old.TG or original['pins']!=dict(A='IN' if k==0 else f'tap{k}',Z=f'tree0_{group}',EN=f'en0_{leaf}',ENB=f'en_b0_{leaf}',VPWR='VPWR',VGND='VGND'):
                raise ValueError('Original leaf mux changed')
            extra=deepcopy(original);extra.update(name=f'u_leaf_parallel{group}_{leaf}',native_name=f'Xleaf_parallel{group}_{leaf}');g['cells'].append(extra)
    used={c['model'] for c in g['cells']};g['orders']={m:p for m,p in g['orders'].items() if m in used}
    g['orders'].update({FINE:['A','CTRL','CTRL_B','VPWR','VGND'],PAIR:['A','Y','VPWR','VGND'],buffer:['A','X','VPWR','VGND']})
    g['physical_pin_aliases']={FINE:dict(NODE='A',EN='CTRL',ENB='CTRL_B',VDD='VPWR',VSS='VGND'),
                               PAIR:dict(IN='A',OUT='Y',VPWR='VPWR',VGND='VGND'),buffer:dict(IN='A',OUT='X',VPWR='VPWR',VGND='VGND')}
    if len(g['cells'])!=179 or len({c['native_name'] for c in g['cells']})!=179:raise ValueError('Physical balanced component count changed')
    return g


def compare_component(g,text,top,profile):
    defs=old.native.definitions(text);ports,body=defs[top]
    if ports!=g['ports']:raise ValueError('Canonical measured bank public interface differs')
    aliases={top+'_unit':(FINE,g['physical_pin_aliases'][FINE]),
             PAIR_SOURCE:(PAIR,g['physical_pin_aliases'][PAIR]),
             'openlvds_parallel_coarse_'+profile+'_v120':(coarse(profile),g['physical_pin_aliases'][coarse(profile)])}
    calls={}
    for w in body:
        end=next((k for k,t in enumerate(w) if '=' in t),len(w));model=w[end-1];nodes=w[1:end-1]
        if w[0] in calls:raise ValueError('Duplicate measured native component')
        if model==old.MIM:
            if w[0]!='Xtail_termination' or dict(t.split('=',1) for t in w[end:])!=dict(w='2',l='2'):
                raise ValueError('Native balancing tail changed')
            model=old.TAIL;pins=dict(zip(['A','VGND'],nodes))
        else:
            if end!=len(w) or model not in defs or len(nodes)!=len(defs[model][0]):raise ValueError('Unknown measured component interface')
            pins=dict(zip(defs[model][0],nodes))
            if model in aliases:
                model,rename=aliases[model];pins={rename[p]:n for p,n in pins.items()}
        calls[w[0]]=(model,pins)
    expected={c['native_name']:(c['model'],c['pins']) for c in g['cells']}
    if len(expected)!=len(g['cells']) or calls!=expected:raise ValueError('Physical graph differs from measured gang components')
    return dict(exact_component_calls_and_named_pins_verified=True,components=len(expected),qualified_phy=False)


def native_source(g,libraries):
    definitions={}
    for text in libraries:
        for model in old.native.definitions(text):
            block=cell_definition(text,model)
            if model in definitions and definitions[model]!=block:raise ValueError('Conflicting native master reference')
            definitions[model]=block
    needed=set()
    def visit(model,ancestors):
        if model in ancestors:raise ValueError('Recursive native master reference')
        if model in needed:return
        if model not in definitions:raise ValueError('Missing native physical master')
        needed.add(model)
        for w in old.native.definitions(definitions[model])[model][1]:
            if not w[0].startswith('X'):raise ValueError('Physical reference contains routing R/C')
            end=next((k for k,t in enumerate(w) if '=' in t),len(w));child=w[end-1]
            if not child.startswith('sky130_fd_pr__'):visit(child,ancestors|{model})
    for model in g['orders']:visit(model,set())
    rows=['.subckt '+g['top']+' '+' '.join(g['ports'])]
    for c in g['cells']:rows.append(c['native_name']+' '+' '.join(c['pins'][p] for p in g['orders'][c['model']])+' '+c['model'])
    return ''.join(definitions[m] for m in sorted(needed))+'\n'.join(rows+['.ends '+g['top'],''])


def native_inventory_proof(g,reference,component,top,profile):
    physical=dimension_inventory(reference,g['top'])
    collapsed=''.join(collapse(cell_definition(component,m)) for m in old.native.definitions(component))
    if physical!=dimension_inventory(collapsed,top):raise ValueError('Measured/physical native dimensions or inventory differ')
    mos=sum(n for (m,w,l),n in physical.items() if 'fet_' in m);mim=sum(n for (m,w,l),n in physical.items() if 'cap_mim' in m)
    if (mos,mim)!=(1133+320*(int(profile[1])-1),42):raise ValueError('Measured gang physical census changed')
    return dict(native_dimensions_and_inventory_preserved=True,native_mos=mos,native_mims=mim,qualified_phy=False)
