#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Normalize all eleven native bank macro frames without changing electrical geometry."""
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import normalize_dcdl_macro_frames_v3 as previous

physical=previous.physical
ROOT=previous.ROOT
sha=previous.sha
VERSION='eleven-weighted-bank-macro-frames-and-placed-port-proof-v2.1'
LAYER=previous.LAYER
boundary=previous.boundary
normalized_lef=previous.normalized_lef
mim_keepouts=previous.mim_keepouts
add_keepouts=previous.add_keepouts
signatures=previous.signatures


def checked_parent(parent):
    record=json.loads((parent/'manifest.json').read_text());i=record['identity'];r=json.loads((parent/'summary.json').read_text())
    if (parent.parent!=ROOT/'build/diagnostics/weighted_bank_assembly_verification_v2'
        or i['version']!='independent-full-weighted-bank-opendb-reload-verification-v2.1'
        or parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or not r['passed'] or r['instances']!=94 or r['macro_instances']!=78 or r['connected_iterms']!=473
        or r['public_ports']!=24 or not r['native_network_equivalence_passed'] or r['route_complete']):
        raise ValueError('Require the exact independently reloaded full native bank assembly')
    assembly=ROOT/i['parent']
    code='import sys; from pathlib import Path; sys.path.insert(0,str(Path(sys.argv[1])/"scripts")); import assemble_weighted_bank_v2 as a; a.bound(Path(sys.argv[2]))'
    subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'),'-c',code,str(ROOT),str(assembly)],check=True)
    def records(path):return Counter(tuple(line.split('\t')) for line in path.read_text().splitlines())
    for a,b in [('connections.tsv','connections.tsv'),('public.tsv','bterms.tsv'),('pins.tsv','pins.tsv')]:
        if records(parent/a)!=records(assembly/b):raise ValueError('Independent OpenDB readback differs from the bound source assembly')
    m=json.loads((assembly/'manifest.json').read_text());macros=json.loads((assembly/'macros.json').read_text())
    if len(macros)!=11 or sum(len(v['instances']) for v in macros.values())!=78:raise ValueError('Incomplete full-bank macro set')
    expected={line.split()[0][1:]:line.split()[-1] for line in (assembly/'bank.spice').read_text().splitlines() if line.startswith('X')}
    observed={w[0]:w[1] for line in (parent/'instances.tsv').read_text().splitlines() if (w:=line.split('\t'))}
    if observed!=expected:raise ValueError('Independent serialized native model identities changed')
    files=[p for p in parent.iterdir() if p.is_file()]+[assembly/n for n in ['manifest.json','summary.json','state.json','macros.json']]
    files += [ROOT/n for n in {**i['inputs'],**i['code']}]
    return m,macros,files


def verify_ports(out,originals,adapted,places):
    """Read both sets of LEFs and compare actual global placed port rectangles."""
    tech=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef'
    counts=[];codes=[]
    for tag,macros in [('original',originals),('normalized',adapted)]:
        commands=[f'read_lef {{{tech}}}']+[f'read_lef {{{m["lef"][0]}}}' for m in macros.values()]
        commands += ['set db [ord::get_db]','if {[[$db getTech] getDbUnitsPerMicron] != 1000} {error "Unexpected DBU"}',
                     'set chip [odb::dbChip_create $db [$db getTech]]','set block [odb::dbBlock_create $chip frames]',
                     f'set f [open {{{out/(tag+"_ports.tsv")}}} w]',f'set g [open {{{out/(tag+"_boxes.tsv")}}} w]']
        for model,macro in macros.items():
            for name,p in macro['instances'].items():
                if p!=places[name] or p['orientation']!='N':raise ValueError('Macro placement changed during normalization')
                x,y=p['location']
                commands += [f'set master [$db findMaster {model}]',f'set inst [odb::dbInst_create $block $master {name}]',
                             f'$inst setLocation {round(x*1000)} {round(y*1000)}','lassign [$inst getOrigin] ox oy','set b [$inst getBBox]',
                             f'puts $g "{name}\t[$b xMin]\t[$b yMin]\t[$b xMax]\t[$b yMax]"',
                             'foreach term [$master getMTerms] {foreach pin [$term getMPins] {foreach shape [$pin getGeometry] {',
                             f'puts $f "{name}\t{model}\t[$term getName]\t[$term getIoType]\t[$term getSigType]\t[[$shape getTechLayer] getName]\t[expr {{[$shape xMin]+$ox}}]\t[expr {{[$shape yMin]+$oy}}]\t[expr {{[$shape xMax]+$ox}}]\t[expr {{[$shape yMax]+$oy}}]"','}}}']
        commands += ['close $f','close $g','exit'];script=out/(tag+'_ports.tcl');script.write_text('\n'.join(commands)+'\n')
        with (out/(tag+'_openroad.log')).open('w') as log:
            process=subprocess.run(['openroad','-no_init','-exit',str(script)],cwd=out,stdout=log,stderr=subprocess.STDOUT)
        codes.append(process.returncode)
    def records(tag,suffix):
        path=out/(tag+'_'+suffix+'.tsv')
        return Counter(tuple(line.split('\t')) for line in path.read_text().splitlines()) if path.exists() else Counter()
    ports=[records(t,'ports') for t in ['original','normalized']];boxes=[records(t,'boxes') for t in ['original','normalized']]
    return dict(passed=codes==[0,0] and bool(ports[0]) and ports[0]==ports[1] and boxes[0]==boxes[1] and len(boxes[0])==78,
                returncodes=codes,placed_macros=len(boxes[0]),placed_port_rectangles=sum(ports[0].values()),
                port_rectangles_identical=ports[0]==ports[1],macro_boxes_identical=boxes[0]==boxes[1],qualified_phy=False)


def build(parent):
    import klayout.db as kdb
    m,macros,files=checked_parent(parent);originals=json.loads(json.dumps(macros))
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';layer_map=pdk/'libs.tech/klayout/tech/sky130A.lyp'
    if 'prBoundary.boundary - 235/4' not in layer_map.read_text():raise ValueError('PDK PR-boundary mapping changed')
    files += [Path(__file__),Path(previous.__file__),ROOT/'scripts/harden_dcdl_bank_v2.py',ROOT/'scripts/harden_dcc_v2.py',layer_map]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),layer=list(LAYER),
        inputs={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in files},
        tools=physical.tool_identity(),klayout_version=kdb.__version__,original_macros=originals,placements=m['identity']['placements'],
        openroad=dict(path=shutil.which('openroad'),sha256=sha(Path(shutil.which('openroad')))))
    out=ROOT/'build/diagnostics/dcdl_macro_frames_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
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
    if (out.parent!=ROOT/'build/diagnostics/weighted_bank_macro_frames_v2' or i['version']!=VERSION
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
