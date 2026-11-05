#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Integrate the native fine repair while preserving every global access rectangle."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import weighted_bank_wide_power_frames_v4 as wide
import mim_switch_abstract_v2 as lef

ROOT=wide.ROOT
sha=wide.sha
frames=wide.frames
NAME='openlvds_weighted_fine_root_b4_v2'
VERSION='weighted-bank-native-fine-repair-frame-and-global-port-proof-v2.1'
CONTEXT='weighted_bank_repaired_fine_frames_v2'


def pin_shift(original,adapted):
    a={m[1]:m[2] for m in lef.PIN.finditer(original)};b={m[1]:m[2] for m in lef.PIN.finditer(adapted)}
    if set(a)!=set(b) or set(a)!={'NODE','EN','ENB','VDD','VSS'}:raise ValueError('Fine repair public interface changed')
    shifts=set()
    for n in a:
        for field in ['DIRECTION','USE']:
            if re.findall(r'\b'+field+r'\s+(\S+)\s*;',a[n])!=re.findall(r'\b'+field+r'\s+(\S+)\s*;',b[n]):raise ValueError('Fine repair public pin type changed')
        x=lef.rectangles(a[n]);y=lef.rectangles(b[n])
        if len(x)!=1 or len(y)!=1 or x[0][0]!=y[0][0]:raise ValueError('Fine repair public access changed')
        r,s=x[0][1],y[0][1]
        if r[0]!=s[0] or r[2]!=s[2] or round(r[3]-r[1],6)!=round(s[3]-s[1],6):raise ValueError('Fine repair access cannot be preserved by vertical placement')
        shifts.add(round(r[1]-s[1],6));shifts.add(round(r[3]-s[3],6))
    if len(shifts)!=1:raise ValueError('Fine repair pin motion is not rigid')
    return shifts.pop()


def network_record(receipt):
    code='import sys,json; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); import verify_weighted_bank_repair_network_v2 as n; p=Path(sys.argv[2]); m=n.bound(p); print(json.dumps(dict(identity=m["identity"],proof=json.loads((p/"summary.json").read_text())["proof"])))'
    p=subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'),'-c',code,str(ROOT),str(receipt)],capture_output=True,text=True,check=True)
    return json.loads(p.stdout)


def derive(parent,network):
    import klayout.db as kdb
    wm=wide.bound(parent);record=network_record(network);proof=record['proof']
    if proof['guard_physical']!=wm['identity']['physical']:raise ValueError('Native bank guard RC does not match physical power rails')
    physical=ROOT/proof['repair_physical'];macros=json.loads((parent/'macros.json').read_text());macro=macros[NAME];folder=physical/NAME
    abstract,translation=frames.normalized_lef((folder/(NAME+'.lef')).read_text());old=Path(macro['lef'][0]).read_text();dy=pin_shift(old,abstract)
    if set(macro['instances'])!={'fine4'}:raise ValueError('Unexpected fine repair multiplicity')
    layout=kdb.Layout();layout.read(str(folder/(NAME+'.gds')));top=layout.cell(NAME)
    if top is None or layout.dbu!=.001:raise ValueError('Unexpected native fine GDS frame')
    before=kdb.Layout();before.read(str(folder/(NAME+'.gds')));a=before.cell(NAME)
    transform=kdb.Trans(*[round(v/layout.dbu) for v in translation]);top.transform(transform);a.transform(transform)
    keepouts=frames.mim_keepouts(layout,top);abstract=frames.add_keepouts(abstract,keepouts,layout.dbu)
    boundary=kdb.Box(*frames.boundary(abstract,layout.dbu))
    if top.bbox()!=boundary:raise ValueError('Native repaired fine GDS/LEF bbox mismatch')
    top.shapes(layout.layer(kdb.LayerInfo(*frames.LAYER))).insert(boundary)
    layers={(l.get_info(i).layer,l.get_info(i).datatype) for l in [before,layout] for i in l.layer_indices()}-{frames.LAYER}
    for layer in layers:
        r=kdb.Region(a.begin_shapes_rec(before.layer(kdb.LayerInfo(*layer))))
        s=kdb.Region(top.begin_shapes_rec(layout.layer(kdb.LayerInfo(*layer))))
        if not (r^s).is_empty():raise ValueError('Fine frame adaptation changed native masks')
    if frames.signatures(before)!=frames.signatures(layout):raise ValueError('Fine frame hierarchy or labels changed')
    original_location=list(macro['instances']['fine4']['location']);macro['instances']['fine4']['location'][1]=round(original_location[1]+dy,6)
    proof=dict(native_network=proof,translation_um=list(translation),placement_delta_um=[0.,dy],original_location_um=original_location,
        new_location_um=macro['instances']['fine4']['location'],boundary_dbu=frames.boundary(abstract,layout.dbu),
        additional_met3_keepouts_dbu=keepouts,physical_xor_changed_layers=[],hierarchy_and_labels_passed=True)
    return macros,layout,abstract,proof,physical,wm


def verify_placed(out,original,adapted):
    tech=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef';codes=[]
    for tag,macros in [('original',original),('adapted',adapted)]:
        lines=[f'read_lef {{{tech}}}']+[f'read_lef {{{m["lef"][0]}}}' for m in macros.values()]
        lines += ['set db [ord::get_db]','set chip [odb::dbChip_create $db [$db getTech]]','set block [odb::dbBlock_create $chip fine_frames]',
            f'set f [open {{{out/(tag+"_ports.tsv")}}} w]',f'set g [open {{{out/(tag+"_boxes.tsv")}}} w]']
        for model,macro in macros.items():
            for name,p in macro['instances'].items():
                if p['orientation']!='N':raise ValueError('Unexpected bank macro orientation')
                x,y=p['location'];lines += [f'set inst [odb::dbInst_create $block [$db findMaster {model}] {name}]',f'$inst setLocation {round(x*1000)} {round(y*1000)}',
                    'lassign [$inst getOrigin] ox oy','set b [$inst getBBox]',f'puts $g "{name}\\t[$b xMin]\\t[$b yMin]\\t[$b xMax]\\t[$b yMax]"',
                    'foreach term [[$inst getMaster] getMTerms] {foreach pin [$term getMPins] {foreach s [$pin getGeometry] {',
                    f'puts $f "{name}\\t{model}\\t[$term getName]\\t[$term getIoType]\\t[$term getSigType]\\t[[$s getTechLayer] getName]\\t[expr {{[$s xMin]+$ox}}]\\t[expr {{[$s yMin]+$oy}}]\\t[expr {{[$s xMax]+$ox}}]\\t[expr {{[$s yMax]+$oy}}]"','}}}']
        lines += ['close $f','close $g','exit'];script=out/(tag+'_ports.tcl');script.write_text('\n'.join(lines)+'\n')
        with (out/(tag+'_ports.log')).open('w') as log:p=subprocess.run(['openroad','-no_init','-exit',str(script)],cwd=out,stdout=log,stderr=subprocess.STDOUT)
        codes.append(p.returncode)
    def records(tag,kind):return Counter((out/(tag+'_'+kind+'.tsv')).read_text().splitlines())
    a,b=[records(t,'ports') for t in ['original','adapted']]
    boxes=[dict(line.split('\t',1) for line in (out/(t+'_boxes.tsv')).read_text().splitlines()) for t in ['original','adapted']]
    others=all(boxes[0][n]==boxes[1].get(n) for n in boxes[0] if n!='fine4')
    return dict(passed=codes==[0,0] and a==b and sum(a.values())==377 and len(boxes[0])==78 and len(boxes[1])==78 and others,
        returncodes=codes,placed_macros=len(boxes[1]),global_pin_rectangles=sum(b.values()),global_pin_rectangles_identical=a==b,other_macro_boxes_identical=others,qualified_phy=False)


def build(parent,network):
    import klayout.db as kdb
    macros,layout,abstract,proof,physical,wm=derive(parent,network);original=json.loads((parent/'macros.json').read_text())
    files=[Path(__file__),Path(wide.__file__),Path(lef.__file__),ROOT/'scripts/verify_weighted_bank_repair_network_v2.py']
    files += [p for folder in [parent,network,physical] for p in folder.rglob('*') if p.is_file() and not p.name.endswith('.lock')]
    tool=Path(shutil.which('openroad'))
    identity=dict(version=VERSION,parent=wm['identity']['parent'],wide_parent=str(parent.relative_to(ROOT)),network=str(network.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)):sha(p) for p in files},klayout_version=kdb.__version__,openroad=dict(path=str(tool),sha256=sha(tool)))
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16];out.mkdir(parents=True,exist_ok=False)
    frames.physical.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    gds=out/(NAME+'.gds');layout.write(str(gds));newlef=out/(NAME+'.lef');newlef.write_text(abstract)
    macros[NAME].update(gds=[str(gds)],lef=[str(newlef)],spice=[str(physical/NAME/(NAME+'.sch.spice'))])
    ports=verify_placed(out,original,macros)
    if not ports['passed']:raise ValueError('Repaired bank global physical pin equivalence failed')
    frames.physical.atomic(out/'macros.json',macros)
    result=dict(passed=True,proof=proof,placed_ports=ports,qualified_phy=False,electrical_qualification_passed=False,
        scope='Native fine repair, complete bank leaf network, normalized masks and all placed access rectangles; no control settling, bank timing, signal routes or PHY admission')
    result['files']={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ['manifest.json','summary.json']}
    frames.physical.atomic(out/'summary.json',result);bound(out);return out


def bound(out):
    import klayout.db as kdb
    m=json.loads((out/'manifest.json').read_text());i=m['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(out/n)!=h for n,h in r['files'].items())
        or kdb.__version__!=i['klayout_version'] or sha(Path(i['openroad']['path']))!=i['openroad']['sha256'] or not r['passed'] or not r['placed_ports']['passed']):raise ValueError('Repaired fine bank frame changed')
    macros,layout,abstract,proof,physical,wm=derive(ROOT/i['wide_parent'],ROOT/i['network'])
    macros[NAME].update(gds=[str(out/(NAME+'.gds'))],lef=[str(out/(NAME+'.lef'))],spice=[str(physical/NAME/(NAME+'.sch.spice'))])
    if (json.loads(json.dumps(proof))!=r['proof'] or (out/(NAME+'.lef')).read_text()!=abstract or macros!=json.loads((out/'macros.json').read_text())):
        raise ValueError('Repaired fine frame regeneration failed')
    return m


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('network',type=Path);a=p.parse_args();print(build(a.parent.resolve(),a.network.resolve()),flush=True)
