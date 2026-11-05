#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate TG banks and independently remeasure complete native cases.

--available binds only terminal cases and never takes over an active campaign.
Full screening still requires every declared sparse point for each profile.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import probe_dcdl_tg_tree_v5 as pilot
import run_native_binary_v2 as runner
from native_binary_raw_v2 import read

ROOT = pilot.ROOT
VERSION = 'independent-native-tg-bank-complete-case-screen-v5.1'
CONTEXT = 'dcdl_tg_tree_verification_v5'


def comparisons(rows):
    results = []
    expected = {(s['coarse'], s['fine']) for s in pilot.specifications()}
    for profile in pilot.circuit.PROFILES:
        selected = [r for r in rows if r['task']['spec']['profile'] == profile]
        by_code = {(r['task']['spec']['coarse'], r['task']['spec']['fine']): r['result'] for r in selected}
        if len(by_code) != len(selected):
            raise ValueError('Duplicate native TG screening point')
        complete = set(by_code) == expected
        steps = []; overlaps = {}
        for edge in ('rise', 'fall'):
            def delay(c, f):
                return by_code[c, f]['samples'][1][edge+'_delay_ps']
            for a, b in ((0, 1), (1, 15), (15, 16), (16, 31)):
                if (0, a) in by_code and (0, b) in by_code:
                    value = delay(0, b)-delay(0, a)
                    steps.append(dict(edge=edge, from_fine=a, to_fine=b, delay_change_ps=value,
                                      sampled_order_passed=bool(value > 0),
                                      adjacent_gap_passed=bool(0 < value <= 20) if b-a == 1 else None))
            if (0, 31) in by_code and (1, 0) in by_code:
                overlaps[edge+'_ps'] = delay(0, 31)-delay(1, 0)
        voltage = bool(selected) and all(r['result']['terminal_screen_passed'] for r in selected)
        controls = bool(selected) and all(r['result']['control_settling_passed'] and r['result']['onehot_control_settling_passed'] for r in selected)
        repeat = bool(selected) and all(v <= 20 for r in selected for v in r['result']['repeated_delay_difference_ps'].values())
        zero = by_code.get((0, 0))
        headroom = zero['zero_code_fast_quarter_headroom_ps'] if zero else None
        quarter = headroom is not None and headroom > 0
        fine = complete and all(s['sampled_order_passed'] and s['adjacent_gap_passed'] is not False for s in steps)
        overlap = len(overlaps) == 2 and all(v > 0 for v in overlaps.values())
        results.append(dict(profile=profile, completed_sparse_points=len(selected), all_sparse_points_present=complete,
                            terminal_screen_passed=voltage, all_static_controls_passed=controls,
                            repeated_pulses_passed=repeat, zero_code_fast_quarter_headroom_ps=headroom,
                            zero_code_quarter_passed=bool(quarter), fine_steps=steps, coarse_overlap=overlaps,
                            sampled_fine_order_and_adjacent_gaps_passed=bool(fine), coarse_overlap_passed=bool(overlap),
                            sparse_native_screen_passed=bool(complete and voltage and controls and repeat and quarter and fine and overlap),
                            dense_legal_code_coverage_proven=False, qualified_phy=False))
    return results


def verify(parent, available=False):
    m = pilot.bound(parent); i = m['identity']
    cells, banks, devices, reports, paths, pdk_files = pilot.libraries(ROOT/i['evidence'])
    if (cells != (parent/'cells.spice').read_text() or '\n'.join(banks.values()) != (parent/'banks.spice').read_text()
            or devices != i['devices'] or reports != i['component_isolation'] or pdk_files != i['pdk_files']):
        raise ValueError('Native TG-bank library/topology/device coverage cannot be regenerated')
    tasks = [t for t in m['tasks'] if (parent/t['id']/'summary.json').exists()] if available else m['tasks']
    if not tasks:
        raise ValueError('No terminal native TG cases available')
    if not available:
        state = json.loads((parent/'state.json').read_text())
        if state != dict(status='complete', cases=len(m['tasks']), errors=0, qualified_phy=False):
            raise ValueError('Require all numerical-error-free complete native TG cases')
        paths += [parent/'state.json', parent/'summary.json']
        aggregate = json.loads((parent/'summary.json').read_text())['rows']
    else:
        aggregate = None
    paths += [parent/n for n in ('manifest.json', 'cells.spice', 'banks.spice')]
    paths += [Path(__file__), Path(runner.__file__)]
    rows = []
    for task in tasks:
        folder = parent/task['id']; r = json.loads((folder/'summary.json').read_text())
        required = {'bench.cir', 'bench.ngspice.cir', 'bench.raw', 'ngspice.log', 'console.log'}
        before = {n: pilot.original.sha(folder/n) for n in r['files']}
        if (r['task'] != task or r['error'] is not None or r['result'] is None
                or not required <= set(r['files']) or before != r['files']
                or (folder/'bench.ngspice.cir').read_text() != runner.translate((folder/'bench.cir').read_text())[0]
                or aggregate is not None and r != aggregate[int(task['id'])]):
            raise ValueError('Native TG terminal-case evidence changed or failed')
        log = (folder/'ngspice.log').read_text(); counts = re.findall(r'No\. of Data Rows\s*:\s*(\d+)', log)
        _, w = read(folder/'bench.raw')
        if (len(counts) != 1 or int(counts[0]) != len(w) or 'Total analysis time (seconds)' not in log
                or re.search(r'(?im)(?:timestep too small|simulation interrupted|run simulation\(s\) aborted)', log)):
            raise ValueError('Native TG log does not attest a complete successful transient')
        result = pilot.measure(folder, task['spec'], i['devices'][task['spec']['profile']])
        if result != r['result'] or any(pilot.original.sha(folder/n) != h for n, h in before.items()):
            raise ValueError('Native TG waveform remeasurement/input stability failed')
        rows.append(dict(task=task, result=result))
        paths += [folder/'summary.json', *[folder/n for n in r['files']]]
    pilot.bound(parent)
    binding = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), case_ids=[t['id'] for t in tasks],
                   inputs={str(p.relative_to(ROOT)): pilot.original.sha(p) for p in paths}, terminal_cases_only=available)
    report = dict(identity=binding, rows=rows, profiles=comparisons(rows),
                  all_consumed_complete_native_waveforms_verified=True, all_declared_cases_consumed=len(tasks) == len(m['tasks']),
                  qualified_phy=False, electrical_qualification_passed=False, legal_code_table_admitted=False, scope=pilot.SCOPE)
    if any(pilot.original.sha(ROOT/n) != h for n, h in binding['inputs'].items()):
        raise ValueError('Native TG evidence changed during verification')
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():
        if json.loads((out/'summary.json').read_text()) != report:
            raise ValueError('Existing native TG proof changed')
    else:
        out.mkdir(parents=True); pilot.original.atomic(out/'summary.json', report)
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    p.add_argument('--available', action='store_true'); p.add_argument('--watch', action='store_true'); a = p.parse_args()
    parent = a.artifact.resolve()
    if a.watch:
        while not (parent/'state.json').exists() or json.loads((parent/'state.json').read_text())['status'] == 'running':
            time.sleep(10)
    print(verify(parent, available=a.available), flush=True)
