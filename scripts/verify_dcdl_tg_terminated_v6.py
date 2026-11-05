#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure complete terminated-bank cases without touching active solvers."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import probe_dcdl_tg_terminated_v6 as pilot
import run_native_binary_v2 as runner
from native_binary_raw_v2 import read

ROOT = pilot.ROOT
VERSION = 'independent-native-tg-tail-termination-complete-case-screen-v6.1'
CONTEXT = 'dcdl_tg_terminated_verification_v6'


def verify(parent, available=False):
    m = pilot.bound(parent); i = m['identity']
    cells, bank, devices, paths, pdk_files, baseline = pilot.libraries(ROOT/i['evidence'])
    if (cells != (parent/'cells.spice').read_text() or bank != (parent/'bank.spice').read_text()
            or devices != i['devices'] or pdk_files != i['pdk_files'] or baseline != i['parent']):
        raise ValueError('Terminated native bank/device witness cannot be regenerated')
    tasks = [t for t in m['tasks'] if (parent/t['id']/'summary.json').exists()] if available else m['tasks']
    if not tasks:
        raise ValueError('No complete native termination cases available')
    aggregate = None
    if not available:
        state = json.loads((parent/'state.json').read_text())
        if state != dict(status='complete', cases=6, errors=0, qualified_phy=False):
            raise ValueError('Require all six complete numerical-error-free native cases')
        aggregate = json.loads((parent/'summary.json').read_text())['rows']
        paths += [parent/'state.json', parent/'summary.json']
    paths += [parent/n for n in ('manifest.json', 'cells.spice', 'bank.spice')]
    paths += [Path(__file__), Path(runner.__file__), Path(pilot.proof.__file__)]
    rows = []
    for task in tasks:
        folder = parent/task['id']; row = json.loads((folder/'summary.json').read_text())
        required = {'bench.cir', 'bench.ngspice.cir', 'bench.raw', 'ngspice.log', 'console.log'}
        before = {n: pilot.previous.original.sha(folder/n) for n in row['files']}
        if (row['task'] != task or row['error'] is not None or row['result'] is None
                or not required <= set(row['files']) or before != row['files']
                or (folder/'bench.ngspice.cir').read_text() != runner.translate((folder/'bench.cir').read_text())[0]
                or aggregate is not None and row != aggregate[int(task['id'])]):
            raise ValueError('Native termination evidence changed or failed')
        log = (folder/'ngspice.log').read_text(); counts = re.findall(r'No\. of Data Rows\s*:\s*(\d+)', log)
        _, data = read(folder/'bench.raw')
        if (len(counts) != 1 or int(counts[0]) != len(data) or 'Total analysis time (seconds)' not in log
                or re.search(r'(?im)(?:timestep too small|simulation interrupted|run simulation\(s\) aborted)', log)):
            raise ValueError('Native termination log does not attest a complete transient')
        result = pilot.measure(folder, task['spec'], devices)
        if result != row['result'] or any(pilot.previous.original.sha(folder/n) != h for n, h in before.items()):
            raise ValueError('Native termination waveform remeasurement or input stability failed')
        rows.append(dict(task=task, result=result))
        paths += [folder/'summary.json', *[folder/n for n in row['files']]]
    pilot.bound(parent)
    binding = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), case_ids=[t['id'] for t in tasks],
                   inputs={str(p.relative_to(ROOT)): pilot.previous.original.sha(p) for p in paths}, terminal_cases_only=available)
    profiles = pilot.proof.comparisons(rows)
    profile = next(p for p in profiles if p['profile'] == pilot.circuit.PROFILE)
    report = dict(identity=binding, rows=rows, profile=profile, all_consumed_complete_native_waveforms_verified=True,
                  all_declared_cases_consumed=len(tasks) == len(m['tasks']), electrical_qualification_passed=False,
                  legal_code_table_admitted=False, qualified_phy=False, scope=pilot.SCOPE)
    if any(pilot.previous.original.sha(ROOT/n) != h for n, h in binding['inputs'].items()):
        raise ValueError('Native termination proof inputs changed during verification')
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():
        if json.loads((out/'summary.json').read_text()) != report:
            raise ValueError('Existing native termination proof changed')
    else:
        out.mkdir(parents=True); pilot.previous.original.atomic(out/'summary.json', report)
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('artifact', type=Path)
    p.add_argument('--available', action='store_true'); p.add_argument('--watch', action='store_true'); a = p.parse_args()
    parent = a.artifact.resolve()
    if a.watch:
        while not (parent/'state.json').exists() or json.loads((parent/'state.json').read_text())['status'] == 'running':
            time.sleep(10)
    print(verify(parent, available=a.available), flush=True)
