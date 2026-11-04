#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Normalize the complete bank macro family in its dedicated, bound namespace.

Retain the initial directory-mismatch artifact and source unchanged. All
physical transformations and checks use the original proven helpers.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import normalize_weighted_bank_frames_v2 as previous

physical=previous.physical
ROOT=previous.ROOT
sha=previous.sha
VERSION='eleven-weighted-bank-macro-frames-and-placed-port-proof-v2.2'
CONTEXT='weighted_bank_macro_frames_v2'
LAYER=previous.LAYER
checked_parent=previous.checked_parent
verify_ports=previous.verify_ports
boundary=previous.boundary
normalized_lef=previous.normalized_lef
mim_keepouts=previous.mim_keepouts
add_keepouts=previous.add_keepouts
signatures=previous.signatures


def build(parent):
    import klayout.db as kdb
    m,macros,files=checked_parent(parent);originals=json.loads(json.dumps(macros))
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';layer_map=pdk/'libs.tech/klayout/tech/sky130A.lyp'
    if 'prBoundary.boundary - 235/4' not in layer_map.read_text():raise ValueError('PDK PR-boundary mapping changed')
    files += [Path(__file__),Path(previous.__file__),Path(previous.previous.__file__),ROOT/'scripts/harden_dcdl_bank_v2.py',ROOT/'scripts/harden_dcc_v2.py',layer_map]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),layer=list(LAYER),
        inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in files},
        tools=physical.tool_identity(),klayout_version=kdb.__version__,original_macros=originals,placements=m['identity']['placements'],
        openroad=dict(path=shutil.which('openroad'),sha256=sha(Path(shutil.which('openroad')))))
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);physical.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));rows=[]
    physical.atomic(out/'state.json',dict(status='adapting',qualified_phy=False))
    try:
        for name,macro in macros.items():
            original=Path(macro['gds'][0]);lef=Path(macro['lef'][0]);layout=kdb.Layout();layout.read(str(original));top=layout.cell(name)
            if top is None:raise ValueError('Missing native macro top cell')
            abstract,(dx,dy)=normalized_lef(lef.read_text())
            translation=kdb.Trans(round(dx/layout.dbu),round(dy/layout.dbu))
            box=kdb.Box(*boundary(lef.read_text(),layout.dbu))
            if top.bbox()!=box:raise ValueError('Native GDS bbox differs from LEF boundary: '+name)
            top.transform(translation)
            keepouts=mim_keepouts(layout,top)
            abstract=add_keepouts(abstract,keepouts,layout.dbu)
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
                additional_met3_keepouts_dbu=keepouts,boundary_dbu=boundary(abstract,layout.dbu),dbu_um=layout.dbu,physical_xor_changed_layers=bad,
                hierarchy_and_labels_after_translation_passed=same,pr_boundary_passed=pr_ok,passed=passed,qualified_phy=False))
        for name,digest in identity['inputs'].items():
            p=Path(name) if Path(name).is_absolute() else ROOT/name
            if sha(p)!=digest:raise ValueError('Native boundary input changed during adaptation')
        port_check=verify_ports(out,originals,macros,identity['placements'])
        if not port_check['passed']:raise ValueError('OpenDB placed macro pins or boxes changed under frame adaptation')
        physical.atomic(out/'macros.json',macros)
        report=dict(rows=rows,passed=all(r['passed'] for r in rows),placed_ports=port_check,qualified_phy=False,
            scope='Eleven native macro zero-origin GDS/LEF frames, PR boundaries and MIM+1.34um M3 keepouts; exact physical-layer XOR, hierarchy/label and placed OpenDB port/bbox equivalence only; no routed bank, electrical or PHY admission')
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ['manifest.json','summary.json','state.json']}
        physical.atomic(out/'summary.json',report)
        physical.atomic(out/'state.json',dict(status='frames_complete',passed=report['passed'],qualified_phy=False))
    
    except Exception as exc:
        physical.atomic(out/'state.json',dict(status='normalization_exception',error=str(exc),qualified_phy=False));raise
    return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(Path(n) if Path(n).is_absolute() else ROOT/n)!=h for n,h in i['inputs'].items())
        or physical.tool_identity()!=i['tools'] or sha(Path(i['openroad']['path']))!=i['openroad']['sha256']):raise ValueError('Weighted-bank frame context changed')
    checked_parent(ROOT/i['parent']);r=json.loads((out/'summary.json').read_text());macros=json.loads((out/'macros.json').read_text())
    if (not r['passed'] or not r['placed_ports']['passed'] or set(macros)!=set(i['original_macros'])
        or [row['macro'] for row in r['rows']]!=list(i['original_macros'])
        or any(sha(out/n)!=h for n,h in r['files'].items())):raise ValueError('Weighted-bank frame output changed')
    for row in r['rows']:
        name=row['macro'];original=i['original_macros'][name]
        if (not row['passed'] or row['physical_xor_changed_layers'] or not row['hierarchy_and_labels_after_translation_passed']
            or not row['pr_boundary_passed'] or sha(ROOT/row['gds'])!=row['gds_sha256'] or sha(ROOT/row['lef'])!=row['lef_sha256']
            or sha(Path(original['gds'][0]))!=row['original_gds_sha256'] or sha(Path(original['lef'][0]))!=row['original_lef_sha256']
            or macros[name]!=dict(original,gds=[str(ROOT/row['gds'])],lef=[str(ROOT/row['lef'])])):raise ValueError('Weighted-bank frame/electrical views changed')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(build(a.artifact.resolve()),flush=True)
