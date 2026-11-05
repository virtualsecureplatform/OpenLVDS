#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only matched complete zero-code RC/parasitic-isolation diagnosis.

The two campaigns may still be active on other cases. Only terminal case-zero
files are consumed, checked before/after; no campaign lock, solver or old state
is changed. This receipt cannot admit either architecture as a physical PHY.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import numpy as np
import probe_uniform_parasitic_v4 as isolated
import run_native_binary_v2 as runner
from native_binary_raw_v2 import validate

ROOT = isolated.ROOT
VERSION = 'matched-complete-native-uniform-zero-stage-delay-diagnosis-v4.1'
CONTEXT = 'uniform_zero_diagnosis_v4'
STAGES = ['IN', 'XD:tap0', 'XD:tree0_0', 'XD:selected', 'OUT']


def consume(parent, module):
    m = module.bound(parent); task = m['tasks'][0]; folder = parent/'0'
    row = json.loads((folder/'summary.json').read_text())
    required = {'bench.cir', 'bench.ngspice.cir', 'bench.raw', 'ngspice.log', 'console.log'}
    if (task['spec']['coarse'] != 0 or task['spec']['fine'] != 0 or row['task'] != task
            or row['error'] is not None or row['result'] is None or not required <= set(row['files'])
            or any(isolated.original.sha(folder/n) != h for n, h in row['files'].items())
            or (folder/'bench.ngspice.cir').read_text() != runner.translate((folder/'bench.cir').read_text())[0]):
        raise ValueError('Require unchanged complete numerical-error-free native zero-code case')
    log = (folder/'ngspice.log').read_text()
    counts = re.findall(r'No\. of Data Rows\s*:\s*(\d+)', log)
    requested = {'v('+n.replace(':', '.').lower()+')' for n in STAGES}
    names, w = validate(folder/'bench.raw', requested, 20e-9)
    if (len(counts) != 1 or int(counts[0]) != len(w) or 'Total analysis time (seconds)' not in log
            or re.search(r'(?im)(?:timestep too small|simulation interrupted|run simulation\(s\) aborted)', log)):
        raise ValueError('Native log does not attest a complete successful transient')
    result = module.measure(folder, task['spec'], m['identity']['devices'])
    if result != row['result']:
        raise ValueError('Native case-zero remeasurement changed')
    idx = {n: i for i, n in enumerate(names)}; time = w[:, idx['time']]*1e12
    paths = [parent/n for n in ('manifest.json', 'cells.spice', 'bank.spice')]
    paths += [folder/'summary.json', *[folder/n for n in row['files']]]
    stages = []
    for up, label in ((True, 'rise'), (False, 'fall')):
        edges = {}
        for node in STAGES:
            values = w[:, idx['v('+node.replace(':', '.').lower()+')']]
            crossing = isolated.original.crossings(time, values, up)
            if len(crossing) != 2:
                raise ValueError('Missing/extra native stage crossing')
            edges[node] = crossing
        for a, b in zip(STAGES, STAGES[1:]):
            delay = edges[b]-edges[a]
            if not np.all(delay > 0):
                raise ValueError('Native stage crossing order changed')
            stages.append(dict(edge=label, from_node=a, to_node=b, delay_ps=delay.tolist()))
    return dict(parent=str(parent.relative_to(ROOT)), spec=task['spec'], complete_records=len(w),
                samples=result['samples'], stage_delays=stages,
                terminal_screen_passed=result['terminal_screen_passed'],
                maximum_terminal_difference_v=max(d['maximum_terminal_difference_v'] for d in result['terminal_stress']),
                violating_mos=sum(not d['passed'] for d in result['terminal_stress']),
                worst_mos=sorted(result['terminal_stress'], key=lambda d: d['maximum_terminal_difference_v'], reverse=True)[:10],
                control_settling_passed=result['control_settling_passed'],
                zero_code_fast_quarter_headroom_ps=result['zero_code_fast_quarter_headroom_ps']), paths


def diagnose(source_parent):
    sm = isolated.bound(source_parent)
    rc_parent = ROOT/sm['identity']['parent']
    cells, bank, devices, reports = isolated.libraries(rc_parent)
    if (cells != (source_parent/'cells.spice').read_text() or bank != (source_parent/'bank.spice').read_text()
            or devices != sm['identity']['devices'] or reports != sm['identity']['component_isolation']):
        raise ValueError('Native parasitic-removal fixture cannot be regenerated')
    rc, paths = consume(rc_parent, isolated.original)
    source, source_paths = consume(source_parent, isolated)
    if rc['spec'] != source['spec']:
        raise ValueError('Native zero-code diagnostic conditions differ')
    paths += source_paths
    paths += [Path(__file__), Path(isolated.__file__), Path(isolated.isolation.__file__), Path(runner.__file__)]
    paths += [ROOT/n for n in sm['identity']['inputs']]
    binding = dict(version=VERSION, rc_parent=str(rc_parent.relative_to(ROOT)), source_parent=str(source_parent.relative_to(ROOT)),
                   inputs={str(p.relative_to(ROOT)): isolated.original.sha(p) for p in paths})
    comparisons = {edge+'_ps': [a[edge+'_delay_ps']-b[edge+'_delay_ps'] for a, b in zip(rc['samples'], source['samples'])]
                   for edge in ('rise', 'fall')}
    report = dict(identity=binding, physical_component_rc=rc, idealized_component_wiring=source,
                  observed_rc_minus_idealized_delay=comparisons, all_consumed_complete_waveforms_verified=True,
                  qualified_phy=False, electrical_qualification_passed=False, legal_code_table_admitted=False,
                  scope='Two complete matched 20ns zero-code native traces only; idealized copy deliberately removes component R/C, no physical timing equivalence, dense codes, all-PVT or PHY admission')
    isolated.bound(source_parent); isolated.original.bound(rc_parent)
    if any(isolated.original.sha(ROOT/n) != h for n, h in binding['inputs'].items()):
        raise ValueError('Native terminal-case evidence changed during diagnosis')
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():
        if json.loads((out/'summary.json').read_text()) != report:
            raise ValueError('Existing matched native diagnosis changed')
    else:
        out.mkdir(parents=True); isolated.original.atomic(out/'summary.json', report)
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    a = p.parse_args(); print(diagnose(a.artifact.resolve()), flush=True)
