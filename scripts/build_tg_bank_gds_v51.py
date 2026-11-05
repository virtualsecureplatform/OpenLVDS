#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Stream the routed both2 bank with original native masks and fresh DRC/LVS."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import klayout.db as db
import probe_tg_bank_route_v50 as route
import physical_cell_adapter_v44 as adapter
import native_bank_inventory_v51 as inventory
native_leaves=inventory.native_leaves

place=route.placement
ROOT=route.ROOT
sha=route.sha
CONTEXT='tg_bank_native_gds_v51'
VERSION='both2-full-routed-native-gds-mask-identity-drc-lvs-v51.1'
CUTS={(67,44),(68,44),(69,44),(70,44),(71,44)}


def validate_parent(parent):
    i,pi=route.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if not r['route_bringup_passed'] or r['router_final_violations']!=0 or any(sha(parent/n)!=h for n,h in r['files'].items()):
        raise ValueError('Require complete, unchanged routing coverage proof')
    if route.check(parent,pi,i['regular_wire_nets'])!=r['connection_and_coverage_check']:
        raise ValueError('Routed native interface and coverage do not reproduce')
    return i,pi


def stream(out,parent,pi,lyt,mapping):
    registry=ROOT/pi['parent'];reg=json.loads((registry/'manifest.json').read_text())['identity']
    tech=db.Technology();tech.load(str(lyt));options=tech.load_layout_options
    options.lefdef_config.read_lef_with_def=False
    options.lefdef_config.lef_files=[reg['tech_lef'],str(registry/'library.lef')]
    options.lefdef_config.map_file=str(mapping)
    options.lefdef_config.net_property_name=None
    options.lefdef_config.instance_property_name=None
    options.lefdef_config.pin_property_name=None
    options.cell_conflict_resolution=db.LoadLayoutOptions.CellConflictResolution.AddToCell
    lib=db.Layout();lib.read(str(parent/'routed.def'),options);top=lib.cell(pi['graph']['top'])
    if top is None or lib.dbu!=.001:raise ValueError('Routed top or GDS scale differs')
    for cell in lib.each_cell():
        if cell.cell_index()!=top.cell_index() and not cell.name.startswith('VIA'):cell.clear()
    lib.read(str(registry/'library.gds'),options)
    for r in pi['plan']['fixed_routes']:
        # OUT serializes as a DEF special net. The two regular-net power
        # buses are retained separately in ODB and must be added explicitly.
        if r['net']=='OUT':continue
        top.shapes(lib.layer(*adapter.ROUTING[r['layer']])).insert(db.Box(*[round(x/lib.dbu) for x in r['rect']]))
    for layer in lib.layer_indexes():
        info=lib.get_info(layer)
        if info.datatype==16 and info.layer in {v[0] for v in adapter.ROUTING.values()}:
            # DEF PIN purpose is annotation. Manufacture the exact canonical
            # port metal below; retain all child-cell pin-purpose geometry.
            top.shapes(layer).clear()
        for shape in list(top.shapes(layer).each()):
            if shape.is_text() and shape.text.string in pi['graph']['ports']:shape.delete()
    for name,p in pi['plan']['ports'].items():
        x0,y0,x1,y1=p['rect'];layer=adapter.ROUTING[p['layer']]
        top.shapes(lib.layer(*layer)).insert(db.Box(*[round(v/lib.dbu) for v in p['rect']]))
        top.shapes(lib.layer(layer[0],5)).insert(db.Text(name,db.Trans(round((x0+x1)/2/lib.dbu),round((y0+y1)/2/lib.dbu))))
    if any(c.is_ghost_cell() for c in lib.each_cell()):raise ValueError('Missing registered native GDS master')
    opts=db.SaveLayoutOptions();opts.select_cell(top.cell_index());file=out/(top.name+'.gds');lib.write(str(file),opts)
    return file


def masks(file,reference,top,die):
    a=db.Layout();a.read(str(reference));b=db.Layout();b.read(str(file));x=a.cell(top);y=b.cell(top)
    if x is None or y is None or a.dbu!=b.dbu:raise ValueError('Native mask comparison has no matching top/scale')
    keys={(l.get_info(i).layer,l.get_info(i).datatype) for l in (a,b) for i in l.layer_indexes()}
    routing=set(adapter.ROUTING.values())|CUTS
    for key in keys:
        before=place.audit.region(a,x,key);after=place.audit.region(b,y,key)
        if key==(235,4):
            # SKY130 prBoundary is placement annotation, not a mask. DEF
            # streamout adds exactly the declared die boundary to leaf marks.
            boundary=db.Region(db.Box(*[round(v/a.dbu) for v in die]))
            if not ((before+boundary)^after).is_empty():raise ValueError('Streamout die boundary differs from placement')
            continue
        if not ((before-after) if key in routing else (before^after)).is_empty():
            raise ValueError('Native source geometry lost or changed: '+str(key))
    return dict(all_native_manufacturing_nonrouting_masks_identical=True,all_original_native_routing_geometry_retained=True,
                die_boundary_matches_declared_placement=True,additional_geometry_limited_to_routing_vias_and_die_boundary=True)


def qualify(out,file,pi):
    registry=ROOT/pi['parent'];reg=json.loads((registry/'manifest.json').read_text())['identity']
    name=pi['graph']['top'];folder=out/'native';folder.mkdir()
    reference=ROOT/reg['graph_parent']/'bank.sch.spice';source=reference.read_text()
    (folder/(name+'.sch.spice')).write_text(source)
    lib=db.Layout();lib.read(str(file));commands=['gds readonly false',f'gds read {{{file}}}']
    for cell in lib.each_cell():commands += [f'load {cell.name}',f'save {cell.name}']
    commands += [f'load {name}']
    for index,port in enumerate(pi['graph']['ports'],1):
        r=pi['plan']['ports'][port]['rect'];x=(r[0]+r[2])/2;y=(r[1]+r[3])/2
        commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um',f'port make {index}']
    commands += [f'save {name}'];place.layout.invoke_magic(folder,'\n'.join(commands),'import_routed')
    result=place.layout.qualify(folder,name)
    if not result['passed']:return result,dict(native_parameters_preserved=False)
    # Compare actual native device dimensions and junction geometry separately
    # from Netgen's topology/model comparison. Only D/S exchange is allowed.
    ports,leaves=native_leaves(source,name)
    extracted=re.sub(r'\n[ \t]*\+[ \t]*',' ',(folder/(name+'.lvs.spice')).read_text())
    _,actual=native_leaves(extracted,name+'_flat')
    parameters=inventory.compare_parameters(leaves,actual)
    counts=Counter(d['model'] for d in leaves)
    if sum(counts.values())!=968 or counts['sky130_fd_pr__cap_mim_m3_1']!=65:
        raise ValueError('Unexpected native routed bank inventory')
    return result,parameters



def prepare(parent):
    i,pi=validate_parent(parent);r=json.loads((parent/'summary.json').read_text())
    techroot=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/klayout'
    lyt=list(techroot.rglob('sky130A.lyt'));mapping=list(techroot.rglob('sky130A.map'))
    if len(lyt)!=1 or len(mapping)!=1:raise ValueError('Require pinned SKY130 streamout technology and map')
    paths=[parent/'manifest.json',parent/'summary.json',*[parent/n for n in r['files']],Path(__file__),Path(inventory.__file__)]
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
                  lyt=str(lyt[0]),mapping=str(mapping[0]),external_files={str(p):sha(p) for p in [lyt[0],mapping[0]]})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(Path(n))!=h for n,h in i['external_files'].items())):raise ValueError('Routed native GDS context changed')
    _,pi=validate_parent(ROOT/i['parent']);return i,pi


def run(out):
    i,pi=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain completed or partial native GDS campaign')
        (out/'state.json').write_text('{"status":"checking_native_gds","qualified_phy":false}\n')
        parent=ROOT/i['parent'];file=stream(out,parent,pi,Path(i['lyt']),Path(i['mapping']))
        routed_identity=json.loads((parent/'manifest.json').read_text())['identity']
        original=ROOT/routed_identity['parent']/(pi['graph']['top']+'.gds')
        mask_proof=masks(file,original,pi['graph']['top'],pi['plan']['die']);physical,parameters=qualify(out,file,pi)
        bound(out);passed=bool(physical['passed'] and parameters['native_parameters_preserved'])
        report=dict(native_routed_gds_passed=passed,mask_proof=mask_proof,physical=physical,native_parameters=parameters,
                    joint_rc_extracted=False,electrical_qualification_passed=False,qualified_phy=False,
                    full_foundry_signoff_passed=False,scope='Routed native masks/dimensions, Magic DRC and strict native LVS only; no antenna, independent foundry signoff, joint RC or timing admission')
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('.execution.lock','state.json')}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n');return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
