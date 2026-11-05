#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent mask, port, MIM-obstruction and well-domain library audit."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import sys
import klayout.db as db
import build_bank_cell_registry_v44 as producer
import physical_cell_adapter_v44 as geometry

ROOT=producer.ROOT
CONTEXT='bank_cell_registry_verification_v47'
VERSION='independent-normalized-bank-library-geometry-v47.1'
sha=producer.sha


def region(lib,top,layer):
    index=lib.find_layer(*layer)
    return db.Region() if index is None else db.Region(top.begin_shapes_rec(index)).merged()


def box(rect,dbu):return db.Box(*[round(x/dbu) for x in rect])


def read(path,model):
    lib=db.Layout();lib.read(str(path));top=lib.cell(model)
    if top is None or lib.dbu!=.001:raise ValueError('Missing master or changed GDS scale')
    return lib,top


def port_roles(block):
    result={}
    for match in geometry.geometry.PIN.finditer(block):
        direction=re.search(r'\bDIRECTION\s+(\w+)\s*;',match[2])
        use=re.search(r'\bUSE\s+(\w+)\s*;',match[2])
        if direction is None or use is None:raise ValueError('Missing explicit pin direction/use')
        result[match[1]]=[direction[1],use[1]]
    return result


def audit(model,spec,record,gds,lef):
    """Compare original manufacturing geometry and independently derive constraints."""
    old,a=read(spec['gds'],model);new,b=read(gds,model)
    dx,dy=[round(x/new.dbu) for x in record['shift_um']]
    layers={(lib.get_info(i).layer,lib.get_info(i).datatype) for lib in (old,new) for i in lib.layer_indexes()}
    for layer in layers:
        if not (region(old,a,layer)^region(new,b,layer).transformed(db.Trans(-dx,-dy))).is_empty():
            raise ValueError('Manufacturing mask changed')
    abstract=geometry.description(lef,model);original=geometry.description(Path(spec['lef']).read_text(),model)
    if (abstract['origin']!=[0.,0.] or
            [round(x/new.dbu) for x in abstract['size']]!=[round(x/new.dbu) for x in record['size_um']]):
        raise ValueError('Wrong physical origin or dimensions')
    if set(abstract['pins'])!=set(spec['order']) or set(record['pins'])!=set(spec['order']):
        raise ValueError('Wrong canonical port inventory')
    roles=port_roles(abstract['block'])
    for pin,shapes in abstract['pins'].items():
        power=pin in ('VPWR','VPB');ground=pin in ('VGND','VNB')
        expected=[spec['directions'][pin].upper(),'POWER' if power else 'GROUND' if ground else 'SIGNAL']
        if roles[pin]!=expected or [record['pins'][pin]['direction'],record['pins'][pin]['use']]!=expected:
            raise ValueError('Wrong canonical port direction or power use')
        if producer.canonical(shapes)!=record['pins'][pin]['shapes']:raise ValueError('Pin rectangle differs from registry')
        for layer,rect in shapes:
            if layer in geometry.ROUTING and not (db.Region(box(rect,new.dbu))-region(new,b,geometry.ROUTING[layer])).is_empty():
                raise ValueError('Pin rectangle is outside actual conductor')
    obs={layer:db.Region() for layer in geometry.ROUTING}
    for match in geometry.geometry.OBS.finditer(abstract['block']):
        for layer,rect in geometry.geometry.rectangles(match[1]):
            if layer in obs:obs[layer].insert(box(rect,new.dbu))
    pins={layer:db.Region() for layer in geometry.ROUTING}
    for shapes in abstract['pins'].values():
        for layer,rect in shapes:
            if layer in pins:pins[layer].insert(box(rect,new.dbu))
    # Every original routing rectangle must remain either routable pin or OBS.
    for layer,rect in geometry.geometry.geometry(original['block']):
        if layer in obs:
            shifted=box(rect,new.dbu).transformed(db.Trans(dx,dy))
            if not (db.Region(shifted)-(obs[layer]+pins[layer])).is_empty():
                raise ValueError('Original routing geometry became unprotected')
    if spec['kind']=='custom':
        index=new.find_layer(70,5)
        labels=[s.text for s in b.shapes(index).each() if s.is_text()] if index is not None else []
        geometry.pins_match(original['pins'],spec['aliases'],spec['order'])
        source_index=old.find_layer(70,5)
        source_labels=[s.text for s in a.shapes(source_index).each() if s.is_text()] if source_index is not None else []
        for legacy,pin in spec['aliases'].items():
            source=[t for t in source_labels if t.string==legacy]
            if len(source)!=1:raise ValueError('Original public GDS label is missing or ambiguous')
            expected=[round((source[0].x+dx)*new.dbu,6),round((source[0].y+dy)*new.dbu,6)]
            if record['pins'][pin]['anchor_um']!=expected:raise ValueError('Alias anchor differs from original public conductor')
        for pin in spec['order']:
            wanted=record['pins'][pin]['anchor_um'];found=[t for t in labels if t.string==pin]
            if len(found)!=1 or [round(found[0].x*new.dbu,6),round(found[0].y*new.dbu,6)]!=wanted:
                raise ValueError('Canonical public GDS label is missing or displaced')
        marker=region(new,b,geometry.MIM)
        if abs(marker.area()*new.dbu**2-producer.CUSTOM[model][1])>1e-8:raise ValueError('Native MIM area changed')
        for poly in marker.each_merged():
            cap=poly.bbox()
            for layer,clearance in [('met3',1.34),('met4',.3)]:
                required=db.Region(cap.enlarged(round(clearance/new.dbu)))
                if layer=='met3':required=required-pins[layer]
                if not (required-obs[layer]).is_empty():raise ValueError('Missing MIM routing keepout')
        if record['well_domain_nets']:raise ValueError('Custom body domain changed')
    else:
        if abstract['block']!=original['block']:raise ValueError('Stock standard-cell abstract changed')
        expected={p:('VGND' if p in ('VNB','VGND') else 'VPWR') for p,shapes in abstract['pins'].items()
                  if not any(layer in geometry.ROUTING for layer,_ in shapes)}
        if record['well_domain_nets']!=expected:raise ValueError('Wrong standard-cell well domain')
        if record['requires_external_taps']!=(model!=producer.TAP):raise ValueError('Missing physical tap requirement')
    return dict(original_masks_preserved=True,pin_roles_and_metal_verified=True,
                original_routing_obstructions_preserved=True,mim_keepouts_verified=True,well_domains_verified=True)


def negative_controls(out,i,records):
    fine='openlvds_mim_switch_2x3_v2';spec=i['specs'][fine];record=records[fine]
    parent=ROOT/i['_parent'];gds=parent/'gds'/(fine+'.gds');lef=(parent/'lef'/(fine+'.lef')).read_text()
    folder=out/'negative_controls';folder.mkdir();results=[]
    def reject(name,model,s,r,g,l):
        try:audit(model,s,r,g,l)
        except ValueError as e:results.append(dict(fault=name,rejected=True,reason=str(e)))
        else:raise ValueError('Physical library corruption accepted: '+name)
    bad=lef.replace('DIRECTION INOUT','DIRECTION INPUT',1)
    (folder/'wrong_fine_direction.lef').write_text(bad)
    reject('wrong_fine_direction',fine,spec,record,gds,bad)
    bad=re.sub(r'(?ms)^  OBS\n.*?^  END\n','',lef)
    (folder/'missing_obstructions.lef').write_text(bad)
    reject('missing_obstructions',fine,spec,record,gds,bad)
    for name,change in [('missing_canonical_label','label'),('missing_native_mim','mask')]:
        lib,top=read(gds,fine)
        if change=='label':
            for shape in top.shapes(lib.find_layer(70,5)).each():
                if shape.is_text() and shape.text.string=='A':
                    t=shape.text;t.string='NODE';shape.text=t
        else:
            top.flatten(True);top.shapes(lib.find_layer(*geometry.MIM)).clear()
        path=folder/(name+'.gds');lib.write(str(path));reject(name,fine,spec,record,path,lef)
    wrong=deepcopy(record);wrong['pins']['A']['shapes'][0][1][0]+=100
    (folder/'wrong_pin_rectangle.json').write_text(json.dumps(wrong,indent=2)+'\n')
    reject('wrong_pin_rectangle',fine,spec,wrong,gds,lef)
    model=producer.SC+'buf_4';wrong=deepcopy(records[model]);wrong['well_domain_nets']['VPB']='VGND'
    (folder/'wrong_nwell_domain.json').write_text(json.dumps(wrong,indent=2)+'\n')
    reject('wrong_nwell_domain',model,i['specs'][model],wrong,parent/'gds'/(model+'.gds'),(parent/'lef'/(model+'.lef')).read_text())
    (folder/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    return results


def verify(parent):
    i=producer.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if not r['registered_cell_library_passed'] or r['qualified_phy'] or r['electrical_qualification_passed']:
        raise ValueError('Require completed unpromoted physical library')
    if any(sha(parent/n)!=h for n,h in r['files'].items()):raise ValueError('Registered asset changed')
    paths=[parent/'manifest.json',parent/'summary.json',*[parent/n for n in r['files']]]
    code=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                 if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
                  code={str(p.relative_to(ROOT)):sha(p) for p in code})
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():bound(out);return out
    out.mkdir(parents=True);(out/'manifest.json').write_text(json.dumps(dict(identity=identity),indent=2)+'\n')
    cells={m:audit(m,s,r['cells'][m],parent/'gds'/(m+'.gds'),(parent/'lef'/(m+'.lef')).read_text()) for m,s in i['specs'].items()}
    combined=db.Layout();combined.read(str(parent/'library.gds'));names=set()
    for model in cells:
        lib,top=read(parent/'gds'/(model+'.gds'),model);incoming={c.name for c in lib.each_cell()}
        if names&incoming:raise ValueError('Hierarchy collision in registered library')
        names|=incoming;joined=combined.cell(model)
        for index in lib.layer_indexes():
            layer=lib.get_info(index)
            if not (region(lib,top,(layer.layer,layer.datatype))^region(combined,joined,(layer.layer,layer.datatype))).is_empty():
                raise ValueError('Merged library masks differ from selected cell')
    if names!={c.name for c in combined.each_cell()}:raise ValueError('Merged library cell inventory differs')
    opendb=producer.check_opendb(out,i,r['cells'])
    controls=negative_controls(out,dict(i,_parent=str(parent.relative_to(ROOT))),r['cells'])
    producer.bound(parent)
    if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Audit inputs changed')
    report=dict(cells=cells,opendb=opendb,merged_library_masks_and_namespace_verified=True,negative_controls=controls,
                independent_geometry_audit_passed=True,physical_body_tap_insertion_still_required=True,
                whole_bank_placement_routing_qualified=False,electrical_qualification_passed=False,qualified_phy=False)
    report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');bound(out);return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity'];r=json.loads((out/'summary.json').read_text())
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
            or any(sha(out/n)!=h for n,h in r['files'].items())
            or not r['independent_geometry_audit_passed'] or len(r['cells'])!=12
            or len(r['negative_controls'])!=6 or not all(c['rejected'] for c in r['negative_controls'])
            or r['qualified_phy'] or r['electrical_qualification_passed'] or r['whole_bank_placement_routing_qualified']):
        raise ValueError('Independent physical library proof changed')
    producer.bound(ROOT/i['parent']);return i


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path)
    print(verify(p.parse_args().parent.resolve()))
