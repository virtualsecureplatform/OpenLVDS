#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Expose existing guarded-pair M3 supplies without changing native masks."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import normalize_weighted_bank_frames_v3 as frames
import mim_switch_abstract_v2 as lef

ROOT=frames.ROOT
sha=frames.sha
NAME='openlvds_nand2b_4_o1_stack_guard_pair_v2'
VERSION='weighted-bank-existing-m3-power-access-v2.1'
CONTEXT='weighted_bank_power_access_v2'


def adapt(text,raw,translation):
    """Move four exact original PG rectangles from OBS to their named pins."""
    pins={m[1]:m[2] for m in lef.PIN.finditer(text)}
    extracted={m[1]:m[2] for m in lef.PIN.finditer(raw)}
    if set(pins)!=set(extracted) or set(pins)!={'A_N','B','Y','VGND','VPWR'}:
        raise ValueError('Guard pair public interface changed')
    additions={}
    for name in ['VGND','VPWR']:
        rails=lef.rectangles(pins[name])
        if len(rails)!=1 or rails[0][0]!='met4':raise ValueError('Expected original shared M4 rail')
        y=(rails[0][1][1]+rails[0][1][3])/2
        shapes=[]
        for layer,r in lef.rectangles(extracted[name]):
            a=tuple(round(v+translation[i%2],6) for i,v in enumerate(r))
            if layer=='met3' and a[1]<y<a[3] and a[2]-a[0]>20:shapes.append((layer,a))
        if len(shapes)!=2:raise ValueError('Require both original child M3 PG rails')
        additions[name]=shapes
    obs=list(lef.OBS.finditer(text))
    if len(obs)!=1:raise ValueError('Require one original OBS block')
    shapes=lef.rectangles(obs[0][1]);wanted=[s for v in additions.values() for s in v]
    for shape in wanted:
        if shapes.count(shape)!=1:raise ValueError('Promoted power rectangle not uniquely hidden in OBS')
        shapes.remove(shape)
    result=lef.OBS.sub('  OBS\n'+lef.render(shapes)+'  END\n',text)
    def promote(m):
        if m[1] not in additions:return m[0]
        if m[2].count('    END\n')!=1:raise ValueError('Unexpected PG port syntax')
        return m[0].replace('    END\n',lef.render(additions[m[1]])+'    END\n')
    result=lef.PIN.sub(promote,result)
    if lef.geometry(result)!=lef.geometry(text):raise ValueError('Physical abstract geometry changed')
    return result,additions


def physical_proof(gds,additions,text):
    import klayout.db as kdb
    layout=kdb.Layout();layout.read(str(gds));top=layout.cell(NAME)
    if top is None or layout.dbu!=.001:raise ValueError('Unexpected native mask frame')
    def region(number,datatype):return kdb.Region(top.begin_shapes_rec(layout.layer(kdb.LayerInfo(number,datatype))))
    metal3=region(70,20);vias=region(70,44);metal4=region(71,20)
    pins={m[1]:lef.rectangles(m[2]) for m in lef.PIN.finditer(text)}
    def box(r):return kdb.Box(*[round(v/layout.dbu) for v in r])
    rows=[]
    for name,shapes in additions.items():
        shared=kdb.Region(box(pins[name][0][1]))
        if not (shared-metal4).is_empty():raise ValueError('Original M4 PG absent in native masks')
        for _,r in shapes:
            access=kdb.Region(box(r));landing=access&shared
            cuts=[p for p in vias.each() if (kdb.Region(p)-landing).is_empty()]
            if not (access-metal3).is_empty() or not cuts:raise ValueError('M3 access lacks native same-net M3/via3/M4 connection')
            rows.append(dict(pin=name,rectangle_um=r,native_via3_cuts=len(cuts),passed=True))
    return rows


def build(parent):
    frames.bound(parent);macros=json.loads((parent/'macros.json').read_text())
    report=json.loads((parent/'summary.json').read_text())
    row=next(r for r in report['rows'] if r['macro']==NAME)
    original=ROOT/row['original_gds'];raw=original.with_suffix('.raw.lef')
    abstract=Path(macros[NAME]['lef'][0]);gds=Path(macros[NAME]['gds'][0])
    changed,additions=adapt(abstract.read_text(),raw.read_text(),row['translation_um'])
    proof=physical_proof(gds,additions,abstract.read_text())
    files=[Path(__file__),Path(lef.__file__),Path(frames.__file__),parent/'manifest.json',parent/'summary.json',parent/'macros.json',raw,abstract,gds]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
                  additions=additions,klayout_version=__import__('klayout.db',fromlist=['__version__']).__version__)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    frames.physical.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    target=out/(NAME+'.lef');target.write_text(changed);macros[NAME]['lef']=[str(target)]
    frames.physical.atomic(out/'macros.json',macros)
    frames.physical.atomic(out/'summary.json',dict(passed=True,proof=proof,unchanged_gds_sha256=sha(gds),
        routing_geometry_multiset_unchanged=True,qualified_phy=False,
        scope='Four existing M3 PG rectangles exposed; native M3/via3/M4 proof, no mask changes, no grid or electrical qualification',
        files={p.name:sha(p) for p in [target,out/'macros.json']}))
    bound(out);return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or not r['passed']
        or any(sha(out/n)!=h for n,h in r['files'].items())):raise ValueError('Power-access view binding changed')
    parent=ROOT/i['parent'];frames.bound(parent)
    macros=json.loads((parent/'macros.json').read_text());old=Path(macros[NAME]['lef'][0])
    row=next(x for x in json.loads((parent/'summary.json').read_text())['rows'] if x['macro']==NAME)
    raw=(ROOT/row['original_gds']).with_suffix('.raw.lef')
    text,additions=adapt(old.read_text(),raw.read_text(),row['translation_um'])
    if text!=(out/(NAME+'.lef')).read_text() or json.loads(json.dumps(additions))!=i['additions']:
        raise ValueError('Power-access regeneration failed')
    proof=physical_proof(Path(macros[NAME]['gds'][0]),additions,old.read_text())
    if json.loads(json.dumps(proof))!=r['proof']:raise ValueError('Native PG connection proof changed')
    macros[NAME]['lef']=[str(out/(NAME+'.lef'))]
    if macros!=json.loads((out/'macros.json').read_text()):raise ValueError('Other macro views changed')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(build(a.artifact.resolve()),flush=True)
