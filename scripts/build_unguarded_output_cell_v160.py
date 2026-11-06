#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remove only the two parallel output MIM guards; requalify native masks and RC."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
import subprocess
import build_parallel_output_cell_v111 as base

ROOT=base.ROOT
sha=base.sha
VERSION='unguarded-parallel-native-inv8-physical-and-fresh-rc-v160.1'
CONTEXT='unguarded_output_cell_v160'
OLD='openlvds_parallel_inv8_v110'
NAME='openlvds_parallel_inv8_unguarded_v160'
INV='openlvds_inv_8_nlvt_o2_v34'
NEW_INV='openlvds_inv_8_nlvt_unguarded_v160'
CAP='clock_mim_2x2_nlvt_v34'


def schematic(text):
    lines=text.splitlines(keepends=True)
    caps=[n for n,line in enumerate(lines) if 'sky130_fd_pr__cap_mim_m3_1' in line]
    if len(caps)!=1 or lines[caps[0]].split()[1:]!=['Y','VGND','sky130_fd_pr__cap_mim_m3_1','l=2','w=2']:
        raise ValueError('Require one shared native definition with a 2x2 output guard')
    del lines[caps[0]]
    result=''.join(lines)
    for old,new in ((OLD,NAME),(INV,NEW_INV)):
        result=re.sub(r'\b'+re.escape(old)+r'\b',new,result)
    return result


def geometry(source,target):
    db=base.db
    lib=db.Layout();lib.read(str(source));inv=lib.cell(INV)
    if inv is None or lib.cell(OLD) is None or lib.cell(CAP) is None:
        raise ValueError('Require original native output hierarchy')
    guards=[i for i in inv.each_inst() if lib.cell(i.cell_index).name==CAP]
    if len(guards)!=1:raise ValueError('Require exactly one guard placement per inverter')
    guards[0].delete()
    inv.name=NEW_INV;lib.cell(OLD).name=NAME
    result=db.Layout();result.dbu=lib.dbu
    top=result.create_cell(NAME);top.copy_tree(lib.cell(NAME));result.write(str(target))
    return mask_check(source,target)


def mask_check(source,target):
    db=base.db
    a=db.Layout();a.read(str(source));b=db.Layout();b.read(str(target))
    if a.dbu!=b.dbu or b.cell(CAP) is not None:raise ValueError('Guard remains or layout scale changed')
    rename={OLD:NAME,INV:NEW_INV}
    expected={rename.get(c.name,c.name) for c in a.each_cell() if c.name!=CAP}
    if {c.name for c in b.each_cell()}!=expected:raise ValueError('Unexpected native hierarchy change')
    layers={(x.get_info(i).layer,x.get_info(i).datatype) for x in (a,b) for i in x.layer_indexes()}
    def shapes(lib,cell,layer):
        index=lib.find_layer(*layer)
        return db.Region() if index is None else db.Region(cell.shapes(index)).merged()
    def placements(lib,cell,remap):
        return Counter((rename.get(lib.cell(i.cell_index).name,lib.cell(i.cell_index).name) if remap else lib.cell(i.cell_index).name,
                        i.cplx_trans.to_s(),i.a.x,i.a.y,i.b.x,i.b.y,i.na,i.nb)
                       for i in cell.each_inst() if not (remap and lib.cell(i.cell_index).name==CAP))
    for old in a.each_cell():
        if old.name==CAP:continue
        new=b.cell(rename.get(old.name,old.name))
        if placements(a,old,True)!=placements(b,new,False):raise ValueError('Non-guard native placement changed')
        for layer in layers:
            if not (shapes(a,old,layer)^shapes(b,new,layer)).is_empty():
                raise ValueError('Native MOS/body or root wiring masks changed')
    return dict(all_non_guard_cell_masks_identical=True,all_non_guard_placements_identical=True,
                output_guard_instances_removed=2,root_wiring_masks_identical=True,qualified_phy=False)


def prepare(parent,hypothesis):
    base.bound(parent)
    report=json.loads((parent/'summary.json').read_text())
    h=json.loads((hypothesis/'summary.json').read_text())
    if not report['parallel_output_component_passed'] or not any(r['variant']=='none' and r['hypothesis_feasible'] for r in h['comparison']):
        raise ValueError('Require qualified native source and complete feasible unguarded hypothesis')
    # Revalidate the formal hypothesis, including every captured source input.
    code='import sys,json;from pathlib import Path;sys.path.insert(0,"scripts");import probe_measured_output_guard_variants_v159 as p;print(json.dumps(p.bound(Path(sys.argv[1]))))'
    checked=subprocess.run([str(ROOT/'build/tools/exact-rc-venv/bin/python'),'-c',code,str(hypothesis)],cwd=ROOT,capture_output=True,text=True,check=True)
    hypothesis_manifest=json.loads(checked.stdout)
    paths=[parent/'manifest.json',parent/'summary.json',*[parent/n for n in report['files']],
           hypothesis/'manifest.json',hypothesis/'summary.json',hypothesis/'state.json',
           *[ROOT/n for n in hypothesis_manifest['identity']['inputs']]]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    design=json.loads((parent/'manifest.json').read_text())['identity']['designs']['inv2']
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),hypothesis=str(hypothesis.relative_to(ROOT)),
                  design=design,inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},
                  math_runtime=base.math_proof.math_proof()['runtime'])
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    return out


def bound(out):
    i=json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent!=ROOT/'build/diagnostics'/CONTEXT or i['version']!=VERSION
        or out.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
        or any(sha(ROOT/n)!=h for n,h in i['inputs'].items())
        or base.math_proof.math_proof()['runtime']!=i['math_runtime']):raise ValueError('Unguarded output context changed')
    base.bound(ROOT/i['parent'])
    return i


def run(out):
    i=bound(out);parent=ROOT/i['parent']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists():raise ValueError('Preserve existing or partial unguarded output evidence')
        (out/'state.json').write_text('{"status":"qualifying","qualified_phy":false}\n')
        original=json.loads((parent/'summary.json').read_text())['rows'][0]
        gds=out/'candidate.gds';masks=geometry(ROOT/original['physical']['gds'],gds)
        design=i['design'];graph=dict(design['graph'],top=NAME)
        physical,params=base.qualify(out,gds,graph,design['plan'],schematic(design['reference']))
        if params['native_primitives']!=32:raise ValueError('Require exactly 32 original native MOS and no MIM')
        source=ROOT/physical['gds']
        digest=hashlib.sha256(source.read_bytes()+Path(base.extractor.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/digest/NAME).exists():raise ValueError('Preserve previous extraction')
        ports={n:dict(x_um=(p['rect'][0]+p['rect'][2])/2,y_um=(p['rect'][1]+p['rect'][3])/2) for n,p in design['plan']['ports'].items()}
        rc=base.extractor.extract(NAME,source,sha(out/'manifest.json'),ports=ports,source_scope=sha(out/'native'/(NAME+'.sch.spice')))
        if rc['ports']!=graph['ports'] or not rc['ports_verified']:raise ValueError('Output RC port order changed')
        proof=base.certify(out,rc,NAME,out/'native'/(NAME+'.lvs.spice'),32)
        bound(out)
        report=dict(physical=physical,native_parameters=params,mask_comparison=masks,extraction=rc,rc_proof=proof,
                    component_physical_rc_passed=True,whole_bank_rc_qualified=False,
                    electrical_qualification_passed=False,qualified_phy=False,
                    scope='Native parallel INV8 with only its two output MIM guards removed, unchanged MOS/body/root wiring masks, fresh DRC/LVS and component RC; full bank timing and PVT pending')
        report['files']={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('.execution.lock','state.json')}
        report['extracted_files']={str((ROOT/rc[k]).relative_to(ROOT)):sha(ROOT/rc[k]) for k in ('raw_netlist','netlist')}
        (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
        (out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path);p.add_argument('--hypothesis',type=Path)
    a=p.parse_args();out=a.artifact.resolve()
    if a.action in ('prepare','campaign'):
        if a.hypothesis is None:p.error('--hypothesis is required')
        out=prepare(out,a.hypothesis.resolve());print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
