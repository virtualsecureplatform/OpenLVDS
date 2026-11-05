#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently reload candidate GDS and verify masks, native geometry and RC."""
import argparse
import hashlib
import json
from pathlib import Path
import build_regular_clock_inverter_v14 as physical
from reduce_rc import reduce_netlist

ROOT = physical.ROOT
VERSION = 'independent-hierarchy-preserved-regular-inverter-gds-native-rc-proof-v15.1'
CONTEXT = 'regular_clock_inverter_verification_v15'
sha = physical.sha
NAME = physical.NAME


def checked(parent):
    i = physical.bound(parent); r = json.loads((parent/'summary.json').read_text())
    old = ROOT/i['parent']/physical.OLD
    state = json.loads((parent/'state.json').read_text())
    if (state != dict(status='complete', passed=True, qualified_phy=False)
            or not all(r[k] is True for k in ('component_physical_rc_passed', 'native_geometry_preserved',
                                             'elementwise_passive_passed', 'rc_topology_passed'))
            or r['qualified_phy'] or r['electrical_qualification_passed']
            or any(sha(parent/n) != h for n, h in r['files'].items())
            or (parent/(NAME+'.sch.spice')).read_text() != physical.schematic((old/(physical.OLD+'.sch.spice')).read_text())
            or (parent/(NAME+'.drc_count.txt')).read_text().strip() != '0'
            or not physical.clean_match((parent/(NAME+'.lvs.log')).read_text())
            or not physical.clean_match((parent/'rc_lvs.log').read_text())):
        raise ValueError('Require unchanged complete native regular-inverter physical/RC proof')
    info = r['extraction']; text = physical.checked_netlist(info); raw = ROOT/info['raw_netlist']
    if (info != json.loads((parent/'extraction.json').read_text())
            or info['gds_sha256'] != sha(parent/(NAME+'.gds'))
            or info['source_scope_sha256'] != sha(parent/(NAME+'.sch.spice'))
            or sha(raw) != info['reduction']['source_sha256']
            or not physical.audit(raw.read_text())['elementwise_passive_passed']
            or not physical.audit(text)['elementwise_passive_passed']
            or physical.mask_audit(old/(physical.OLD+'.gds'), parent/(NAME+'.gds')) != r['mask_comparison']
            or physical.native_signature((old/(physical.OLD+'.lvs.spice')).read_text(), True)
            != physical.native_signature((parent/(NAME+'.lvs.spice')).read_text())):
        raise ValueError('Regular inverter native geometry/source/passive RC binding changed')
    return i, r, old


def negative_mask_checks(out, old, parent):
    import klayout.db as db
    reference = old/(physical.OLD+'.gds'); candidate = parent/(NAME+'.gds')
    tests = []
    for fault in ('extra_metal3', 'hvt_marker_retained'):
        layout, cell, _ = physical.masks(candidate, NAME)
        if fault == 'extra_metal3':
            cell.shapes(layout.layer(70, 20)).insert(db.Box(100000, 100000, 100400, 100400))
        else:
            cell.shapes(layout.layer(*physical.MARKER)).insert(db.Box(0, 0, 400, 400))
        file = out/(fault+'.gds'); layout.write(str(file))
        try:
            physical.mask_audit(reference, file)
        except ValueError:
            tests.append(dict(fault=fault, rejected=True))
        else:
            raise ValueError('Independent mask negative control was accepted')
    return tests


def verify(parent):
    i, r, old = checked(parent)
    paths = [p for p in parent.iterdir() if p.is_file() and p.name != '.execution.lock']
    paths += [ROOT/r['extraction'][k] for k in ('raw_netlist', 'netlist')]
    paths += [Path(__file__), Path(physical.__file__), ROOT/'scripts/reduce_rc.py',
              ROOT/'scripts/audit_rc_comments_v2.py', ROOT/'scripts/audit_passive_rc_v3.py', ROOT/'scripts/lvs_utils.py']
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), tools=i['tools'],
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in paths})
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():
        bound(out); return out
    out.mkdir(parents=True)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity, qualified_phy=False), indent=2)+'\n')
    source = (parent/(NAME+'.sch.spice')).read_text(); (out/(NAME+'.sch.spice')).write_text(source)
    layout, _, _ = physical.masks(parent/(NAME+'.gds'), NAME)
    commands = ['gds readonly false', f'gds read {{{parent/(NAME+".gds")}}}']
    for cell in layout.each_cell():
        commands += [f'load {cell.name}', f'save {cell.name}']
    commands += [f'load {NAME}']
    for index, pin in enumerate(i['ports'].values(), 1):
        x, y = pin['x_um'], pin['y_um']
        commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um', f'port make {index}']
    commands += [f'save {NAME}']
    physical.original.layout.invoke_magic(out, '\n'.join(commands), 'fresh_gds_import')
    result = physical.original.layout.qualify(out, NAME)
    if (not result['passed'] or physical.mask_audit(old/(physical.OLD+'.gds'), out/(NAME+'.gds')) != r['mask_comparison']
            or physical.native_signature((out/(NAME+'.lvs.spice')).read_text())
            != physical.native_signature((old/(physical.OLD+'.lvs.spice')).read_text(), True)):
        raise ValueError('Independent fresh-GDS physical/native proof failed')
    regenerated = out/'regenerated.spice'
    reduction = reduce_netlist(ROOT/r['extraction']['raw_netlist'], regenerated)
    if reduction != r['extraction']['reduction'] or sha(regenerated) != r['extraction']['netlist_sha256']:
        raise ValueError('Independent raw-to-simulator exact reduction changed')
    negatives = negative_mask_checks(out, old, parent)
    checked(parent)
    result = dict(physical=result, extraction=r['extraction'], mask_comparison=r['mask_comparison'],
                  fresh_gds_native_geometry_verified=True, exact_reduction_regenerated=True,
                  raw_and_reduced_passivity_passed=True, negative_controls=negatives,
                  component_physical_rc_passed=True, passed=True, qualified_phy=False,
                  electrical_qualification_passed=False,
                  scope='Independent fresh-GDS DRC/LVS and native junction proof, exact non-HVTP masks, positive raw/reduced RC and regenerated exact reduction; no bank or timing admission')
    result['outputs'] = {p.name: sha(p) for p in out.iterdir() if p.is_file() and p.name != 'manifest.json'}
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    bound(out)
    return out


def bound(out):
    i = json.loads((out/'manifest.json').read_text())['identity']; r = json.loads((out/'summary.json').read_text())
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(sha(out/n) != h for n, h in r['outputs'].items())
            or not all(r[k] is True for k in ('passed', 'component_physical_rc_passed', 'fresh_gds_native_geometry_verified',
                                             'exact_reduction_regenerated', 'raw_and_reduced_passivity_passed'))
            or not all(n['rejected'] for n in r['negative_controls']) or len(r['negative_controls']) != 2
            or r['qualified_phy'] or r['electrical_qualification_passed']):
        raise ValueError('Independent regular-inverter receipt changed or incomplete')
    _, parent, old = checked(ROOT/i['parent'])
    if (r['extraction'] != parent['extraction']
            or (out/(NAME+'.drc_count.txt')).read_text().strip() != '0'
            or not physical.clean_match((out/(NAME+'.lvs.log')).read_text())
            or physical.mask_audit(old/(physical.OLD+'.gds'), out/(NAME+'.gds')) != parent['mask_comparison']
            or physical.native_signature((out/(NAME+'.lvs.spice')).read_text())
            != physical.native_signature((old/(physical.OLD+'.lvs.spice')).read_text(), True)):
        raise ValueError('Independent regular-inverter native proof changed')
    return i


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    a = p.parse_args(); print(verify(a.artifact.resolve()), flush=True)
