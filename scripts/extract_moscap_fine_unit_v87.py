#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Certify compact fine-cell RC with junctions from unchanged native masks."""
from collections import Counter
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
import moscap_junction_reconstruction_v86 as repair
import native_bank_inventory_v51 as inventory
import extract_native_flat_v4 as extractor
import verify_tg_bank_joint_rc_v52 as math_proof
from build_tapped_output_cells_v72 import certify
from inspect_mim_switch_2x3_pcells_v2 import tools, sha
from reduce_rc import reduce_netlist

ROOT = layout.ROOT


def hashed_identity(folder):
    i = json.loads((folder/'manifest.json').read_text())
    if folder.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]:
        raise ValueError('Fine-cell context identity changed')
    return i


def checked(parent, measurements):
    pi = hashed_identity(parent); mi = hashed_identity(measurements)
    if (parent.parent != ROOT/'build/diagnostics/moscap_fine_physical_v84'
        or pi['version'] != 'moscap-fine-compact-two-row-native-layout-v84.1'
        or measurements.parent != ROOT/'build/diagnostics/moscap_primitive_junctions_v85'
        or mi['version'] != 'isolated-native-gate-cap-junction-measurement-v85.1'
        or any(sha(ROOT/n) != h for n, h in {**pi['code'], **pi['parent_files'], **mi['inputs']}.items())
        or tools() != pi['tools'] or tools() != mi['tools']):
        raise ValueError('Physical fine-cell or isolated-junction inputs changed')
    for path in pi['parent_files']:
        if Path(path).name == 'manifest.json':
            info = json.loads((ROOT/path).read_text())
            if any(sha(Path(n)) != h for n, h in info['pdk_files'].items()):
                raise ValueError('Fine-cell PDK changed')
    pr = json.loads((parent/'summary.json').read_text())
    mr = json.loads((measurements/'summary.json').read_text())
    if (not pr['passed'] or pr['drc_count'] != '0' or not pr['lvs_passed'] or pr['devices'] != 6
        or pr['qualified_phy'] or not mr['isolated_primitive_junction_measurements_passed']
        or mr['qualified_phy'] or len(mr['rows']) != 6
        or any(sha(measurements/n) != h for n, h in mr['files'].items())):
        raise ValueError('Require complete native geometry and isolated-junction measurements')
    for row in mr['rows']:
        cell = row['primitive']['cell']
        text = re.sub(r'\n[ \t]*\+[ \t]*', ' ', (measurements/cell/(cell+'.lvs.spice')).read_text())
        _, actual = inventory.native_leaves(text, cell+'_flat')
        if actual != [row['actual']]:
            raise ValueError('Isolated measured junctions disagree with native extraction')
    repair.junction_library(mr['rows'])
    return pi, pr, mr


def region(lib, cell, key):
    index = lib.find_layer(*key)
    return db.Region() if index is None else db.Region(cell.begin_shapes_rec(index)).merged()


def masks(gds, top, reference, rows, measurements):
    lib = db.Layout(); lib.read(str(gds)); root = lib.cell(top)
    if root is None:
        raise ValueError('Fine-cell GDS top missing')
    ports, devices = layout.flatten(layout.circuits(reference), top)
    library = repair.junction_library(rows)
    expected = Counter(library[repair.geometry_key(d)]['cell'] for d in devices if 'fet_' in d['model'])
    observed = Counter(); active = []; evidence = []; compared = set()
    routing = {(67, 20), (68, 20), (69, 20), (70, 20), (71, 20), (72, 20),
               (67, 44), (68, 44), (69, 44), (70, 44), (71, 44), (235, 4)}
    for index in lib.layer_indexes():
        info = lib.get_info(index); key = (info.layer, info.datatype)
        if key not in routing and not db.Region(root.shapes(index)).is_empty():
            raise ValueError('Fine-cell root adds manufacturing geometry outside native primitives')
    instances = list(root.each_inst())
    if len(instances) != 6:
        raise ValueError('Fine-cell physical primitive count changed')
    for inst in instances:
        cell = lib.cell(inst.cell_index)
        if cell.name not in expected:
            continue
        if inst.na != 0 or inst.nb != 0 or inst.trans.is_mirror() or inst.trans.angle != 0:
            raise ValueError('Require individually placed untranslated-orientation native MOS cells')
        observed[cell.name] += 1
        r = region(lib, cell, (65, 20)).transformed(inst.trans)
        if r.is_empty() or any(not (r & prior).is_empty() for prior in active):
            raise ValueError('Placed MOS active regions overlap or are missing')
        active.append(r)
        if cell.name in compared:
            continue
        measured = db.Layout(); measured.read(str(measurements/cell.name/(cell.name+'.gds')))
        other = measured.cell(cell.name)
        if other is None or measured.dbu != lib.dbu:
            raise ValueError('Measured primitive GDS scale/top differs')
        keys = {(l.get_info(i).layer, l.get_info(i).datatype) for l in (lib, measured) for i in l.layer_indexes()}
        for key in keys:
            # V85 adds only a gate-metal escape to meet minimum M1 area.
            if key == (68, 20):
                continue
            if not (region(lib, cell, key) ^ region(measured, other, key)).is_empty():
                raise ValueError('Placed native primitive masks differ from measured junction geometry')
        evidence.append(dict(cell=cell.name, all_masks_except_gate_metal_identical=True))
        compared.add(cell.name)
    if observed != expected or len(active) != 5:
        raise ValueError('Fine-cell MOS primitive identities changed')
    return dict(primitive_masks=evidence, native_mos_instances=5,
                all_native_active_regions_separate=True, root_additions_limited_to_routing=True)


def run(parent, measurements):
    pi, physical, mr = checked(parent, measurements); top = unit.name(pi['profile'])
    gds = ROOT/physical['gds']; reference = parent/(top+'.sch.spice')
    paths = [p for base in (parent, measurements) for p in base.rglob('*') if p.is_file()]
    paths += [ROOT/n for n in {**pi['parent_files'], **mi_inputs(measurements)}]
    paths += [Path(m.__file__).resolve() for m in list(sys.modules.values())
              if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts']
    pdk = Path(os.environ['PDK_ROOT'])/'sky130A'
    external = [pdk/'libs.tech/magic/sky130A.magicrc', pdk/'libs.tech/netgen/sky130A_setup.tcl']
    external += [p for p in (pdk/'libs.tech/magic').glob('*') if p.is_file()]
    identity = dict(version='compact-moscap-native-mask-derived-junctions-and-component-rc-v87.1',
                    parent=str(parent.relative_to(ROOT)), measurements=str(measurements.relative_to(ROOT)),
                    inputs={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}, tools=tools(),
                    external_files={str(p): sha(p) for p in sorted(set(external))},
                    math_runtime=math_proof.math_proof()['runtime'])
    out = ROOT/'build/diagnostics/moscap_fine_rc_v87'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(identity, indent=2)+'\n'); print(out, flush=True)
    mask_proof = masks(gds, top, reference.read_text(), mr['rows'], measurements)
    folder = out/'native'; folder.mkdir(); (folder/reference.name).write_bytes(reference.read_bytes())
    lib = db.Layout(); lib.read(str(gds)); commands = ['gds readonly false', f'gds read {{{gds}}}']
    for cell in lib.each_cell():
        commands += [f'load {cell.name}', f'save {cell.name}']
    commands.append(f'load {top}')
    for index, pin in enumerate(physical['ports'].values(), 1):
        x, y = pin['x_um'], pin['y_um']
        commands += [f'box values {x-.05}um {y-.05}um {x+.05}um {y+.05}um', f'port make {index}']
    commands.append(f'save {top}'); layout.invoke_magic(folder, '\n'.join(commands), 'import_gds')
    native_geometry = layout.qualify(folder, top)
    if not native_geometry['passed']:
        raise ValueError('Reimported compact GDS DRC/LVS failed')
    digest = hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()
    if (ROOT/'build/extracted'/digest[:16]/top).exists():
        raise ValueError('Retain existing or partial compact fine-cell RC extraction')
    original = extractor.extract(top, gds, sha(out/'manifest.json'), ports=physical['ports'], source_scope=sha(reference))
    if not original['passed'] or original['ports'] != ['NODE', 'EN', 'ENB', 'VDD', 'VSS']:
        raise ValueError('Original compact RC extraction/interface failed')
    raw = (ROOT/original['raw_netlist']).read_text()
    corrected, measured_reference, correction = repair.reconstruct(raw, top, reference.read_text(), mr['rows'])
    target = out/'corrected'; target.mkdir()
    raw_path = target/'raw.spice'; raw_path.write_text(corrected)
    ref_path = target/'measured_reference.spice'; ref_path.write_text(measured_reference)
    reduced_path = target/'reduced.spice'; reduction = reduce_netlist(raw_path, reduced_path)
    info = dict(original, raw_netlist=str(raw_path.relative_to(ROOT)), netlist=str(reduced_path.relative_to(ROOT)),
                netlist_sha256=sha(reduced_path), reduction=reduction, junctions_reconstructed_from_native_masks=True)
    proof = certify(target, info, top, ref_path, 6)
    if repair.reconstruct(raw, top, reference.read_text(), mr['rows']) != (corrected, measured_reference, correction):
        raise ValueError('Measured-junction reconstruction cannot regenerate exactly')
    if (any(sha(ROOT/n) != h for n, h in identity['inputs'].items())
        or any(sha(Path(n)) != h for n, h in identity['external_files'].items())
        or tools() != identity['tools'] or math_proof.math_proof()['runtime'] != identity['math_runtime']):
        raise ValueError('Compact component RC inputs changed')
    checked(parent, measurements)
    report = dict(profile=pi['profile'], mask_proof=mask_proof, native_geometry=native_geometry,
        original_extraction=original, junction_reconstruction=correction, extraction=info, rc_proof=proof,
        fine_cell_geometry_and_component_rc_passed=True, original_extraction_preserved=True,
        complete_bank_interconnect_qualified=False, electrical_qualification_passed=False, qualified_phy=False)
    report['files'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file()}
    namespace = (ROOT/original['raw_netlist']).parent
    report['original_extracted_files'] = {str(p.relative_to(ROOT)): sha(p) for p in namespace.glob('*') if p.is_file()}
    (out/'summary.json').write_text(json.dumps(report, indent=2)+'\n'); print(out, flush=True)
    return out


def mi_inputs(measurements):
    return json.loads((measurements/'manifest.json').read_text())['inputs']


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('parent', type=Path)
    p.add_argument('--measurements', type=Path, required=True); a = p.parse_args()
    run(a.parent.resolve(), a.measurements.resolve())
