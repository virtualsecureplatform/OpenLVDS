#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Prove the separated pair changes only permitted routing, preserving natives."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import build_nand2b_guard_pair_v4 as previous
import build_nand2b_separated_pair_v3 as candidate
import verify_nand2b_separated_output_v3 as child_proof

ROOT=candidate.ROOT
VERSION='native-nand2b-separated-pair-mask-source-proof-v3.1'
CONTEXT='nand2b_separated_pair_proof_v3'
sha=candidate.sha


def masks(a_path,b_path):
    import klayout.db as kdb
    a=kdb.Layout();a.read(str(a_path));b=kdb.Layout();b.read(str(b_path))
    if a.dbu!=b.dbu:raise ValueError('Pair GDS coordinate grid changed')
    rename={previous.NAME:candidate.NAME,previous.CHILD:candidate.CHILD}
    names={c.name for c in a.each_cell()};targets={c.name for c in b.each_cell()}
    if {rename.get(n,n) for n in names}!=targets:raise ValueError('Pair native/guard hierarchy changed')
    layers=sorted({(i.layer,i.datatype) for layout in [a,b] for i in layout.layer_infos()});changes={}
    for name in sorted(names):
        other=rename.get(name,name)
        def places(layout,cell,normalize):
            return Counter((normalize.get(layout.cell(i.cell_index).name,layout.cell(i.cell_index).name),i.cplx_trans.to_s(),
                            i.a.x,i.a.y,i.b.x,i.b.y,i.na,i.nb) for i in layout.cell(cell).each_inst())
        if places(a,name,rename)!=places(b,other,{}):raise ValueError('Native pair placement changed: '+name)
        changed=[]
        for layer in layers:
            if name in rename:
                ra=kdb.Region(a.cell(name).shapes(a.layer(kdb.LayerInfo(*layer))))
                rb=kdb.Region(b.cell(other).shapes(b.layer(kdb.LayerInfo(*layer))))
            else:
                ra=kdb.Region(a.cell(name).begin_shapes_rec(a.layer(kdb.LayerInfo(*layer))))
                rb=kdb.Region(b.cell(other).begin_shapes_rec(b.layer(kdb.LayerInfo(*layer))))
            if not (ra^rb).is_empty():changed.append(tuple(layer))
        allowed=({(70,20),(70,44),(71,20),(71,16)} if name==previous.NAME else
                 {(69,20),(69,44),(70,20),(70,16)} if name==previous.CHILD else set())
        if set(changed)-allowed:raise ValueError('Unexpected native/non-routing mask change: '+name+' '+str(changed))
        if changed:changes[name]=changed
    if set(changes)!={previous.NAME,previous.CHILD}:raise ValueError('Missing explicit child and pair routing change')
    direct=list(b.cell(candidate.NAME).each_inst())
    if len(direct)!=2 or any(b.cell(i.cell_index).name!=candidate.CHILD for i in direct):raise ValueError('Require exactly two native guarded children')
    return dict(native_cell_masks_identical=True,all_child_placements_identical=True,
        compared_cells=len(names),compared_layers=len(layers),routing_changes=changes,paired_children=2)


def verify(original,repaired,proof):
    previous.bound(original);cm=candidate.bound(repaired);child_proof.bound(proof,ROOT/cm['identity']['parent'])
    old=json.loads((original/'summary.json').read_text());new=json.loads((repaired/'summary.json').read_text())
    if not old['passed'] or not new['passed'] or len(old['rows'])!=1 or len(new['rows'])!=1:raise ValueError('Require both clean native pairs')
    before=old['rows'][0];after=new['rows'][0];a=child_proof.clean_row(original,before);b=child_proof.clean_row(repaired,after)
    old_text=(a/(previous.NAME+'.sch.spice')).read_text();new_text=(b/(candidate.NAME+'.sch.spice')).read_text()
    if old_text.replace(previous.NAME,candidate.NAME).replace(previous.CHILD,candidate.CHILD)!=new_text:
        raise ValueError('Native pair source changed beyond the proven model-name mapping')
    if before['placement']!=after['placement']:raise ValueError('Paired native child placement changed')
    for pin in previous.PORTS:
        expected=dict(before['ports'][pin])
        if pin=='Y':expected['y_um']=10.
        if after['ports'][pin]!=expected:raise ValueError('Unexpected pair pin change: '+pin)
    result=masks(a/(previous.NAME+'.gds'),b/(candidate.NAME+'.gds'))
    paths=[proof/'summary.json',Path(__file__),Path(previous.__file__),Path(candidate.__file__),Path(child_proof.__file__)]
    for parent,name in [(original,previous.NAME),(repaired,candidate.NAME)]:
        paths += [parent/n for n in ['manifest.json','summary.json','state.json']]
        paths += [parent/name/n for n in ['summary.json',name+'.gds',name+'.lef',name+'.sch.spice',name+'.drc_count.txt',name+'.lvs.log']]
    identity=dict(version=VERSION,original=str(original.relative_to(ROOT)),repaired=str(repaired.relative_to(ROOT)),
        child_proof=str(proof.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Pair source/mask comparison changed')
    out.mkdir(parents=True,exist_ok=False);(out/'summary.json').write_text(json.dumps(dict(identity=identity,proof=result,
        source_identical_except_proven_model_names=True,passed=True,qualified_phy=False,electrical_qualification_passed=False,
        scope='Unchanged native masks/source/placements with separated child/pair output routing; no coupling or electrical timing admission'),indent=2)+'\n');return out


def bound(out,parent):
    r=json.loads((out/'summary.json').read_text());i=r['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['repaired']!=str(parent.relative_to(ROOT)) or r['passed'] is not True
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):raise ValueError('Native pair proof context changed')
    previous.bound(ROOT/i['original']);m=candidate.bound(parent);child_proof.bound(ROOT/i['child_proof'],ROOT/m['identity']['parent']);return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('repaired',type=Path);p.add_argument('--child-proof',type=Path,required=True);a=p.parse_args()
    print(verify(a.original.resolve(),a.repaired.resolve(),a.child_proof.resolve()),flush=True)
