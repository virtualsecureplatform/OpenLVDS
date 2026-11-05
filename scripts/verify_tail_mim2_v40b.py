#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent primitive-mask, fresh-GDS native MIM and exact-RC proof."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import build_tail_mim2_v39 as physical
from reduce_rc import reduce_netlist

ROOT = physical.ROOT
sha = physical.sha
NAME = physical.NAME
VERSION = 'independent-tail-mim2-safe-access-gds-and-passive-rc-v40.2'
CONTEXT = 'tail_mim2_verification_v40b'


def primitive_masks(parent,gds):
    i=physical.bound(parent)
    return physical.masks(ROOT/i['parent'],gds)


def routing_masks(parent,gds):
    import klayout.db as db
    a=db.Layout();a.read(str(parent/(NAME+'.gds')))
    b=db.Layout();b.read(str(gds))
    if a.dbu != b.dbu or a.cell(NAME) is None or b.cell(NAME) is None:
        raise ValueError('Tail MIM root or coordinate scale changed')
    keys={(l.get_info(i).layer,l.get_info(i).datatype) for l in (a,b) for i in l.layer_indexes()}
    for key in keys:
        def region(layout):
            i=layout.find_layer(*key)
            return db.Region() if i is None else db.Region(layout.cell(NAME).begin_shapes_rec(i)).merged()
        if not (region(a)^region(b)).is_empty(): raise ValueError('Tail MIM routing or primitive masks changed')
    return dict(all_routed_mask_regions_identical=True)


def checked(parent):
    i = physical.bound(parent); r = json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
            or not r['component_physical_rc_passed'] or not r['rc_topology_passed'] or r['qualified_phy']
            or any(sha(parent/n) != h for n, h in r['files'].items())
            or (parent/(NAME+'.drc_count.txt')).read_text().strip() != '0'
            or not physical.native.clean_match((parent/(NAME+'.lvs.log')).read_text())
            or not physical.native.clean_match((parent/'rc_lvs.log').read_text())):
        raise ValueError('Require complete unchanged native MIM physical/RC evidence')
    physical.native_check((parent/(NAME+'.lvs.spice')).read_text())
    primitive_masks(parent, parent/(NAME+'.gds'))
    info = r['extraction']; text = physical.native.checked_netlist(info)
    if (info != json.loads((parent/'extraction.json').read_text())
            or info['gds_sha256'] != sha(parent/(NAME+'.gds'))
            or info['source_scope_sha256'] != sha(parent/(NAME+'.sch.spice'))
            or sha(ROOT/info['raw_netlist']) != info['reduction']['source_sha256']
            or not physical.native.audit((ROOT/info['raw_netlist']).read_text())['elementwise_passive_passed']
            or not physical.native.audit(text)['elementwise_passive_passed']):
        raise ValueError('Native MIM passive RC binding changed')
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
    commands += [f'load {physical.CAP}', f'save {physical.CAP}']
    commands += [f'load {NAME}']
    for index, pin in enumerate(i['ports'].values(), 1):
        x, y = pin['x_um'], pin['y_um']
        commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um', f'port make {index}']
    commands += [f'save {NAME}']
    physical.native.layout.invoke_magic(out, '\n'.join(commands), 'fresh_gds_import')
    fresh = physical.native.layout.qualify(out, NAME)
    if not fresh['passed']:
        raise ValueError('Independent fresh-GDS TG DRC/LVS failed')
    physical.native_check((out/(NAME+'.lvs.spice')).read_text())
    masks = primitive_masks(parent, out/(NAME+'.gds'))
    routes = routing_masks(parent, out/(NAME+'.gds'))
    net = out/'regenerated.spice'; reduction = reduce_netlist(ROOT/r['extraction']['raw_netlist'], net)
    if reduction != r['extraction']['reduction'] or sha(net) != r['extraction']['netlist_sha256']:
        raise ValueError('Native MIM exact RC reduction changed')
    original = (out/(NAME+'.lvs.spice')).read_text(); negatives = []
    for fault, changed in (('wrong_cap_dimensions', original.replace('w=2', 'w=3', 1)),
                           ('shorted_cap', original.replace(' VGND ', ' A ', 1))):
        (out/(fault+'.spice')).write_text(changed)
        try:
            physical.native_check(changed)
        except ValueError:
            negatives.append(dict(fault=fault, rejected=True))
        else:
            raise ValueError('Native MIM negative control was accepted')
    checked(parent)
    result = dict(physical=fresh, primitive_masks=masks, routing_masks=routes, extraction=r['extraction'],
                  exact_reduction_regenerated=True, negative_controls=negatives,
                  component_physical_rc_passed=True, qualified_phy=False, electrical_qualification_passed=False,
                  scope='Independent native 2x2 balancing MIM masks/placement, fresh-GDS DRC/LVS, routed-mask identity, passive RC and exact reduction; no bank timing or PHY admission')
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
            or r['negative_controls'] != [dict(fault='wrong_cap_dimensions', rejected=True), dict(fault='shorted_cap', rejected=True)]
            or r['qualified_phy'] or r['electrical_qualification_passed']):
        raise ValueError('Independent native MIM proof changed')
    _, parent = checked(ROOT/i['parent'])
    if (r['extraction'] != parent['extraction'] or primitive_masks(ROOT/i['parent'], out/(NAME+'.gds')) != r['primitive_masks']
            or routing_masks(ROOT/i['parent'], out/(NAME+'.gds')) != r['routing_masks']
            or (out/(NAME+'.drc_count.txt')).read_text().strip() != '0'
            or not physical.native.clean_match((out/(NAME+'.lvs.log')).read_text())):
        raise ValueError('Independent native MIM GDS/native proof changed')
    physical.native_check((out/(NAME+'.lvs.spice')).read_text())
    return i


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    a = p.parse_args(); print(verify(a.artifact.resolve()), flush=True)
