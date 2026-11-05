#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Measure native-terminal crossing bands without inferring passive-node traces.

TG RC separates public tap/tree nodes from all native terminals. The fixture
need not save those passive nodes for its numerical/voltage gate. Diagnose
only actual saved terminals; do not label their crossing bands as public-net
delay or reconstruct an unsaved waveform.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import probe_tg_component_bank_v23 as pilot
import verify_tg_component_bank_v23 as proof
from uniform_tree_parasitic_isolation_v4 import isolate
from native_binary_raw_v2 import validate
from probe_dcdl_uniform_tree_v3 import crossings

ROOT = pilot.ROOT
VERSION = 'saved-native-terminal-only-tg-bank-path-crossing-bands-v24.1'
CONTEXT = 'tg_component_path_diagnosis_v24'


def terminal_group(cells, bank, devices, tag, port, indices):
    defs = pilot.helper.circuit.native.definitions(bank)
    if len(defs) != 1:
        raise ValueError('Require one native bank')
    _, body = next(iter(defs.values()))
    matches = [w for w in body if w[0] == tag]
    if len(matches) != 1:
        raise ValueError('Missing or duplicate selected-path instance')
    model = matches[0][-1]
    component = pilot.helper.cell_definition(cells, model)
    _, report = isolate(component, model)
    ports, instances = pilot.helper.circuit.native.definitions(component)[model]
    if port not in ports:
        raise ValueError('Unknown component path port')
    mapped = {d['name']: d for d in devices}; terminals = set()
    for w in instances:
        if not w[0].startswith('X'):
            continue
        end = next((i for i, token in enumerate(w) if '=' in token), len(w))
        if end != 6 or not ('nfet_' in w[end-1] or 'pfet_' in w[end-1]):
            continue
        device = mapped.get('XD:'+tag+':'+w[0])
        if device is None or device['model'] != w[end-1]:
            raise ValueError('Selected native-terminal census changed')
        for index in indices:
            if report['wire_aliases'].get(w[1+index]) == port:
                terminals.add(device['terminals'][index])
    if not terminals:
        raise ValueError('No actual native terminal at the selected port')
    return sorted(terminals)


def groups(cells, bank, devices):
    result = [('input', ['IN'], True)]
    for label, tag, port, indices, count in (
            ('input_driver_native_output', 'Xinput_inverse', 'Y', (0, 2), 16),
            ('first_tg_native_input', 'Xswitch0_0_0', 'A', (0, 2), 2),
            ('first_tg_native_output', 'Xswitch0_0_0', 'Z', (0, 2), 2),
            ('root_tg_native_input', 'Xswitch1_0_0', 'A', (0, 2), 2),
            ('root_tg_native_output', 'Xswitch1_0_0', 'Z', (0, 2), 2),
            ('fine_driver_native_input', 'Xfine_driver', 'A', (1,), 16),
            ('fine_driver_native_output', 'Xfine_driver', 'Y', (0, 2), 16)):
        nodes = terminal_group(cells, bank, devices, tag, port, indices)
        if len(nodes) != count:
            raise ValueError('Native terminal band lost a finger or selected TG terminal')
        result.append((label, nodes, label == 'fine_driver_native_output'))
    return result+[('output', ['OUT'], True)]


def measure(folder, selected):
    def column(n):
        return 'v('+n.replace(':', '.').lower()+')'
    names, w = validate(folder/'bench.raw', {column(n) for _, nodes, _ in selected for n in nodes}, 20e-9)
    idx = {n: i for i, n in enumerate(names)}; t = w[:, idx['time']]*1e12
    if t[0] > 1e-6:
        raise ValueError('Selected path trace omits startup')
    rows = []
    for pulse, base in enumerate((0, 10000)):
        window = (t >= base) & (t <= base+10000)
        for up, edge in ((True, 'rise'), (False, 'fall')):
            bands = []
            for label, nodes, same in selected:
                measured = []
                for node in nodes:
                    points = crossings(t[window], w[window, idx[column(node)]], up if same else not up)
                    if len(points) != 1:
                        raise ValueError('Missing/extra actual native-terminal crossing')
                    measured.append(dict(node=node, crossing_ps=float(points[0])))
                bands.append(dict(group=label, earliest_ps=min(x['crossing_ps'] for x in measured),
                                  latest_ps=max(x['crossing_ps'] for x in measured), terminals=measured))
            intervals = [dict(start=a['group'], end=b['group'],
                              minimum_delay_ps=b['earliest_ps']-a['latest_ps'],
                              maximum_delay_ps=b['latest_ps']-a['earliest_ps']) for a, b in zip(bands, bands[1:])]
            rows.append(dict(pulse=pulse, edge=edge, bands=bands, native_terminal_intervals=intervals,
                             public_input_to_output_delay_ps=bands[-1]['earliest_ps']-bands[0]['earliest_ps']))
    return rows


def diagnose(evidence):
    receipt = json.loads((evidence/'summary.json').read_text()); binding = receipt['identity']
    parent = ROOT/binding['parent']
    if (evidence.parent != ROOT/'build/diagnostics'/proof.CONTEXT or binding['version'] != proof.VERSION
            or not receipt['all_declared_cases_consumed'] or proof.verify(parent) != evidence):
        raise ValueError('Require the independently rechecked complete two-case component-RC gate')
    m = pilot.bound(parent); rows = []; paths = [evidence/'summary.json', Path(__file__)]
    paths += [ROOT/n for n in binding['inputs']]
    for row in receipt['rows']:
        task = row['task']; spec = task['spec']; profile = spec['profile']
        if spec['coarse'] != 0 or spec['fine'] != 0:
            raise ValueError('This path diagnosis is explicitly zero-code only')
        cells = (parent/f'cells_{profile}.spice').read_text(); bank = (parent/f'bank_{profile}.spice').read_text()
        selected = groups(cells, bank, m['identity']['devices'][profile])
        measured = measure(parent/task['id'], selected)
        for r in measured:
            expected = row['result']['samples'][r['pulse']][r['edge']+'_delay_ps']
            if abs(r['public_input_to_output_delay_ps']-expected) > 1e-9:
                raise ValueError('Terminal path does not reproduce measured external propagation')
        rows.append(dict(task=task, measurements=measured))
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)),
                    inputs={str(p.relative_to(ROOT)): pilot.helper.sha(p) for p in paths})
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    report = dict(identity=identity, rows=rows, passive_node_waveforms_reconstructed=False,
                  only_saved_native_terminals_and_public_io_measured=True, qualified_phy=False,
                  scope='Measured native-terminal crossing bands/intervals only; no unsaved public tap/tree voltages inferred, no new circuit or PHY admission')
    if any(pilot.helper.sha(ROOT/n) != h for n, h in identity['inputs'].items()):
        raise ValueError('Native path evidence changed during measurement')
    if out.exists():
        if json.loads((out/'summary.json').read_text()) != report:
            raise ValueError('Existing native-terminal diagnosis changed')
    else:
        out.mkdir(parents=True); pilot.helper.atomic(out/'summary.json', report)
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    a = p.parse_args(); print(diagnose(a.artifact.resolve()), flush=True)
