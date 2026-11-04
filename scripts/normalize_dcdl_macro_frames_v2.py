#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Normalize GDS/LEF coordinate frames and add PR boundaries for bank macros.

Require an exact rigid translation of all physical layers, labels and instances.
Original GDS/LEF/SPICE
and their electrical proofs remain immutable; whole-bank signoff is separate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import harden_dcdl_bank_v2 as physical

ROOT=physical.ROOT
sha=physical.sha
VERSION='native-dcdl-macro-zero-origin-rigid-frame-copy-v2.1'
LAYER=(235,4)


def boundary(lef,dbu):
    origin=re.findall(r'(?m)^\s*ORIGIN\s+([-\d.]+)\s+([-\d.]+)\s*;',lef)
    size=re.findall(r'(?m)^\s*SIZE\s+([\d.]+)\s+BY\s+([\d.]+)\s*;',lef)
    if len(origin)!=1 or len(size)!=1:raise ValueError('Require unique native LEF origin/size')
    x,y=map(float,origin[0]);w,h=map(float,size[0]);values=[-x,-y,w-x,h-y]
    if any(abs(v/dbu-round(v/dbu))>1e-6 for v in values):raise ValueError('LEF boundary is not on GDS grid')
    return [round(v/dbu) for v in values]


def normalized_lef(text):
    origins=re.findall(r'(?m)^\s*ORIGIN\s+([-\d.]+)\s+([-\d.]+)\s*;',text)
    if len(origins)!=1 or re.search(r'(?m)^\s*(POLYGON|PATH|VIA)\s',text):raise ValueError('Unsupported macro abstract geometry')
    dx,dy=map(float,origins[0])
    def rect(match):
        values=list(map(float,match.groups()[1:5]));values=[v+(dx if n%2==0 else dy) for n,v in enumerate(values)]
        return match[1]+'RECT '+' '.join(f'{v:.6f}' for v in values)+' ;'
    result=re.sub(r'(?m)^(\s*)RECT\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s+([-\d.]+)\s*;',rect,text)
    result=re.sub(r'(?m)^(\s*)ORIGIN\s+[-\d.]+\s+[-\d.]+\s*;',lambda m:m[1]+'ORIGIN 0.000 0.000 ;',result)
    return result,(dx,dy)


def signatures(layout):
    result={}
    for cell in layout.each_cell():
        instances=sorted((layout.cell(i.cell_index).name,str(i.cplx_trans),str(i.a),str(i.b),i.na,i.nb) for i in cell.each_inst())
        texts=[]
        for layer in layout.layer_indices():
            info=layout.get_info(layer)
            if (info.layer,info.datatype)==LAYER:continue
            texts += [(info.layer,info.datatype,str(s.text)) for s in cell.shapes(layer).each() if s.is_text()]
        result[cell.name]=dict(instances=instances,texts=sorted(texts))
    return result


def build(parent):
    import klayout.db as kdb
    m,macros,files=physical.checked_parent(parent)
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';layer_map=pdk/'libs.tech/klayout/tech/sky130A.lyp'
    if 'prBoundary.boundary - 235/4' not in layer_map.read_text():raise ValueError('PDK PR-boundary mapping changed')
    files += [Path(__file__),ROOT/'scripts/harden_dcdl_bank_v2.py',layer_map]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),layer=list(LAYER),
        inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in files},
        tools=physical.tool_identity(),klayout_version=kdb.__version__)
    out=ROOT/'build/diagnostics/dcdl_macro_frames_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);physical.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));rows=[]
    for name,macro in macros.items():
        original=Path(macro['gds'][0]);lef=Path(macro['lef'][0]);layout=kdb.Layout();layout.read(str(original));top=layout.cell(name)
        if top is None:raise ValueError('Missing native macro top cell')
        abstract,(dx,dy)=normalized_lef(lef.read_text())
        translation=kdb.Trans(round(dx/layout.dbu),round(dy/layout.dbu))
        box=kdb.Box(*boundary(lef.read_text(),layout.dbu))
        if top.bbox()!=box:raise ValueError('Native GDS bbox differs from LEF boundary: '+name)
        top.transform(translation)
        box=kdb.Box(*boundary(abstract,layout.dbu))
        if top.bbox()!=box:raise ValueError('Normalized GDS bbox mismatch')
        index=layout.layer(kdb.LayerInfo(*LAYER));old=kdb.Region(top.shapes(index))
        if not old.is_empty() and not (old^kdb.Region(box)).is_empty():raise ValueError('Conflicting existing PR boundary')
        if old.is_empty():top.shapes(index).insert(box)
        folder=out/name;folder.mkdir();gds=folder/(name+'.gds');layout.write(str(gds));newlef=folder/(name+'.lef');newlef.write_text(abstract)
        before=kdb.Layout();before.read(str(original));after=kdb.Layout();after.read(str(gds));a=before.cell(name);a.transform(translation);b=after.cell(name);bad=[]
        layers={(l.get_info(i).layer,l.get_info(i).datatype) for l in [before,after] for i in l.layer_indices()}-{LAYER}
        for number,datatype in sorted(layers):
            li=kdb.LayerInfo(number,datatype);x=before.layer(li);y=after.layer(li)
            if not (kdb.Region(a.begin_shapes_rec(x))^kdb.Region(b.begin_shapes_rec(y))).is_empty():bad.append([number,datatype])
        same=signatures(before)==signatures(after)
        pr=kdb.Region(b.shapes(after.layer(kdb.LayerInfo(*LAYER))));pr_ok=(pr^kdb.Region(box)).is_empty()
        passed=not bad and same and pr_ok
        if not passed:raise ValueError('Boundary adaptation changed native electrical geometry or labels')
        macro['gds']=[str(gds)];macro['lef']=[str(newlef)]
        rows.append(dict(macro=name,gds=str(gds.relative_to(ROOT)),gds_sha256=sha(gds),
            original_gds=str(original.relative_to(ROOT)),original_gds_sha256=sha(original),
            lef=str(newlef.relative_to(ROOT)),lef_sha256=sha(newlef),original_lef_sha256=sha(lef),translation_um=[dx,dy],
            boundary_dbu=boundary(abstract,layout.dbu),dbu_um=layout.dbu,physical_xor_changed_layers=bad,
            hierarchy_and_labels_after_translation_passed=same,pr_boundary_passed=pr_ok,passed=passed,qualified_phy=False))
    for name,digest in identity['inputs'].items():
        p=Path(name) if Path(name).is_absolute() else ROOT/name
        if sha(p)!=digest:raise ValueError('Native boundary input changed during adaptation')
    physical.atomic(out/'macros.json',macros);physical.atomic(out/'summary.json',dict(rows=rows,passed=all(r['passed'] for r in rows),qualified_phy=False,
        scope='Zero-origin GDS/LEF frames plus PR metadata; all other layers, labels and hierarchy exactly rigidly translated; instance placement coordinates and global port geometry preserved; whole-bank signoff required'))
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(build(a.artifact.resolve()),flush=True)
