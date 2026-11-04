#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prove native LI access for the ten diagnosed FF guard targets.

Only labels/ports change; native masks and MOS geometry remain exact. FF
private-node coordinate anchors may lie in N/P diffusion or native polysilicon.
No guard geometry, new contact, DRC, RC or electrical admission follows.
"""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import inspect_clock_cell_access_v2 as access
import diagnose_native_ff_reset_guards_v2 as diagnosis

ROOT=access.ROOT
sha=access.sha
VERSION='native-guarded-ff-diffusion-or-poly-private-li-access-v2.2'
MODEL='sky130_fd_sc_hd__dfrtp_1'


def reference(source,selected):
    available=set(access.private_nodes(source))
    if not selected or len(set(selected))!=len(selected) or not set(selected)<=available:
        raise ValueError('Guard target is not an actual native private terminal')
    mapping={n:'GUARD'+str(i) for i,n in enumerate(sorted(selected))}
    lines=source.splitlines();lines[0]+=''.join(' '+n for n in mapping.values())
    text='\n'.join(lines)+'\n'
    for old,new in mapping.items():text=re.sub(r'(?<!\S)'+re.escape(old)+r'(?!\S)',new,text)
    return text,mapping


def annotate(text,mapping):
    # Reuse the native LI survey, replacing only its diffusion label choices.
    result,points=access.annotate(text,mapping);layer=None;rectangles={}
    for line in text.splitlines():
        if line.startswith('<< '):layer=line[3:-3]
        if line.startswith('rect '):rectangles.setdefault(layer,[]).append(list(map(int,line.split()[1:])))
    for private,name in mapping.items():
        a,b=re.fullmatch(r'a_(\d+)_(\d+)#',private).groups();x,y=int(a)+2,int(b)+2
        choices=[layer for layer in ['ndiff','pdiff','poly'] if any(r[0]<=x<r[2] and r[1]<=y<r[3] for r in rectangles.get(layer,[]))]
        if len(choices)!=1:raise ValueError('Missing or ambiguous actual private conductor access: '+private)
        original=f'rlabel ndiff {x} {y} {x} {y} 0 {name}'
        if result.count(original)!=1:raise ValueError('Native private label changed')
        result=result.replace(original,f'rlabel {choices[0]} {x} {y} {x} {y} 0 {name}')
    if result.split('<< labels >>')[0]!=text.split('<< labels >>')[0]:raise ValueError('Native masks changed')
    return result,points


def inspect(targets):
    proof=json.loads((targets/'summary.json').read_text());i=proof['identity']
    if (i['version']!=diagnosis.VERSION or targets.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or not proof['all_violations_have_private_candidates'] or len(proof['selected_private_nodes'])!=10
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):raise ValueError('Require exact diagnosed FF guard targets')
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';sc=pdk/'libs.ref/sky130_fd_sc_hd'
    pdks=[sc/'gds/sky130_fd_sc_hd.gds',sc/'spice/sky130_fd_sc_hd.spice',pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    if str(pdks[1])!=i['source_library'] or sha(pdks[1])!=i['source_library_sha256']:raise ValueError('Native FF source library changed')
    code=[Path(__file__),Path(access.__file__),Path(diagnosis.__file__),Path(access.layout.__file__),Path(access.environment.__file__),
          ROOT/'scripts/build_compound_drivers_v3.py',ROOT/'scripts/label_nand_mid_access_v2.py',ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,model=MODEL,selected_private_nodes=proof['selected_private_nodes'],targets=str(targets.relative_to(ROOT)),
        inputs={str((targets/'summary.json').relative_to(ROOT)):sha(targets/'summary.json')},
        pdk_files={str(p):sha(p) for p in pdks},code={str(p.relative_to(ROOT)):sha(p) for p in code},tools=access.environment.tools())
    out=ROOT/'build/diagnostics/guarded_ff_access_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(identity,indent=2)+'\n')
    source=access.cell_definition(pdks[1].read_text(),MODEL);extended,mapping=reference(source,identity['selected_private_nodes'])
    (out/'native_source.spice').write_text(source);(out/'reference.spice').write_text(extended)
    access.layout.invoke_magic(out,f'gds readonly false\ngds read {{{pdks[0]}}}\nload {MODEL} -silent\nsave {{{out/MODEL}}}','native_geometry')
    native=out/(MODEL+'.mag');text,points=annotate(native.read_text(),mapping);probe=MODEL+'_guard_access_probe'
    (out/(probe+'.mag')).write_text(text)
    access.layout.invoke_magic(out,f'load {probe} -silent\nextract all\next2spice lvs\next2spice -o labelled.spice {probe}.ext','labelled')
    setup=access.strict_setup(out/'setup.tcl',pdks[3]);log=out/'lvs.log'
    proc=subprocess.run(['netgen','-batch','lvs',f'{out/"labelled.spice"} {probe}',f'{out/"reference.spice"} {MODEL}',str(setup),str(log)],cwd=out,capture_output=True,text=True)
    (out/'console.log').write_text(proc.stdout+proc.stderr);matched=access.clean_match(log.read_text() if log.exists() else '',proc.returncode)
    ext=(out/(probe+'.ext')).read_text();nodes={};groups={}
    for private,name in mapping.items():
        labels=access.connected_labels(ext,name);groups[name]=labels
        nodes[name]=dict(private_source_node=private,existing_li_access={n:p for n,p in points.items() if n in labels})
    distinct=all(not(a&b) for a,b in itertools.combinations(groups.values(),2));existing=all(n['existing_li_access'] for n in nodes.values())
    files=[native,out/(probe+'.mag'),out/(probe+'.ext'),out/'native_source.spice',out/'reference.spice',out/'labelled.spice',log]
    if any(sha(Path(n))!=h for n,h in identity['pdk_files'].items()):raise ValueError('Native PDK changed')
    result=dict(identity=identity,model=MODEL,private_nodes=nodes,topology_passed=matched,private_nodes_distinct=distinct,
        all_selected_nodes_have_existing_li_access=existing,native_mask_geometry_unchanged=True,
        passed=bool(matched and distinct and existing),files={str(p.relative_to(ROOT)):sha(p) for p in files},qualified_phy=False,
        scope='Label-only native FF access and exact-source topology proof for ten diagnosed targets; no added contacts, guards, DRC, RC or timing admission')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(inspect(a.artifact.resolve()),flush=True)
