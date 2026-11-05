#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent fresh-GDS and exact-RC proof for the smaller native guard."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import build_nlvt_guard2_v34 as physical
from reduce_rc import reduce_netlist

ROOT = physical.ROOT
sha = physical.sha
NAME = physical.NAME
VERSION = 'independent-nlvt-native-2x2-guard-gds-and-rc-v35.1'
CONTEXT = 'nlvt_guard2_verification_v35'


def checked(parent):
    i = physical.bound(parent); r = json.loads((parent/'summary.json').read_text()); old = ROOT/i['parent']
    if (json.loads((parent/'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
            or not all(r[k] is True for k in ('component_physical_rc_passed', 'rc_topology_passed'))
            or r['qualified_phy'] or r['electrical_qualification_passed']
            or any(sha(parent/n) != h for n, h in r['files'].items())
            or (parent/(NAME+'.sch.spice')).read_text() != physical.schematic((old/(physical.OLD+'.sch.spice')).read_text())
            or (parent/(NAME+'.drc_count.txt')).read_text().strip() != '0'
            or not physical.previous.tg.clean_match((parent/(NAME+'.lvs.log')).read_text())
            or not physical.previous.tg.clean_match((parent/'rc_lvs.log').read_text())):
        raise ValueError('Require unchanged complete small-guard physical/RC evidence')
    capref = parent/(physical.CAP+'.gds')
    info = r['extraction']; text = physical.previous.tg.checked_netlist(info)
    if (info != json.loads((parent/'extraction.json').read_text())
            or info['gds_sha256'] != sha(parent/(NAME+'.gds'))
            or info['source_scope_sha256'] != sha(parent/(NAME+'.sch.spice'))
            or sha(ROOT/info['raw_netlist']) != info['reduction']['source_sha256']
            or not physical.previous.tg.audit((ROOT/info['raw_netlist']).read_text())['elementwise_passive_passed']
            or not physical.previous.tg.audit(text)['elementwise_passive_passed']
            or physical.mask_check(old/(physical.OLD+'.gds'), parent/(NAME+'.gds'), capref) != r['mask_comparison']
            or physical.native_check((old/(physical.OLD+'.lvs.spice')).read_text(), (parent/(NAME+'.lvs.spice')).read_text()) != r['native_comparison']):
        raise ValueError('Small-guard geometry, native or RC binding changed')
    return i, r, old


def verify(parent):
    i, r, old = checked(parent)
    capref = parent/(physical.CAP+'.gds')
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
    (out/(NAME+'.sch.spice')).write_bytes((parent/(NAME+'.sch.spice')).read_bytes())
    layout, _, _ = physical.previous.masktools.masks(parent/(NAME+'.gds'), NAME)
    commands = ['gds readonly false', f'gds read {{{parent/(NAME+".gds")}}}']
    for cell in layout.each_cell():
        commands += [f'load {cell.name}', f'save {cell.name}']
    commands += [f'load {NAME}']
    for index, pin in enumerate(i['ports'].values(), 1):
        x, y = pin['x_um'], pin['y_um']
        commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um', f'port make {index}']
    commands += [f'save {NAME}']
    physical.previous.tg.layout.invoke_magic(out, '\n'.join(commands), 'fresh_gds_import')
    fresh = physical.previous.tg.layout.qualify(out, NAME)
    if (not fresh['passed']
            or physical.mask_check(old/(physical.OLD+'.gds'), out/(NAME+'.gds'), capref) != r['mask_comparison']
            or physical.native_check((old/(physical.OLD+'.lvs.spice')).read_text(), (out/(NAME+'.lvs.spice')).read_text()) != r['native_comparison']):
        raise ValueError('Independent fresh-GDS small-guard proof failed')
    regenerated = out/'regenerated.spice'
    reduction = reduce_netlist(ROOT/r['extraction']['raw_netlist'], regenerated)
    if reduction != r['extraction']['reduction'] or sha(regenerated) != r['extraction']['netlist_sha256']:
        raise ValueError('Small-guard exact reduction changed')
    import klayout.db as db
    negatives = []
    for fault in ('extra_root_metal1', 'changed_mos_child'):
        layout, cell, _ = physical.previous.masktools.masks(parent/(NAME+'.gds'), NAME)
        target = cell if fault == 'extra_root_metal1' else layout.cell(physical.OLD+'_core')
        if target is None:
            raise ValueError('Missing native core for negative control')
        target.shapes(layout.layer(68, 20)).insert(db.Box(100000, 100000, 100400, 100400))
        file = out/(fault+'.gds'); layout.write(str(file))
        try:
            physical.mask_check(old/(physical.OLD+'.gds'), file, capref)
        except ValueError:
            negatives.append(dict(fault=fault, rejected=True))
        else:
            raise ValueError('Small-guard negative mask control was accepted')
    checked(parent)
    result = dict(physical=fresh, extraction=r['extraction'], mask_comparison=r['mask_comparison'],
                  native_comparison=r['native_comparison'], negative_controls=negatives,
                  fresh_gds_native_verified=True, exact_reduction_regenerated=True,
                  component_physical_rc_passed=True, qualified_phy=False, electrical_qualification_passed=False,
                  scope='Independent native low-Vt 2x2 guard GDS/mask/placement/junction DRC/LVS, passive RC and exact reduction; no bank timing/PVT or PHY admission')
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
            or not all(r[k] is True for k in ('fresh_gds_native_verified', 'exact_reduction_regenerated', 'component_physical_rc_passed'))
            or r['negative_controls'] != [dict(fault='extra_root_metal1', rejected=True), dict(fault='changed_mos_child', rejected=True)]
            or r['qualified_phy'] or r['electrical_qualification_passed']):
        raise ValueError('Independent small-guard proof changed or incomplete')
    _, parent, old = checked(ROOT/i['parent'])
    capref = ROOT/i['parent']/(physical.CAP+'.gds')
    if (r['extraction'] != parent['extraction']
            or (out/(NAME+'.drc_count.txt')).read_text().strip() != '0'
            or not physical.previous.tg.clean_match((out/(NAME+'.lvs.log')).read_text())
            or physical.mask_check(old/(physical.OLD+'.gds'), out/(NAME+'.gds'), capref) != parent['mask_comparison']
            or physical.native_check((old/(physical.OLD+'.lvs.spice')).read_text(), (out/(NAME+'.lvs.spice')).read_text()) != parent['native_comparison']):
        raise ValueError('Independent small-guard native geometry proof changed')
    return i


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    a = p.parse_args(); print(verify(a.artifact.resolve()), flush=True)
