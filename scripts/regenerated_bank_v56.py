# SPDX-License-Identifier: GPL-3.0-only
"""Move the input inversion after each first-level mux, using qualified INV2."""
import native_clock_components_v2 as native

NAME='openlvds_dcdl_c16_f32_regenerated_v56'


def transform(cells,bank,old_top,inverter):
    defs=native.definitions(cells);roots=native.definitions(bank)
    if set(roots)!={old_top} or inverter not in defs:raise ValueError('Missing original bank or qualified inverter')
    ports,body=roots[old_top];order=defs[inverter][0];rows=[];removed=0;roots_changed=set()
    if set(order)!={'A','Y','VGND','VPWR'}:raise ValueError('Unexpected native inverter interface')
    for w in body:
        if not w[0].startswith('X'):raise ValueError('Unknown active bank statement')
        end=next((j for j,v in enumerate(w) if '=' in v),len(w));model=w[end-1];nodes=w[1:end-1]
        if w[0]=='Xinput_inverse':
            if model!=inverter or dict(zip(order,nodes))!=dict(A='IN',Y='tap0',VGND='VGND',VPWR='VPWR'):
                raise ValueError('Original input inversion changed')
            removed+=1;continue
        nodes=['IN' if n=='tap0' else n for n in nodes]
        for group in range(4):
            if w[0]!=f'Xswitch1_0_{group}':continue
            if model not in defs:raise ValueError('Missing root TG model')
            position=defs[model][0].index('A')
            if nodes[position]!=f'tree0_{group}':raise ValueError('Original root TG input changed')
            nodes[position]=f'regenerated{group}';roots_changed.add(group)
        rows.append(' '.join([w[0],*nodes,*w[end-1:]]))
    if removed!=1 or roots_changed!=set(range(4)):raise ValueError('Missing input inversion or root mux branch')
    for group in range(4):
        pins=dict(A=f'tree0_{group}',Y=f'regenerated{group}',VGND='VGND',VPWR='VPWR')
        rows.append(f'Xgroup_inverse{group} '+' '.join(pins[p] for p in order)+' '+inverter)
    return '.subckt '+NAME+' '+' '.join(ports)+'\n'+'\n'.join(rows)+'\n.ends '+NAME+'\n'


def primitive_counts(text,top):
    from collections import Counter
    defs=native.definitions(text);result=Counter()
    def walk(model,seen):
        if model in seen:raise ValueError('Recursive regenerated bank')
        for w in defs[model][1]:
            if w[0][0].upper() in ('R','C'):continue
            end=next((j for j,v in enumerate(w) if '=' in v),len(w));child=w[end-1]
            if child in defs:walk(child,seen|{model})
            else:result[child]+=1
    walk(top,set());return dict(result)
