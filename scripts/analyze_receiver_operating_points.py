#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Analyze retained OP evidence without rerunning SPICE or altering its producer."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import receiver_operating_point_probe as probe
from receiver_static_diagnosis import capture_manifest


def measurements(folder, points):
    results = []
    for index, point in enumerate(points):
        names, wave = probe.read_raw(folder / f'point_{index}.raw')
        if wave.shape != (1, len(names)) or not np.isfinite(wave).all() or len(set(names)) != len(names):
            raise ValueError('Expected one finite operating point with unique vectors')
        values = dict(zip(names, wave[0]))
        # ngspice preserves units on user-defined vectors: current and voltage
        # aliases receive i(...) and v(...), conductances remain bare names.
        aliases = dict(id='i(tail_id)', gm='tail_gm', gds='tail_gds', vdsat='v(tail_vdsat)')
        tail = {}
        for field, alias in aliases.items():
            original = probe.TAIL + '[' + field + ']'
            if field == 'id': original = 'i(' + original + ')'
            if field == 'vdsat': original = 'v(' + original + ')'
            if alias not in values or original not in values or values[alias] != values[original]:
                raise ValueError('Missing or inconsistent model parameter: ' + field)
            tail[field] = float(values[alias])
        if any(abs(values['v(' + node + ')'] - point[node + '_v']) > 1e-8 for node in ['p', 'n']):
            raise ValueError('Operating point differs from original input')
        differences = {node: float(values['v(' + node.replace(':', '.').lower() + ')'] - point['expected']['V(' + node + ')'])
                       for node in probe.NODES}
        results.append(dict(time_ns=point['time_ns'], tail=tail,
            power=dict(rails_mw=float((-3.3 * values['i(vio)'] - 1.8 * values['i(vdig)']) * 1e3),
                       reference_mw=float(-1.2 * values['i(vref)'] * 1e3)),
            voltage_differences_from_transient_v=differences,
            waveform_sha256=probe.digest(folder / f'point_{index}.raw')))
    return results


def analyze(folder):
    if not folder.is_relative_to(probe.ROOT / 'build/diagnostics/receiver_operating_points'):
        raise ValueError('Use a retained operating-point context')
    manifest = json.loads((folder / 'manifest.json').read_text())
    identity = manifest['identity']
    if [p['time_ns'] for p in identity['points']] not in [[10, 130], list(range(10, 144, 12))]:
        raise ValueError('Expected original static sample points')
    def validate():
        if (probe.provenance() != identity['simulator_provenance'] or
            any(probe.digest(probe.ROOT / 'scripts' / name) != sha for name, sha in identity['code'].items()) or
            any(probe.digest(probe.ROOT / name) != sha for name, sha in identity['inputs'].items()) or
            any(probe.digest(folder / name) != sha for name, sha in manifest['files'].items())):
            raise ValueError('Operating-point source context changed')
        parent = probe.ROOT / identity['parent']
        if ((folder / 'source.spice').read_text() != (parent / 'source.spice').read_text() or
            (folder / 'bench.cir').read_text() != probe.operating_deck((parent / 'bench.cir').read_text(), parent, folder, identity['points'])):
            raise ValueError('Operating-point source fixture changed')
    validate()
    proofs = {name: probe.digest(folder / name) for name in ['manifest.json', 'ngspice.log', 'console.log'] +
              [f'point_{i}.raw' for i in range(len(identity['points']))]}
    receipt = dict(producer_sha256=probe.digest(Path(__file__)), proofs=proofs)
    results = measurements(folder, identity['points'])
    validate()
    if any(probe.digest(folder / name) != sha for name, sha in proofs.items()):
        raise ValueError('Operating-point evidence changed during analysis')
    key = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()[:16]
    out = folder / 'analysis' / key
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'manifest.json', receipt)
    capture_manifest(out / 'summary.json', dict(diagnostic_complete=True, qualified_phy=False, results=results,
        scope='Two or twelve original fixed-supply schematic static points; no native/dynamic/all-PVT qualification'))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    print(analyze(parser.parse_args().artifact.resolve()))
