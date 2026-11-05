#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independent fresh-GDS and exact-RC proof for native low-Vt data components."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import build_nlvt_data_components_v29 as physical
from reduce_rc import reduce_netlist

ROOT = physical.ROOT
sha = physical.sha
VERSION = 'independent-native-nlvt-data-components-gds-and-rc-v30.1'
CONTEXT = 'nlvt_data_components_verification_v30'


def checked(parent):
    i = physical.bound(parent); r = json.loads((parent/'summary.json').read_text())
    if (json.loads((parent/'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
            or not r['component_physical_rc_passed'] or r['qualified_phy'] or r['electrical_qualification_passed']
            or any(sha(parent/n) != h for n, h in r['files'].items())
            or [row['profile'] for row in r['rows']] != list(physical.SPECS)):
        raise ValueError('Require unchanged complete native low-Vt physical/RC evidence')
    for row in r['rows']:
        profile = row['profile']; spec = physical.SPECS[profile]; folder = parent/profile
        name = spec['name']; info = i['components'][profile]
        if (not row['component_physical_rc_passed'] or not row['rc_topology_passed']
                or row['qualified_phy'] or row['electrical_qualification_passed']
                or (folder/(name+'.drc_count.txt')).read_text().strip() != '0'
                or not physical.tg.clean_match((folder/(name+'.lvs.log')).read_text())
                or not physical.tg.clean_match((folder/'rc_lvs.log').read_text())
                or physical.mask_audit(ROOT/info['reference'], folder/(name+'.gds'), spec) != row['mask_comparison']
                or physical.native_signature((ROOT/info['native']).read_text(), spec, True)
                   != physical.native_signature((folder/(name+'.lvs.spice')).read_text(), spec)):
            raise ValueError('Native low-Vt physical masks, geometry or LVS changed')
        rc = row['extraction']; text = physical.tg.checked_netlist(rc)
        if (rc != json.loads((folder/'extraction.json').read_text())
                or rc['gds_sha256'] != sha(folder/(name+'.gds'))
                or rc['source_scope_sha256'] != sha(folder/(name+'.sch.spice'))
                or sha(ROOT/rc['raw_netlist']) != rc['reduction']['source_sha256']
                or not physical.tg.audit((ROOT/rc['raw_netlist']).read_text())['elementwise_passive_passed']
                or not physical.tg.audit(text)['elementwise_passive_passed']):
            raise ValueError('Native low-Vt passive RC binding changed')
    return i, r


def verify(parent):
    import klayout.db as db
    i, r = checked(parent)
    paths = [p for p in parent.rglob('*') if p.is_file() and p.name != '.execution.lock']
    paths += [ROOT/row['extraction'][k] for row in r['rows'] for k in ('raw_netlist', 'netlist')]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), tools=i['tools'],
                    cad_python=dict(path=sys.executable, sha256=sha(Path(sys.executable))),
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in paths})
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():
        bound(out); return out
    out.mkdir(parents=True)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity, qualified_phy=False), indent=2)+'\n')
    rows = []
    for row in r['rows']:
        profile = row['profile']; spec = physical.SPECS[profile]; name = spec['name']
        folder = out/profile; folder.mkdir(); source = parent/profile
        (folder/(name+'.sch.spice')).write_text((source/(name+'.sch.spice')).read_text())
        layout = db.Layout(); layout.read(str(source/(name+'.gds')))
        commands = ['gds readonly false', f'gds read {{{source/(name+".gds")}}}']
        for child in layout.each_cell():
            commands += [f'load {child.name}', f'save {child.name}']
        commands += [f'load {name}']
        for index, pin in enumerate(i['components'][profile]['ports'].values(), 1):
            x, y = pin['x_um'], pin['y_um']
            commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um', f'port make {index}']
        commands += [f'save {name}']
        physical.tg.layout.invoke_magic(folder, '\n'.join(commands), 'fresh_gds_import')
        fresh = physical.tg.layout.qualify(folder, name)
        masks = physical.mask_audit(ROOT/i['components'][profile]['reference'], folder/(name+'.gds'), spec)
        original_native = (ROOT/i['components'][profile]['native']).read_text()
        native = (folder/(name+'.lvs.spice')).read_text()
        if (not fresh['passed'] or masks != row['mask_comparison']
                or physical.native_signature(original_native, spec, True) != physical.native_signature(native, spec)):
            raise ValueError('Independent fresh-GDS low-Vt physical check failed')
        net = folder/'regenerated.spice'; reduction = reduce_netlist(ROOT/row['extraction']['raw_netlist'], net)
        if reduction != row['extraction']['reduction'] or sha(net) != row['extraction']['netlist_sha256']:
            raise ValueError('Low-Vt data-component exact RC reduction changed')
        # Real GDS corruption must fail the implant-only mask gate.
        corrupt = db.Layout(); corrupt.read(str(source/(name+'.gds')))
        corrupt.cell(name).shapes(corrupt.layer(68, 20)).insert(db.Box(-1000, -1000, -800, -800))
        fault = folder/'wrong_metal.gds'; corrupt.write(str(fault))
        try:
            physical.mask_audit(ROOT/i['components'][profile]['reference'], fault, spec)
        except ValueError:
            pass
        else:
            raise ValueError('Actual non-implant mask corruption was accepted')
        rows.append(dict(profile=profile, physical=fresh, mask_comparison=masks, extraction=row['extraction'],
                         native_geometry_preserved=True, exact_reduction_regenerated=True,
                         wrong_metal_gds_rejected=True, component_physical_rc_passed=True, qualified_phy=False))
    checked(parent)
    result = dict(rows=rows, component_physical_rc_passed=True, qualified_phy=False, electrical_qualification_passed=False,
                  scope='Independent fresh-GDS implant-only masks, strict native LVS/junction geometry and exact passive RC; no bank or PHY qualification')
    result['outputs'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file() and p.name != 'manifest.json'}
    (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
    bound(out); return out


def bound(out):
    i = json.loads((out/'manifest.json').read_text())['identity']; r = json.loads((out/'summary.json').read_text())
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(sha(out/n) != h for n, h in r['outputs'].items())
            or sha(Path(i['cad_python']['path'])) != i['cad_python']['sha256']
            or not r['component_physical_rc_passed'] or r['qualified_phy'] or r['electrical_qualification_passed']):
        raise ValueError('Independent native low-Vt component proof changed')
    pi, parent = checked(ROOT/i['parent'])
    if [x['profile'] for x in r['rows']] != list(physical.SPECS):
        raise ValueError('Incomplete native low-Vt component proof')
    for row, original in zip(r['rows'], parent['rows']):
        spec = physical.SPECS[row['profile']]; name = spec['name']; folder = out/row['profile']
        if (not row['exact_reduction_regenerated'] or not row['wrong_metal_gds_rejected']
                or not row['component_physical_rc_passed'] or row['qualified_phy']
                or row['extraction'] != original['extraction'] or row['mask_comparison'] != original['mask_comparison']
                or physical.mask_audit(ROOT/pi['components'][row['profile']]['reference'], folder/(name+'.gds'), spec) != row['mask_comparison']
                or (folder/(name+'.drc_count.txt')).read_text().strip() != '0'
                or not physical.tg.clean_match((folder/(name+'.lvs.log')).read_text())
                or physical.native_signature((ROOT/pi['components'][row['profile']]['native']).read_text(), spec, True)
                   != physical.native_signature((folder/(name+'.lvs.spice')).read_text(), spec)):
            raise ValueError('Independent low-Vt GDS or native proof changed')
    return i


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    a = p.parse_args(); print(verify(a.artifact.resolve()), flush=True)
