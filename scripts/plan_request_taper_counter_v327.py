#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Fit qualified REQUEST/CLK buffers into the unchanged native counter plan.

Planning only: no counter geometry, RC, native timing or PHY admission.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import build_strong_storage_counter_v234 as routing
import build_repaired_clock_counter_v191 as assembly
import preflight_request_taper_counter_v326 as materials
from probe_digital_dcc_v2 import atomic

ROOT = materials.ROOT
VERSION = 'native-request-taper-counter-buffer-width-floorplan-v327.1'
CONTEXT = 'request_taper_counter_plan_v327'
PREFLIGHT = ROOT/'build/diagnostics/counter_buffer_material_preflight_v326/7654d308b75a4197'
sha = materials.sha


def overlaps(cells, macros, placements):
    boxes = {}
    for cell in cells:
        b = macros[cell['model']]['bbox']; p = placements[cell['name']]
        boxes[cell['name']] = [b[0]+p['x'], b[1]+p['y'], b[2]+p['x'], b[3]+p['y']]
    names = sorted(boxes)
    return [[a, b] for k, a in enumerate(names) for b in names[k+1:]
            if min(boxes[a][2], boxes[b][2]) > max(boxes[a][0], boxes[b][0])
            and min(boxes[a][3], boxes[b][3]) > max(boxes[a][1], boxes[b][1])]


def plan(cells, macros):
    if len(cells) != 22 or len({c['name'] for c in cells}) != 22:
        raise ValueError('Require unchanged 22 native counter roles')
    byname = {c['name']: c for c in cells}
    for role, model in materials.ROLES.items():
        net = 'REQUEST' if role.startswith('request') else 'RCLK'
        output = 'request_i' if role.startswith('request') else 'CLK'
        expected = dict(name=role, model=model, pins=dict(A=net, X=output, VGND='VGND', VPWR='VPWR'))
        if byname.get(role) != expected:
            raise ValueError('Actual native buffer role, polarity or public pins changed')
    # The old 24um corridor gives only 42.30um between buffer origins.
    # The qualified CLK buffer is 54.14um wide. Widen the corridor; retain
    # the original row, bus, direct-feedback and escape construction.
    configuration = dict(assembly.default_plan(), corridor_um=40.)
    result = routing.strong_plan(cells, macros, configuration)
    bad = overlaps(cells, macros, result['placements'])
    if bad:
        raise ValueError('Native macro footprints overlap: '+repr(bad))
    gaps = {}
    for role in ('request_driver', 'clock_driver'):
        first, second = byname[role], byname[role+'_parallel']
        a = result['placements'][role]; b = result['placements'][role+'_parallel']
        gap = b['x']+macros[second['model']]['bbox'][0]-a['x']-macros[first['model']]['bbox'][2]
        if gap <= 0:
            raise ValueError('Parallel native buffer footprints overlap')
        gaps[role] = gap
    return dict(result, parallel_buffer_footprint_gaps_um=gaps)


def bound_materials(preflight=PREFLIGHT):
    manifest = json.loads((preflight/'manifest.json').read_text()); identity = manifest['identity']
    report = json.loads((preflight/'summary.json').read_text())
    if (preflight.parent != ROOT/'build/diagnostics'/materials.CONTEXT
            or preflight.name != hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
            or identity['version'] != materials.VERSION
            or json.loads((preflight/'state.json').read_text()) != dict(status='complete', passed=True, qualified_phy=False)
            or report.get('counter_materials_compatible') is not True
            or report.get('strict_native_topology_equivalence_passed') is not True
            or any(sha(ROOT/n if not Path(n).is_absolute() else Path(n)) != h for n, h in identity['inputs'].items())
            or any(sha(preflight/n) != h for n, h in report['files'].items())):
        raise ValueError('Require unchanged complete native integration preflight')
    macros = deepcopy(identity['macros'])
    physicals = {materials.REQ: ROOT/'build/diagnostics/request_taper_buffer_physical_v323/8cfc7cf7b15b78c9',
                 materials.CLK: materials.CLOCK}
    for name, physical in physicals.items():
        if str((physical/'summary.json').relative_to(ROOT)) not in identity['inputs']:
            raise ValueError('Physical buffer is outside the captured native materials')
        r = json.loads((physical/'summary.json').read_text())
        row = dict(r['physical'], ports=r['ports'], macro=name,
                   gds_sha256=r['gds_sha256'], lef_sha256=r['lef_sha256'])
        macros[name] = assembly.macro(name, ROOT/macros[name]['folder'], row)
    return identity, deepcopy(identity['cells']), macros


def run():
    identity, cells, macros = bound_materials()
    old = routing.strong_plan(cells, macros, assembly.default_plan())
    previous_overlaps = overlaps(cells, macros, old['placements'])
    expected = [['clock_driver', 'clock_driver_parallel'], ['request_driver', 'request_driver_parallel']]
    if previous_overlaps != expected:
        raise ValueError('Require the measured original parallel-buffer footprint conflicts')
    proposed = plan(cells, macros)
    paths = [PREFLIGHT/n for n in ('manifest.json', 'summary.json', 'state.json')]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
        if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    inputs = {**identity['inputs'], **{str(p.relative_to(ROOT)):sha(p) for p in paths}}
    record = dict(version=VERSION, preflight=str(PREFLIGHT.relative_to(ROOT)),
                  cells=cells, macros=macros, inputs=inputs, plan=proposed)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    atomic(out/'manifest.json', dict(identity=record, qualified_phy=False))
    atomic(out/'summary.json', dict(previous_buffer_overlaps=previous_overlaps,
        macro_footprints_nonoverlapping=True, spine_clearance_checked=True,
        parallel_buffer_footprint_gaps_um=proposed['parallel_buffer_footprint_gaps_um'],
        native_geometry_built=False, whole_counter_shared_wire_rc_qualified=False,
        counter_timing_qualified=False, qualified_phy=False,
        scope='Actual native dimensions and deterministic placement/escape/spine plan only; final v317 timing gate still required before routing, no DRC/LVS/RC/PVT/PHY admission'))
    atomic(out/'state.json', dict(status='complete', planning_completed=True, qualified_phy=False))
    return out


if __name__ == '__main__':
    print(run(), flush=True)
