#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native NMOS-LVT INV8/BUF4 pair: implant-only masks and fresh component RC."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import build_stacked_nlvt_tg_v27 as tg
import verify_stacked_nlvt_tg_v28 as tgproof
import build_regular_clock_inverter_v14 as masktools

ROOT = tg.ROOT
sha = tg.sha
VERSION = 'native-nlvt-data-inverter-buffer-implant-only-and-fresh-rc-v29.1'
CONTEXT = 'nlvt_data_components_v29'
MARKER = (125, 44)
HVT = (78, 44)
REGULAR_N = 'sky130_fd_pr__nfet_01v8'
HVT_P = 'sky130_fd_pr__pfet_01v8_hvt'
SPECS = {
    'inv3': dict(old='openlvds_inv_8_regular_o3_v17', name='openlvds_inv_8_nlvt_o3_v29',
                 core='openlvds_inv_8_regular_core_v14', n=8, p=8, mim=1),
    'bufpair': dict(old='openlvds_buf_4_pair_v2', name='openlvds_buf_4_pair_nlvt_v29',
                    core='sky130_fd_sc_hd__buf_4', n=10, p=10, mim=0),
}


def region(layout, cell, key):
    import klayout.db as db
    index = layout.find_layer(*key)
    return db.Region() if index is None else db.Region(cell.begin_shapes_rec(index)).merged()


def implant(layout, cell):
    return (region(layout, cell, (66, 20)) & region(layout, cell, (65, 20)) &
            region(layout, cell, (93, 44))).sized(round(.18/layout.dbu)).merged()


def native_signature(text, spec, normalize=False):
    definitions = tg.layout.circuits(text)
    if len(definitions) != 1:
        raise ValueError('Require a single flat native component')
    ports, devices = next(iter(definitions.values()))
    expected_ports = {'A', 'Y' if spec['mim'] else 'X', 'VPWR', 'VGND'}
    if set(ports) != expected_ports or len(devices) != spec['n']+spec['p']+spec['mim']:
        raise ValueError('Native component interface or device count changed')
    signatures = []
    for _, nodes, model, params in devices:
        values = {k: float(v) for k, v in params.items()}
        if normalize:
            model = {REGULAR_N: tg.N, HVT_P: tg.P}.get(model, model)
        if model in (tg.N, tg.P):
            if set(values) != {'w', 'l', 'ad', 'as', 'pd', 'ps'} or values['l'] != .15:
                raise ValueError('Native device dimensions/junction coverage changed')
            if nodes[3] != ('VGND' if model == tg.N else 'VPWR'):
                raise ValueError('Native data-component body tie changed')
            ends = tuple(sorted(((values['ad'], values['pd']), (values['as'], values['ps']))))
            signatures.append((model, values['w'], values['l'], ends))
        elif model == 'sky130_fd_pr__cap_mim_m3_1' and values == {'w': 3., 'l': 3.}:
            signatures.append((model, 3., 3.))
        else:
            raise ValueError('Unexpected native primitive in low-Vt data component')
    if sum(s[0] == tg.N for s in signatures) != spec['n'] or sum(s[0] == tg.P for s in signatures) != spec['p']:
        raise ValueError('Native low-Vt N / regular P counts changed')
    return sorted(signatures)


def schematic(text, spec):
    if text.count('.subckt '+spec['old']+' ') != 1 or text.count('.subckt '+spec['core']+' ') != 1:
        raise ValueError('Require original native hierarchical component source')
    return text.replace(REGULAR_N, tg.N).replace(HVT_P, tg.P).replace(spec['core'], spec['name']+'_core').replace(spec['old'], spec['name'])


def mask_audit(reference, candidate, spec):
    import klayout.db as db
    a, ca, before = masktools.masks(reference, spec['old'])
    b, _, after = masktools.masks(candidate, spec['name'])
    expected = implant(a, ca)
    if a.dbu != b.dbu or MARKER in before or expected.is_empty():
        raise ValueError('Require fresh low-Vt marker at unchanged geometry scale')
    if not (after.get(MARKER, db.Region()) ^ expected).is_empty() or HVT in after:
        raise ValueError('Low-Vt marker enclosure or HVT removal differs from the native recipe')
    for key in set(before) | set(after):
        if key not in (MARKER, HVT) and not (before.get(key, db.Region()) ^ after.get(key, db.Region())).is_empty():
            raise ValueError('Low-Vt data component changed a non-implant mask')
    if (HVT in before) != (spec['mim'] == 0):
        raise ValueError('Unexpected original PMOS implant flavor')
    return dict(nlvt_marker_area_um2=expected.area()*a.dbu**2,
                removed_hvtp_area_um2=before.get(HVT, db.Region()).area()*a.dbu**2,
                all_other_mask_regions_identical=True, native_channel_enclosure_um=.18)


def prepare(evidence, tg_evidence):
    import klayout.db as db
    paths, external = tg.native_evidence(evidence)
    ti = tgproof.bound(tg_evidence); tp = ROOT/ti['parent']
    external.update(tg.bound(tp)['external_files'])
    external[str(Path(db.__file__))] = sha(Path(db.__file__))
    external[str(Path(sys.executable))] = sha(Path(sys.executable))
    paths += [tg_evidence/'manifest.json', tg_evidence/'summary.json']
    paths += [ROOT/n for n in ti['inputs']]
    # Establish this exact marker construction against the generated native PCell.
    primitive = tp/'stacked_n168_nlvt_v27.gds'
    layout = db.Layout(); layout.read(str(primitive)); cell = layout.top_cell()
    if not (region(layout, cell, MARKER) ^ implant(layout, cell)).is_empty():
        raise ValueError('Native NMOS-LVT PCell does not match the proposed implant recipe')
    paths.append(primitive)
    candidates = list({p for p in paths if p.suffix == '.gds'})
    components = {}
    for profile, spec in SPECS.items():
        matches = [p for p in candidates if p.name == spec['old']+'.gds']
        if len(matches) != 1:
            raise ValueError('Require exactly one bound original component GDS')
        gds = matches[0]; folder = gds.parent
        if profile == 'inv3':
            metadata = folder/'manifest.json'
            ports = json.loads(metadata.read_text())['identity']['ports']
        else:
            metadata = folder.parent/'summary.json'
            row = next(r for r in json.loads(metadata.read_text())['rows'] if r['macro'] == spec['old'])
            if not row['passed'] or row['drc_count'] != '0' or not row['lvs_passed']:
                raise ValueError('Original buffer physical proof failed')
            ports = row['ports']
        source = folder/(spec['old']+'.sch.spice'); native = folder/(spec['old']+'.lvs.spice')
        native_signature(native.read_text(), spec, True)
        paths += [gds, source, native, metadata]
        components[profile] = dict(reference=str(gds.relative_to(ROOT)), source=str(source.relative_to(ROOT)),
                                    native=str(native.relative_to(ROOT)), ports=ports)
    code = sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                   if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)), tg_evidence=str(tg_evidence.relative_to(ROOT)),
                    components=components, specs=SPECS, inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
                    code={str(p.relative_to(ROOT)): sha(p) for p in code}, external_files=external,
                    tools=tg.primitives.environment.tools())
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out/'manifest.json').write_text(json.dumps(dict(identity=identity, qualified_phy=False), indent=2)+'\n')
    for profile, spec in SPECS.items():
        folder = out/profile; folder.mkdir()
        (folder/(spec['name']+'.sch.spice')).write_text(schematic((ROOT/components[profile]['source']).read_text(), spec))
    return out


def bound(out):
    i = json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION or i['specs'] != SPECS
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in {**i['inputs'], **i['code']}.items())
            or any(sha(Path(n)) != h for n, h in i['external_files'].items())
            or tg.primitives.environment.tools() != i['tools']):
        raise ValueError('Low-Vt physical data-component context changed')
    for profile, spec in SPECS.items():
        if (out/profile/(spec['name']+'.sch.spice')).read_text() != schematic((ROOT/i['components'][profile]['source']).read_text(), spec):
            raise ValueError('Low-Vt data-component source changed')
    return i


def build_component(out, profile, spec, info):
    import klayout.db as db
    folder = out/profile; name = spec['name']; reference = ROOT/info['reference']
    layout, cell, _ = masktools.masks(reference, spec['old'])
    marker = layout.layer(*MARKER); hvt = layout.find_layer(*HVT)
    # Work in each child's own coordinates. Preserve hierarchy and label scope.
    for child in list(layout.each_cell()):
        local = db.Region(child.shapes(layout.layer(66, 20)))
        local &= db.Region(child.shapes(layout.layer(65, 20)))
        local &= db.Region(child.shapes(layout.layer(93, 44)))
        if not local.is_empty():
            child.shapes(marker).insert(local.sized(round(.18/layout.dbu)).merged())
        if hvt is not None:
            child.shapes(hvt).clear()
    core = layout.cell(spec['core'])
    if core is None:
        raise ValueError('Original native component core is missing')
    core.name = name+'_core'; cell.name = name
    options = db.SaveLayoutOptions(); options.select_cell(cell.cell_index())
    layout.write(str(folder/(name+'.candidate.gds')), options)
    comparison = mask_audit(reference, folder/(name+'.candidate.gds'), spec)
    commands = ['gds readonly false', f'gds read {name}.candidate.gds']
    for child in layout.each_cell():
        commands += [f'load {child.name}', f'save {child.name}']
    commands += [f'load {name}']
    for index, pin in enumerate(info['ports'].values(), 1):
        x, y = pin['x_um'], pin['y_um']
        commands += [f'box values {x-.1}um {y-.1}um {x+.1}um {y+.1}um', f'port make {index}']
    commands += [f'save {name}']
    tg.layout.invoke_magic(folder, '\n'.join(commands), 'import_candidate')
    physical = tg.layout.qualify(folder, name)
    (folder/'physical.json').write_text(json.dumps(physical, indent=2)+'\n')
    if not physical['passed'] or mask_audit(reference, folder/(name+'.gds'), spec) != comparison:
        raise ValueError('Low-Vt physical DRC/LVS or mask round trip failed; retain evidence')
    if native_signature((ROOT/info['native']).read_text(), spec, True) != native_signature((folder/(name+'.lvs.spice')).read_text(), spec):
        raise ValueError('Low-Vt data-component junction geometry changed')
    digest = hashlib.sha256((folder/(name+'.gds')).read_bytes()+Path(tg.extraction.__file__).read_bytes()).hexdigest()[:16]
    if (ROOT/'build/extracted'/digest/name).exists():
        raise ValueError('Retain existing low-Vt component RC extraction')
    rc = tg.extraction.extract(name, folder/(name+'.gds'), sha(out/'manifest.json'),
                               ports=info['ports'], source_scope=sha(folder/(name+'.sch.spice')))
    (folder/'extraction.json').write_text(json.dumps(rc, indent=2)+'\n')
    text = tg.checked_netlist(rc)
    if not tg.audit(text)['elementwise_passive_passed']:
        raise ValueError('Low-Vt data-component RC failed passivity')
    collapsed = folder/'wire_collapsed.spice'; collapsed.write_text(tg.collapse(text))
    setup = tg.strict_setup(folder/'rc_setup.tcl', Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/netgen/sky130A_setup.tcl')
    log = folder/'rc_lvs.log'
    p = subprocess.run(['netgen', '-batch', 'lvs', f'{collapsed} {name}', f'{folder/(name+".sch.spice")} {name}', str(setup), str(log)], cwd=folder, capture_output=True, text=True)
    (folder/'rc_console.log').write_text(p.stdout+p.stderr)
    if not tg.clean_match(log.read_text() if log.exists() else '', p.returncode):
        raise ValueError('Low-Vt component RC topology failed strict LVS')
    return dict(profile=profile, physical=physical, mask_comparison=comparison, extraction=rc,
                native_geometry_preserved=True, rc_topology_passed=True, component_physical_rc_passed=True,
                electrical_qualification_passed=False, qualified_phy=False)


def run(out):
    i = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain existing or partial low-Vt component campaign')
        (out/'state.json').write_text('{"status":"building","qualified_phy":false}\n')
        rows = []
        for profile, spec in SPECS.items():
            row = build_component(out, profile, spec, i['components'][profile]); rows.append(row)
            (out/profile/'summary.json').write_text(json.dumps(row, indent=2)+'\n')
        bound(out)
        result = dict(rows=rows, component_physical_rc_passed=True, qualified_phy=False,
                      electrical_qualification_passed=False,
                      scope='Only native LVT-N implant addition and buffer HVT-P removal; unchanged other masks, dimensions and junctions, strict LVS and fresh passive component RC; no bank timing or PHY qualification')
        result['files'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*') if p.is_file() and p.name not in ('.execution.lock', 'state.json')}
        (out/'summary.json').write_text(json.dumps(result, indent=2)+'\n')
        (out/'state.json').write_text('{"status":"complete","passed":true,"qualified_phy":false}\n')
        return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run', 'campaign']); p.add_argument('artifact', type=Path)
    p.add_argument('--tg-evidence', type=Path)
    a = p.parse_args(); out = a.artifact.resolve()
    if a.action in ('prepare', 'campaign'):
        if a.tg_evidence is None: p.error('--tg-evidence is required')
        out = prepare(out, a.tg_evidence.resolve()); print(out, flush=True)
    if a.action in ('run', 'campaign'):
        print(run(out), flush=True)
