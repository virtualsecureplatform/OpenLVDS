#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Preserve native hierarchy while changing only the guarded INV8 HVTP implant.

Only HVTP (78/44) is removed. Every other mask is compared as an exact region.
Fresh DRC/LVS, native junction signatures and passive RC are required. This
candidate component does not admit a bank, clock backend or PHY.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import build_clock_cell_shunts_v4 as original
import extract_native_flat_v4 as extraction
from audit_rc_comments_v2 import collapse
from audit_passive_rc_v3 import audit
from lvs_utils import strict_setup, clean_match
from spice_library import checked_netlist

ROOT = original.ROOT
VERSION = 'guarded-inv8-regular-pmos-implant-only-physical-and-rc-v14.1'
CONTEXT = 'regular_clock_inverter_v14'
OLD = 'openlvds_inv_8_o4_shunted_v2'
NAME = 'openlvds_inv_8_regular_o4_v14'
HVT = 'sky130_fd_pr__pfet_01v8_hvt'
REGULAR = 'sky130_fd_pr__pfet_01v8'
MARKER = (78, 44)
sha = original.sha


def schematic(text):
    core = 'sky130_fd_sc_hd__inv_8'
    if (text.count(HVT) != 8 or text.count(core) != 2 or text.count(OLD) != 2
            or text.count('sky130_fd_pr__cap_mim_m3_1 w=4 l=4') != 1):
        raise ValueError('Require the exact eight-PMOS, guarded native inverter source')
    return text.replace(HVT, REGULAR).replace(core, 'openlvds_inv_8_regular_core_v14').replace(OLD, NAME)


def native_signature(text, normalize_hvt=False):
    """Compare native terminals and junctions, permitting only MOS D/S swap."""
    defs = original.layout.circuits(text)
    if len(defs) != 1:
        raise ValueError('Require one complete flat native device definition')
    ports, devices = next(iter(defs.values()))
    if set(ports) != {'A', 'Y', 'VGND', 'VPWR'} or len(devices) != 17:
        raise ValueError('Guarded inverter must retain sixteen MOS and one native MIM')
    result = []
    for _, nodes, model, params in devices:
        values = {k: float(v) for k, v in params.items()}
        if model == HVT and normalize_hvt:
            model = REGULAR
        if 'fet_' in model:
            if set(values) != {'w', 'l', 'ad', 'as', 'pd', 'ps'}:
                raise ValueError('Native junction parameter coverage changed')
            ends = tuple(sorted(((nodes[0], values['ad'], values['pd']), (nodes[2], values['as'], values['ps']))))
            result.append((model, values['w'], values['l'], nodes[1], nodes[3], ends))
        elif model == 'sky130_fd_pr__cap_mim_m3_1' and set(values) == {'w', 'l'}:
            result.append((model, values['w'], values['l'], tuple(sorted(nodes))))
        else:
            raise ValueError('Unexpected primitive in guarded inverter')
    models = [d[0] for d in result]
    if models.count(REGULAR) != 8 or models.count('sky130_fd_pr__nfet_01v8') != 8:
        raise ValueError('Require all eight regular P and eight original N fingers')
    return sorted(result)


def masks(path, top):
    import klayout.db as db
    layout = db.Layout(); layout.read(str(path)); cell = layout.cell(top)
    if cell is None:
        raise ValueError('Missing physical inverter top')
    regions = {(layout.get_info(i).layer, layout.get_info(i).datatype):
               db.Region(cell.begin_shapes_rec(i)).merged() for i in layout.layer_indexes()}
    return layout, cell, {k: v for k, v in regions.items() if not v.is_empty()}


def mask_audit(reference, candidate):
    import klayout.db as db
    a, _, before = masks(reference, OLD); b, _, after = masks(candidate, NAME)
    if a.dbu != b.dbu or MARKER not in before or MARKER in after:
        raise ValueError('Require complete HVTP removal at the identical geometry scale')
    changed = [k for k in set(before) | set(after)
               if not (before.get(k, db.Region()) ^ after.get(k, db.Region())).is_empty()]
    if set(changed) != {MARKER}:
        raise ValueError('Threshold candidate changed a non-HVTP mask')
    return dict(only_changed_mask=list(MARKER), removed_hvtp_area_um2=before[MARKER].area()*a.dbu**2,
                all_other_mask_regions_identical=True)


def prepare(parent):
    import klayout.db as db
    original.bound(parent); report = json.loads((parent/'summary.json').read_text())
    rows = [r for r in report['rows'] if r['macro'] == OLD]
    if not report['passed'] or len(rows) != 1 or not rows[0]['passed'] or rows[0]['drc_count'] != '0' or not rows[0]['lvs_passed']:
        raise ValueError('Require the original qualified isolated inverter geometry')
    row = rows[0]; folder = parent/OLD
    for suffix, key in (('.gds', 'gds_sha256'), ('.lef', 'lef_sha256'), ('.sch.spice', 'lvs_source_sha256')):
        if sha(folder/(OLD+suffix)) != row[key]:
            raise ValueError('Original inverter physical receipt changed')
    source = schematic((folder/(OLD+'.sch.spice')).read_text())
    native_signature((folder/(OLD+'.lvs.spice')).read_text(), normalize_hvt=True)
    paths = [parent/'manifest.json', parent/'summary.json', parent/'state.json']
    paths += [folder/(OLD+s) for s in ('.gds', '.lef', '.sch.spice', '.lvs.spice', '.lvs.log', '.drc_count.txt')]
    code = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                   if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), ports=row['ports'],
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
                    code={str(p.relative_to(ROOT)): sha(p) for p in code}, tools=original.native.environment.tools(),
                    klayout=dict(version=db.__version__, module=str(Path(db.__file__)), sha256=sha(Path(db.__file__))),
                    source_sha256=hashlib.sha256(source.encode()).hexdigest())
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity, qualified_phy=False), indent=2)+'\n')
    (out/(NAME+'.sch.spice')).write_text(source)
    return out


def bound(out):
    import klayout.db as db
    i = json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in {**i['code'], **i['inputs']}.items())
            or original.native.environment.tools() != i['tools']
            or i['klayout'] != dict(version=db.__version__, module=str(Path(db.__file__)), sha256=sha(Path(db.__file__)))
            or sha(out/(NAME+'.sch.spice')) != i['source_sha256']):
        raise ValueError('Regular inverter physical context changed')
    original.bound(ROOT/i['parent'])
    return i


def run(out):
    import klayout.db as db
    i = bound(out); parent = ROOT/i['parent']/OLD; reference = parent/(OLD+'.gds')
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior or partial regular-inverter execution')
        (out/'state.json').write_text('{"status":"building","qualified_phy":false}\n')
        layout, cell, regions = masks(reference, OLD)
        if MARKER not in regions:
            raise ValueError('Original inverter has no HVT marker')
        # Preserve child pin scope and per-cell boundary annotations. Flattening
        # GDS promotes VNB/VPB and changes generated boundary masks on export.
        marker = layout.find_layer(*MARKER)
        for child in layout.each_cell():
            child.shapes(marker).clear()
        core = layout.cell('sky130_fd_sc_hd__inv_8')
        if core is None:
            raise ValueError('Missing original native inverter child')
        core.name = 'openlvds_inv_8_regular_core_v14'
        cell.name = NAME
        options = db.SaveLayoutOptions(); options.select_cell(cell.cell_index())
        layout.write(str(out/(NAME+'.candidate.gds')), options)
        comparison = mask_audit(reference, out/(NAME+'.candidate.gds'))
        commands = ['gds readonly false', f'gds read {NAME}.candidate.gds']
        # Persist the entire imported subtree before another Magic process
        # reloads the macro; saving only the root loses custom child cells.
        for child in layout.each_cell():
            commands += [f'load {child.name}', f'save {child.name}']
        commands += [f'load {NAME}']
        for index, pin in enumerate(i['ports'].values(), 1):
            x, y = pin['x_um'], pin['y_um']
            commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um', f'port make {index}']
        commands += [f'save {NAME}']
        original.layout.invoke_magic(out, '\n'.join(commands), 'import_candidate')
        physical = original.layout.qualify(out, NAME)
        comparison_after_magic = mask_audit(reference, out/(NAME+'.gds'))
        if comparison_after_magic != comparison:
            raise ValueError('Magic physical round trip changed the mask-difference proof')
        if native_signature((parent/(OLD+'.lvs.spice')).read_text(), True) != native_signature((out/(NAME+'.lvs.spice')).read_text()):
            raise ValueError('Changed more than the eight native PMOS models or lost junction geometry')
        (out/'physical.json').write_text(json.dumps(dict(physical, mask_comparison=comparison, native_geometry_preserved=True), indent=2)+'\n')
        if not physical['passed']:
            raise ValueError('Candidate physical DRC/LVS failed; retain all evidence')
        digest = hashlib.sha256((out/(NAME+'.gds')).read_bytes()+Path(extraction.__file__).read_bytes()).hexdigest()[:16]
        if (ROOT/'build/extracted'/digest/NAME).exists():
            raise ValueError('Retain prior regular-inverter RC namespace')
        rc = extraction.extract(NAME, out/(NAME+'.gds'), sha(out/'manifest.json'),
                                ports=i['ports'], source_scope=sha(out/(NAME+'.sch.spice')))
        (out/'extraction.json').write_text(json.dumps(rc, indent=2)+'\n')
        text = checked_netlist(rc)
        if not audit(text)['elementwise_passive_passed']:
            raise ValueError('Candidate extraction is not elementwise passive')
        collapsed = out/'wire_collapsed.spice'; collapsed.write_text(collapse(text))
        setup = strict_setup(out/'rc_setup.tcl', Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
        log = out/'rc_lvs.log'
        process = subprocess.run(['netgen', '-batch', 'lvs', f'{collapsed} {NAME}',
                                  f'{out/(NAME+".sch.spice")} {NAME}', str(setup), str(log)], cwd=out, capture_output=True, text=True)
        (out/'rc_console.log').write_text(process.stdout+process.stderr)
        if not clean_match(log.read_text() if log.exists() else '', process.returncode):
            raise ValueError('Candidate RC topology failed strict LVS')
        bound(out)
        result = dict(physical=physical, mask_comparison=comparison, native_geometry_preserved=True,
                      extraction=rc, rc_topology_passed=True, elementwise_passive_passed=True,
                      component_physical_rc_passed=True, electrical_qualification_passed=False, qualified_phy=False,
                      scope='Only HVTP removed from the isolated guarded INV8; unchanged other mask regions/native geometry, fresh DRC/LVS and passive distributed RC; no bank or timing qualification')
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
