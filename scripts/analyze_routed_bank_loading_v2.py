#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Report passive loading and native terminal fanout on the routed bank path.

R connectivity is used only to identify logical DC nets. The extracted model
is never collapsed or changed for simulation. MOS/MIM intrinsic capacitance and
distributed timing cannot be inferred from these passive-capacitance totals.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import re
import subprocess
import native_clock_components_v2 as parsing
from reduce_rc import number
from probe_digital_dcc_v2 import sha,atomic
from spice_library import checked_netlist

ROOT=Path(__file__).resolve().parents[1]
VERSION='routed-bank-passive-loading-and-native-terminal-fanout-v2.1'


class Nets:
    def __init__(self):self.parents={}
    def root(self,n):
        self.parents.setdefault(n,n);p=n
        while self.parents[p]!=p:p=self.parents[p]
        while self.parents[n]!=n:
            old=self.parents[n];self.parents[n]=p;n=old
        return p
    def join(self,a,b):
        a,b=self.root(a),self.root(b)
        if a!=b:self.parents[b]=a


def loading(text,anchors):
    defs=parsing.definitions(text)
    if len(defs)!=1:raise ValueError('Require one flat routed bank')
    _,body=next(iter(defs.values()));nets=Nets();caps=[];resistors=[];devices=[]
    for original in body:
        w=' '.join(original).split('$',1)[0].split()
        if w[0][0].upper()=='R':
            if len(w)!=4 or number(w[3])<=0:raise ValueError('Nonpositive/unsupported resistor')
            nets.join(w[1],w[2]);resistors.append(w)
        elif w[0][0].upper()=='C':
            if len(w)!=4 or number(w[3])<0:raise ValueError('Negative/unsupported capacitor')
            for n in w[1:3]:nets.root(n)
            caps.append(w)
        elif w[0][0].upper()=='X':
            end=next((i for i,v in enumerate(w) if '=' in v),len(w));nodes=w[1:end-1]
            for n in nodes:nets.root(n)
            devices.append((w[0],nodes,w[end-1],dict(v.split('=',1) for v in w[end:])))
        else:raise ValueError('Unsupported routed-bank element')
    members=defaultdict(list)
    for n in list(nets.parents):members[nets.root(n)].append(n)
    names={};chosen={}
    for name,pattern in anchors.items():
        matches=[n for n in nets.parents if re.fullmatch(pattern,n)]
        roots={nets.root(n) for n in matches}
        if len(roots)!=1:raise ValueError('Missing or ambiguous logical net anchor: '+name)
        root=next(iter(roots))
        if root in names:raise ValueError('Distinct logical path nets are shorted')
        names[root]=name;chosen[name]=dict(root=root,matches=sorted(matches))
    counts=defaultdict(int)
    for w in resistors:counts[nets.root(w[1])]+=1
    result={}
    for name,anchor in chosen.items():
        root=anchor['root'];external=defaultdict(float);internal=0.;terminal_counts=defaultdict(int);widths=defaultdict(float);mims=[]
        for w in caps:
            a,b=map(nets.root,w[1:3]);value=number(w[3])*1e15
            if a==b==root:internal+=value
            elif a==root or b==root:
                other=b if a==root else a;external[names.get(other,'other_nets')]+=value
        for tag,nodes,model,params in devices:
            if 'nfet_' in model or 'pfet_' in model:
                if len(nodes)!=4:raise ValueError('Wrong native MOS port count')
                for terminal,n in zip(['drain','gate','source','bulk'],nodes):
                    if nets.root(n)==root:
                        terminal_counts[terminal]+=1;widths[terminal]+=number(params['w'])
            elif 'cap_mim_' in model and any(nets.root(n)==root for n in nodes):
                mims.append(dict(device=tag,width_um=number(params['w']),length_um=number(params['l'])))
        result[name]=dict(anchor_pattern=anchors[name],anchor_matches=anchor['matches'],rc_vertices=len(members[root]),
            resistor_elements=counts[root],external_parasitic_capacitance_ff=dict(external),
            total_external_parasitic_capacitance_ff=sum(external.values()),intra_net_distributed_capacitance_ff=internal,
            native_mos_terminal_counts=dict(terminal_counts),native_mos_terminal_width_um=dict(widths),direct_native_mim_devices=mims)
    return result


def analyze(parent):
    m=json.loads((parent/'manifest.json').read_text());i=m['identity']
    code='import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); import extract_dcdl_bank_rc_v2 as e; e.bound(Path(sys.argv[2]))'
    subprocess.run([i['tools']['python'],'-c',code,str(ROOT),str(parent)],check=True)
    report=json.loads((parent/'summary.json').read_text());info=report['extraction']
    if not report['passed'] or not report['rc_topology_passed']:raise ValueError('Require passing whole-bank RC/topology')
    text=checked_netlist(info)
    anchors=dict(IN='IN',f0=r'turn0\.B(?:\.t\d+)?',t0=r'merge0\.A(?:\.t\d+)?',
                 p0=r'merge0\.B(?:\.t\d+)?',r0=r'fine_unit30\.NODE(?:\.t\d+)?',OUT='OUT',VGND='VGND',VPWR='VPWR')
    result=loading(text,anchors)
    paths=[parent/'manifest.json',parent/'summary.json',ROOT/info['netlist'],Path(__file__),Path(parsing.__file__),
           ROOT/'scripts/reduce_rc.py',ROOT/'scripts/spice_library.py']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},anchors=anchors)
    out=ROOT/'build/diagnostics/routed_bank_loading_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'summary.json',dict(identity=identity,nets=result,qualified_phy=False,
        scope='Unmodified extracted passive loading and native terminal fanout; no intrinsic-capacitance, transient, reduced-model or timing qualification'))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(analyze(a.artifact.resolve()),flush=True)
