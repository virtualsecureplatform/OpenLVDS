#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Register normalized bank GDS/LEF with aliases, MIM keepouts and body domains."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import layout
import physical_cell_adapter_v44 as adapter

ROOT=layout.ROOT
VERSION='both2-normalized-physical-cell-library-mim-and-body-domains-v44.1'
CONTEXT='bank_cell_registry_v44'
SC='sky130_fd_sc_hd__'
TAP=SC+'tapvpwrvgnd_1'
FILL=SC+'fill_1'
CUSTOM={
 'openlvds_inv_8_nlvt_o2_v34':('nlvt_guard2_v34',4.),
 'openlvds_buf_4_pair_nlvt_v29':('nlvt_data_components_v29',0.),
 'openlvds_tg_quad_stacked_nlvt_v27':('stacked_nlvt_tg_v27',0.),
 'openlvds_mim_switch_2x3_v2':('mim_switch_2x3_physical_v2',10.),
 'openlvds_tail_mim2_v39':('tail_mim2_v39',4.),
}
FINE_ALIASES=dict(NODE='A',EN='CTRL',ENB='CTRL_B',VDD='VPWR',VSS='VGND')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value):return json.loads(json.dumps(value,sort_keys=True))


def verify_graph(evidence):
    code='import sys,json;from pathlib import Path;sys.path.insert(0,str(Path(sys.argv[1])/"scripts"));import verify_tg_bank_netlist_v46 as p;print(json.dumps(p.bound(Path(sys.argv[2])),sort_keys=True))'
    p=subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'),'-c',code,str(ROOT),str(evidence)],capture_output=True,text=True,check=True)
    i=json.loads(p.stdout);parent=ROOT/i['parent'];pi=json.loads((parent/'manifest.json').read_text())['identity']
    if evidence.parent!=ROOT/'build/diagnostics/tg_bank_netlist_verification_v46':raise ValueError('Require the independent both2 physical graph proof')
    data=json.loads((parent/'bank.json').read_text())
    directions={m:{p:v['direction'] for p,v in data['modules'][m]['ports'].items()} for m in pi['graph']['orders']}
    return i,parent,pi,directions


def select_sources(pi,directions,pdk):
    lef=pdk/'libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef'
    gds=pdk/'libs.ref/sky130_fd_sc_hd/gds/sky130_fd_sc_hd.gds'
    text=lef.read_text();specs={}
    for model,order in pi['graph']['orders'].items():
        if model in CUSTOM:
            context,_=CUSTOM[model]
            found=[ROOT/n for n in pi['inputs'] if n.startswith('build/diagnostics/'+context+'/') and Path(n).name==model+'.gds']
            if len(found)!=1:raise ValueError('Require one bound physical GDS for '+model)
            source=found[0];source_lef=source.with_suffix('.lef')
            aliases=FINE_ALIASES if model=='openlvds_mim_switch_2x3_v2' else {p:p for p in order}
            specs[model]=dict(kind='custom',gds=str(source),lef=str(source_lef),order=order,directions=directions[model],aliases=aliases)
        elif model.startswith(SC):
            adapter.description(text,model)
            specs[model]=dict(kind='standard',gds=str(gds),lef=str(lef),order=order,directions=directions[model],aliases={p:p for p in order})
        else:raise ValueError('Unknown physical bank model')
    for model,role in [(TAP,'well_tap'),(FILL,'well_bridge_filler')]:
        pins=adapter.description(text,model)['pins']
        if not set(pins)<= {'VPWR','VGND','VPB','VNB'}:raise ValueError('Support cell contains a functional signal pin')
        specs[model]=dict(kind='standard',role=role,gds=str(gds),lef=str(lef),order=list(pins),directions={p:'inout' for p in pins},aliases={p:p for p in pins})
    return specs


def region(db,lib,cell,key):
    index=lib.find_layer(*key)
    return db.Region() if index is None else db.Region(cell.begin_shapes_rec(index)).merged()


def transformed_cell(spec,model):
    import klayout.db as db
    lib=db.Layout();lib.read(spec['gds']);top=lib.cell(model)
    if top is None or lib.dbu!=.001:raise ValueError('Missing physical master or noncanonical 1 nm GDS grid')
    info=adapter.description(Path(spec['lef']).read_text(),model)
    marker=region(db,lib,top,adapter.MIM)
    if spec['kind']=='custom' and abs(marker.area()*lib.dbu**2-CUSTOM[model][1])>1e-8:
        raise ValueError('Unexpected native MIM marker geometry')
    if spec['kind']=='standard' and not marker.is_empty():raise ValueError('Unexpected MIM in standard control/support cell')
    ox,oy=info['origin'];w,h=info['size']
    box=db.Box(round(-ox/lib.dbu),round(-oy/lib.dbu),round((w-ox)/lib.dbu),round((h-oy)/lib.dbu))
    keepouts=[]
    for polygon in marker.each_merged():
        cap=polygon.bbox()
        if polygon.area()!=cap.area():raise ValueError('Nonrectangular native MIM marker')
        halo=cap.enlarged(round(adapter.M3_CLEARANCE/lib.dbu));box=box+halo
        keepouts += [('met3',halo),('met4',cap.enlarged(round(adapter.M4_CLEARANCE/lib.dbu)))]
    shift=(-box.left,-box.bottom) if spec['kind']=='custom' else (0,0)
    size=[box.width()*lib.dbu,box.height()*lib.dbu] if spec['kind']=='custom' else info['size']
    anchors={}
    if spec['kind']=='custom':
        index=lib.find_layer(70,5)
        if index is None:raise ValueError('Custom cell has no public M3 labels')
        for name in spec['aliases']:
            labels=[s.text for s in top.shapes(index).each() if s.is_text() and s.text.string==name]
            if len(labels)!=1:raise ValueError('Missing/ambiguous public M3 label: '+name)
            anchors[name]=(labels[0].x*lib.dbu,labels[0].y*lib.dbu)
        ko=[(layer,tuple(round(v*lib.dbu,6) for v in (b.left+shift[0],b.bottom+shift[1],b.right+shift[0],b.top+shift[1]))) for layer,b in keepouts]
        lef,pins=adapter.integration_lef(info['block'],model,spec['order'],spec['directions'],spec['aliases'],anchors,
                                       [x*lib.dbu for x in shift],size,ko)
    else:
        pins=adapter.standard_pins(info['block'],model,spec['order'],spec['directions']);lef=info['block']
    # Root names must match the physical netlist. Descendants get compact,
    # root-specific names, so shared legacy PCell/tap names cannot collide.
    todo=[top.cell_index()];seen=set()
    while todo:
        index=todo.pop()
        if index in seen:continue
        seen.add(index);todo += [i.cell_index for i in lib.cell(index).each_inst()]
    tag=hashlib.sha256(model.encode()).hexdigest()[:8];renamed={}
    for index in sorted(seen):
        child=lib.cell(index)
        if index!=top.cell_index():
            old=child.name;child.name='ov44_'+tag+'_'+hashlib.sha256(old.encode()).hexdigest()[:8];renamed[old]=child.name
    for index in lib.layer_indexes():
        for shape in top.shapes(index).each():
            if shape.is_text() and shape.text.string in spec['aliases']:
                text=shape.text;text.string=spec['aliases'][text.string];shape.text=text
    top.transform(db.Trans(0,False,shift[0],shift[1]))
    metadata=canonical(dict(size_um=size,shift_um=[x*lib.dbu for x in shift],source_origin_um=info['origin'],pins=pins,
                            aliases=spec['aliases'],renamed_children=renamed,mim_area_um2=marker.area()*lib.dbu**2,
                            mim_m3_clearance_um=adapter.M3_CLEARANCE,mim_m4_clearance_um=adapter.M4_CLEARANCE,
                            requires_external_taps=spec['kind']=='standard' and model!=TAP,
                            well_domain_nets={pin:('VGND' if pin in ('VNB','VGND') else 'VPWR') for pin,data in pins.items() if data.get('well_domain_only')},
                            role=spec.get('role','functional'),kind=spec['kind']))
    return lib,top,lef,metadata


def audit_asset(spec,model,gds,lef,metadata):
    import klayout.db as db
    before=db.Layout();before.read(spec['gds']);a=before.cell(model)
    after=db.Layout();after.read(str(gds));b=after.cell(model)
    if a is None or b is None or before.dbu!=after.dbu:raise ValueError('Registered GDS master or scale changed')
    dx,dy=[round(x/after.dbu) for x in metadata['shift_um']]
    keys={(l.get_info(i).layer,l.get_info(i).datatype) for l in (before,after) for i in l.layer_indexes()}
    for key in keys:
        if not (region(db,before,a,key)^region(db,after,b,key).transformed(db.Trans(0,False,-dx,-dy))).is_empty():
            raise ValueError('Registered manufacturing mask changed: '+model+' '+str(key))
    info=adapter.description(lef.read_text(),model)
    if info['origin']!=[0.,0.] or set(info['pins'])!=set(spec['order']):raise ValueError('Registered LEF origin or interface changed')
    for pin,p in metadata['pins'].items():
        observed=canonical(info['pins'][pin])
        if observed!=p['shapes']:raise ValueError('Registered pin geometry changed')
        for layer,rect in p['shapes']:
            if layer not in adapter.ROUTING:continue
            shape=db.Region(db.Box(*[round(x/after.dbu) for x in rect]))
            if not (shape-region(db,after,b,adapter.ROUTING[layer])).is_empty():
                raise ValueError('LEF routing pin extends outside actual GDS metal: '+model+'/'+pin+'/'+layer)
    return dict(all_native_masks_preserved_under_translation=True,all_routing_pin_rectangles_on_actual_metal=True,
                logical_interface_and_zero_origin_verified=True)


def prepare(evidence):
    import klayout.db as db
    gi,parent,pi,directions=verify_graph(evidence)
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';specs=select_sources(pi,directions,pdk)
    paths=[evidence/'manifest.json',evidence/'summary.json',*[ROOT/n for n in gi['inputs']],parent/'bank.sch.spice']
    external=dict(pi['external_files'])
    for s in specs.values():
        for key in ('gds','lef'):
            p=Path(s[key])
            if p.is_relative_to(ROOT):paths.append(p)
            else:external[str(p)]=sha(p)
    tech=pdk/'libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef'
    external[str(tech)]=sha(tech)
    code=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                 if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    identity=dict(version=VERSION,evidence=str(evidence.relative_to(ROOT)),graph_parent=str(parent.relative_to(ROOT)),specs=specs,
                  inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},code={str(p.relative_to(ROOT)):sha(p) for p in code},
                  external_files=external,tech_lef=str(tech),openroad=dict(path=shutil.which('openroad'),sha256=sha(Path(shutil.which('openroad')))),
                  tools={n:dict(path=shutil.which(n),sha256=sha(Path(shutil.which(n)))) for n in ('magic','netgen')},
                  klayout=dict(version=db.__version__,module_sha256=sha(Path(db.__file__))))
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    import klayout.db as db
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
            or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in {**i['inputs'],**i['code']}.items())
            or any(sha(Path(n))!=h for n,h in i['external_files'].items())
            or any(sha(Path(t['path']))!=t['sha256'] for t in [i['openroad'],*i['tools'].values()])
            or i['klayout']!=dict(version=db.__version__,module_sha256=sha(Path(db.__file__)))):
        raise ValueError('Physical bank cell registry context changed')
    return i


def check_opendb(out,i,records):
    tcl='read_lef {'+i['tech_lef']+'}\nread_lef {'+str(out/'library.lef')+'}\nset db [ord::get_db]\n'
    tcl+='set f [open {'+str(out/'opendb.tsv')+'} w]\nputs $f "UNITS\\t[[$db getTech] getDbUnitsPerMicron]"\n'
    for model in records:
        tcl+='set master [$db findMaster '+model+']\nif {$master == "NULL"} {error "Missing master"}\n'
        tcl+='puts $f "MASTER\\t'+model+'\\t[$master getWidth]\\t[$master getHeight]"\n'
        tcl+='foreach term [$master getMTerms] {\nputs $f "PIN\\t'+model+'\\t[$term getName]\\t[$term getIoType]\\t[$term getSigType]"\n'
        tcl+='foreach pin [$term getMPins] {foreach s [$pin getGeometry] {puts $f "BOX\\t'+model+'\\t[$term getName]\\t[[$s getTechLayer] getName]\\t[$s xMin]\\t[$s yMin]\\t[$s xMax]\\t[$s yMax]"}}\n}\n'
    tcl+='close $f\nexit\n';(out/'check.tcl').write_text(tcl)
    p=subprocess.run([i['openroad']['path'],'-no_init','-exit',str(out/'check.tcl')],cwd=out,capture_output=True,text=True)
    (out/'openroad.log').write_text(p.stdout+p.stderr);p.check_returncode()
    units=None;masters={};pins={};boxes={}
    for line in (out/'opendb.tsv').read_text().splitlines():
        w=line.split('\t')
        if w[0]=='UNITS':units=int(w[1])
        elif w[0]=='MASTER':masters[w[1]]=[int(x) for x in w[2:]]
        elif w[0]=='PIN':pins.setdefault(w[1],{})[w[2]]=w[3:]
        elif w[0]=='BOX':boxes.setdefault((w[1],w[2]),[]).append((w[3],tuple(int(x) for x in w[4:])))
    if not units or set(masters)!=set(records):raise ValueError('OpenDB master inventory changed')
    for model,r in records.items():
        if masters[model]!=[round(x*units) for x in r['size_um']] or set(pins.get(model,{}))!=set(r['pins']):
            raise ValueError('OpenDB master size or port inventory changed')
        for pin,d in r['pins'].items():
            expected=sorted((layer,tuple(round(x*units) for x in rect)) for layer,rect in d['shapes'])
            if pins[model][pin]!=[d['direction'],d['use']] or sorted(boxes.get((model,pin),[]))!=expected:
                raise ValueError('OpenDB pin direction, use or rectangle changed: '+model+'/'+pin)
    return dict(all_opendb_masters_and_pin_rectangles_verified=True,db_units_per_um=units)


def run(out):
    import klayout.db as db
    import fcntl
    i=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial physical cell registry')
        (out/'state.json').write_text('{"status":"building","qualified_phy":false}\n')
        (out/'gds').mkdir();(out/'lef').mkdir();records={};lefs=[];combined=db.Layout();combined.dbu=.001;names=set()
        for model,spec in i['specs'].items():
            lib,top,lef,record=transformed_cell(spec,model)
            gds=out/'gds'/(model+'.gds');options=db.SaveLayoutOptions();options.select_cell(top.cell_index());lib.write(str(gds),options)
            path=out/'lef'/(model+'.lef');path.write_text('VERSION 5.7 ;\n'+lef)
            record['audit']=audit_asset(spec,model,gds,path,record)
            selected=db.Layout();selected.read(str(gds));incoming={c.name for c in selected.each_cell()}
            if names&incoming:raise ValueError('Registered hierarchy names collide')
            names|=incoming;combined.read(str(gds));lefs.append(lef);records[model]=record
        combined.write(str(out/'library.gds'))
        (out/'library.lef').write_text('VERSION 5.7 ;\nDIVIDERCHAR "/" ;\nBUSBITCHARS "[]" ;\n'+''.join(lefs)+'END LIBRARY\n')
        observed=check_opendb(out,i,records)
        # Fresh GDS/native checks for the five custom masters also verify that
        # public-label aliases and origin shifts preserve device connectivity.
        source=(ROOT/i['graph_parent']/'bank.sch.spice').read_text();qualification={}
        for model,spec in i['specs'].items():
            if spec['kind']!='custom':continue
            folder=out/'native'/model;folder.mkdir(parents=True)
            block=re.search(r'(?ims)^\.subckt\s+'+re.escape(model)+r'\s[^\n]*\n.*?^\.ends[^\n]*',source)
            if block is None:raise ValueError('Missing reference native component')
            expected=block[0]+'\n';(folder/(model+'.sch.spice')).write_text(expected)
            file=out/'gds'/(model+'.gds');lib=db.Layout();lib.read(str(file))
            commands=['gds readonly false',f'gds read {{{file}}}']
            for cell in lib.each_cell():commands += [f'load {cell.name}',f'save {cell.name}']
            commands += [f'load {model}']
            for index,pin in enumerate(spec['order'],1):
                x,y=records[model]['pins'][pin]['anchor_um']
                commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um',f'port make {index}']
            commands += [f'save {model}'];layout.invoke_magic(folder,'\n'.join(commands),'import_registered')
            q=layout.qualify(folder,model)
            if not q['passed']:raise ValueError('Registered custom cell failed fresh native DRC/LVS: '+model)
            if adapter.parameter_signature(expected)!=adapter.parameter_signature((folder/(model+'.lvs.spice')).read_text()):
                raise ValueError('Registered custom native dimensions/junctions changed')
            qualification[model]=dict(physical=q,native_dimensions_and_junctions_preserved=True)
        bound(out)
        report=dict(cells=records,opendb=observed,custom_native_qualification=qualification,registered_cell_library_passed=True,
                    functional_masters=10,support_masters=2,physical_body_tap_insertion_still_required=True,
                    whole_bank_placement_routing_qualified=False,electrical_qualification_passed=False,qualified_phy=False)
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('.execution.lock','state.json')}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
        return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
