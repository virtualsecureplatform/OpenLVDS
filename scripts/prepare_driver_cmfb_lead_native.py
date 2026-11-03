#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Native core/bias pilots bound explicitly to the compensated source campaign."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path

import assemble_driver_compact_native as assembly
import build_driver_cmfb_lead as physical
import observe_compact_driver_loop as observation
import prepare_driver_complete_native_pilot as complete
import probe_driver_compact_native as pilot
from layout import circuits, flatten
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
sha = assembly.sha


def selected_source(layout_report, schematic):
    identity = layout_report['identity']
    if not all(n in identity for n in ['source_readiness', 'source']):
        raise ValueError('Require explicit compensated source selection in the physical producer')
    source, ready = physical.source_ready(ROOT / identity['source_readiness'])
    if str(source.relative_to(ROOT)) != identity['source']:
        raise ValueError('Compensated physical/source campaign binding changed')
    model = (source / 'tt_25_negative_op/source.spice').read_text()
    if (schematic != model or hashlib.sha256(model.encode()).hexdigest() !=
            layout_report['source_sha256'] or sha(source / 'tt_25_negative_op/source.spice') != ready['source_sha256']):
        raise ValueError('Physical assembly and complete compensated source circuit differ')
    return source, ready


def lead_target(source, placements):
    name = assembly.TOP + '__XCM__XCMFB_RZ0'
    devices = {d['name']: d for d in flatten(circuits(source), assembly.TOP)[1]}
    matches = [p for p in placements if name in p['members']]
    expected = assembly.TOP + '__XCM__CMFB_LEAD_C'
    if (name not in devices or len(matches) != 1 or devices[name]['nodes'][1] != expected
            or devices[name]['model'] != 'sky130_fd_pr__res_high_po_0p35'):
        raise ValueError('Require the original source-identified compensation resistor plate')
    return {'CMFB_LEAD_C': dict(physical_pin=matches[0]['instance'] + '.R2',
        source_net=expected, members=[name])}


def prepare(assembled):
    if pilot.engine() != 'ngspice':
        raise ValueError('Use the pinned ngspice runtime')
    if not assembled.is_relative_to(ROOT / 'build/diagnostics/driver_compact_native_library'):
        raise ValueError('Require the audited compensated core/bias assembly')
    a = json.loads((assembled / 'summary.json').read_text())
    extraction = ROOT / a['identity']['extraction']
    if (a.get('assembly_complete') is not True or a.get('component_reference_count') != 1
            or a.get('two_core_endpoint_reference_count') != 1
            or any(sha(assembled / n) != h for n, h in a['files'].items())
            or assembly.assemble(extraction) != assembled):
        raise ValueError('Require complete unchanged native core/bias assembly')
    r = json.loads((extraction / 'summary.json').read_text())
    layout = ROOT / r['identity']['parent']
    p = json.loads((layout / 'summary.json').read_text())
    schematic = (assembled / 'schematic.spice').read_text()
    source, ready = selected_source(p, schematic)
    model = (assembled / 'native.spice').read_text()
    placements = p['designs'][assembly.TOP]['placements']
    targets = complete.analog_targets(schematic, placements)
    targets.update(lead_target(schematic, placements))
    extra = assembly.observations((assembled / 'observation_flat.ext').read_text(),
        assembly.text_block(model, assembly.TOP), targets)
    observations = dict(a['observations'], **extra)
    inputs = {**a['identity']['inputs'], **ready['proofs']}
    inputs.update({str((assembled / n).relative_to(ROOT)): h for n, h in a['files'].items()})
    tasks = [dict(id=f'{corner}_{temp}_{op}', process=corner, temperature=temp, op=op)
        for corner, temp in pilot.POINTS for op in pilot.reference.shape.CASES]
    paths = [assembled / 'summary.json', extraction / 'summary.json', layout / 'summary.json',
        ROOT / p['identity']['source_readiness'], ROOT / 'requirements.json']
    paths += [source / t['id'] / n for t in tasks for n in ['source.spice', 'bench.cir']]
    inputs.update({str(path.relative_to(ROOT)): sha(path) for path in paths})
    code = dict(a['identity']['code'])
    code.update({n: sha(ROOT / 'scripts' / n) for n in set(pilot.CODE + [
        Path(__file__).name, 'build_driver_cmfb_lead.py', 'qualify_driver_cmfb_lead_source.py',
        'probe_driver_cmfb_lead.py', 'prepare_driver_complete_native_pilot.py',
        'observe_compact_driver_loop.py', 'driver_native_stress.py'])})
    identity = dict(extraction=str(extraction.relative_to(ROOT)), source=str(source.relative_to(ROOT)),
        source_readiness=p['identity']['source_readiness'], assembly=str(assembled.relative_to(ROOT)),
        points=[list(point) for point in pilot.POINTS], inputs=inputs, code=code,
        simulator=pilot.provenance(), view='native_core_and_native_bias', scope=
        'Six actual lead-compensated native core-plus-native-bias pilots at TT25/SS25/FF40, '
        'both initial polarities, explicitly selected from the independently verified '
        'full compensated source campaign. Fresh source/GDS and RC audit for the new '
        'circuit; one shared reference per endpoint. Original 80 ns/1 ps fixed-rail '
        '100 ohm/2 pF-per-pin fixtures. All 305 actual MOS terminal voltages plus '
        'source-identified CMFB/sense/lead-capacitor conductors recorded without '
        'ideal aliases. Public waveform checks use the existing native pilot runner. '
        'No long-component, reliability, all-PVT native or PHY admission.')
    out = ROOT / 'build/diagnostics/driver_compact_native_pilot' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        for task in tasks:
            old = source / task['id']
            folder = out / task['id']
            folder.mkdir(exist_ok=True)
            public = pilot.fixture((old / 'bench.cir').read_text(), old, folder)
            deck, probes, mos = observation.fixture(public, folder, folder, model, observations)
            for name, body in [('source.spice', model), ('bench.cir', deck),
                    ('probes.json', json.dumps(probes, sort_keys=True, indent=2) + '\n'),
                    ('mos_observations.json', json.dumps(mos, sort_keys=True, indent=2) + '\n')]:
                path = folder / name
                if path.exists() and path.read_text() != body:
                    raise ValueError('Prepared compensated native pilot changed')
                if not path.exists():
                    path.write_text(body)
            task['files'] = {n: sha(folder / n) for n in [
                'source.spice', 'bench.cir', 'probes.json', 'mos_observations.json']}
        capture_manifest(out / 'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('assembly', type=Path)
    args = p.parse_args()
    print(prepare(args.assembly.resolve()), flush=True)
