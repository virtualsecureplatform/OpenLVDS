# SPDX-License-Identifier: GPL-3.0-only
"""Named-pin physical view of the both2 bank, including the fixed tail MIM.

The native-only SPICE view is for connectivity/LVS, never electrical timing.
"""
from collections import Counter
import hashlib
import json
import re
import native_clock_components_v2 as native
from build_compound_drivers_v3 import cell_definition
from audit_rc_comments_v2 import collapse

VERSION='both2-named-pin-physical-bank-native-graph-v45.1'
SOURCE='openlvds_dcdl_c16_f32_both2_v36'
NAME='openlvds_dcdl_c16_f32_both2_physical_v45'
TAIL='openlvds_tail_mim2_v39'
MIM='sky130_fd_pr__cap_mim_m3_1'
SC='sky130_fd_sc_hd__'
TG='openlvds_tg_quad_stacked_nlvt_v27'
FINE='openlvds_mim_switch_2x3_v2'
FINE_ALIASES=dict(NODE='A',EN='CTRL',ENB='CTRL_B',VDD='VPWR',VSS='VGND')
INV='openlvds_inv_8_nlvt_o2_v34'
BUFFER='openlvds_buf_4_pair_nlvt_v29'
RAILS={'VPWR','VGND','VPB','VNB'}


def direction(model,pin):
    if pin in RAILS:return 'inout'
    if model==TAIL:return 'inout'
    if model==TG:return 'inout' if pin in ('A','Z') else 'input'
    if model==FINE:return 'inout' if pin=='A' else 'input'
    if model in (INV,SC+'inv_1',SC+'inv_4'):return 'output' if pin=='Y' else 'input'
    if model in (BUFFER,SC+'buf_1',SC+'buf_4',SC+'and2_4'):return 'output' if pin=='X' else 'input'
    raise ValueError('Unknown physical component direction: '+model)


def graph(cells,bank,tail):
    definitions=native.definitions(cells);roots=native.definitions(bank);td=native.definitions(tail)
    if set(roots)!={SOURCE} or set(td)!={TAIL} or td[TAIL][0]!=['A','VGND']:
        raise ValueError('Source bank or physical tail interface changed')
    ports,body=roots[SOURCE]
    expected=['IN','OUT',*[f'S{i}' for i in range(4)],*[f'E{i}' for i in range(31)],'VPWR','VGND']
    if ports!=expected:raise ValueError('Physical bank top interface changed')
    orders={};instances=[];seen=set();tails=0
    for words in body:
        if not words[0].startswith('X') or words[0] in seen:raise ValueError('Changed or duplicate native bank instance')
        seen.add(words[0]);end=next((i for i,w in enumerate(words) if '=' in w),len(words));model=words[end-1];nodes=words[1:end-1]
        if model==MIM:
            params=dict(w.split('=',1) for w in words[end:])
            if (words[0]!='Xtail_termination' or nodes!=['unused_tail','VGND']
                    or {k:float(v) for k,v in params.items()}!={'w':2.,'l':2.}):
                raise ValueError('Bare tail MIM changed before physical mapping')
            model=TAIL;order=td[TAIL][0];tails+=1
        else:
            if end!=len(words) or model not in definitions:raise ValueError('Unexpected parameterized or missing component')
            order=definitions[model][0]
            if model==FINE:
                if set(order)!=set(FINE_ALIASES):raise ValueError('Fine source interface changed')
                order=[FINE_ALIASES[p] for p in order]
        if len(nodes)!=len(order) or len(set(order))!=len(order):raise ValueError('Physical component port count changed')
        for p in order:direction(model,p)
        if model in orders and orders[model]!=order:raise ValueError('Conflicting physical component interfaces')
        orders[model]=order
        instances.append(dict(name='u_'+words[0][1:],native_name=words[0],model=model,pins=dict(zip(order,nodes))))
    if tails!=1:raise ValueError('Require exactly one physical balancing-tail cell')
    identifiers=set(ports)|{n for c in instances for n in c['pins'].values()}|{c['name'] for c in instances}
    if any(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_$]*',n) is None for n in identifiers):
        raise ValueError('Unsupported physical net or instance identifier')
    return dict(top=NAME,ports=ports,orders=orders,cells=instances,physical_pin_aliases={FINE:FINE_ALIASES})


def verilog(g):
    rows=['// SPDX-License-Identifier: GPL-3.0-only','// Connectivity only; no timing or PHY admission.','`default_nettype none',f'module {NAME} (']
    rows += [',\n'.join('    '+('inout' if p in RAILS else 'output' if p=='OUT' else 'input')+' wire '+p for p in g['ports']),');']
    nets=sorted({n for c in g['cells'] for n in c['pins'].values()}-set(g['ports']))
    rows += ['    (* keep = 1 *) wire '+n+';' for n in nets]
    for c in g['cells']:
        rows.append('    (* keep = 1, dont_touch = 1 *) '+c['model']+' '+c['name']+' ('+', '.join('.'+p+'('+n+')' for p,n in c['pins'].items())+');')
    return '\n'.join(rows+['endmodule','`default_nettype wire',''])


def blackboxes(g):
    rows=['// SPDX-License-Identifier: GPL-3.0-only','// Native physical interfaces only.','`default_nettype none']
    for model in sorted(g['orders']):
        rows += ['(* blackbox *) module '+model+' (',',\n'.join('    '+direction(model,p)+' wire '+p for p in g['orders'][model]),');','endmodule']
    return '\n'.join(rows+['`default_nettype wire',''])


def native_component(text,model):
    text=collapse(text)
    if model!=FINE:return text
    lines=[]
    for line in text.splitlines():
        w=line.split()
        if w and w[0].lower()=='.subckt':w=[*w[:2],*[FINE_ALIASES.get(p,p) for p in w[2:]]]
        elif w and w[0].startswith('X'):
            end=next((i for i,t in enumerate(w) if '=' in t),len(w))
            w=[w[0],*[FINE_ALIASES.get(n,n) for n in w[1:end-1]],*w[end-1:]]
        lines.append(' '.join(w))
    return '\n'.join(lines)+'\n'


def native_view(cells,bank,tail,g):
    used={c['model'] for c in g['cells']};library=''
    for model in sorted(used):
        text=tail if model==TAIL else cell_definition(cells,model)
        library+=native_component(text,model)
    top=['* Connectivity/LVS only; all routing R/C omitted, never use for timing.',f'.subckt {NAME} '+' '.join(g['ports'])]
    for c in g['cells']:
        top.append(c['native_name']+' '+' '.join(c['pins'][p] for p in g['orders'][c['model']])+' '+c['model'])
    top += ['.ends '+NAME,'']
    reference=''.join(collapse(cell_definition(cells,m)) for m in sorted(used-{TAIL}))+bank
    physical=library+'\n'.join(top)
    before=signature(reference,SOURCE);after=signature(physical,NAME)
    if before!=after:raise ValueError('Physical graph changed native devices, pins, body ties or parameters')
    counts=Counter(key[0] for key in after for _ in range(after[key]))
    digest=hashlib.sha256(json.dumps(sorted(after.items()),sort_keys=True).encode()).hexdigest()
    return physical,dict(native_model_counts=dict(counts),native_primitives=sum(counts.values()),
                          native_signature_sha256=digest,exact_native_connectivity_and_parameters_preserved=True)


def signature(text,top):
    definitions=native.definitions(text);leaves=Counter()
    def walk(model,mapping,path,ancestors):
        if model in ancestors:raise ValueError('Recursive physical native view')
        ports,body=definitions[model]
        if set(ports)!=set(mapping):raise ValueError('Native interface mapping changed')
        for w in body:
            if not w[0].startswith('X'):raise ValueError('LVS native view contains a non-native element')
            end=next((i for i,v in enumerate(w) if '=' in v),len(w));child=w[end-1]
            nodes=['0' if n=='0' else mapping.get(n,path+'__'+n) for n in w[1:end-1]]
            params=tuple(sorted(tuple(t.split('=',1)) for t in w[end:]))
            if child in definitions:
                if params or len(nodes)!=len(definitions[child][0]):raise ValueError('Parameterized or changed native hierarchy')
                walk(child,dict(zip(definitions[child][0],nodes)),path+'__'+w[0],ancestors|{model})
            elif child.startswith('sky130_fd_pr__'):
                count=2 if child==MIM else 4 if 'fet_' in child else None
                if count is None or len(nodes)!=count:raise ValueError('Unexpected native physical primitive')
                if child==MIM:nodes=sorted(nodes)
                leaves[(child,tuple(nodes),params)]+=1
            else:raise ValueError('Missing native definition')
    walk(top,{p:p for p in definitions[top][0]},'BANK',set())
    return leaves


def verify_json(data,g):
    modules=data['modules'];module=modules.get(NAME)
    if module is None or set(module['ports'])!=set(g['ports']):raise ValueError('Missing or changed physical top ports')
    scalar={n:i['bits'][0] for n,i in module['netnames'].items() if len(i['bits'])==1}
    nets=set(g['ports'])|{n for c in g['cells'] for n in c['pins'].values()}
    if (not nets<=set(scalar) or any(type(scalar[n]) is not int for n in nets)
            or len({scalar[n] for n in nets})!=len(nets)):
        raise ValueError('Physical nets are missing, constant or merged')
    for p in g['ports']:
        d='inout' if p in RAILS else 'output' if p=='OUT' else 'input'
        if module['ports'][p]!=dict(direction=d,bits=[scalar[p]]):raise ValueError('Physical top connection or direction changed')
    if set(module['cells'])!={c['name'] for c in g['cells']}:raise ValueError('Physical graph lost or added a component')
    for c in g['cells']:
        a=module['cells'][c['name']]
        if (a['type']!=c['model'] or a.get('parameters')
                or a['connections']!={p:[scalar[n]] for p,n in c['pins'].items()}
                or a['port_directions']!={p:direction(c['model'],p) for p in c['pins']}):
            raise ValueError('Physical component pin, body tie or model changed: '+c['name'])
        if any(int(a['attributes'].get(k,'0'),2)!=1 for k in ('keep','dont_touch')):
            raise ValueError('Physical component preservation attribute lost')
    if set(modules)!={NAME,*g['orders']}:raise ValueError('Physical hierarchy changed')
    for model,ports in g['orders'].items():
        a=modules[model]
        if (int(a['attributes'].get('blackbox','0'),2)!=1 or a.get('cells') or set(a['ports'])!=set(ports)
                or any(a['ports'][p]['direction']!=direction(model,p) for p in ports)):
            raise ValueError('Physical blackbox semantics changed')
    return dict(exact_native_component_graph_verified=True,components=len(g['cells']),
                explicit_body_and_supply_pins=True,qualified_phy=False,electrical_qualification_passed=False,
                scope='Named-pin physical netlist import only; no placement/routing, RC, timing, PVT or PHY admission')
