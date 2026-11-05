# SPDX-License-Identifier: GPL-3.0-only
"""Map physical extraction aliases to canonical controls without changing RC."""
from collections import Counter,defaultdict
import re
import shlex
import native_clock_components_v2 as native
from native_bank_inventory_v51 import exact_number


class Union:
    def __init__(self):self.parent={}
    def find(self,n):
        self.parent.setdefault(n,n)
        if self.parent[n]!=n:self.parent[n]=self.find(self.parent[n])
        return self.parent[n]
    def join(self,a,b):
        a,b=self.find(a),self.find(b)
        if a!=b:self.parent[b]=a


def instances(mag,plan):
    if 'magscale 1 2\n' not in mag:raise ValueError('Require actual 5 nm Magic coordinate scale')
    wanted={(c['model'],*[round(v/.005) for v in plan['placements'][c['name']]]):c['name'] for c in plan['cells']}
    result={};current=None
    for line in mag.splitlines():
        w=line.split()
        if w and w[0]=='use':current=w[1:3]
        elif w and w[0]=='transform' and current:
            m,name=current;values=list(map(int,w[1:]));current=None
            if m not in {c['model'] for c in plan['cells']}:continue
            if values[:2]+values[3:5]!=[1,0,0,1]:raise ValueError('Unexpected rotated native instance')
            key=(m,values[2],values[5])
            if key not in wanted or wanted[key] in result:raise ValueError('Magic instance differs from placed source')
            result[wanted[key]]=name
    if set(result)!={c['name'] for c in plan['cells']}:raise ValueError('Missing original physical cell in Magic')
    return result


def mapping(mag,ext,rc,graph,plan):
    names=instances(mag,plan);u=Union();observed=set()
    for line in ext.splitlines():
        if not line.startswith(('node ','equiv ','port ')):continue
        w=shlex.split(line)
        observed.add(w[1]);u.find(w[1])
        if w[0]=='equiv':observed.add(w[2]);u.join(w[1],w[2])
    assignments=[]
    for c in graph['cells']:
        for pin,net in c['pins'].items():
            alias=names[c['name']]+'.'+pin
            # Well-only pins can disappear into their continuous substrate;
            # physical bulk connectivity is already required by native LVS.
            if alias not in observed:
                if pin in ('VNB','VPB'):continue
                raise ValueError('Missing native extraction alias: '+alias)
            assignments.append((alias,net))
    vertices=set();defs=native.definitions(rc)
    if set(defs)!={graph['top']}:raise ValueError('Require one actual flat joint RC bank')
    ports,body=defs[graph['top']]
    if ports!=graph['ports']:raise ValueError('Joint RC public order differs')
    for w in body:
        if w[0][0].upper()=='R':u.join(w[1],w[2]);vertices.update(w[1:3])
        elif w[0][0].upper()=='X':
            end=next((i for i,t in enumerate(w) if '=' in t),len(w));vertices.update(w[1:end-1])
    for n in vertices:
        base=re.sub(r'\.t\d+$','',n)
        if base in observed:u.join(n,base)
    labels=defaultdict(set)
    for alias,net in assignments:labels[u.find(alias)].add(net)
    for port in graph['ports']:
        if port not in observed:raise ValueError('Missing native public extraction alias')
        labels[u.find(port)].add(port)
    if any(len(values)!=1 for values in labels.values()):raise ValueError('Physical alias/R network joins different logical nets')
    labelled={n:next(iter(labels[u.find(n)])) for n in vertices if labels.get(u.find(n))}
    canonical=set(graph['ports'])|{n for c in graph['cells'] for n in c['pins'].values()}
    if set(labelled.values())!=canonical:raise ValueError('Not all canonical nets have actual RC observations')
    devices=native.mapped_mos(rc,graph['top'],{p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in ports},'XD')
    byname={d['name'].split(':')[-1]:d for d in devices};gates=[]
    for w in body:
        if not w[0].upper().startswith('X'):continue
        end=next((i for i,t in enumerate(w) if '=' in t),len(w));model=w[end-1]
        if 'fet_' not in model:continue
        p=dict(t.split('=',1) for t in w[end:]);width=exact_number(p['w'])
        kind='tg' if (model.endswith('nfet_01v8_lvt') and width==exact_number('1.68')) or (model.endswith('pfet_01v8') and width==exact_number('3.36')) else 'fine' if (model.endswith('nfet_01v8') and width==exact_number('.42')) or (model.endswith('pfet_01v8') and width==exact_number('.84')) else None
        if kind is None:continue
        node=w[2];label=labelled.get(node)
        pattern=r'en(?:_b)?[01]_[0-3]' if kind=='tg' else r'fine(?:_b)?\d+'
        if label is None or re.fullmatch(pattern,label) is None:raise ValueError('Native programming gate lacks its logical control label')
        gates.append(dict(device=byname[w[0]]['name'],gate_node=byname[w[0]]['terminals'][1],control=label,kind=kind))
    if len(devices)!=903 or Counter(g['kind'] for g in gates)!=Counter(fine=93,tg=40):raise ValueError('Incomplete actual MOS or programming-gate coverage')
    controls=[]
    for d in devices:
        for node in d['terminals']:
            raw=node[3:] if node.startswith('XD:') else 'VPWR' if node=='VDD' else 'VGND' if node=='0' else node
            label=labelled.get(raw)
            if label and re.fullmatch(r'(?:select(?:_b)?\d+|fine(?:_b)?\d+|en(?:_b)?[01]_[0-3])',label):
                controls.append(dict(node=node,control=label))
    controls=[dict(node=n,control=c) for n,c in sorted({(r['node'],r['control']) for r in controls})]
    return dict(devices=devices,programming_gates=gates,controls=controls,magic_instance_names=names,
                observed_canonical_nets=len(canonical),physical_instances=len(names),rc_model_changed=False)
