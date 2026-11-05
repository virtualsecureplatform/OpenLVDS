#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reimport fine-cell GDS and certify actual junctions and distributed RC."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import klayout.db as db
import layout
import moscap_fine_unit_v77 as unit
import build_tg_bank_gds_v51 as native
import extract_native_flat_v4 as extractor
import verify_tg_bank_joint_rc_v52 as math_proof
from build_tapped_output_cells_v72 import certify
from inspect_mim_switch_2x3_pcells_v2 import tools, sha

ROOT = layout.ROOT


def checked(parent):
    if parent.parent != ROOT/'build/diagnostics/moscap_fine_physical_v78':
        raise ValueError('Require new native gate-cap fine-cell geometry')
    identity = json.loads((parent/'manifest.json').read_text())
    if (parent.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
        or identity['version'] != 'moscap-fine-native-layout-v78.1'
        or any(sha(ROOT/n) != h for n, h in {**identity['code'], **identity['parent_files']}.items())
        or tools() != identity['tools']):
        raise ValueError('Physical fine-cell inputs changed')
    for path in identity['parent_files']:
        if Path(path).name == 'manifest.json':
            pi = json.loads((ROOT/path).read_text())
            if any(sha(Path(n)) != h for n, h in pi['pdk_files'].items()):
                raise ValueError('Physical fine-cell PDK changed')
    result = json.loads((parent/'summary.json').read_text())
    if (not result['passed'] or result['drc_count'] != '0' or not result['lvs_passed']
        or result['devices'] != 6 or result['qualified_phy']):
        raise ValueError('Require passing isolated physical cell')
    return identity, result


def run(parent):
    pi, physical = checked(parent); top = unit.name(pi['profile'])
    gds = ROOT/physical['gds']
    paths = list(parent.glob('*'))
    paths += [ROOT/n for n in pi['parent_files']]
    paths += [Path(m.__file__).resolve() for m in list(sys.modules.values())
              if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts']
    identity = dict(version='moscap-fine-native-gds-junction-and-component-rc-v79.1',
                    parent=str(parent.relative_to(ROOT)), tools=tools(),
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths)) if p.is_file()},
                    math_runtime=math_proof.math_proof()['runtime'])
    out = ROOT/'build/diagnostics/moscap_fine_rc_v79'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(identity, indent=2)+'\n')
    print(out, flush=True)
    folder = out/'native'; folder.mkdir()
    reference = parent/(top+'.sch.spice')
    (folder/reference.name).write_bytes(reference.read_bytes())
    lib = db.Layout(); lib.read(str(gds))
    commands = ['gds readonly false', f'gds read {{{gds}}}']
    for cell in lib.each_cell():
        commands += [f'load {cell.name}', f'save {cell.name}']
    commands.append(f'load {top}')
    for index, (port, pin) in enumerate(physical['ports'].items(), 1):
        x, y = pin['x_um'], pin['y_um']
        commands += [f'box values {x-.05}um {y-.05}um {x+.05}um {y+.05}um', f'port make {index}']
    commands.append(f'save {top}')
    layout.invoke_magic(folder, '\n'.join(commands), 'import_gds')
    native_geometry = layout.qualify(folder, top)
    if not native_geometry['passed']:
        raise ValueError('Reimported fine-cell GDS failed native DRC/LVS')
    native_reference = folder/(top+'.lvs.spice')
    _, expected = native.native_leaves(reference.read_text(), top)
    _, actual = native.native_leaves(re.sub(r'\n[ \t]*\+[ \t]*', ' ', native_reference.read_text()), top+'_flat')
    params = native.inventory.compare_parameters(expected, actual)
    if params['native_primitives'] != 6 or sum('fet_' in d['model'] for d in actual) != 5:
        raise ValueError('Gate-cap MOS devices were lost during GDS extraction')
    digest = hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()
    namespace = ROOT/'build/extracted'/digest[:16]/top
    if namespace.exists():
        raise ValueError('Retain existing or partial fine-cell RC extraction')
    info = extractor.extract(top, gds, sha(out/'manifest.json'), ports=physical['ports'],
                             source_scope=sha(reference))
    if info['ports'] != ['NODE', 'EN', 'ENB', 'VDD', 'VSS'] or not info['ports_verified']:
        raise ValueError('Extracted fine-cell public interface changed')
    proof = certify(out, info, top, native_reference, 6)
    if (any(sha(ROOT/n) != h for n, h in identity['inputs'].items())
        or math_proof.math_proof()['runtime'] != identity['math_runtime']):
        raise ValueError('Fine-cell qualification inputs changed during execution')
    checked(parent)
    report = dict(profile=pi['profile'], native_geometry=native_geometry,
                  native_parameters=params, extraction=info, rc_proof=proof,
                  fine_cell_geometry_and_component_rc_passed=True,
                  complete_bank_interconnect_qualified=False,
                  electrical_qualification_passed=False, qualified_phy=False)
    report['files'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()}
    report['extracted_files'] = {str(p.relative_to(ROOT)): sha(p) for p in namespace.glob('*') if p.is_file()}
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(out, flush=True)
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('parent', type=Path)
    run(p.parse_args().parent.resolve())
