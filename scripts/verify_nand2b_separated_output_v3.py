#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently prove native masks/source/placements survive output rerouting."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import build_nand2b_stack_guard_v2 as previous
import build_nand2b_separated_output_v3 as candidate
from lvs_utils import clean_match

ROOT=candidate.ROOT
VERSION='native-nand2b-separated-output-mask-source-proof-v3.1'
CONTEXT='nand2b_separated_output_proof_v3'
sha=candidate.sha


def same_source(old,new,old_name,new_name):
    if old.count(old_name)!=2 or new.count(new_name)!=2 or new.replace(new_name,old_name)!=old:
        raise ValueError('More than the root model name changed in native source')


def clean_row(parent,row):
    name=row['macro'];folder=parent/name
    if (not row['passed'] or row['drc_count']!='0' or not row['lvs_passed']
        or (folder/(name+'.drc_count.txt')).read_text().strip()!='0'
        or not clean_match((folder/(name+'.lvs.log')).read_text())
        or sha(folder/(name+'.gds'))!=row['gds_sha256'] or sha(folder/(name+'.lef'))!=row['lef_sha256']):
        raise ValueError('Require unchanged clean native DRC/LVS geometry')
    return folder


def compare_masks(old_gds,new_gds,old_top,new_top):
    import klayout.db as kdb
    a=kdb.Layout();a.read(str(old_gds));b=kdb.Layout();b.read(str(new_gds))
    if a.dbu!=b.dbu:raise ValueError('Native GDS coordinate grid changed')
    old_cells={c.name for c in a.each_cell()}-{old_top};new_cells={c.name for c in b.each_cell()}-{new_top}
    if old_cells!=new_cells or not old_cells:raise ValueError('Native cell/guard hierarchy changed')
    layers=sorted({(i.layer,i.datatype) for l in [a,b] for i in l.layer_infos()})
    def region(layout,name,layer):return kdb.Region(layout.cell(name).begin_shapes_rec(layout.layer(kdb.LayerInfo(*layer))))
    for name in sorted(old_cells):
        for layer in layers:
            if not (region(a,name,layer)^region(b,name,layer)).is_empty():
                raise ValueError('Native child mask changed: '+name+' '+str(layer))
    def placements(layout,name):
        return Counter((layout.cell(i.cell_index).name,i.cplx_trans.to_s(),i.a.x,i.a.y,i.b.x,i.b.y,i.na,i.nb)
                       for i in layout.cell(name).each_inst())
    old_placements=placements(a,old_top);new_placements=placements(b,new_top)
    if old_placements!=new_placements:raise ValueError('Native gate/MIM/body-contact placement changed')
    changed=[]
    for layer in layers:
        # Compare root routing only; descendants are separately proven above.
        ra=kdb.Region(a.cell(old_top).shapes(a.layer(kdb.LayerInfo(*layer))))
        rb=kdb.Region(b.cell(new_top).shapes(b.layer(kdb.LayerInfo(*layer))))
        if not (ra^rb).is_empty():changed.append(list(layer))
    allowed={(69,20),(69,44),(70,20),(70,16)}
    if not changed or any(tuple(l) not in allowed for l in changed):raise ValueError('Non-M2/via2/M3 root mask changed: '+str(changed))
    return dict(native_cells=sorted(old_cells),compared_layers=len(layers),native_child_masks_identical=True,
                direct_child_placements_identical=True,direct_children=sum(old_placements.values()),changed_root_layers=changed)


def verify(original,repaired):
    previous.bound(original);candidate.bound(repaired)
    old=json.loads((original/'summary.json').read_text());new=json.loads((repaired/'summary.json').read_text())
    if not old['passed'] or not new['passed'] or [r['variant'] for r in old['rows']]!=[r['variant'] for r in new['rows']]:
        raise ValueError('Require the same two clean guarded native variants')
    paths=[original/n for n in ['manifest.json','summary.json','state.json']]+[repaired/n for n in ['manifest.json','summary.json','state.json']];rows=[]
    for before,after in zip(old['rows'],new['rows']):
        a=clean_row(original,before);b=clean_row(repaired,after);an=before['macro'];bn=after['macro']
        same_source((a/(an+'.sch.spice')).read_text(),(b/(bn+'.sch.spice')).read_text(),an,bn)
        if before['body_tap_row']!=after['body_tap_row'] or before['private_landings']!=after['private_landings']:
            raise ValueError('Native body contacts or proven private-node landing changed')
        for pin in before['ports']:
            expected=dict(before['ports'][pin])
            if pin=='Y':expected['y_um']=5.
            if after['ports'].get(pin)!=expected:raise ValueError('Unexpected public pin change: '+pin)
        proof=compare_masks(a/(an+'.gds'),b/(bn+'.gds'),an,bn)
        rows.append(dict(variant=after['variant'],before=an,after=bn,proof=proof,source_identical_except_root_name=True,
            old_y_um=before['ports']['Y']['y_um'],new_y_um=after['ports']['Y']['y_um']))
        for folder,name in [(a,an),(b,bn)]:
            paths += [folder/n for n in [name+'.gds',name+'.lef',name+'.sch.spice',name+'.drc_count.txt',name+'.lvs.log','summary.json']]
    paths += [Path(__file__),Path(previous.__file__),Path(candidate.__file__),ROOT/'scripts/lvs_utils.py']
    identity=dict(version=VERSION,original=str(original.relative_to(ROOT)),repaired=str(repaired.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in paths})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Physical native proof changed during comparison')
    out.mkdir(parents=True,exist_ok=False);(out/'summary.json').write_text(json.dumps(dict(identity=identity,rows=rows,
        passed=True,qualified_phy=False,electrical_qualification_passed=False,
        scope='Native child masks/source/placements identical and clean routing-only output escape change; no extracted coupling or timing qualification'),indent=2)+'\n');return out


def bound(out,parent):
    r=json.loads((out/'summary.json').read_text());i=r['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or i['repaired']!=str(parent.relative_to(ROOT)) or r['passed'] is not True
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())):raise ValueError('Native mask/source proof context changed')
    previous.bound(ROOT/i['original']);candidate.bound(parent);return r


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('original',type=Path);p.add_argument('repaired',type=Path);a=p.parse_args()
    print(verify(a.original.resolve(),a.repaired.resolve()),flush=True)
