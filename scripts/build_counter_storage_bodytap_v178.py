#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Add a physical substrate-contact row to the unchanged guarded storage NAND."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import build_clock_cell_shunts_v4 as source
import build_parallel_output_cell_v111 as rc_proof
import native_bank_inventory_v51 as inventory

ROOT=source.ROOT
sha=source.sha
VERSION='storage-nand2-guarded-native-mirrored-body-tap-row-and-rc-v178.1'
CONTEXT='counter_storage_bodytap_v178'
OLD='openlvds_nand2_4_o3_shunted_v2'
NAME='openlvds_nand2_4_o3_bodytap_v178'
TAP=source.TAP
LAYERS={'metal1':(68,20),'via1':(68,44),'metal2':(69,20),'via2':(69,44),'metal3':(70,20)}


def plan(lef):
    gate=source.native.lef_cell(lef,'sky130_fd_sc_hd__nand2_4');tap=source.native.lef_cell(lef,TAP)
    width=gate['width']+2*tap['width'];count=round(width/tap['width']);y=-.4;power=y-tap['height'];ground_y=-.8;vpwr_y=3.6;row_power=-4.
    if abs(count*tap['width']-width)>source.layout.GRID/2:raise ValueError('Tap row must fill exact native sites')
    g=source.layout.Geometry()
    for x in (tap['width']/2,width-tap['width']/2):
        g.via12(x,y);g.wire('metal2',x,y,x,ground_y,.4);g.via23(x,ground_y)
        g.via12(x,power);g.wire('metal2',x,power,x,row_power,.4);g.via23(x,row_power)
    g.wire('metal3',-1.,row_power,width-tap['width']/2,row_power,.6)
    g.via23(-1.,row_power);g.wire('metal2',-1.,row_power,-1.,vpwr_y,.4)
    g.via23(-1.,vpwr_y);g.wire('metal3',-1.,vpwr_y,.3,vpwr_y,.6)
    if set(g.layers)-set(LAYERS):raise ValueError('Unexpected substrate-row routing layer')
    return dict(count=count,pitch_um=tap['width'],ground_y_um=y,power_y_um=power,layers=dict(g.layers))


def schematic(text,p):
    renamed=re.sub(r'\b'+OLD+r'\b',NAME,text);marker='.ends '+NAME+'\n'
    if renamed.count(marker)!=1 or 'Xtap_bottom' in renamed:raise ValueError('Require the original unmodified storage NAND reference')
    return renamed.replace(marker,''.join(f'Xtap_bottom{k} VGND VPWR {TAP}\n' for k in range(p['count']))+marker)


def geometry(text,tap_box,p):
    if 'tap_bottom' in text or text.count('<< labels >>')!=1:raise ValueError('Require original guarded macro Magic view')
    for layer,rectangles in p['layers'].items():
        marker='<< '+layer+' >>';shapes='\n'.join('rect '+' '.join(map(str,r)) for r in rectangles)
        if marker in text:text=text.replace(marker,marker+'\n'+shapes,1)
        else:
            match=re.search(r'(?m)^use ',text)
            if match is None:raise ValueError('Missing original native hierarchy')
            text=text[:match.start()]+marker+'\n'+shapes+'\n'+text[match.start():]
    taps=[]
    for k in range(p['count']):
        taps += [f'use {TAP} tap_bottom{k}','timestamp 0',
                 f'transform 1 0 {round(k*p["pitch_um"]/source.layout.GRID)} 0 -1 {round(p["ground_y_um"]/source.layout.GRID)}',
                 'box '+' '.join(str(round(v/source.layout.GRID)) for v in tap_box)]
    return text.replace('<< labels >>','\n'.join(taps)+'\n<< labels >>',1)


def contact_row_witness(folder,p):
    """Independent row-only CIF reference, including native implant abutment masks."""
    name=NAME+'_contact_row';box=source.native.native_bbox(folder/(TAP+'.mag'))
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0']
    for layer,rectangles in p['layers'].items():
        lines += ['<< '+layer+' >>',*['rect '+' '.join(map(str,r)) for r in rectangles]]
    for k in range(p['count']):
        lines += [f'use {TAP} tap_bottom{k}','timestamp 0',
                  f'transform 1 0 {round(k*p["pitch_um"]/source.layout.GRID)} 0 -1 {round(p["ground_y_um"]/source.layout.GRID)}',
                  'box '+' '.join(str(round(v/source.layout.GRID)) for v in box)]
    lines.append('<< end >>');(folder/(name+'.mag')).write_text('\n'.join(lines)+'\n')
    source.layout.invoke_magic(folder,f'load {name} -silent\ngds write {name}.gds','contact_row_cif_witness')
    return folder/(name+'.gds')


def masks(reference,candidate,p,witness):
    db=rc_proof.db;a=db.Layout();a.read(str(reference));b=db.Layout();b.read(str(candidate));w=db.Layout();w.read(str(witness))
    if a.dbu!=.001 or b.dbu!=a.dbu or w.dbu!=a.dbu:raise ValueError('Native storage macro scale changed')
    if {c.name for c in b.each_cell()}!={NAME if c.name==OLD else c.name for c in a.each_cell()}:raise ValueError('Original native masters changed')
    layers={(x.get_info(i).layer,x.get_info(i).datatype) for x in (a,b,w) for i in x.layer_indexes()}
    def region(lib,cell,layer):
        index=lib.find_layer(*layer)
        return db.Region() if index is None else db.Region(cell.shapes(index)).merged()
    def placements(lib,cell):return Counter((lib.cell(i.cell_index).name,i.cplx_trans.to_s(),i.a.x,i.a.y,i.b.x,i.b.y,i.na,i.nb) for i in cell.each_inst())
    extra=Counter((TAP,db.ICplxTrans(1,0,True,round(k*p['pitch_um']/a.dbu),round(p['ground_y_um']/a.dbu)).to_s(),0,0,0,0,0,0) for k in range(p['count']))
    if {c.name for c in w.each_cell()}!={NAME+'_contact_row',TAP} or placements(w,w.cell(NAME+'_contact_row'))!=extra:
        raise ValueError('Contact-row witness has a different hierarchy or placement')
    for layer in layers:
        if not (region(a,a.cell(TAP),layer)^region(w,w.cell(TAP),layer)).is_empty():raise ValueError('Contact-row witness changed native tap masks')
    for old in a.each_cell():
        new=b.cell(NAME if old.name==OLD else old.name)
        if new is None:raise ValueError('Native gate, tap or MIM master missing')
        for layer in layers:
            expected=region(a,old,layer)
            if old.name==OLD:expected|=region(w,w.cell(NAME+'_contact_row'),layer)
            if not (expected.merged()^region(b,new,layer)).is_empty():raise ValueError('Native masks differ beyond declared tap-row wiring')
        wanted=placements(a,old)+(extra if old.name==OLD else Counter())
        if wanted!=placements(b,new):raise ValueError('Native placement differs beyond declared mirrored tap row')
    return dict(all_original_native_child_masks_and_placements_identical=True,only_declared_contact_row_cif_masks_and_supply_wiring_added=True,
                original_output_and_stack_mim_geometry_preserved=True,mirrored_native_body_taps=p['count'],qualified_phy=False)


def parent_inputs(parent,cause):
    m=source.bound(parent);report=json.loads((parent/'summary.json').read_text());rows=[r for r in report['rows'] if r['macro']==OLD]
    if not report['passed'] or len(rows)!=1 or not rows[0]['passed']:raise ValueError('Require complete qualified original storage NAND')
    folder=parent/OLD;row=rows[0]
    if sha(folder/(OLD+'.gds'))!=row['gds_sha256']:raise ValueError('Original storage masks changed')
    r=json.loads((cause/'summary.json').read_text());manifest=json.loads((cause.parent/'manifest.json').read_text())
    failed=[d for d in r['result']['terminal_stress'] if not d['passed']]
    if (r['error'] is not None or r['task'] not in manifest['tasks'] or r['task']['variant']!='3'
        or r['task']['spec']['process']!='ss' or r['task']['spec']['temperature']!=0 or r['task']['spec']['stop_level']!=0
        or len(failed)!=1 or failed[0]['device']!='XD:XR:Xlow0_q:X0'
        or any(sha(cause/n)!=h for n,h in r['files'].items())):raise ValueError('Require the completed larger-guard storage reset failure')
    return m,row,folder,r


def prepare(parent,cause):
    m,row,folder,r=parent_inputs(parent,cause)
    # Use the same pinned native library as the qualified source.
    import os
    lef=Path(os.environ['PDK_ROOT'])/'sky130A/libs.ref/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef'
    p=plan(lef.read_text())
    paths=[parent/'manifest.json',parent/'summary.json',*[x for x in folder.iterdir() if x.is_file()],cause.parent/'manifest.json',cause/'summary.json',*[cause/n for n in r['files']]]
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),cause=str(cause.relative_to(ROOT)),plan=p,ports=list(row['ports']),anchors=row['ports'],
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},external_files={str(lef):sha(lef),**m['identity']['pdk_files']},
           tools=source.native.environment.tools(),math_runtime=rc_proof.math_proof.math_proof()['runtime'])
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items()) or any(sha(Path(n))!=h for n,h in i['external_files'].items())
        or source.native.environment.tools()!=i['tools'] or rc_proof.math_proof.math_proof()['runtime']!=i['math_runtime']):raise ValueError('Storage body-tap context changed')
    parent_inputs(ROOT/i['parent'],ROOT/i['cause']);return i


def run(out):
    i=bound(out);parent=ROOT/i['parent']/OLD
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain existing or partial physical storage repair')
        (out/'state.json').write_text('{"status":"qualifying","qualified_phy":false}\n')
        for f in parent.glob('*.mag'):
            if f.name!=OLD+'.mag':shutil.copy2(f,out/f.name)
        (out/(NAME+'.mag')).write_text(geometry((parent/(OLD+'.mag')).read_text(),source.native.native_bbox(parent/(TAP+'.mag')),i['plan']))
        (out/(NAME+'.sch.spice')).write_text(schematic((parent/(OLD+'.sch.spice')).read_text(),i['plan']))
        physical=source.layout.qualify(out,NAME)
        (out/'physical.json').write_text(json.dumps(physical,indent=2)+'\n')
        if not physical['passed']:raise ValueError('Native tap-row DRC/LVS failed; retain geometry')
        witness=contact_row_witness(out,i['plan'])
        mask=masks(parent/(OLD+'.gds'),out/(NAME+'.gds'),i['plan'],witness)
        normalize=lambda s:re.sub(r'\n[ \t]*\+[ \t]*',' ',s)
        _,before=inventory.native_leaves(normalize((parent/(OLD+'.lvs.spice')).read_text()),OLD+'_flat')
        public,after=inventory.native_leaves(normalize((out/(NAME+'.lvs.spice')).read_text()),NAME+'_flat')
        params=inventory.compare_parameters(before,after)
        if public!=i['ports']:raise ValueError('Storage macro public interface order changed')
        gds=out/(NAME+'.gds');digest=hashlib.sha256(gds.read_bytes()+Path(rc_proof.extractor.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/digest/NAME).exists():raise ValueError('Retain existing tap-row extraction')
        anchors={n:i['anchors'][n] for n in i['ports']}
        rc=rc_proof.extractor.extract(NAME,gds,sha(out/'manifest.json'),ports=anchors,source_scope=sha(out/(NAME+'.sch.spice')))
        if rc['ports']!=i['ports'] or not rc['ports_verified']:raise ValueError('Storage RC interface order changed')
        proof=rc_proof.certify(out,rc,NAME,out/(NAME+'.lvs.spice'),len(before))
        bound(out)
        result=dict(physical=physical,native_parameters=params,mask_comparison=mask,extraction=rc,rc_proof=proof,
            component_physical_rc_passed=True,counter_timing_qualified=False,whole_clock_rc_qualified=False,qualified_phy=False,
            scope='Unchanged native guarded NAND2 MOS and MIMs plus a mirrored substrate-contact row and explicit supply routes; fresh component DRC/LVS/RC, no integrated counter or PHY admission')
        result['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('.execution.lock','state.json')}
        result['extracted_files']={str((ROOT/rc[k]).relative_to(ROOT)):sha(ROOT/rc[k]) for k in ('raw_netlist','netlist')}
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n');(out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--cause',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.cause is None:p.error('--cause required')
        out=prepare(out,a.cause.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
