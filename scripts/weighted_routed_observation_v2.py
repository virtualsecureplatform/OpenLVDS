# SPDX-License-Identifier: GPL-3.0-only
"""Observe routed controls through Magic aliases and actual resistor components.

Union operations identify observation groups only; they never change SPICE.
Every low-voltage MOS terminal is retained for the six-pair voltage screen.
"""
import re
import shlex
from collections import Counter,defaultdict

MOS={'sky130_fd_pr__nfet_01v8','sky130_fd_pr__pfet_01v8','sky130_fd_pr__pfet_01v8_hvt'}
PASSIVE={'sky130_fd_pr__cap_mim_m3_1','sky130_fd_pr__res_generic_po'}
DIODE='sky130_fd_pr__diode_pw2nd_05v5'


class Groups:
    def __init__(self):self.parent={}
    def root(self,n):
        self.parent.setdefault(n,n)
        p=n
        while self.parent[p]!=p:p=self.parent[p]
        while n!=p:
            following=self.parent[n];self.parent[n]=p;n=following
        return p
    def join(self,a,b):self.parent[self.root(b)]=self.root(a)


def observations(text,ext,top):
    # definitions() deliberately rejects R/C; parse the flat SPICE statements here.
    rows=[];ports=[];active=False
    for line in text.splitlines():
        w=line.split('$',1)[0].split()
        if not w or w[0].startswith('*'):continue
        if w[0].lower()=='.subckt':
            if active or ports or w[1]!=top:raise ValueError('Require one exact flat routed-bank model')
            ports=w[2:];active=True
        elif w[0]=='+':
            if not active or rows:raise ValueError('Unexpected routed SPICE continuation')
            ports+=w[1:]
        elif w[0].lower()=='.ends':active=False
        elif active:rows.append(w)
        else:raise ValueError('Statement outside flat routed model')
    if active or len(set(ports))!=len(ports) or not ports:raise ValueError('Invalid flat model or terminal list')
    wires=Groups();nodes=set();devices=[];primitives=Counter();names=set()
    def observed(n):
        return '0' if n in ['0','VGND'] else 'VDD' if n=='VPWR' else n if n in ports else 'XD:'+n
    for w in rows:
        if w[0] in names:raise ValueError('Duplicate routed element')
        names.add(w[0]);kind=w[0][0].upper()
        if kind in ['R','C']:
            if len(w)!=4:raise ValueError('Malformed flat RC element')
            nodes.update(w[1:3])
            if kind=='R':wires.join(w[1],w[2])
        elif kind=='X':
            end=next((i for i,t in enumerate(w) if '=' in t),len(w))
            model=w[end-1];terminals=w[1:end-1];nodes.update(terminals);primitives[model]+=1
            if model in MOS:
                if len(terminals)!=4:raise ValueError('Routed MOS terminal count changed')
                devices.append(dict(name='XD:'+w[0],model=model,terminals=[observed(n) for n in terminals],limit_v=1.95))
            elif model in PASSIVE or model==DIODE:
                if len(terminals)!=2:raise ValueError('Routed passive/diode terminal count changed')
            else:raise ValueError('Unrecognized routed primitive '+model)
        else:raise ValueError('Unsupported routed element '+w[0])
    if not devices:raise ValueError('Missing routed MOS observations')
    aliases=Groups();canonical=set()
    for line in ext.splitlines():
        if not line.startswith(('node ','equiv ')):continue
        w=shlex.split(line)
        if w[0]=='node':canonical.add(w[1]);aliases.root(w[1])
        elif w[0]=='equiv':aliases.join(w[1],w[2])
    bases=defaultdict(list)
    for n in canonical:bases[aliases.root(n)].append(n)
    components=defaultdict(list)
    for n in nodes:components[wires.root(n)].append(n)
    controls=[];used=set()
    selections=[('coarse',i,[f'coarse_buffer{i}.X',f'forward{i}.B',f'turn{i}.A_N',f'pass{i}.B']) for i in range(15)]
    selections += [(kind,i,pins) for i in range(5) for kind,pins in [
        ('fine',[f'fine_buffer{i}.X',f'fine_inverse{i}.A',f'fine{i}.EN']),
        ('fine_b',[f'fine_inverse{i}.Y',f'fine{i}.ENB'])]]
    for kind,bit,pins in selections:
        if any(p not in aliases.parent for p in pins) or len({aliases.root(p) for p in pins})!=1:
            raise ValueError('Native routed control pin aliases do not agree: '+str(pins))
        labels=bases[aliases.root(pins[0])]
        if len(labels)!=1:raise ValueError('Ambiguous native extraction control net')
        base=labels[0]
        seeds=[n for n in nodes if n==base or re.fullmatch(re.escape(base)+r'\.[nt]\d+',n)]
        roots={wires.root(n) for n in seeds}
        if len(roots)!=1:raise ValueError('Missing or disconnected routed control resistor component: '+base)
        root=roots.pop();group=sorted(components[root])
        if root in used or set(group)&set(ports):raise ValueError('Routed controls short one another or a public terminal')
        used.add(root)
        controls.append(dict(kind=kind,bit=bit,pins=pins,canonical_net=base,nodes=[observed(n) for n in group]))
    return dict(devices=devices,controls=controls,primitive_counts=dict(sorted(primitives.items())),ports=ports)
