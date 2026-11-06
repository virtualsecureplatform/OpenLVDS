#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Restore exact native masks after gated balanced-bank routing and run DRC/LVS.

Consumes the new native-IN-access route; the failed v135 route is retained.
Strict device census/dimension/junction checks remain mandatory. No joint RC,
periodic/PVT timing or PHY admission follows from router or geometry success.
"""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import klayout.db as db
import route_measured_balanced_bank_v149 as route
import build_tg_bank_gds_v51 as legacy
import measured_bank_native_inventory_v138 as inventory

ROOT=route.ROOT
sha=route.sha
VERSION='measured-balanced-routed-native-masks-hierarchy-drc-lvs-inventory-v150.1'
CONTEXT='measured_balanced_native_gds_v150'


def validate(parent):
    ri,ii,pi=route.bound(parent);r=json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text())!=dict(status='complete',passed=True,qualified_phy=False)
        or not r['route_bringup_passed'] or r['router_final_violations']!=0
        or any(sha(parent/n)!=h for n,h in r['files'].items())
        or route.check(parent,ri,ii)!=r['connection_and_coverage_check']):
        raise ValueError('Require complete unchanged zero-violation gated route and native coverage')
    return ri,pi,r


def native_cells(file,placed,pi):
    """Check stored native hierarchy and placements, beyond flattened mask XOR."""
    original=db.Layout();original.read(str(placed/'library.gds'))
    final=db.Layout();final.read(str(file));top=final.cell(pi['graph']['top'])
    if original.dbu!=.001 or final.dbu!=original.dbu or top is None:raise ValueError('Native GDS hierarchy has wrong top/scale')
    needed=set()
    def visit(name):
        if name in needed:return
        cell=original.cell(name)
        if cell is None:raise ValueError('Missing original native GDS master')
        needed.add(name)
        for inst in cell.each_inst():visit(inst.cell.name)
    for c in pi['plan']['cells']:visit(c['model'])
    for name in sorted(needed):
        a=original.cell(name);b=final.cell(name)
        if b is None:raise ValueError('Stored native child/master was dropped: '+name)
        route.interface.placement.audit_cell(original,a,final,b)
    records=pi['records'];actual=Counter()
    for inst in top.each_inst():
        if inst.cell.name not in records:
            if not inst.cell.name.startswith('VIA'):raise ValueError('Unknown extra routed GDS instance')
            continue
        if inst.is_regular_array() or inst.trans.angle!=0 or inst.trans.is_mirror():raise ValueError('Routed native placement transform changed')
        actual[(inst.cell.name,inst.trans.disp.x,inst.trans.disp.y)]+=1
    expected=Counter((c['model'],*[round(v/final.dbu) for v in pi['plan']['placements'][c['name']]]) for c in pi['plan']['cells'])
    if actual!=expected:raise ValueError('Stored routed GDS native placement multiplicity differs')
    return dict(all_used_native_masks_hierarchy_and_labels_preserved=True,all_native_placements_preserved=True,
                native_instances=sum(actual.values()),native_hierarchy_cells=len(needed))


def qualify(out,file,placed,pi,profile):
    name=pi['graph']['top'];folder=out/'native';folder.mkdir();source=(placed/'reference.spice').read_text()
    (folder/(name+'.sch.spice')).write_text(source)
    lib=db.Layout();lib.read(str(file));commands=['gds readonly false',f'gds read {{{file}}}']
    for cell in lib.each_cell():commands += [f'load {cell.name}',f'save {cell.name}']
    commands += [f'load {name}']
    for index,port in enumerate(pi['graph']['ports'],1):
        x0,y0,x1,y1=pi['plan']['ports'][port]['rect'];x=(x0+x1)/2;y=(y0+y1)/2
        commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um',f'port make {index}']
    commands += [f'save {name}'];legacy.place.layout.invoke_magic(folder,'\n'.join(commands),'import_measured_balanced')
    physical=legacy.place.layout.qualify(folder,name)
    extracted=re.sub(r'\n[ \t]*\+[ \t]*',' ',(folder/(name+'.lvs.spice')).read_text())
    parameters=error=None
    try:parameters=inventory.verify(source,name,extracted,name+'_flat',profile)
    except ValueError as e:error=str(e)
    return physical,parameters,error


def prepare(parent):
    ri,pi,r=validate(parent);techroot=Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/klayout'
    lyts=list(techroot.rglob('sky130A.lyt'));maps=list(techroot.rglob('sky130A.map'))
    if len(lyts)!=1 or len(maps)!=1:raise ValueError('Require exact SKY130 streamout technology/map')
    paths=[parent/'manifest.json',parent/'summary.json',parent/'state.json',*[parent/n for n in r['files']]]
    paths+=sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    i=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),placement=ri['placement'],profile=ri['profile'],
           inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},lyt=str(lyts[0]),mapping=str(maps[0]),
           external_files={str(p):sha(p) for p in [lyts[0],maps[0]]},
           scope='Strict routed native mask/hierarchy/placement, Magic DRC, native LVS and device parameters; no joint RC, timing or PHY admission')
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);(out/'manifest.json').write_text(json.dumps(dict(identity=i,qualified_phy=False),indent=2)+'\n');return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or any(sha(Path(n))!=h for n,h in i['external_files'].items())):raise ValueError('Measured balanced GDS context changed')
    ri,pi,_=validate(ROOT/i['parent'])
    if ri['placement']!=i['placement'] or ri['profile']!=i['profile']:raise ValueError('Routed native profile/placement changed')
    return i,pi


def run(out):
    i,pi=bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Retain previous or partial native GDS campaign')
        (out/'state.json').write_text('{"status":"checking_native_gds","qualified_phy":false}\n')
        parent=ROOT/i['parent'];placed=ROOT/i['placement'];mask=hierarchy=physical=parameters=error=None
        try:
            file=legacy.stream(out,parent,dict(pi,parent=i['placement']),Path(i['lyt']),Path(i['mapping']))
            mask=legacy.masks(file,placed/(pi['graph']['top']+'.gds'),pi['graph']['top'],pi['plan']['die'])
            hierarchy=native_cells(file,placed,pi)
            physical,parameters,error=qualify(out,file,placed,pi,i['profile'])
        except (ValueError,RuntimeError,subprocess.CalledProcessError) as e:error=str(e)
        bound(out);passed=bool(mask and hierarchy and physical and physical['passed'] and parameters and parameters['native_parameters_preserved'] and error is None)
        r=dict(native_routed_gds_passed=passed,mask_proof=mask,native_hierarchy_proof=hierarchy,physical=physical,native_parameters=parameters,error=error,
               joint_rc_extracted=False,electrical_qualification_passed=False,qualified_phy=False,full_foundry_signoff_passed=False,scope=i['scope'])
        r['files']={str(f.relative_to(out)):sha(f) for f in out.rglob('*') if f.is_file() and f.name not in ['state.json','.execution.lock']}
        (out/'summary.json').write_text(json.dumps(r,indent=2)+'\n');(out/'state.json').write_text(json.dumps(dict(status='complete',passed=passed,qualified_phy=False))+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);a=p.parse_args();out=a.artifact.resolve()
    if a.action in ['prepare','campaign']:out=prepare(out);print(out,flush=True)
    if a.action in ['run','campaign']:print(run(out),flush=True)
