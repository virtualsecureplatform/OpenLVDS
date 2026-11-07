#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Route the actual qualified P10/N8 -> P20/N16 REQUEST-buffer component."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import sys
import klayout.db as db
import build_tapered_fine_driver_v308 as small
import build_discharge_fine_driver_v218 as large
import build_parallel_output_cell_v111 as proof
import native_bank_inventory_v51 as inventory
import layout

ROOT = small.ROOT
NAME = 'openlvds_request_taper_buffer_v323'
PORTS = ['A', 'X', 'VGND', 'VPWR']
VERSION = 'qualified-p10n8-p20n16-native-request-buffer-layout-v323.1'
CONTEXT = 'request_taper_buffer_physical_v323'
STAGES = (
    (small, 'tapered_fine_driver_physical_v308/e54a2292b8e29d55', dict(p_fingers=10, n_fingers=8)),
    (large, 'discharge_fine_driver_physical_v218/e9cdc083fc9a84bc', dict(p_fingers=20, n_fingers=16)),
)
LAYERS = {'metal3': (70, 20), 'metal4': (71, 20)}
SCOPE = ('Actual two-master P10/N8 then P20/N16 positive REQUEST-buffer layout; '
         'existing native masks/junctions preserved, new M3 supplies/M4 interstage wire; '
         'component DRC/LVS only, no counter timing/shared RC/SS40/PVT/DCC/PHY admission')
atomic = small.atomic


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024*1024):
            digest.update(block)
    return digest.hexdigest()


def materials():
    rows, paths, external = [], [], {}
    for producer, context, spec in STAGES:
        parent = ROOT/'build/diagnostics'/context
        manifest = producer.bound(parent)
        identity = manifest['identity']
        report = json.loads((parent/'summary.json').read_text())
        if (json.loads((parent/'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
                or report.get('passed') is not True):
            raise ValueError('Require complete passing native inverter layouts')
        selected = [r for r in report['rows'] if r['spec'] == spec]
        if len(selected) != 1:
            raise ValueError('Qualified REQUEST stage selection changed')
        row = selected[0]
        folder = parent/row['macro']
        if (row['drc_count'] != '0' or row['lvs_passed'] is not True or row['native_inventory_passed'] is not True
                or any(sha(folder/n) != h for n, h in row['files'].items())
                or sha(ROOT/row['gds']) != row['gds_sha256']):
            raise ValueError('Qualified REQUEST stage geometry/evidence changed')
        lib = db.Layout()
        lib.read(str(ROOT/row['gds']))
        cell = lib.cell(row['macro'])
        if cell is None:
            raise ValueError('Missing qualified native stage GDS master')
        box = cell.bbox()
        reference = folder/(row['macro']+'.lvs.spice')
        rows.append(dict(macro=row['macro'], spec=spec, gds=row['gds'], ports=row['ports'],
            reference=str(reference.relative_to(ROOT)), dbu=lib.dbu,
            bbox_um=[v*lib.dbu for v in (box.left, box.bottom, box.right, box.top)]))
        paths += [parent/n for n in ('manifest.json', 'summary.json', 'state.json')]
        paths += [folder/'summary.json', *[folder/n for n in row['files']], *[ROOT/n for n in identity['inputs']]]
        external.update(identity['external_files'])
    return rows, paths, external


def cold_evidence():
    paths = []
    for number, stamp in ((0, '20261107T010347Z'), (1, '20261107T014342Z')):
        file = ROOT/'build/reports/request_taper_native_replay'/stamp/'summary.json'
        report = json.loads(file.read_text())
        rows = report['rows']
        if (report.get('analysis_completed') is not True or report.get('all_original_native_metrics_reproduced') is not True
                or len(rows) != 1 or rows[0]['native_mos'] != 808
                or rows[0]['case'] != 'build/diagnostics/request_taper_counter_v317/a9021aae03b1ad1c/'+str(number)
                or rows[0]['task']['spec']['stop_level'] != number
                or rows[0]['recorded_gates'].get('hypothesis_point_checks_passed') is not True
                or any(sha(ROOT/n) != h for n, h in report['inputs'].items())):
            raise ValueError('Require both independently replayed SS0 REQUEST-taper points')
        paths += [file, *[ROOT/n for n in report['inputs']]]
    return paths


def design(rows):
    if len(rows) != 2 or [r['spec'] for r in rows] != [r[2] for r in STAGES] or rows[0]['dbu'] != rows[1]['dbu']:
        raise ValueError('Require exact ordered qualified REQUEST stage masters')
    for row in rows:
        if list(row['ports']) != ['A', 'Y', 'VGND', 'VPWR']:
            raise ValueError('Qualified native stage port order changed')
        for pin, layer in (('A', 'metal4'), ('Y', 'metal4'), ('VGND', 'metal3'), ('VPWR', 'metal3')):
            if row['ports'][pin]['layer'] != layer:
                raise ValueError('Qualified native stage access layer changed')
    snap = lambda value: round(value/layout.GRID)*layout.GRID
    a, b = rows
    first = [snap(2-a['bbox_um'][0]), snap(2-a['bbox_um'][1])]
    second = [snap(first[0]+a['bbox_um'][2]+8-b['bbox_um'][0]), snap(2-b['bbox_um'][1])]
    positions = [first, second]
    def point(k, pin):
        return [snap(positions[k][0]+rows[k]['ports'][pin]['x_um']),
                snap(positions[k][1]+rows[k]['ports'][pin]['y_um'])]
    bus = snap(max(positions[k][1]+rows[k]['bbox_um'][3] for k in (0, 1))+2)
    routes = []
    def wire(net, layer, a, b, width):
        if a[0] != b[0] and a[1] != b[1]:
            raise ValueError('Non-Manhattan REQUEST route')
        routes.append(dict(net=net, layer=layer,
            rect=[snap(min(a[0], b[0])-width/2), snap(min(a[1], b[1])-width/2),
                  snap(max(a[0], b[0])+width/2), snap(max(a[1], b[1])+width/2)]))
    y, x = point(0, 'Y'), point(1, 'A')
    wire('internal_b', 'metal4', y, [y[0], bus], .6)
    wire('internal_b', 'metal4', [y[0], bus], [x[0], bus], .6)
    wire('internal_b', 'metal4', [x[0], bus], x, .6)
    for supply in ('VGND', 'VPWR'):
        a, b = point(0, supply), point(1, supply)
        if a[1] != b[1]:
            raise ValueError('Qualified REQUEST supply rows no longer align')
        wire(supply, 'metal3', a, b, .8)
    ports = {}
    for public, k, pin in (('A', 0, 'A'), ('X', 1, 'Y'), ('VGND', 0, 'VGND'), ('VPWR', 0, 'VPWR')):
        x, y = point(k, pin)
        ports[public] = dict(rows[k]['ports'][pin], x_um=x, y_um=y)
    return dict(placements=positions, ports=ports, routes=routes, interstage_route_y_um=bus,
                input_to_output_polarity='noninverting', local_rc_qualified=False, qualified_phy=False)


def reference(rows):
    text = '\n'.join((ROOT/r['reference']).read_text() for r in rows)
    body = ['.subckt '+NAME+' '+' '.join(PORTS),
        'Xrestore0 A internal_b VGND VPWR '+rows[0]['macro']+'_flat',
        'Xrestore1 internal_b X VGND VPWR '+rows[1]['macro']+'_flat', '.ends '+NAME]
    ports, devices = layout.flatten(layout.circuits(text+'\n'+'\n'.join(body)+'\n'), NAME)
    if (len(devices) != 56 or sum('fet_' in d['model'] for d in devices) != 54
            or sum('cap_mim' in d['model'] for d in devices) != 2):
        raise ValueError('REQUEST-buffer native reference inventory changed')
    return layout.schematic_text(NAME, ports, devices)


def prepare():
    rows, paths, external = materials()
    paths += cold_evidence()
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, stages=rows, plan=design(rows), reference=reference(rows),
        inputs={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))},
        external_files=external, tools=small.primitive.environment.tools(), scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    atomic(out/'manifest.json', dict(identity=identity, qualified_phy=False))
    return out


def bound(out):
    identity = json.loads((out/'manifest.json').read_text())['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or identity['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or any(sha(ROOT/n) != h for n, h in identity['inputs'].items())
            or any(sha(Path(n)) != h for n, h in identity['external_files'].items())
            or identity['tools'] != small.primitive.environment.tools()
            or identity['plan'] != design(identity['stages']) or identity['reference'] != reference(identity['stages'])):
        raise ValueError('Native REQUEST-buffer physical context changed')
    return identity


def masks_equal(a, ca, b, cb):
    if a.dbu != b.dbu:
        raise ValueError('Native GDS database unit changed')
    layers = {(a.get_info(i).layer, a.get_info(i).datatype) for i in a.layer_indices()}
    layers |= {(b.get_info(i).layer, b.get_info(i).datatype) for i in b.layer_indices()}
    for layer in layers:
        ra = db.Region(ca.begin_shapes_rec(a.layer(*layer)))
        rb = db.Region(cb.begin_shapes_rec(b.layer(*layer)))
        if not (ra ^ rb).is_empty():
            raise ValueError('Qualified native master masks changed: '+str(layer))
    return dict(all_native_masks_identical=True, checked_layers=len(layers))


def draw(folder, rows, plan):
    lib = db.Layout()
    lib.dbu = rows[0]['dbu']
    root = lib.create_cell(NAME)
    for k, row in enumerate(rows):
        old = db.Layout()
        old.read(str(ROOT/row['gds']))
        master = lib.create_cell(row['macro'])
        master.copy_tree(old.cell(row['macro']))
        x, y = plan['placements'][k]
        root.insert(db.CellInstArray(master.cell_index(), db.Trans(round(x/lib.dbu), round(y/lib.dbu))))
    for route in plan['routes']:
        root.shapes(lib.layer(*LAYERS[route['layer']])).insert(db.Box(*[round(v/lib.dbu) for v in route['rect']]))
    for name in PORTS:
        port = plan['ports'][name]
        layer = LAYERS[port['layer']]
        x, y, width = port['x_um'], port['y_um'], port['width_um']
        root.shapes(lib.layer(*layer)).insert(db.Box(*[round(v/lib.dbu) for v in (x-width/2, y-width/2, x+width/2, y+width/2)]))
        root.shapes(lib.layer(layer[0], 5)).insert(db.Text(name, db.Trans(round(x/lib.dbu), round(y/lib.dbu))))
    path = folder/(NAME+'.gds')
    options = db.SaveLayoutOptions()
    options.select_cell(root.cell_index())
    lib.write(str(path), options)
    return path


def native_witness(path, rows, plan):
    lib = db.Layout()
    lib.read(str(path))
    root = lib.cell(NAME)
    actual = sorted((i.cell.name, i.trans.disp.x, i.trans.disp.y) for i in root.each_inst())
    expected = sorted((r['macro'], round(p[0]/lib.dbu), round(p[1]/lib.dbu))
                      for r, p in zip(rows, plan['placements']))
    if actual != expected:
        raise ValueError('REQUEST native stage placements changed')
    witnesses = []
    for row in rows:
        old = db.Layout()
        old.read(str(ROOT/row['gds']))
        witnesses.append(dict(macro=row['macro'], **masks_equal(old, old.cell(row['macro']), lib, lib.cell(row['macro']))))
    return dict(all_qualified_stage_masks_preserved=True, exact_stage_placements_verified=True, stages=witnesses)


def run(out):
    identity = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain previous or partial REQUEST-buffer geometry')
        atomic(out/'state.json', dict(status='routing', qualified_phy=False))
        try:
            folder = out/'component'
            folder.mkdir()
            file = draw(folder, identity['stages'], identity['plan'])
            atomic(folder/'original_native_witness.json', native_witness(file, identity['stages'], identity['plan']))
            graph = dict(top=NAME, ports=PORTS)
            ports = {n: dict(layer=p['layer'], rect=[p['x_um']-p['width_um']/2, p['y_um']-p['width_um']/2,
                     p['x_um']+p['width_um']/2, p['y_um']+p['width_um']/2]) for n, p in identity['plan']['ports'].items()}
            physical, parameters = proof.qualify(folder, file, graph, dict(ports=ports), identity['reference'])
            if parameters['native_primitives'] != 56 or parameters['newly_characterized_junction_devices'] != 0:
                raise ValueError('Qualified native REQUEST junction inventory changed')
            final = ROOT/physical['gds']
            witness = native_witness(final, identity['stages'], identity['plan'])
            lef = final.with_suffix('.lef')
            raw = lef.with_suffix('.raw.lef')
            raw.write_bytes(lef.read_bytes())
            types = dict(A=('INPUT', 'SIGNAL'), X=('OUTPUT', 'SIGNAL'),
                         VGND=('INOUT', 'GROUND'), VPWR=('INOUT', 'POWER'))
            text, pins = small.access.restrict(raw.read_text(), identity['plan']['ports'], types)
            lef.write_text(text)
            bound(out)
            report = dict(physical=physical, native_parameters=parameters, native_master_witness=witness,
                native_mos=54, native_mims=2, ports=identity['plan']['ports'], integration_pins=pins,
                gds_sha256=sha(final), lef_sha256=sha(lef), request_buffer_physical_passed=True,
                local_rc_qualified=False, counter_timing_qualified=False, qualified_phy=False, scope=SCOPE)
            report['files'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*')
                if p.is_file() and p.name not in ('state.json', '.execution.lock')}
            atomic(out/'summary.json', report)
            atomic(out/'state.json', dict(status='complete', passed=True, qualified_phy=False))
        except Exception as error:
            atomic(out/'state.json', dict(status='failed', error=str(error), qualified_phy=False))
            raise
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'campaign'))
    parser.add_argument('artifact', type=Path, nargs='?')
    args = parser.parse_args()
    if (args.action == 'run') != (args.artifact is not None):
        parser.error('run requires the prepared artifact; prepare/campaign take no artifact')
    artifact = args.artifact.resolve() if args.action == 'run' else prepare()
    print(artifact, flush=True)
    if args.action in ('run', 'campaign'):
        print(run(artifact), flush=True)
