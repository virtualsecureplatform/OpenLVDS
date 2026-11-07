#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Realize the passed counter's additional 5x5 MIM as native physical material.

Only native electrode access labels are added. This is not a new counter
placement, shared-wire extraction, or electrical/PVT admission.
"""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import klayout.db as db
import layout
import native_bank_inventory_v51 as inventory
import restrict_macro_rails_v6 as abstract
import inspect_mim_switch_pcells_v2 as environment
import build_counter_output_mim5_v335 as failed_source

ROOT=layout.ROOT
VERSION='passed-counter-5x5-native-mim-fabrication-mask-witness-v336.1'
CONTEXT='counter_output_mim5_physical_v336'
NAME='openlvds_counter_output_mim5_v336'
PRIMITIVE='openlvds_native_mim5_v336'
CAP='sky130_fd_pr__cap_mim_m3_1'
PORTS=['Y','VGND']
SCOPE=('Actual pinned-PDK 5x5 MIM with unchanged native fabrication masks and separately verified native labels, explicit native '
       'top/bottom electrode labels; component DRC/LVS/LEF/native inventory only, '
       'no local RC/new counter geometry/shared RC/timing/PVT/DLL/PHY admission')


def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()


def atomic(path,value):
    temporary=path.with_suffix('.tmp');temporary.write_text(json.dumps(value,indent=2)+'\n');temporary.replace(path)


def schematic():
    return '\n'.join(['.subckt '+NAME+' '+' '.join(PORTS),
        'XC Y VGND '+CAP+' w=5 l=5','.ends '+NAME,''])


def validate_source(report,manifest,row,state):
    i=manifest['identity'];result=row.get('result') or {}
    added=i.get('added_native_mim',{})
    if (i.get('version')!='request-taper-low0-extra-5x5-output-mim-startup-repair-v332.1'
            or state!=dict(status='complete',cases=1,errors=0,qualified_phy=False)
            or row.get('error') is not None or row.get('task')!=manifest['tasks'][0]
            or row['task']['spec']!=i['spec']
            or (added.get('model'),added.get('width_um'),added.get('length_um'))!=(CAP,5,5)
            or result.get('hypothesis_point_checks_passed') is not True
            or result.get('terminal_screen_passed') is not True
            or len(result.get('terminal_stress',[]))!=808
            or not all(d['passed'] and math.isfinite(d['max_terminal_difference_v'])
                       and d['max_terminal_difference_v']<=d['limit_v'] for d in result['terminal_stress'])
            or report.get('all_original_native_metrics_reproduced') is not True
            or report.get('parameters_changed') is not False or len(report.get('rows',[]))!=1
            or report['rows'][0].get('all_original_native_metrics_reproduced') is not True
            or report['rows'][0].get('native_mos')!=808):
        raise ValueError('Require the exact fully replayed passing 5x5 native counter source')
    sample=report['rows'][0]['exact_limiting_samples']['whole_counter']
    worst=max(result['terminal_stress'],key=lambda d:d['max_terminal_difference_v'])
    if (sample['device']!=worst['device'] or sample['peak_v']!=worst['max_terminal_difference_v']
            or sample['margin_v']<=0):raise ValueError('Limiting passed native stress sample changed')


def source_material(evidence):
    report=json.loads((evidence/'summary.json').read_text())
    if len(report.get('rows',[]))!=1:raise ValueError('Require one original native source replay')
    case=ROOT/report['rows'][0]['case'];parent=case.parent
    if parent.parent!=ROOT/'build/diagnostics/request_taper_output_shunt_v332' or case.name!='0':
        raise ValueError('Require the original 5x5 source point')
    manifest=json.loads((parent/'manifest.json').read_text());i=manifest['identity']
    if parent.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]:
        raise ValueError('Original native source identity changed')
    row=json.loads((case/'summary.json').read_text())
    validate_source(report,manifest,row,json.loads((parent/'state.json').read_text()))
    if (any(sha(ROOT/n)!=h for n,h in report['inputs'].items())
            or any(sha(case/n)!=h for n,h in row['files'].items())
            or any(sha(parent/n)!=h for n,h in manifest['libraries'].items())):
        raise ValueError('Original passing native source files changed')
    paths=[evidence/'summary.json',*[ROOT/n for n in report['inputs']],
           *[parent/n for n in ('manifest.json','summary.json','state.json',*manifest['libraries'])],
           case/'summary.json',*[case/n for n in row['files']]]
    return paths,dict(case=str(case.relative_to(ROOT)),native_source_cases=1,
        width_um=5,length_um=5,model=CAP,native_peak_v=report['rows'][0]['exact_limiting_samples']['whole_counter']['peak_v'])


def prepare(evidence):
    paths,source=source_material(evidence)
    diagnosis,failed_paths=failure_diagnosis();paths+=failed_paths
    paths += sorted({Path(mod.__file__).resolve() for mod in list(sys.modules.values())
        if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    paths += [ROOT/'requirements.json',ROOT/'build/apptainer/openlvds.sif.sha256']
    pdk=Path(os.environ['PDK_ROOT'])/'sky130A';magic=pdk/'libs.tech/magic'
    external=[magic/'sky130A.magicrc',*magic.glob('*.tcl'),*magic.glob('*.tech'),pdk/'libs.tech/netgen/sky130A_setup.tcl']
    external += [Path(mod.__file__).resolve() for name,mod in list(sys.modules.items())
                 if name.startswith('klayout') and getattr(mod,'__file__',None)]
    identity=dict(version=VERSION,diagnosis=diagnosis,evidence=str(evidence.relative_to(ROOT)),source=source,
        reference=schematic(),inputs={str(p.relative_to(ROOT)):sha(p) for p in sorted(set(paths))},
        external_files={str(p):sha(p) for p in external},tools=environment.tools(),
        klayout=str(getattr(db,'__version__','unknown')),scope=SCOPE)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False));return out


def bound(out):
    m=json.loads((out/'manifest.json').read_text());i=m['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION or i['reference']!=schematic()
            or i['scope']!=SCOPE or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
            or any(sha(Path(n))!=h for n,h in i['external_files'].items())
            or environment.tools()!=i['tools'] or str(getattr(db,'__version__','unknown'))!=i['klayout']):
        raise ValueError('Native 5x5 output-capacitor physical context changed')
    return m


def access_plan(info):
    if (set(info['ports'])!={'C1','C2'} or info['ports']['C1'][0]!='mimcapcontact'
            or info['ports']['C2'][0]!='via3' or len(info['bbox'])!=4
            or not all(math.isfinite(v) for v in info['bbox'])
            or info['bbox'][2]<=info['bbox'][0] or info['bbox'][3]<=info['bbox'][1]):
        raise ValueError('Require native top/bottom MIM electrode accesses and finite bounds')
    dx,dy=-info['bbox'][0],-info['bbox'][1]
    ports={}
    for name,native,layer in [('Y','C1','metal4'),('VGND','C2','metal3')]:
        _,x,y=info['ports'][native]
        if (not all(math.isfinite(v) for v in (x,y)) or not info['bbox'][0]<=x<=info['bbox'][2]
                or not info['bbox'][1]<=y<=info['bbox'][3]):raise ValueError('Native electrode is outside its masks')
        ports[name]=dict(layer=layer,x_um=x+dx,y_um=y+dy,width_um=.24,native_electrode=native)
    return dict(dx_um=dx,dy_um=dy,ports=ports)


def fabrication_region(lib,cell,layer):
    region=db.Region();shapes=cell.begin_shapes_rec(lib.layer(*layer))
    while not shapes.at_end():
        shape=shapes.shape()
        # GDS Text is an annotation, never a fabrication polygon. In the pinned
        # KLayout, zero-area Text markers can survive Region XOR even when the
        # two labels are identical. Keep all non-text geometry on every layer.
        if not shape.is_text():region.insert(shape.polygon.transformed(shapes.trans()))
        shapes.next()
    return region


def native_texts(lib,cell):
    result=[]
    for k in lib.layer_indices():
        info=lib.get_info(k);shapes=cell.begin_shapes_rec(k)
        while not shapes.at_end():
            if shapes.shape().is_text():
                result.append((info.layer,info.datatype,shapes.shape().text.transformed(shapes.trans()).to_s()))
            shapes.next()
    return sorted(result)


def labels_equal(a,ca,b,cb):
    old=native_texts(a,ca);new=native_texts(b,cb)
    if old!=new:raise ValueError('Native capacitor text annotations changed')
    return dict(all_native_labels_preserved=True,native_text_records=len(old))


def masks_equal(a,ca,b,cb,dx=0,dy=0):
    if a.dbu!=b.dbu:raise ValueError('Native capacitor GDS units changed')
    layers={(a.get_info(k).layer,a.get_info(k).datatype) for k in a.layer_indices()}
    layers|={(b.get_info(k).layer,b.get_info(k).datatype) for k in b.layer_indices()}
    transform=db.Trans(round(dx/a.dbu),round(dy/a.dbu))
    for layer in layers:
        expected=fabrication_region(a,ca,layer).transformed(transform)
        actual=fabrication_region(b,cb,layer)
        if not (expected^actual).is_empty():raise ValueError('Native capacitor fabrication masks changed: '+str(layer))
    return dict(all_native_masks_preserved=True,checked_layers=len(layers),
                policy='All non-Text polygon/box/path geometry on every layer; native Text checked independently')


def failure_diagnosis():
    parent=ROOT/'build/diagnostics/counter_output_mim5_physical_v335/d4ce90cd8e8eb0c0'
    failed_source.bound(parent)
    state=json.loads((parent/'state.json').read_text())
    if state.get('status')!='failed' or state.get('error')!="Native capacitor masks changed: (71, 5)":
        raise ValueError('Require the retained original Text-mask witness failure')
    a=db.Layout();a.read(str(parent/(failed_source.PRIMITIVE+'.gds')))
    b=db.Layout();b.read(str(parent/(failed_source.NAME+'.gds')))
    old=a.cell(failed_source.PRIMITIVE);new=b.cell(failed_source.PRIMITIVE)
    marker=db.Region(old.begin_shapes_rec(a.layer(71,5))).transformed(db.Trans(0,0))
    after=db.Region(new.begin_shapes_rec(b.layer(71,5)))
    if marker.area()!=0 or after.area()!=0 or (marker^after).is_empty():
        raise ValueError('Original zero-area Text-marker mismatch does not reproduce')
    child=masks_equal(a,old,b,new);labels=labels_equal(a,old,b,new)
    info=layout.pcell_info(parent/(failed_source.PRIMITIVE+'.mag'));plan=access_plan(info)
    whole=masks_equal(a,old,b,b.cell(failed_source.NAME),plan['dx_um'],plan['dy_um'])
    drc=(parent/(failed_source.NAME+'.drc_count.txt')).read_text().strip()
    if drc!='0' or not layout.clean_match((parent/(failed_source.NAME+'.lvs.log')).read_text()):
        raise ValueError('Retained capacitor DRC/LVS evidence does not pass')
    paths=[parent/n for n in ('manifest.json','state.json',failed_source.PRIMITIVE+'.gds',
        failed_source.PRIMITIVE+'.mag',failed_source.NAME+'.gds',failed_source.NAME+'.lvs.log',
        failed_source.NAME+'.lvs.spice',failed_source.NAME+'.sch.spice',failed_source.NAME+'.drc_count.txt')]
    return dict(failed_artifact=str(parent.relative_to(ROOT)),original_zero_area_text_xor_failure_reproduced=True,
                native_fabrication_witness=child,native_label_witness=labels,whole_fabrication_witness=whole),paths


def draw(out):
    layout.invoke_magic(out,f'''load {PRIMITIVE} -silent
box values 0 0 0 0
set p [sky130::sky130_fd_pr__cap_mim_m3_1_defaults]
dict set p w 5
dict set p l 5
sky130::sky130_fd_pr__cap_mim_m3_1_draw $p
save {PRIMITIVE}
gds write {PRIMITIVE}.gds
''','native_pcell')
    info=layout.pcell_info(out/(PRIMITIVE+'.mag'));plan=access_plan(info)
    lines=['magic','tech sky130A','magscale 1 2','timestamp 0',f'use {PRIMITIVE} cap','timestamp 0',
        f'transform 1 0 {round(plan["dx_um"]/layout.GRID)} 0 1 {round(plan["dy_um"]/layout.GRID)}',
        'box '+' '.join(str(round(v/layout.GRID)) for v in info['bbox']),'<< labels >>']
    for number,pin in enumerate(PORTS,1):
        p=plan['ports'][pin];x=round(p['x_um']/layout.GRID);y=round(p['y_um']/layout.GRID)
        lines += [f'rlabel {p["layer"]} {x} {y} {x} {y} 0 {pin}',f'port {number} nsew']
    (out/(NAME+'.mag')).write_text('\n'.join(lines+['<< end >>','']))
    (out/(NAME+'.sch.spice')).write_text(schematic())
    physical=layout.qualify(out,NAME)
    raw=out/(NAME+'.raw.lef');raw.write_bytes((out/(NAME+'.lef')).read_bytes())
    lef,pins=abstract.restrict(raw.read_text(),plan['ports'],dict(Y=('INPUT','SIGNAL'),VGND=('INOUT','GROUND')))
    (out/(NAME+'.lef')).write_text(lef)
    reference=inventory.native_leaves(schematic(),NAME)[1]
    extracted=re.sub(r'\n[ \t]*\+[ \t]*',' ',(out/(NAME+'.lvs.spice')).read_text())
    ports,devices=inventory.native_leaves(extracted,NAME+'_flat')
    if ports!=PORTS or Counter(d['model'] for d in devices)!={CAP:1}:raise ValueError('Require one native 5x5 MIM and no MOS')
    parameters=inventory.compare_parameters(reference,devices)
    old=db.Layout();old.read(str(out/(PRIMITIVE+'.gds')))
    new=db.Layout();new.read(str(out/(NAME+'.gds')));root=new.cell(NAME)
    instances=list(root.each_inst())
    expected=(PRIMITIVE,round(plan['dx_um']/new.dbu),round(plan['dy_um']/new.dbu))
    if len(instances)!=1 or (instances[0].cell.name,instances[0].trans.disp.x,instances[0].trans.disp.y)!=expected:
        raise ValueError('Native capacitor hierarchy or placement changed')
    child=masks_equal(old,old.cell(PRIMITIVE),new,new.cell(PRIMITIVE))
    labels=labels_equal(old,old.cell(PRIMITIVE),new,new.cell(PRIMITIVE))
    whole=masks_equal(old,old.cell(PRIMITIVE),new,root,plan['dx_um'],plan['dy_um'])
    return dict(physical=physical,plan=plan,lef_access=pins,native_inventory=parameters,
        native_mos=0,native_mim=1,native_masks=child,native_labels=labels,whole_masks=whole,
        passed=bool(physical['passed'] and child['all_native_masks_preserved'] and labels['all_native_labels_preserved'] and whole['all_native_masks_preserved']))


def run(out):
    bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain prior or partial native capacitor geometry')
        atomic(out/'state.json',dict(status='building',qualified_phy=False))
        try:
            result=draw(out);bound(out)
            result.update(qualified_phy=False,local_rc_qualified=False,counter_geometry_qualified=False,scope=SCOPE)
            result['files']={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ('manifest.json','state.json','.execution.lock')}
            atomic(out/'summary.json',result)
            atomic(out/'state.json',dict(status='complete',passed=result['passed'],qualified_phy=False))
        except Exception as exc:
            atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='action',required=True)
    q=sub.add_parser('prepare');q.add_argument('evidence',type=Path)
    q=sub.add_parser('run');q.add_argument('artifact',type=Path);a=p.parse_args()
    print(prepare(a.evidence.resolve()) if a.action=='prepare' else run(a.artifact.resolve()),flush=True)
