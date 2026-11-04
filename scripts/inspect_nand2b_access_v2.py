#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prove private inverter/stack LI access in the native NAND2B4 cell.

Only extraction labels change. Multiple stack nodes remain distinct and LVS
uses the exact original native MOS source with additional private-node ports.
"""
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import layout
import inspect_mim_switch_pcells_v2 as environment
from build_compound_drivers_v3 import cell_definition
from label_nand_mid_access_v2 import connected_labels
from lvs_utils import strict_setup,clean_match

ROOT=layout.ROOT
VERSION='native-nand2b-inverter-and-stack-private-li-access-v2.1'
MODELS=['nand2b_4']
sha=environment.sha


def private_nodes(source):
    ports=source.splitlines()[0].split()[2:];nodes=set()
    for line in source.splitlines()[1:-1]:
        w=line.split()
        if not w or w[0].startswith('*'):continue
        if not w[0].startswith('X') or len(w)<6 or not w[5].startswith('sky130_fd_pr__'):
            raise ValueError('Unexpected native clock cell transistor')
        nodes.update(w[1:5])
    result=sorted(nodes-set(ports))
    if any(re.fullmatch(r'a_\d+_\d+#',n) is None for n in result):raise ValueError('Unknown private-node coordinate')
    return result


def reference(source):
    nodes=private_nodes(source);mapping={n:'MID'+str(i) for i,n in enumerate(nodes)}
    lines=source.splitlines();lines[0]+=''.join(' '+n for n in mapping.values())
    text='\n'.join(lines)+'\n'
    for old,new in mapping.items():text=re.sub(r'(?<!\S)'+re.escape(old)+r'(?!\S)',new,text)
    return text,mapping


def annotate(text,mapping):
    if text.count('<< labels >>\n')!=1:raise ValueError('Missing native labels')
    numbers=[int(v) for v in re.findall(r'(?m)^port (\d+)',text)]
    if not numbers:raise ValueError('Missing native ports')
    labels=[];points={};layer=None
    for i,(private,name) in enumerate(mapping.items(),max(numbers)+1):
        a,b=re.fullmatch(r'a_(\d+)_(\d+)#',private).groups();x,y=int(a)+2,int(b)+2
        labels += [f'rlabel ndiff {x} {y} {x} {y} 0 {name}',f'port {i} nsew']
    for line in text.splitlines():
        if line.startswith('<< '):layer=line[3:-3]
        if not line.startswith('rect ') or layer!='locali':continue
        a,b,c,d=map(int,line.split()[1:])
        if c-a<34 or d-b<34:continue
        x,y=round((a+c)/2),round((b+d)/2);name='LI_'+str(len(points))
        points[name]=dict(coordinate_um=[x*layout.GRID,y*layout.GRID],rectangle_um=[v*layout.GRID for v in [a,b,c,d]])
        labels.append(f'rlabel locali {x} {y} {x} {y} 0 {name}')
    result=text.replace('<< labels >>\n','<< labels >>\n'+'\n'.join(labels)+'\n')
    if result.split('<< labels >>')[0]!=text.split('<< labels >>')[0]:raise ValueError('Native masks changed')
    return result,points


def inspect():
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';sc=pdk/'libs.ref/sky130_fd_sc_hd'
    pdks=[sc/'gds/sky130_fd_sc_hd.gds',sc/'spice/sky130_fd_sc_hd.spice',pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    code=[Path(__file__),Path(layout.__file__),Path(environment.__file__),ROOT/'scripts/build_compound_drivers_v3.py',ROOT/'scripts/label_nand_mid_access_v2.py',ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,models=MODELS,pdk_files={str(p):sha(p) for p in pdks},code={str(p.relative_to(ROOT)):sha(p) for p in code},tools=environment.tools())
    out=ROOT/'build/diagnostics/nand2b_access_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(identity,indent=2)+'\n')
    library=pdks[1].read_text();rows=[]
    for short in MODELS:
        model='sky130_fd_sc_hd__'+short;folder=out/short;folder.mkdir();source=cell_definition(library,model)
        extended,mapping=reference(source);(folder/'native_source.spice').write_text(source);(folder/'reference.spice').write_text(extended)
        layout.invoke_magic(folder,f'gds readonly false\ngds read {{{pdks[0]}}}\nload {model} -silent\nsave {{{folder/model}}}', 'native_geometry')
        native=folder/(model+'.mag');text,points=annotate(native.read_text(),mapping);probe=model+'_access_probe'
        (folder/(probe+'.mag')).write_text(text)
        layout.invoke_magic(folder,f'load {probe} -silent\nextract all\next2spice lvs\next2spice -o labelled.spice {probe}.ext','labelled')
        setup=strict_setup(folder/'setup.tcl',pdks[3]);log=folder/'lvs.log'
        process=subprocess.run(['netgen','-batch','lvs',f'{folder/"labelled.spice"} {probe}',f'{folder/"reference.spice"} {model}',str(setup),str(log)],cwd=folder,capture_output=True,text=True)
        (folder/'console.log').write_text(process.stdout+process.stderr)
        matched=clean_match(log.read_text() if log.exists() else '',process.returncode);ext=(folder/(probe+'.ext')).read_text();access={};groups={}
        for private,name in mapping.items():
            labels=connected_labels(ext,name);groups[name]=labels
            access[name]=dict(private_source_node=private,existing_li_access={n:p for n,p in points.items() if n in labels})
        distinct=all(not (a&b) for a,b in itertools.combinations(groups.values(),2))
        existing=all(a['existing_li_access'] for a in access.values())
        files=[native,folder/(probe+'.mag'),folder/(probe+'.ext'),folder/'native_source.spice',folder/'reference.spice',folder/'labelled.spice',log]
        row=dict(model=model,private_nodes=access,topology_passed=matched,private_nodes_distinct=distinct,
            all_private_nodes_have_existing_li_access=existing,native_mask_geometry_unchanged=True,
            files={str(p.relative_to(ROOT)):sha(p) for p in files},qualified_phy=False)
        rows.append(row);(folder/'summary.json').write_text(json.dumps(row,indent=2)+'\n')
    if any(sha(Path(n))!=h for n,h in identity['pdk_files'].items()):raise ValueError('Native PDK changed')
    result=dict(identity=identity,rows=rows,passed=all(r['topology_passed'] and r['private_nodes_distinct'] and r['all_private_nodes_have_existing_li_access'] for r in rows),
        qualified_phy=False,scope='Label-only native cell access and exact-source topology proof; no added contacts, shunts, DRC, RC or clock timing admission')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return out


if __name__=='__main__':print(inspect(),flush=True)
