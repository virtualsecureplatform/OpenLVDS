#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent primitive-mask, fresh-GDS native TG and exact-RC proof."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import build_dual_contact_tg_300_v3 as physical
from reduce_rc import reduce_netlist

ROOT = physical.ROOT
sha = physical.sha
NAME = physical.NAME
VERSION = 'independent-dual-contact-tg-gds-mask-passive-rc-300-v1'
CONTEXT = 'dual_contact_tg_verification_300_v1'


def primitive_masks(parent, gds):
    import klayout.db as db
    import math
    physical.bound(parent)
    recipes = json.loads((parent/'primitive_geometry.json').read_text())
    if len(recipes) != 2 or {r['model'] for r in recipes} != {physical.N, physical.P}:
        raise ValueError('Require two recorded native primitive recipes')
    actual = db.Layout(); actual.read(str(gds)); top = actual.cell(NAME)
    if top is None or len(list(top.each_inst())) != 2:
        raise ValueError('Require both primitive TG children')
    for recipe in recipes:
        cell = recipe['cell']; expected = db.Layout(); expected.read(str(parent/(cell+'.gds')))
        child = actual.cell(cell)
        if child is None or actual.dbu != expected.dbu:
            raise ValueError('Native primitive child or coordinate grid changed')
        keys = {(l.get_info(n).layer, l.get_info(n).datatype) for l in (actual, expected) for n in l.layer_indexes()}
        def region(layout, c, key):
            index = layout.find_layer(*key)
            return db.Region() if index is None else db.Region(c.begin_shapes_rec(index)).merged()
        for key in keys:
            if not (region(actual, child, key)^region(expected, expected.cell(cell), key)).is_empty():
                raise ValueError('Actual TG primitive mask differs from native PCell')
        is_n = recipe['model'] == physical.N
        y = 0. if is_n else 6.0
        if not math.isclose(recipe['center_y_um'], y) or recipe['mirror_x'] != (not is_n):
            raise ValueError('Recorded native placement changed')
        instances = [inst for inst in top.each_inst() if inst.cell_index == child.cell_index()]
        transform = db.Trans(0, False, 0, 0) if is_n else db.Trans(2, True, 0, round(y/actual.dbu))
        if len(instances) != 1 or instances[0].trans != transform or instances[0].is_regular_array():
            raise ValueError('Native TG primitive placement changed')
    return dict(all_native_primitive_masks_identical=True, native_child_placements_verified=True)


def checked(parent):
    i = physical.bound(parent); r = json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
            or not r['component_physical_rc_passed'] or not r['rc_topology_passed'] or r['qualified_phy']
            or any(sha(parent/n) != h for n, h in r['files'].items())
            or (parent/(NAME+'.drc_count.txt')).read_text().strip() != '0'
            or not physical.clean_match((parent/(NAME+'.lvs.log')).read_text())
            or not physical.clean_match((parent/'rc_lvs.log').read_text())):
        raise ValueError('Require complete unchanged native TG physical/RC evidence')
    physical.native_check((parent/(NAME+'.lvs.spice')).read_text())
    primitive_masks(parent, parent/(NAME+'.gds'))
    info = r['extraction']; text = physical.checked_netlist(info)
    if (info != json.loads((parent/'extraction.json').read_text())
            or info['gds_sha256'] != sha(parent/(NAME+'.gds'))
            or info['source_scope_sha256'] != sha(parent/(NAME+'.sch.spice'))
            or sha(ROOT/info['raw_netlist']) != info['reduction']['source_sha256']
            or not physical.audit((ROOT/info['raw_netlist']).read_text())['elementwise_passive_passed']
            or not physical.audit(text)['elementwise_passive_passed']):
        raise ValueError('Native TG passive RC binding changed')
    return i, r


def verify(parent):
    i, r = checked(parent)
    paths = [p for p in parent.iterdir() if p.is_file() and p.name != '.execution.lock']
    paths += [ROOT/r['extraction'][k] for k in ('raw_netlist', 'netlist')]
    paths += [Path(__file__), Path(physical.__file__), ROOT/'scripts/reduce_rc.py', ROOT/'scripts/lvs_utils.py']
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), tools=i['tools'],
                    cad_python=dict(path=sys.executable, sha256=sha(Path(sys.executable))),
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in paths})
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():
        bound(out); return out
    out.mkdir(parents=True)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity, qualified_phy=False), indent=2)+'\n')
    (out/(NAME+'.sch.spice')).write_text(physical.schematic())
    commands = ['gds readonly false', f'gds read {{{parent/(NAME+".gds")}}}']
    for recipe in json.loads((parent/'primitive_geometry.json').read_text()):
        cell = recipe['cell']; commands += [f'load {cell}', f'save {cell}']
    commands += [f'load {NAME}']
    for index, pin in enumerate(r['ports'].values(), 1):
        x, y = pin['x_um'], pin['y_um']
        commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um', f'port make {index}']
    commands += [f'save {NAME}']
    physical.layout.invoke_magic(out, '\n'.join(commands), 'fresh_gds_import')
    fresh = physical.layout.qualify(out, NAME)
    if not fresh['passed']:
        raise ValueError('Independent fresh-GDS TG DRC/LVS failed')
    physical.native_check((out/(NAME+'.lvs.spice')).read_text())
    masks = primitive_masks(parent, out/(NAME+'.gds'))
    net = out/'regenerated.spice'; reduction = reduce_netlist(ROOT/r['extraction']['raw_netlist'], net)
    if reduction != r['extraction']['reduction'] or sha(net) != r['extraction']['netlist_sha256']:
        raise ValueError('Native TG exact RC reduction changed')
    original = (out/(NAME+'.lvs.spice')).read_text(); negatives = []
    for fault, changed in (('wrong_gate', original.replace(' ENB ', ' EN ', 1)),
                           ('wrong_junction', original.replace('ad=0.9744', 'ad=0.9743', 1))):
        (out/(fault+'.spice')).write_text(changed)
        try:
            physical.native_check(changed)
        except ValueError:
            negatives.append(dict(fault=fault, rejected=True))
        else:
            raise ValueError('Native TG negative control was accepted')
    checked(parent)
    result = dict(physical=fresh, primitive_masks=masks, extraction=r['extraction'],
                  exact_reduction_regenerated=True, negative_controls=negatives,
                  component_physical_rc_passed=True, qualified_phy=False, electrical_qualification_passed=False,
                  scope='Independent primitive-mask/placement and fresh-GDS native TG DRC/LVS, raw/reduced passivity and exact RC reduction; no decoder/common wiring or bank timing admission')
    result['outputs'] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != 'manifest.json'}
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    bound(out); return out


def bound(out):
    i = json.loads((out/'manifest.json').read_text())['identity']; r = json.loads((out/'summary.json').read_text())
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(sha(out/n) != h for n, h in r['outputs'].items())
            or sha(Path(i['cad_python']['path'])) != i['cad_python']['sha256']
            or not r['exact_reduction_regenerated'] or not r['component_physical_rc_passed']
            or r['negative_controls'] != [dict(fault='wrong_gate', rejected=True), dict(fault='wrong_junction', rejected=True)]
            or r['qualified_phy'] or r['electrical_qualification_passed']):
        raise ValueError('Independent native TG proof changed')
    _, parent = checked(ROOT/i['parent'])
    if (r['extraction'] != parent['extraction'] or primitive_masks(ROOT/i['parent'], out/(NAME+'.gds')) != r['primitive_masks']
            or (out/(NAME+'.drc_count.txt')).read_text().strip() != '0'
            or not physical.clean_match((out/(NAME+'.lvs.log')).read_text())):
        raise ValueError('Independent native TG GDS/native proof changed')
    physical.native_check((out/(NAME+'.lvs.spice')).read_text())
    return i


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    a = p.parse_args(); print(verify(a.artifact.resolve()), flush=True)
