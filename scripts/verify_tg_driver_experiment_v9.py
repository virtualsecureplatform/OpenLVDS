#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate diagnostic variants and remeasure complete native waveforms."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import probe_tg_driver_experiment_v9 as pilot
import run_native_binary_v2 as runner
import verify_dcdl_tg_tree_v5 as comparison
from native_binary_raw_v2 import read

ROOT = pilot.ROOT
VERSION = 'independent-native-driver-and-selector-borrowed-rc-screen-v9.1'
CONTEXT = 'tg_driver_experiment_verification_v9'


def comparisons(rows):
    results = []
    # Keep the exact existing sparse limits and required six codes. Relabel
    # each isolated profile only while calling the established comparison.
    for profile in pilot.circuit.PROFILES:
        selected = [dict(r, task=dict(r['task'], spec=dict(r['task']['spec'], profile='double_direct')))
                    for r in rows if r['task']['spec']['profile'] == profile]
        result = next(p for p in comparison.comparisons(selected) if p['profile'] == 'double_direct')
        results.append(dict(result, profile=profile, inverter_rc_physically_equivalent=False,
                            whole_bank_rc_retained=False, electrical_qualification_passed=False, qualified_phy=False))
    return results


def verify(parent, available=False):
    m = pilot.bound(parent); i = m['identity']; helper = pilot.helper
    cells, banks, devices, gates, changes, paths, pdk_files, baseline = pilot.libraries(ROOT/i['evidence'])
    if (devices != i['devices'] or gates != i['fine_control_gates'] or changes != i['changes']
            or pdk_files != i['pdk_files'] or baseline != i['parent']
            or any(cells[p] != (parent/f'cells_{p}.spice').read_text()
                   or banks[p] != (parent/f'bank_{p}.spice').read_text() for p in pilot.circuit.PROFILES)):
        raise ValueError('Native driver/selector model and device coverage cannot be regenerated')
    tasks = [t for t in m['tasks'] if (parent/t['id']/'summary.json').exists()] if available else m['tasks']
    if not tasks:
        raise ValueError('No complete native driver/selector cases available')
    aggregate = None
    if not available:
        state = json.loads((parent/'state.json').read_text())
        if state != dict(status='complete', cases=len(m['tasks']), errors=0, qualified_phy=False):
            raise ValueError('Require all numerical-error-free complete native driver/selector cases')
        aggregate = json.loads((parent/'summary.json').read_text())['rows']
        paths += [parent/'state.json', parent/'summary.json']
    paths += [parent/'manifest.json', *[parent/n for n in m['libraries']]]
    paths += [Path(__file__), Path(comparison.__file__), Path(runner.__file__)]
    rows = []
    for task in tasks:
        folder = parent/task['id']; row = json.loads((folder/'summary.json').read_text()); profile = task['spec']['profile']
        required = {'bench.cir', 'bench.ngspice.cir', 'bench.raw', 'ngspice.log', 'console.log'}
        before = {n: helper.sha(folder/n) for n in row['files']}
        if (row['task'] != task or row['error'] is not None or row['result'] is None
                or not required <= set(row['files']) or before != row['files']
                or (folder/'bench.ngspice.cir').read_text() != runner.translate((folder/'bench.cir').read_text())[0]
                or aggregate is not None and row != aggregate[int(task['id'])]):
            raise ValueError('Native driver/selector terminal-case evidence changed or failed')
        log = (folder/'ngspice.log').read_text(); counts = re.findall(r'No\. of Data Rows\s*:\s*(\d+)', log)
        _, w = read(folder/'bench.raw')
        if (len(counts) != 1 or int(counts[0]) != len(w) or 'Total analysis time (seconds)' not in log
                or re.search(r'(?im)(?:timestep too small|simulation interrupted|run simulation\(s\) aborted)', log)):
            raise ValueError('Native driver/selector log does not attest a complete successful transient')
        result = pilot.measure(folder, task['spec'], devices[profile], gates[profile])
        if result != row['result'] or any(helper.sha(folder/n) != h for n, h in before.items()):
            raise ValueError('Native driver/selector waveform remeasurement or input stability failed')
        rows.append(dict(task=task, result=result))
        paths += [folder/'summary.json', *[folder/n for n in row['files']]]
    pilot.bound(parent)
    binding = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), case_ids=[t['id'] for t in tasks],
                   inputs={str(p.relative_to(ROOT)): helper.sha(p) for p in paths}, terminal_cases_only=available)
    report = dict(identity=binding, rows=rows, profiles=comparisons(rows),
                  all_consumed_complete_native_waveforms_verified=True, all_declared_cases_consumed=len(tasks) == len(m['tasks']),
                  inverter_rc_physically_equivalent=False, whole_bank_rc_retained=False,
                  qualified_phy=False, electrical_qualification_passed=False, legal_code_table_admitted=False, scope=pilot.SCOPE)
    if any(helper.sha(ROOT/n) != h for n, h in binding['inputs'].items()):
        raise ValueError('Native driver/selector proof inputs changed')
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():
        if json.loads((out/'summary.json').read_text()) != report:
            raise ValueError('Existing native driver/selector proof changed')
    else:
        out.mkdir(parents=True); helper.atomic(out/'summary.json', report)
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    p.add_argument('--available', action='store_true'); p.add_argument('--watch', action='store_true'); a = p.parse_args()
    parent = a.artifact.resolve()
    if a.watch:
        while not (parent/'state.json').exists() or json.loads((parent/'state.json').read_text())['status'] == 'running':
            time.sleep(10)
    print(verify(parent, available=a.available), flush=True)
