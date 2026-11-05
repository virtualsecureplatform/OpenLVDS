#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Verified low-Vt INV8 with a native 2x2 MIM output guard and fresh RC."""
import argparse
from collections import Counter
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import verify_nlvt_data_components_v30 as parent_proof

previous = parent_proof.physical
ROOT = previous.ROOT
sha = previous.sha
VERSION = 'nlvt-inv8-native-2x2-output-guard-physical-and-rc-v34.1'
CONTEXT = 'nlvt_guard2_v34'
OLD = previous.SPECS['inv3']['name']
NAME = 'openlvds_inv_8_nlvt_o2_v34'
OLD_CAP = 'clock_mim_3x3_v17'
CAP = 'clock_mim_2x2_nlvt_v34'
EXTENSION = (8.68, 7.8, 9.58, 8.2)


def schematic(text):
    needle = 'sky130_fd_pr__cap_mim_m3_1 w=3 l=3'
    if text.count('.subckt '+OLD+' ') != 1 or text.count('.ends '+OLD+'\n') != 1 or text.count(needle) != 1:
        raise ValueError('Require the exact native low-Vt inverter and one 3x3 guard')
    return text.replace('.subckt '+OLD+' ', '.subckt '+NAME+' ', 1).replace('.ends '+OLD+'\n', '.ends '+NAME+'\n', 1).replace(needle, 'sky130_fd_pr__cap_mim_m3_1 w=2 l=2', 1)


def native_check(old, new):
    definitions = previous.tg.layout.circuits(new)
    if len(definitions) != 1: raise ValueError('Require one complete native guarded inverter')
    _, devices = next(iter(definitions.values()))
    caps = [(nodes, params) for _, nodes, model, params in devices if model == 'sky130_fd_pr__cap_mim_m3_1']
    if len(caps) != 1 or set(caps[0][0]) != {'VGND', 'Y'} or {k:float(v) for k,v in caps[0][1].items()} != {'w':2.,'l':2.}:
        raise ValueError('Require exactly one native 2x2 output-to-ground guard')
    # Normalize only the deliberate MIM dimension change for the old native
    # signature checker; native geometry/topology are separately checked by LVS.
    lines = []
    for line in new.splitlines():
        w = line.split()
        if w and w[0].startswith('X') and 'sky130_fd_pr__cap_mim_m3_1' in w:
            w = ['w=3' if x.startswith('w=') else 'l=3' if x.startswith('l=') else x for x in w]
            line = ' '.join(w)
        lines.append(line)
    spec = previous.SPECS['inv3']
    if previous.native_signature(old, spec) != previous.native_signature('\n'.join(lines)+'\n', spec):
        raise ValueError('Native MOS dimensions, junctions or body ties changed')
    return dict(all_sixteen_native_mos_and_junctions_preserved=True, native_guard_mim_um=[2,2])


def mask_check(reference, candidate, cap_reference):
    import klayout.db as db
    a, ac, _ = previous.masktools.masks(reference, OLD)
    b, bc, _ = previous.masktools.masks(candidate, NAME)
    c = db.Layout(); c.read(str(cap_reference))
    if a.dbu != b.dbu or b.dbu != c.dbu or c.cell(CAP) is None:
        raise ValueError('Native MIM reference or coordinate scale changed')
    def placements(layout, cell, remap=False):
        return Counter((OLD_CAP if remap and layout.cell(i.cell_index).name == CAP else layout.cell(i.cell_index).name,
                        i.cplx_trans.to_s(),i.a.x,i.a.y,i.b.x,i.b.y,i.na,i.nb) for i in cell.each_inst())
    if placements(a,ac) != placements(b,bc,True): raise ValueError('Native child placement changed')
    layers = {(l.get_info(i).layer,l.get_info(i).datatype) for l in (a,b,c) for i in l.layer_indexes()}
    def region(layout, cell, layer, recursive):
        index = layout.find_layer(*layer)
        if index is None: return db.Region()
        return db.Region(cell.begin_shapes_rec(index) if recursive else cell.shapes(index)).merged()
    for name in {a.cell(i.cell_index).name for i in ac.each_inst()}-{OLD_CAP}:
        if b.cell(name) is None: raise ValueError('Native MOS/body child missing')
        for layer in layers:
            if not (region(a,a.cell(name),layer,True)^region(b,b.cell(name),layer,True)).is_empty():
                raise ValueError('Native MOS/body child masks changed')
    if a.cell(OLD_CAP) is None or b.cell(CAP) is None: raise ValueError('Missing guard MIM child')
    extension = db.Region(db.Box(*[round(x/a.dbu) for x in EXTENSION]))
    for layer in layers:
        before = region(a,ac,layer,False); after = region(b,bc,layer,False)
        expected = (before|extension).merged() if layer == (70,20) else before
        if not (expected^after).is_empty(): raise ValueError('Unexpected root routing mask change')
        if not (region(b,b.cell(CAP),layer,True)^region(c,c.cell(CAP),layer,True)).is_empty():
            raise ValueError('Guard MIM differs from the generated native 2x2 PCell')
    return dict(mos_body_child_masks_identical=True,child_placements_identical=True,
                changed_root_routing_layers=[[70,20]],ground_m3_extension_um=list(EXTENSION),
                guard_matches_generated_native_2x2_pcell=True)


def prepare(evidence):
    binding = parent_proof.bound(evidence); parent = ROOT/binding['parent']; pi = previous.bound(parent)
    source = parent/'inv3'
    paths = [evidence/'manifest.json',evidence/'summary.json',*[ROOT/n for n in binding['inputs']]]
    paths += [p for p in source.iterdir() if p.is_file() and (p.suffix == '.mag' or p.name in (OLD+'.gds',OLD+'.sch.spice',OLD+'.lvs.spice'))]
    paths += [ROOT/n for n in pi['inputs']]
    code = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                   if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION,evidence=str(evidence.relative_to(ROOT)),parent=str(source.relative_to(ROOT)),
                    ports=pi['components']['inv3']['ports'],tools=pi['tools'],external_files=pi['external_files'],
                    inputs={str(p.relative_to(ROOT)):sha(p) for p in paths},code={str(p.relative_to(ROOT)):sha(p) for p in code})
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity,qualified_phy=False),indent=2)+'\n')
    (out/(NAME+'.sch.spice')).write_text(schematic((source/(OLD+'.sch.spice')).read_text()))
    return out


def bound(out):
    i = json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n,h in {**i['inputs'],**i['code']}.items())
            or any(sha(Path(n)) != h for n,h in i['external_files'].items())
            or previous.tg.primitives.environment.tools() != i['tools']
            or (out/(NAME+'.sch.spice')).read_text() != schematic((ROOT/i['parent']/(OLD+'.sch.spice')).read_text())):
        raise ValueError('Native low-Vt 2x2-guard context changed')
    return i


def run(out):
    i = bound(out); parent = ROOT/i['parent']; layout = previous.tg.layout
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'state.json').exists(): raise ValueError('Retain prior or partial 2x2-guard evidence')
        (out/'state.json').write_text('{"status":"building","qualified_phy":false}\n')
        for file in parent.glob('*.mag'):
            if file.name != OLD+'.mag': shutil.copy2(file,out/file.name)
        layout.invoke_magic(out,f'''load {CAP} -silent
box values 0 0 0 0
set p [sky130::sky130_fd_pr__cap_mim_m3_1_defaults]
dict set p w 2
dict set p l 2
sky130::sky130_fd_pr__cap_mim_m3_1_draw $p
save {CAP}
gds write {CAP}.gds''','native_guard_pcell')
        text = (parent/(OLD+'.mag')).read_text()
        if text.count('use '+OLD_CAP+' ') != 1 or text.count('<< metal3 >>') != 1:
            raise ValueError('Original MIM placement or root routing format changed')
        text = text.replace('use '+OLD_CAP+' ','use '+CAP+' ',1)
        rectangle = 'rect '+' '.join(str(round(x/layout.GRID)) for x in EXTENSION)
        text = text.replace('<< metal3 >>','<< metal3 >>\n'+rectangle,1)
        (out/(NAME+'.mag')).write_text(text)
        physical = layout.qualify(out,NAME)
        (out/'physical.json').write_text(json.dumps(physical,indent=2)+'\n')
        if not physical['passed']: raise ValueError('Native 2x2-guard DRC/LVS failed; retain evidence')
        masks = mask_check(parent/(OLD+'.gds'),out/(NAME+'.gds'),out/(CAP+'.gds'))
        native = native_check((parent/(OLD+'.lvs.spice')).read_text(),(out/(NAME+'.lvs.spice')).read_text())
        extraction = previous.tg.extraction
        digest = hashlib.sha256((out/(NAME+'.gds')).read_bytes()+Path(extraction.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/digest/NAME).exists(): raise ValueError('Retain existing 2x2-guard RC')
        rc = extraction.extract(NAME,out/(NAME+'.gds'),sha(out/'manifest.json'),ports=i['ports'],source_scope=sha(out/(NAME+'.sch.spice')))
        (out/'extraction.json').write_text(json.dumps(rc,indent=2)+'\n'); text = previous.tg.checked_netlist(rc)
        if not previous.tg.audit(text)['elementwise_passive_passed']: raise ValueError('Native 2x2-guard RC failed passivity')
        collapsed = out/'wire_collapsed.spice'; collapsed.write_text(previous.tg.collapse(text))
        setup = previous.tg.strict_setup(out/'rc_setup.tcl',Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
        log = out/'rc_lvs.log'
        p = subprocess.run(['netgen','-batch','lvs',f'{collapsed} {NAME}',f'{out/(NAME+".sch.spice")} {NAME}',str(setup),str(log)],cwd=out,capture_output=True,text=True)
        (out/'rc_console.log').write_text(p.stdout+p.stderr)
        if not previous.tg.clean_match(log.read_text() if log.exists() else '',p.returncode): raise ValueError('Native 2x2-guard RC topology failed LVS')
        bound(out)
        result = dict(physical=physical,mask_comparison=masks,native_comparison=native,extraction=rc,
                      component_physical_rc_passed=True,rc_topology_passed=True,qualified_phy=False,electrical_qualification_passed=False,
                      scope='Native low-Vt INV8 with real 2x2 output guard, identical MOS/body masks and placements, explicit M3 ground extension and fresh passive RC; no bank timing or PHY admission')
        result['files'] = {p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name not in ('.execution.lock','state.json')}
        (out/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
        (out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
        return out


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run','campaign']);p.add_argument('artifact',type=Path)
    a = p.parse_args();out = a.artifact.resolve()
    if a.action in ('prepare','campaign'):out=prepare(out);print(out,flush=True)
    if a.action in ('run','campaign'):print(run(out),flush=True)
