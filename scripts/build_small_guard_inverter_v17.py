#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Physical regular INV8 with a native 3x3 output MIM and actual routed RC.

Retain every MOS/body mask and placement. Replace only the MIM child and
extend its ground M3 landing by 0.5 um. No bank/electrical admission is made.
"""
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
import verify_regular_clock_inverter_v15 as parent_proof

previous = parent_proof.physical
ROOT = previous.ROOT
sha = previous.sha
VERSION = 'regular-inv8-native-3x3-guard-physical-and-fresh-rc-v17.1'
CONTEXT = 'small_guard_inverter_v17'
OLD = previous.NAME
NAME = 'openlvds_inv_8_regular_o3_v17'
OLD_CAP = 'clock_mim_4x4_v2'
CAP = 'clock_mim_3x3_v17'
EXTENSION = (9.18, 7.8, 10.08, 8.2)


def schematic(text):
    needle = 'sky130_fd_pr__cap_mim_m3_1 w=4 l=4'
    if text.count(OLD) != 2 or text.count(needle) != 1:
        raise ValueError('Require the exact physical regular inverter and one 4x4 MIM')
    return text.replace(OLD, NAME).replace(needle, 'sky130_fd_pr__cap_mim_m3_1 w=3 l=3')


def native_check(old, new):
    a = previous.native_signature(old); b = previous.native_signature(new)
    cap = 'sky130_fd_pr__cap_mim_m3_1'
    if ([d for d in a if d[0] != cap] != [d for d in b if d[0] != cap]
            or [d for d in a if d[0] == cap] != [(cap, 4., 4., ('VGND', 'Y'))]
            or [d for d in b if d[0] == cap] != [(cap, 3., 3., ('VGND', 'Y'))]):
        raise ValueError('Changed native MOS geometry/connections or unexpected guard MIM')
    return dict(all_sixteen_mos_and_junctions_preserved=True, native_guard_mim_um=[3, 3])


def mask_check(reference, candidate):
    import klayout.db as db
    a, ac, _ = previous.masks(reference, OLD); b, bc, _ = previous.masks(candidate, NAME)
    if a.dbu != b.dbu:
        raise ValueError('Physical coordinate scale changed')
    def placements(layout, cell, remap=False):
        return Counter((OLD_CAP if remap and layout.cell(i.cell_index).name == CAP else layout.cell(i.cell_index).name,
                        i.cplx_trans.to_s(), i.a.x, i.a.y, i.b.x, i.b.y, i.na, i.nb) for i in cell.each_inst())
    if placements(a, ac) != placements(b, bc, True):
        raise ValueError('Native child placement changed')
    children = {a.cell(i.cell_index).name for i in ac.each_inst()}-{OLD_CAP}
    layers = {(l.get_info(i).layer, l.get_info(i).datatype) for l in (a, b) for i in l.layer_indexes()}
    def region(layout, cell, layer, recursive):
        index = layout.find_layer(*layer)
        if index is None:
            return db.Region()
        return db.Region(cell.begin_shapes_rec(index) if recursive else cell.shapes(index)).merged()
    for child in children:
        if b.cell(child) is None:
            raise ValueError('Native child missing')
        for layer in layers:
            if not (region(a, a.cell(child), layer, True)^region(b, b.cell(child), layer, True)).is_empty():
                raise ValueError('MOS/body-contact mask changed')
    rectangle = db.Region(db.Box(*[round(x/a.dbu) for x in EXTENSION]))
    for layer in layers:
        before = region(a, ac, layer, False); after = region(b, bc, layer, False)
        expected = (before|rectangle).merged() if layer == (70, 20) else before
        if not (expected^after).is_empty():
            raise ValueError('Unexpected root routing mask change: '+str(layer))
    if a.cell(OLD_CAP) is None or b.cell(CAP) is None:
        raise ValueError('Missing old or new native MIM child')
    return dict(mos_body_child_masks_identical=True, child_placements_identical=True,
                changed_root_routing_layers=[[70, 20]], ground_m3_extension_um=list(EXTENSION),
                native_capacitor_child_replaced=True)


def prepare(evidence):
    parent_proof.bound(evidence)
    binding = json.loads((evidence/'manifest.json').read_text())['identity']
    parent = ROOT/binding['parent']; i = previous.bound(parent)
    original = ROOT/i['parent']
    cap = original/'openlvds_nand3_2_o3_shunted_v2/clock_mim_3x3_v2.mag'
    source = schematic((parent/(OLD+'.sch.spice')).read_text())
    paths = [evidence/'manifest.json', evidence/'summary.json', parent/'manifest.json', parent/'summary.json', cap]
    paths += [p for p in parent.iterdir() if p.is_file() and (p.suffix == '.mag' or p.name in (OLD+'.gds', OLD+'.lvs.spice', OLD+'.sch.spice'))]
    code = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                   if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)), parent=str(parent.relative_to(ROOT)),
                    cap_source=str(cap.relative_to(ROOT)), ports=i['ports'], tools=i['tools'],
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
                    code={str(p.relative_to(ROOT)): sha(p) for p in code},
                    source_sha256=hashlib.sha256(source.encode()).hexdigest())
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity, qualified_phy=False), indent=2)+'\n')
    (out/(NAME+'.sch.spice')).write_text(source)
    return out


def bound(out):
    i = json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in {**i['inputs'], **i['code']}.items())
            or previous.original.native.environment.tools() != i['tools']
            or sha(out/(NAME+'.sch.spice')) != i['source_sha256']):
        raise ValueError('Small-guard physical context changed')
    parent_proof.bound(ROOT/i['evidence'])
    return i


def run(out):
    i = bound(out); parent = ROOT/i['parent']; layout = previous.original.layout
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior or partial small-guard physical work')
        (out/'state.json').write_text('{"status":"building","qualified_phy":false}\n')
        for file in parent.glob('*.mag'):
            if file.name != OLD+'.mag':
                shutil.copy2(file, out/file.name)
        shutil.copy2(ROOT/i['cap_source'], out/(CAP+'.mag'))
        text = (parent/(OLD+'.mag')).read_text()
        if text.count('use '+OLD_CAP+' ') != 1 or text.count('<< metal3 >>') != 1:
            raise ValueError('Original native MIM placement or routing format changed')
        text = text.replace('use '+OLD_CAP+' ', 'use '+CAP+' ', 1)
        rect = 'rect '+' '.join(str(round(x/layout.GRID)) for x in EXTENSION)
        text = text.replace('<< metal3 >>', '<< metal3 >>\n'+rect, 1)
        (out/(NAME+'.mag')).write_text(text)
        physical = layout.qualify(out, NAME)
        (out/'physical.json').write_text(json.dumps(physical, indent=2)+'\n')
        if not physical['passed']:
            raise ValueError('Small-guard DRC/LVS failed; retain evidence')
        masks = mask_check(parent/(OLD+'.gds'), out/(NAME+'.gds'))
        native = native_check((parent/(OLD+'.lvs.spice')).read_text(), (out/(NAME+'.lvs.spice')).read_text())
        digest = hashlib.sha256((out/(NAME+'.gds')).read_bytes()+Path(previous.extraction.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/digest/NAME).exists():
            raise ValueError('Retain existing small-guard extraction')
        rc = previous.extraction.extract(NAME, out/(NAME+'.gds'), sha(out/'manifest.json'),
                                         ports=i['ports'], source_scope=sha(out/(NAME+'.sch.spice')))
        (out/'extraction.json').write_text(json.dumps(rc, indent=2)+'\n')
        text = previous.checked_netlist(rc)
        if not previous.audit(text)['elementwise_passive_passed']:
            raise ValueError('Small-guard RC is not elementwise passive')
        collapsed = out/'wire_collapsed.spice'; collapsed.write_text(previous.collapse(text))
        setup = previous.strict_setup(out/'rc_setup.tcl', Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
        log = out/'rc_lvs.log'
        process = subprocess.run(['netgen', '-batch', 'lvs', f'{collapsed} {NAME}', f'{out/(NAME+".sch.spice")} {NAME}', str(setup), str(log)], cwd=out, capture_output=True, text=True)
        (out/'rc_console.log').write_text(process.stdout+process.stderr)
        if not previous.clean_match(log.read_text() if log.exists() else '', process.returncode):
            raise ValueError('Small-guard RC topology failed strict LVS')
        bound(out)
        result = dict(physical=physical, mask_comparison=masks, native_comparison=native, extraction=rc,
                      component_physical_rc_passed=True, rc_topology_passed=True, elementwise_passive_passed=True,
                      qualified_phy=False, electrical_qualification_passed=False,
                      scope='Native regular INV8 with smaller real MIM and M3 ground extension, unchanged MOS/body masks and placements, fresh DRC/LVS and passive RC; no bank/timing admission')
        result['files'] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name not in ('.execution.lock', 'state.json')}
        (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
        (out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
        return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run', 'campaign']); p.add_argument('artifact', type=Path)
    a = p.parse_args(); out = a.artifact.resolve()
    if a.action in ('prepare', 'campaign'):
        out = prepare(out); print(out, flush=True)
    if a.action in ('run', 'campaign'):
        print(run(out), flush=True)
