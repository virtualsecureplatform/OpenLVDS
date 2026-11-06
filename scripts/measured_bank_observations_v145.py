# SPDX-License-Identifier: GPL-3.0-only
"""Map actual balanced-bank RC terminals using physical instances and aliases.

Never infer missing signal/control aliases. Keep every RC-separated native
terminal, and verify programming gates against each physical macro's pins.
"""
from collections import Counter,defaultdict
import re
import shlex
import regenerated_bank_observations_v60 as original
from dcdl_tg_tree_v5 import control_targets

native=original.native
number=original.exact_number
TG='openlvds_tg_quad_stacked_nlvt_v27'
FINE='openlvds_fine_moscap_w126_middle_v124'
N='sky130_fd_pr__nfet_01v8'
NLVT='sky130_fd_pr__nfet_01v8_lvt'
P='sky130_fd_pr__pfet_01v8'


def expected_programming(graph):
    expected=Counter();counts=Counter()
    for cell in graph['cells']:
        pins=cell['pins']
        if cell['model']==TG:
            expected[('tg',NLVT,'1.68',pins['EN'])]+=1;expected[('tg',P,'3.36',pins['ENB'])]+=1;counts['tg']+=1
        elif cell['model']==FINE:
            expected[('fine',N,'.42',pins['CTRL'])]+=1;expected[('fine',N,'.42',pins['CTRL_B'])]+=1
            expected[('fine',P,'.84',pins['CTRL_B'])]+=1;counts['fine']+=1
    if counts!=Counter(tg=40,fine=31):raise ValueError('Require all 40 balanced TG and 31 fine macros')
    return Counter((kind,model,number(width),control) for (kind,model,width,control),n in expected.items() for _ in range(n))


def aliases(mag,ext,rc,graph,plan):
    names=original.instances(mag,plan);u=original.Union();observed=set()
    for line in ext.splitlines():
        if not line.startswith(('node ','equiv ','port ')):continue
        w=shlex.split(line);observed.add(w[1]);u.find(w[1])
        if w[0]=='equiv':observed.add(w[2]);u.join(w[1],w[2])
    assignments=[]
    for cell in graph['cells']:
        for pin,net in cell['pins'].items():
            alias=names[cell['name']]+'.'+pin
            if alias not in observed:
                if pin in ('VNB','VPB'):continue
                raise ValueError('Missing native extraction alias: '+alias)
            assignments.append((alias,net))
    definitions=native.definitions(rc)
    if set(definitions)!={graph['top']}:raise ValueError('Require one actual flat measured joint RC bank')
    ports,body=definitions[graph['top']]
    if ports!=graph['ports']:raise ValueError('Measured joint RC public order differs')
    vertices=set()
    for w in body:
        if w[0][0].upper()=='R':u.join(w[1],w[2]);vertices.update(w[1:3])
        elif w[0][0].upper()=='X':
            end=next((k for k,t in enumerate(w) if '=' in t),len(w));vertices.update(w[1:end-1])
    for node in vertices:
        base=re.sub(r'\.t\d+$','',node)
        if base in observed:u.join(node,base)
    labels=defaultdict(set)
    for alias,net in assignments:labels[u.find(alias)].add(net)
    for port in graph['ports']:
        if port not in observed:raise ValueError('Missing native public extraction alias')
        labels[u.find(port)].add(port)
    if any(len(values)!=1 for values in labels.values()):raise ValueError('Physical aliases/R network join different logical nets')
    labelled={n:next(iter(labels[u.find(n)])) for n in vertices if labels.get(u.find(n))}
    canonical=set(graph['ports'])|{net for c in graph['cells'] for net in c['pins'].values()}
    if set(labelled.values())!=canonical:raise ValueError('Missing actual RC observations for canonical nets')
    return names,labelled,body,len(canonical)


def mapping(mag,ext,rc,graph,plan,profile):
    if profile not in ('b2','b3'):raise ValueError('Unknown measured bank profile')
    expected=expected_programming(graph);names,labelled,body,canonical_count=aliases(mag,ext,rc,graph,plan)
    ports=graph['ports'];devices=native.mapped_mos(rc,graph['top'],{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports},'XD')
    byname={d['name'].split(':')[-1]:d for d in devices};gates=[];actual=Counter()
    kinds={(NLVT,number('1.68')):'tg',(P,number('3.36')):'tg',(N,number('.42')):'fine',(P,number('.84')):'fine'}
    for w in body:
        if not w[0].upper().startswith('X'):continue
        end=next((k for k,t in enumerate(w) if '=' in t),len(w));model=w[end-1]
        if 'fet_' not in model:continue
        params=dict(t.split('=',1) for t in w[end:]);width=number(params['w']);kind=kinds.get((model,width))
        if kind is None:continue
        label=labelled.get(w[2]);pattern=r'en(?:_b)?[01]_[0-3]' if kind=='tg' else r'fine(?:_b)?\d+'
        if label is None or re.fullmatch(pattern,label) is None:raise ValueError('Programming gate lacks its actual logical control label')
        actual[(kind,model,width,label)]+=1
        gates.append(dict(device=byname[w[0]]['name'],gate_node=byname[w[0]]['terminals'][1],control=label,kind=kind))
    if actual!=expected or len(gates)!=173 or len(devices)!=(1453 if profile=='b2' else 1773):
        raise ValueError('Incomplete actual native MOS or typed per-control programming-gate coverage')
    targets=set(control_targets(0,0));controls=set()
    for device in devices:
        for node in device['terminals']:
            raw=node[3:] if node.startswith('XD:') else 'VPWR' if node=='VDD' else 'VGND' if node=='0' else node
            label=labelled.get(raw)
            if label in targets:controls.add((node,label))
    if {c for _,c in controls}!=targets or len(targets)!=86:raise ValueError('Missing actual terminal observations for a logical control')
    return dict(devices=devices,programming_gates=gates,controls=[dict(node=n,control=c) for n,c in sorted(controls)],
                magic_instance_names=names,observed_canonical_nets=canonical_count,logical_controls=sorted(targets),
                physical_instances=len(names),typed_per_control_gate_coverage_verified=True,rc_model_changed=False)
