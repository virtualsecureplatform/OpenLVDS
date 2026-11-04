#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Integrate a clean wider-power pair into the bank's original native frames."""
import argparse
import hashlib
import json
from pathlib import Path
import build_nand2b_guard_pair_v4 as pair
import normalize_weighted_bank_frames_v3 as frames
import mim_switch_abstract_v2 as lef

ROOT=frames.ROOT
sha=frames.sha
NAME=pair.NAME
VERSION='weighted-bank-wide-pair-power-frame-proof-v2.2'
CONTEXT='weighted_bank_wide_power_frames_v2'


def derive(parent,physical):
    import klayout.db as kdb
    frames.bound(parent);pair.bound(physical)
    result=json.loads((physical/'summary.json').read_text())
    if not result['passed'] or len(result['rows'])!=1 or not result['rows'][0]['passed']:
        raise ValueError('Require clean native wider pair DRC/LVS')
    row=result['rows'][0];folder=physical/NAME
    macros=json.loads((parent/'macros.json').read_text());macro=macros[NAME]
    if (folder/(NAME+'.sch.spice')).read_text()!=Path(macro['spice'][0]).read_text():
        raise ValueError('Wider PG pair changed native devices or schematic')
    abstract,translation=frames.normalized_lef((folder/(NAME+'.lef')).read_text())
    old=Path(macro['lef'][0]).read_text()
    if frames.boundary(old,.001)!=frames.boundary(abstract,.001):raise ValueError('Native pair footprint changed')
    a={m[1]:m for m in lef.PIN.finditer(old)};b={m[1]:m for m in lef.PIN.finditer(abstract)}
    if set(a)!=set(b):raise ValueError('Native pair ports changed')
    for name in ['A_N','B','Y']:
        if a[name][0]!=b[name][0]:raise ValueError('Signal abstract changed')
    expected={}
    for name in ['VGND','VPWR']:
        x=lef.rectangles(a[name][2]);y=lef.rectangles(b[name][2])
        if len(x)!=1 or len(y)!=1 or x[0][0]!='met4' or y[0][0]!='met4':raise ValueError('PG access layer changed')
        r=x[0][1];s=y[0][1]
        if (r[0]!=s[0] or r[2]!=s[2] or abs((r[1]+r[3])-(s[1]+s[3]))>1e-6
            or abs(s[3]-s[1]-1.6)>1e-6 or not s[1]<r[1]<r[3]<s[3]):raise ValueError('Unexpected PG widening')
        expected[name]=(r,s)
    layout=kdb.Layout();layout.read(str(folder/(NAME+'.gds')));top=layout.cell(NAME)
    top.transform(kdb.Trans(*[round(v/layout.dbu) for v in translation]))
    keepouts=frames.mim_keepouts(layout,top);abstract=frames.add_keepouts(abstract,keepouts,layout.dbu)
    boundary=kdb.Box(*frames.boundary(abstract,layout.dbu))
    if top.bbox()!=boundary:raise ValueError('Wider pair GDS changed boundary')
    top.shapes(layout.layer(kdb.LayerInfo(*frames.LAYER))).insert(boundary)
    original=kdb.Layout();original.read(macro['gds'][0]);before=original.cell(NAME)
    def region(l,t,layer):return kdb.Region(t.begin_shapes_rec(l.layer(kdb.LayerInfo(*layer))))
    layers={(l.get_info(i).layer,l.get_info(i).datatype) for l in [original,layout] for i in l.layer_indices()}
    def box(r):return kdb.Box(*[round(v/layout.dbu) for v in r])
    delta=kdb.Region()
    for r,s in expected.values():delta+=kdb.Region(box(s))-kdb.Region(box(r))
    for layer in layers:
        observed=region(original,before,layer)^region(layout,top,layer)
        wanted=delta if layer==(71,20) else kdb.Region()
        if not (observed^wanted).is_empty():raise ValueError('Unexpected native mask delta: '+str(layer))
    if frames.signatures(original)!=frames.signatures(layout):raise ValueError('Native hierarchy or labels changed')
    return macros,layout,abstract,dict(translation_um=list(translation),additional_met3_keepouts_dbu=keepouts,
        exact_pg_widening_only=True,unchanged_footprint=True,unchanged_signal_pins=True,unchanged_native_schematic=True)


def build(parent,physical):
    macros,layout,abstract,proof=derive(parent,physical)
    files=[Path(__file__),Path(pair.__file__),Path(frames.__file__),Path(lef.__file__)]
    files += [p for folder in [parent,physical] for p in folder.rglob('*') if p.is_file() and not p.name.endswith('.lock')]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),physical=str(physical.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);frames.physical.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    gds=out/(NAME+'.gds');layout.write(str(gds));newlef=out/(NAME+'.lef');newlef.write_text(abstract)
    macros[NAME]['gds']=[str(gds)];macros[NAME]['lef']=[str(newlef)]
    frames.physical.atomic(out/'macros.json',macros)
    frames.physical.atomic(out/'summary.json',dict(passed=True,proof=proof,qualified_phy=False,
        fresh_electrical_qualification_required=True,scope='Only two M4 PG rail widths changed; native DRC/LVS, mask delta, hierarchy and interface proof; no routed bank or electrical admission',
        files={p.name:sha(p) for p in [gds,newlef,out/'macros.json']}))
    bound(out);return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or not r['passed']
        or any(sha(out/n)!=h for n,h in r['files'].items())):raise ValueError('Wide-power bank frame changed')
    macros,layout,abstract,proof=derive(ROOT/i['parent'],ROOT/i['physical'])
    macros[NAME]['gds']=[str(out/(NAME+'.gds'))];macros[NAME]['lef']=[str(out/(NAME+'.lef'))]
    if (proof!=r['proof'] or abstract!=(out/(NAME+'.lef')).read_text()
        or macros!=json.loads((out/'macros.json').read_text())):raise ValueError('Wider PG frame regeneration changed')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('physical',type=Path);a=p.parse_args();print(build(a.parent.resolve(),a.physical.resolve()),flush=True)
