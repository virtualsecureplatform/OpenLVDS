#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Normalize measured fine/output cells for physical bank integration.

Standalone library additions only. Existing registries, bank timing and PHY
admission are not modified. Preserve every manufacturing mask under translation.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import layout
import build_bank_cell_registry_v44 as registry
import physical_cell_adapter_v44 as adapter
import native_bank_inventory_v51 as inventory

ROOT=layout.ROOT
sha=registry.sha
VERSION='measured-fine-and-parallel-output-canonical-physical-views-v114.1'
CONTEXT='clock_cell_views_v114'
FINE=ROOT/'build/diagnostics/moscap_fine_rc_v87/348ca2c69a6af091'
PAIR=ROOT/'build/diagnostics/parallel_output_cell_v111/719aa3336298176d'
FINE_ALIASES=dict(NODE='A',EN='CTRL',ENB='CTRL_B',VDD='VPWR',VSS='VGND')
PAIR_ALIASES=dict(IN='A',OUT='Y',VPWR='VPWR',VGND='VGND')


def reference(text,source,target,aliases):
    """Rename the top/interface without altering private nodes or primitives."""
    defs=layout.circuits(text)
    if source not in defs or set(defs[source][0])!=set(aliases):
        raise ValueError('Source component interface changed')
    if len(set(aliases.values()))!=len(aliases):
        raise ValueError('Canonical component aliases are not bijective')
    # Work on the top definition only: child pin names are independent namespaces.
    block=registry.re.search(r'(?ims)^\.subckt\s+'+re.escape(source)+r'\s[^\n]*\n.*?^\.ends[^\n]*',text)
    if block is None:raise ValueError('Source component definition missing')
    replacement=re.sub(r'\b(?:'+ '|'.join(map(re.escape,[source,*aliases]))+r')\b',
                       lambda m:target if m[0]==source else aliases[m[0]],block[0])
    return text[:block.start()]+replacement+text[block.end():]


def sources():
    # Numeric receipt checks run in the pinned scientific Python, while this
    # process uses CAD Python for KLayout/OpenDB/native layout tools.
    code='import sys;sys.path.insert(0,"scripts");import post_mux_output_rc_bank_v112 as c;c.checked_cell(c.ROOT/sys.argv[1]);c.checked_driver()'
    subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'),'-c',code,str(FINE.relative_to(ROOT))],cwd=ROOT,check=True)
    fi=json.loads((FINE/'manifest.json').read_text());fr=json.loads((FINE/'summary.json').read_text())
    pi=json.loads((PAIR/'manifest.json').read_text())['identity'];pr=json.loads((PAIR/'summary.json').read_text())
    fp=ROOT/fi['parent'];fs='openlvds_moscap_fine_w126_v77'
    row=pr['rows'][0];ps=row['graph']['top'];pp=ROOT/row['physical']['gds']
    specs={
        'openlvds_fine_moscap_w126_far_v114':dict(source_top=fs,gds=str(ROOT/fr['native_geometry']['gds']),
            lef=str((ROOT/fr['native_geometry']['gds']).with_suffix('.lef')),
            schematic=str(fp/(fs+'.sch.spice')),native_reference=str(fp/(fs+'.lvs.spice')),
            aliases=FINE_ALIASES,order=['A','CTRL','CTRL_B','VPWR','VGND'],
            directions=dict(A='inout',CTRL='input',CTRL_B='input',VPWR='inout',VGND='inout'),mim_area_um2=4.,native_primitives=6),
        'openlvds_parallel_inv8_registered_v114':dict(source_top=ps,gds=str(pp),lef=str(pp.with_suffix('.lef')),
            schematic=str(PAIR/'inv2/native'/(ps+'.sch.spice')),native_reference=str(PAIR/'inv2/native'/(ps+'.lvs.spice')),
            aliases=PAIR_ALIASES,order=['A','Y','VPWR','VGND'],
            directions=dict(A='input',Y='output',VPWR='inout',VGND='inout'),mim_area_um2=8.,native_primitives=34),
    }
    paths=[]
    for parent,i,r,extracted in [(FINE,fi,fr,'original_extracted_files'),(PAIR,pi,pr,'extracted_files')]:
        paths += [parent/'manifest.json',parent/'summary.json',*[ROOT/n for n in i['inputs']],*[parent/n for n in r['files']],*[ROOT/n for n in r[extracted]]]
    for s in specs.values():paths += [Path(s[k]) for k in ['gds','lef','schematic','native_reference']]
    return specs,sorted(set(paths))


def prepare():
    import klayout.db as db
    specs,paths=sources();pdk=Path(os.environ['PDK_ROOT'])/'sky130A'
    external=[pdk/'libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef',
              pdk/'libs.tech/magic/sky130A.magicrc',pdk/'libs.tech/netgen/sky130A_setup.tcl']
    code=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                 if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    tools={n:dict(path=shutil.which(n),sha256=sha(Path(shutil.which(n)))) for n in ['openroad','magic','netgen']}
    i=dict(version=VERSION,specs=specs,inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
           code={str(p.relative_to(ROOT)):sha(p) for p in code},external_files={str(p):sha(p) for p in external},
           tech_lef=str(external[0]),openroad=tools['openroad'],tools=tools,
           klayout=dict(version=db.__version__,module_sha256=sha(Path(db.__file__))))
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    import klayout.db as db
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
        or any(sha(Path(n))!=h for n,h in i['external_files'].items())
        or any(sha(Path(t['path']))!=t['sha256'] for t in i['tools'].values())
        or i['klayout']!=dict(version=db.__version__,module_sha256=sha(Path(db.__file__)))):
        raise ValueError('Canonical component inputs changed')
    return i


def normalize(spec,target):
    import klayout.db as db
    lib=db.Layout();lib.read(spec['gds']);top=lib.cell(spec['source_top'])
    if top is None or lib.dbu!=.001:raise ValueError('Source native scale/top changed')
    top.name=target
    original=Path(spec['lef']).read_text()
    renamed=re.sub(r'\b'+re.escape(spec['source_top'])+r'\b',target,original)
    info=adapter.description(renamed,target);marker=registry.region(db,lib,top,adapter.MIM)
    if abs(marker.area()*lib.dbu**2-spec['mim_area_um2'])>1e-8:raise ValueError('Native guard/output MIM geometry changed')
    ox,oy=info['origin'];w,h=info['size']
    box=db.Box(round(-ox/lib.dbu),round(-oy/lib.dbu),round((w-ox)/lib.dbu),round((h-oy)/lib.dbu))
    keepouts=[]
    for polygon in marker.each_merged():
        cap=polygon.bbox()
        if cap.area()!=polygon.area():raise ValueError('Nonrectangular MIM marker')
        halo=cap.enlarged(round(adapter.M3_CLEARANCE/lib.dbu));box=box+halo
        keepouts += [('met3',halo),('met4',cap.enlarged(round(adapter.M4_CLEARANCE/lib.dbu)))]
    shift=(-box.left,-box.bottom);size=[box.width()*lib.dbu,box.height()*lib.dbu]
    anchors={};label_index=lib.find_layer(70,5)
    if label_index is None:raise ValueError('Missing actual public M3 labels')
    for pin in spec['aliases']:
        labels=[s.text for s in top.shapes(label_index).each() if s.is_text() and s.text.string==pin]
        if len(labels)!=1:raise ValueError('Missing/ambiguous actual public port: '+pin)
        anchors[pin]=(labels[0].x*lib.dbu,labels[0].y*lib.dbu)
    ko=[(layer,tuple(round(v*lib.dbu,6) for v in (b.left+shift[0],b.bottom+shift[1],b.right+shift[0],b.top+shift[1]))) for layer,b in keepouts]
    lef,pins=adapter.integration_lef(renamed,target,spec['order'],spec['directions'],spec['aliases'],anchors,
                                    [x*lib.dbu for x in shift],size,ko)
    todo=[top.cell_index()];seen=set();renamed_children={};tag=hashlib.sha256(target.encode()).hexdigest()[:8]
    while todo:
        index=todo.pop()
        if index in seen:continue
        seen.add(index);todo += [i.cell_index for i in lib.cell(index).each_inst()]
    for index in sorted(seen):
        child=lib.cell(index)
        if child!=top:
            old=child.name;child.name='ov114_'+tag+'_'+hashlib.sha256(old.encode()).hexdigest()[:8];renamed_children[old]=child.name
    for index in lib.layer_indexes():
        for shape in top.shapes(index).each():
            if shape.is_text() and shape.text.string in spec['aliases']:
                text=shape.text;text.string=spec['aliases'][text.string];shape.text=text
    top.transform(db.Trans(0,False,*shift))
    record=dict(size_um=size,shift_um=[v*lib.dbu for v in shift],pins=pins,aliases=spec['aliases'],
                mim_area_um2=spec['mim_area_um2'],requires_external_taps=False,kind='custom',role='functional',
                renamed_children=renamed_children,well_domain_nets={})
    return lib,top,lef,record


def audit(spec,target,gds,lef,record):
    import klayout.db as db
    before=db.Layout();before.read(spec['gds']);a=before.cell(spec['source_top'])
    after=db.Layout();after.read(str(gds));b=after.cell(target)
    if a is None or b is None or before.dbu!=after.dbu:raise ValueError('Canonical mask scale/top changed')
    dx,dy=[round(v/after.dbu) for v in record['shift_um']]
    keys={(l.get_info(index).layer,l.get_info(index).datatype) for l in [before,after] for index in l.layer_indexes()}
    for key in keys:
        if not (registry.region(db,before,a,key)^registry.region(db,after,b,key).transformed(db.Trans(0,False,-dx,-dy))).is_empty():
            raise ValueError('Canonical manufacturing mask changed: '+str(key))
    info=adapter.description(lef.read_text(),target)
    if info['origin']!=[0.,0.] or set(info['pins'])!=set(spec['order']):raise ValueError('Canonical LEF interface changed')
    for pin,data in record['pins'].items():
        if json.loads(json.dumps(info['pins'][pin]))!=json.loads(json.dumps(data['shapes'])):raise ValueError('Canonical LEF pin changed')
        for layer,rect in data['shapes']:
            shape=db.Region(db.Box(*[round(x/after.dbu) for x in rect]))
            if not (shape-registry.region(db,after,b,adapter.ROUTING[layer])).is_empty():raise ValueError('Canonical pin outside actual native metal')
    return dict(all_native_masks_preserved_under_translation=True,all_pins_on_actual_native_metal=True,zero_origin_verified=True)


def native(out,spec,target,record,gds):
    import klayout.db as db
    folder=out/'native'/target;folder.mkdir(parents=True)
    ref=reference(Path(spec['schematic']).read_text(),spec['source_top'],target,spec['aliases'])
    (folder/(target+'.sch.spice')).write_text(ref)
    lib=db.Layout();lib.read(str(gds));commands=['gds readonly false',f'gds read {{{gds}}}']
    for cell in lib.each_cell():commands += [f'load {cell.name}',f'save {cell.name}']
    commands += [f'load {target}']
    for n,pin in enumerate(spec['order'],1):
        x,y=record['pins'][pin]['anchor_um'];commands += [f'box values {x-.05}um {y-.05}um {x+.05}um {y+.05}um',f'port make {n}']
    commands += [f'save {target}'];layout.invoke_magic(folder,'\n'.join(commands),'import_canonical')
    result=layout.qualify(folder,target)
    if not result['passed']:raise ValueError('Canonical native DRC/LVS failed')
    def leaves(text,top):return inventory.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*',' ',text),top)[1]
    actual=leaves((folder/(target+'.lvs.spice')).read_text(),target+'_flat')
    expected=leaves(ref,target);params=inventory.compare_parameters(expected,actual)
    original=leaves(Path(spec['native_reference']).read_text(),spec['source_top']+'_flat')
    preservation=inventory.compare_parameters(original,actual)
    if params['native_primitives']!=spec['native_primitives']:raise ValueError('Canonical native inventory changed')
    return dict(physical=result,reference_parameters=params,original_native_junctions_preserved=preservation)


def run(out):
    import klayout.db as db
    i=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial canonical views')
        (out/'state.json').write_text('{"status":"qualifying","qualified_phy":false}\n')
        (out/'gds').mkdir();(out/'lef').mkdir();records={};proofs={};combined=db.Layout();combined.dbu=.001;names=set();lefs=[]
        for model,spec in i['specs'].items():
            lib,top,lef,record=normalize(spec,model)
            gds=out/'gds'/(model+'.gds');options=db.SaveLayoutOptions();options.select_cell(top.cell_index());lib.write(str(gds),options)
            path=out/'lef'/(model+'.lef');path.write_text('VERSION 5.7 ;\n'+lef)
            record['audit']=audit(spec,model,gds,path,record)
            fresh=db.Layout();fresh.read(str(gds));incoming={c.name for c in fresh.each_cell()}
            if names&incoming:raise ValueError('Canonical component hierarchy names collide')
            names|=incoming;combined.read(str(gds));lefs.append(lef);records[model]=record
            proofs[model]=native(out,spec,model,record,gds)
        combined.write(str(out/'library.gds'))
        (out/'library.lef').write_text('VERSION 5.7 ;\nDIVIDERCHAR "/" ;\nBUSBITCHARS "[]" ;\n'+''.join(lefs)+'END LIBRARY\n')
        opendb=registry.check_opendb(out,i,records);bound(out)
        report=dict(cells=records,native_qualification=proofs,opendb=opendb,canonical_component_views_passed=True,
                    complete_bank_interconnect_qualified=False,electrical_qualification_passed=False,qualified_phy=False)
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path,nargs='?');a=p.parse_args()
    if a.action=='run' and a.artifact is None:p.error('run requires an artifact')
    out=prepare() if a.action in ['prepare','campaign'] else a.artifact.resolve();print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
