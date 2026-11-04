#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Find actual LI access to native NAND stack nodes without changing masks.

Expose MID as an extraction port and prove it against the exact native source.
Candidate LI labels identify existing conductors on that same electrical node.
This does not add a contact, capacitor, routable abstraction or timing proof.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import layout
import inspect_nand_stack_access_v2 as original
import inspect_mim_switch_pcells_v2 as environment
from lvs_utils import strict_setup,clean_match

ROOT=layout.ROOT
VERSION='native-nand-labelled-mid-li-access-v2.1'
sha=environment.sha


def annotate(text,private):
    match=re.fullmatch(r'a_(\d+)_(\d+)#',private)
    if match is None:raise ValueError('Unexpected source stack coordinate')
    x,y=[int(v)+2 for v in match.groups()];numbers=[int(v) for v in re.findall(r'(?m)^port (\d+)',text)]
    if not numbers or text.count('<< labels >>\n')!=1:raise ValueError('Missing native cell ports/labels')
    labels=[f'rlabel ndiff {x} {y} {x} {y} 0 MID',f'port {max(numbers)+1} nsew'];points={};layer=None
    for line in text.splitlines():
        if line.startswith('<< '):layer=line[3:-3]
        if line.startswith('rect ') and layer=='locali':
            a,b,c,d=map(int,line.split()[1:])
            if c-a<34 or d-b<34:continue
            px,py=round((a+c)/2),round((b+d)/2);name=f'LI_{len(points)}'
            points[name]=dict(coordinate_um=[px*layout.GRID,py*layout.GRID],rectangle_um=[v*layout.GRID for v in [a,b,c,d]])
            labels.append(f'rlabel locali {px} {py} {px} {py} 0 {name}')
    result=text.replace('<< labels >>\n','<< labels >>\n'+'\n'.join(labels)+'\n')
    if result.split('<< labels >>')[0]!=text.split('<< labels >>')[0]:raise ValueError('Native mask geometry changed')
    return result,points


def source_with_mid(text,private):
    if private not in original.private_nodes(text):raise ValueError('Unknown native stack node')
    lines=text.splitlines();lines[0]+=' MID'
    return re.sub(r'(?<!\S)'+re.escape(private)+r'(?!\S)','MID','\n'.join(lines)+'\n')


def connected_labels(text,label):
    parents={}
    def root(n):
        parents.setdefault(n,n)
        if parents[n]!=n:parents[n]=root(parents[n])
        return parents[n]
    for a,b in re.findall(r'(?m)^equiv "([^"]+)" "([^"]+)"',text):parents[root(b)]=root(a)
    target=root(label)
    return {n for n in list(parents) if root(n)==target}


def build(parent):
    pm=json.loads((parent/'manifest.json').read_text());report=json.loads((parent/'summary.json').read_text())
    if pm['version']!=original.VERSION or report['identity']!=pm:raise ValueError('Wrong native inspection')
    if any(sha(Path(n))!=h for n,h in pm['pdk_files'].items()):raise ValueError('Native inspection PDK changed')
    files=[parent/'manifest.json',parent/'summary.json'];rows=[]
    selected=[r for r in report['rows'] if r['model'].endswith(('nand2_2','nand2_8'))]
    if len(selected)!=2:raise ValueError('Require the actual drive-2 and output NAND models')
    for row in selected:
        folder=parent/row['model'].removeprefix('sky130_fd_sc_hd__');mag=folder/(row['model']+'.mag');src=folder/'native_source.spice'
        if sha(mag)!=row['mag_sha256'] or sha(src)!=row['source_sha256']:raise ValueError('Native masks/source changed')
        files += [mag,src]
    setup=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl'
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
        code={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),Path(original.__file__),Path(layout.__file__),ROOT/'scripts/lvs_utils.py']},
        tools=environment.tools(),netgen_setup=str(setup),netgen_setup_sha256=sha(setup))
    out=ROOT/'build/diagnostics/nand_mid_access_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(identity,indent=2)+'\n')
    for row in selected:
        model=row['model'];source=parent/model.removeprefix('sky130_fd_sc_hd__');folder=out/model;folder.mkdir()
        text=(source/'native_source.spice').read_text();private=original.private_nodes(text)
        if len(private)!=1:raise ValueError('Require one explicit native NAND stack net')
        annotated,points=annotate((source/(model+'.mag')).read_text(),private[0]);name=model+'_mid_probe'
        (folder/(name+'.mag')).write_text(annotated);(folder/'reference.spice').write_text(source_with_mid(text,private[0]))
        layout.invoke_magic(folder,f'load {name} -silent\nextract all\next2spice lvs\next2spice -o labelled.spice {name}.ext','labelled')
        tech=strict_setup(folder/'setup.tcl',setup);log=folder/'lvs.log'
        process=subprocess.run(['netgen','-batch','lvs',f'{folder/"labelled.spice"} {name}',f'{folder/"reference.spice"} {model}',
            str(tech),str(log)],cwd=folder,capture_output=True,text=True)
        (folder/'console.log').write_text(process.stdout+process.stderr)
        matched=clean_match(log.read_text() if log.exists() else '',process.returncode)
        labels=connected_labels((folder/(name+'.ext')).read_text(),'MID')
        access={n:p for n,p in points.items() if n in labels}
        rows.append(dict(model=model,private_source_node=private[0],mid_topology_passed=matched,
            existing_li_access=access,labels_only=True,native_mask_geometry_unchanged=True,qualified_phy=False))
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Native inspection changed during labelling')
    result=dict(rows=rows,mid_topology_passed=all(r['mid_topology_passed'] for r in rows),
        all_mid_nodes_have_existing_li_access=all(r['existing_li_access'] for r in rows),qualified_phy=False,
        scope='Label-only electrical MID-port matching and existing LI access inspection; no added masks, contact, DRC, RC or timing admission')
    (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');return out


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(build(a.artifact.resolve()),flush=True)
