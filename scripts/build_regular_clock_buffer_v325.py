#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Physical P20/N16 -> P20/N16 positive CLK buffer and complete local RC."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import klayout.db as db
import build_request_taper_buffer_v323 as support
import extract_native_flat_v4 as extractor

ROOT = support.ROOT
NAME = 'openlvds_regular_clock_buffer_v325'
MODEL = 'openlvds_discharge_p20n16_v218'
PORTS = ['A', 'X', 'VGND', 'VPWR']
VERSION = 'regular-p20n16-two-inverter-clk-buffer-native-layout-and-local-rc-v325.1'
CONTEXT = 'regular_clock_buffer_v325'
SCOPE = ('Two unchanged qualified P20/N16 masters with actual M3 supply and M4 interstage '
         'wires; native masks/parameters, DRC/LVS and complete passive/local RC proof only; '
         'no counter transient/shared-wire/SS40/PVT/DCC/PHY admission')
sha = support.sha
atomic = support.atomic
proof = support.proof


def design(row):
    if row['macro'] != MODEL or row['spec'] != dict(p_fingers=20, n_fingers=16):
        raise ValueError('Require the actual qualified regular P20/N16 clock stage')
    if list(row['ports']) != ['A', 'Y', 'VGND', 'VPWR']:
        raise ValueError('Clock stage public port order changed')
    for pin, layer in (('A', 'metal4'), ('Y', 'metal4'), ('VGND', 'metal3'), ('VPWR', 'metal3')):
        if row['ports'][pin]['layer'] != layer:
            raise ValueError('Qualified CLK stage access layer changed')
    snap = lambda value: round(value/support.layout.GRID)*support.layout.GRID
    box = row['bbox_um']
    first = [snap(2-box[0]), snap(2-box[1])]
    second = [snap(first[0]+box[2]+8-box[0]), first[1]]
    positions = [first, second]
    point = lambda k, pin: [snap(positions[k][0]+row['ports'][pin]['x_um']),
                            snap(positions[k][1]+row['ports'][pin]['y_um'])]
    height = snap(first[1]+box[3]+2)
    routes = []
    def wire(net, layer, a, b, width):
        if a[0] != b[0] and a[1] != b[1]:
            raise ValueError('Non-Manhattan CLK route')
        routes.append(dict(net=net, layer=layer,
            rect=[snap(min(a[0], b[0])-width/2), snap(min(a[1], b[1])-width/2),
                  snap(max(a[0], b[0])+width/2), snap(max(a[1], b[1])+width/2)]))
    a, b = point(0, 'Y'), point(1, 'A')
    wire('internal_b', 'metal4', a, [a[0], height], .6)
    wire('internal_b', 'metal4', [a[0], height], [b[0], height], .6)
    wire('internal_b', 'metal4', [b[0], height], b, .6)
    for supply in ('VGND', 'VPWR'):
        wire(supply, 'metal3', point(0, supply), point(1, supply), .8)
    ports = {}
    for public, k, pin in (('A', 0, 'A'), ('X', 1, 'Y'), ('VGND', 0, 'VGND'), ('VPWR', 0, 'VPWR')):
        x, y = point(k, pin)
        ports[public] = dict(row['ports'][pin], x_um=x, y_um=y)
    return dict(placements=positions, ports=ports, routes=routes, interstage_route_y_um=height,
                input_to_output_polarity='noninverting', qualified_phy=False)


def reference(row):
    source = (ROOT/row['reference']).read_text()
    model = MODEL+'_flat'
    wrapper = '\n'.join(['.subckt '+NAME+' '+' '.join(PORTS),
        'Xrestore0 A internal_b VGND VPWR '+model,
        'Xrestore1 internal_b X VGND VPWR '+model, '.ends '+NAME])
    ports, devices = support.layout.flatten(support.layout.circuits(source+'\n'+wrapper+'\n'), NAME)
    if (len(devices) != 74 or sum('fet_' in d['model'] for d in devices) != 72
            or sum('cap_mim' in d['model'] for d in devices) != 2):
        raise ValueError('Regular CLK buffer native reference inventory changed')
    return support.layout.schematic_text(NAME, ports, devices)


def prepare():
    rows, paths, external = support.materials()
    selected = [r for r in rows if r['macro'] == MODEL]
    if len(selected) != 1:
        raise ValueError('Missing qualified P20/N16 CLK stage')
    row = selected[0]
    paths += support.cold_evidence()
    paths += [ROOT/'scripts/exact_rc_candidate.py']
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    identity = dict(version=VERSION, stage=row, plan=design(row), reference=reference(row),
        inputs={str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}, external_files=external,
        tools=support.small.primitive.environment.tools(), math_runtime=proof.math_proof.math_proof()['runtime'], scope=SCOPE)
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
            or identity['tools'] != support.small.primitive.environment.tools()
            or identity['math_runtime'] != proof.math_proof.math_proof()['runtime']
            or identity['plan'] != design(identity['stage']) or identity['reference'] != reference(identity['stage'])):
        raise ValueError('Regular CLK buffer physical/RC context changed')
    return identity


def draw(folder, row, plan):
    lib = db.Layout()
    lib.dbu = row['dbu']
    root = lib.create_cell(NAME)
    old = db.Layout()
    old.read(str(ROOT/row['gds']))
    master = lib.create_cell(MODEL)
    master.copy_tree(old.cell(MODEL))
    # One actual native master, instantiated twice; never append its tree twice.
    for x, y in plan['placements']:
        root.insert(db.CellInstArray(master.cell_index(), db.Trans(round(x/lib.dbu), round(y/lib.dbu))))
    for route in plan['routes']:
        root.shapes(lib.layer(*support.LAYERS[route['layer']])).insert(db.Box(*[round(v/lib.dbu) for v in route['rect']]))
    for name in PORTS:
        p = plan['ports'][name]
        layer = support.LAYERS[p['layer']]
        x, y, w = p['x_um'], p['y_um'], p['width_um']
        root.shapes(lib.layer(*layer)).insert(db.Box(*[round(v/lib.dbu) for v in (x-w/2, y-w/2, x+w/2, y+w/2)]))
        root.shapes(lib.layer(layer[0], 5)).insert(db.Text(name, db.Trans(round(x/lib.dbu), round(y/lib.dbu))))
    file = folder/(NAME+'.gds')
    options = db.SaveLayoutOptions()
    options.select_cell(root.cell_index())
    lib.write(str(file), options)
    return file


def native_witness(file, row, plan):
    lib = db.Layout()
    lib.read(str(file))
    root = lib.cell(NAME)
    actual = sorted((i.cell.name, i.trans.disp.x, i.trans.disp.y) for i in root.each_inst())
    expected = sorted((MODEL, round(x/lib.dbu), round(y/lib.dbu)) for x, y in plan['placements'])
    if actual != expected:
        raise ValueError('Regular CLK buffer native placements changed')
    old = db.Layout()
    old.read(str(ROOT/row['gds']))
    witness = support.masks_equal(old, old.cell(MODEL), lib, lib.cell(MODEL))
    return dict(all_qualified_native_masks_preserved=True, exact_two_stage_placements_verified=True, mask_witness=witness)


def run(out):
    identity = bound(out)
    row, plan = identity['stage'], identity['plan']
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain previous or partial regular CLK buffer qualification')
        atomic(out/'state.json', dict(status='routing', qualified_phy=False))
        try:
            folder = out/'component'
            folder.mkdir()
            file = draw(folder, row, plan)
            atomic(folder/'original_native_witness.json', native_witness(file, row, plan))
            ports = {n: dict(layer=p['layer'], rect=[p['x_um']-p['width_um']/2, p['y_um']-p['width_um']/2,
                p['x_um']+p['width_um']/2, p['y_um']+p['width_um']/2]) for n, p in plan['ports'].items()}
            physical, parameters = proof.qualify(folder, file, dict(top=NAME, ports=PORTS), dict(ports=ports), identity['reference'])
            if parameters['native_primitives'] != 74 or parameters['newly_characterized_junction_devices'] != 0:
                raise ValueError('Original regular CLK stage native junctions changed')
            gds = ROOT/physical['gds']
            witness = native_witness(gds, row, plan)
            lef = gds.with_suffix('.lef')
            raw = lef.with_suffix('.raw.lef')
            raw.write_bytes(lef.read_bytes())
            types = dict(A=('INPUT', 'SIGNAL'), X=('OUTPUT', 'SIGNAL'), VGND=('INOUT', 'GROUND'), VPWR=('INOUT', 'POWER'))
            text, pins = support.small.access.restrict(raw.read_text(), plan['ports'], types)
            lef.write_text(text)
            atomic(out/'physical.json', dict(physical=physical, native_parameters=parameters,
                native_master_witness=witness, integration_pins=pins))
            digest = hashlib.sha256(gds.read_bytes()+Path(extractor.__file__).read_bytes()).hexdigest()[:16]
            if (ROOT/'build/extracted'/digest/NAME).exists():
                raise ValueError('Retain existing or partial regular CLK buffer extraction')
            atomic(out/'state.json', dict(status='extracting', qualified_phy=False))
            info = extractor.extract(NAME, gds, sha(out/'manifest.json'), ports=plan['ports'],
                source_scope=sha(gds.parent/(NAME+'.sch.spice')))
            atomic(out/'extraction.json', info)
            if not info['passed'] or info['ports_verified'] is not True or info['ports'] != PORTS:
                raise ValueError('Regular CLK buffer fresh extraction/interface failed')
            target = out/'proof'
            target.mkdir()
            rc = proof.certify(target, info, NAME, gds.parent/(NAME+'.lvs.spice'), 74)
            if rc['independent_terminal_current_witness']['runtime'] != identity['math_runtime']:
                raise ValueError('Independent regular CLK buffer math runtime changed')
            bound(out)
            report = dict(physical=physical, native_parameters=parameters, native_master_witness=witness,
                integration_pins=pins, ports=plan['ports'], extraction=info, rc_proof=rc,
                gds_sha256=sha(gds), lef_sha256=sha(lef), regular_clock_buffer_local_rc_qualified=True,
                native_mos=72, native_mims=2, actual_interstage_and_supply_rc_included=True,
                counter_timing_qualified=False, whole_counter_shared_wire_rc_qualified=False,
                all_pvt_covered=False, electrical_qualification_passed=False, qualified_phy=False, scope=SCOPE)
            report['files'] = {str(p.relative_to(out)): sha(p) for p in out.rglob('*')
                if p.is_file() and p.name not in ('state.json', '.execution.lock')}
            report['extracted_files'] = {info[k]: sha(ROOT/info[k]) for k in ('raw_netlist', 'netlist')}
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
