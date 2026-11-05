#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Recover only the known passive-tail probe reporting fault, without reruns.

Every active MOS terminal, every distributed fine gate, and complete pulse/log
evidence remain mandatory. The unsaved passive public-node range stays null.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import time
import probe_dcdl_tg_component_rc_v7 as producer
import measure_tg_component_rc_v8 as measurement
import run_native_binary_v2 as runner
from native_binary_raw_v2 import read

ROOT = producer.ROOT
VERSION = 'complete-native-component-rc-passive-probe-report-recovery-v8.1'
CONTEXT = 'dcdl_tg_component_rc_recovery_v8'
KNOWN_ERROR = 'Missing requested native vectors'


def verify(parent, available=False):
    m = producer.bound(parent); i = m['identity']; helper = producer.previous.previous.original
    cells, bank, devices, gates, restored, paths, pdk_files, baseline = producer.libraries(ROOT/i['evidence'])
    if (cells != (parent/'cells.spice').read_text() or bank != (parent/'bank.spice').read_text()
            or devices != i['devices'] or gates != i['fine_control_gates']
            or restored != i['restored_components'] or pdk_files != i['pdk_files'] or baseline != i['parent']):
        raise ValueError('Native component-RC fixture/witness cannot be regenerated')
    tasks = [t for t in m['tasks'] if (parent/t['id']/'summary.json').exists()] if available else m['tasks']
    if not tasks:
        raise ValueError('No terminal native component-RC cases available')
    aggregate = None
    if not available:
        state = json.loads((parent/'state.json').read_text())
        if state != dict(status='complete', cases=6, errors=6, qualified_phy=False):
            raise ValueError('Require all six terminal cases with the known reporter fault')
        aggregate = json.loads((parent/'summary.json').read_text())['rows']
        paths += [parent/'state.json', parent/'summary.json']
    paths += [parent/n for n in ('manifest.json', 'cells.spice', 'bank.spice')]
    paths += [Path(__file__), Path(measurement.__file__), Path(runner.__file__), Path(producer.previous.proof.__file__)]
    rows = []
    for task in tasks:
        folder = parent/task['id']; original = json.loads((folder/'summary.json').read_text())
        required = {'bench.cir', 'bench.ngspice.cir', 'bench.raw', 'ngspice.log', 'console.log'}
        before = {n: helper.sha(folder/n) for n in original['files']}
        if (original['task'] != task or original['error'] != KNOWN_ERROR or original['result'] is not None
                or not required <= set(original['files']) or before != original['files']
                or (folder/'bench.ngspice.cir').read_text() != runner.translate((folder/'bench.cir').read_text())[0]
                or aggregate is not None and original != aggregate[int(task['id'])]):
            raise ValueError('Require the exact known native reporting failure and unchanged files')
        names, w = read(folder/'bench.raw'); log = (folder/'ngspice.log').read_text()
        counts = re.findall(r'No\. of Data Rows\s*:\s*(\d+)', log)
        if ('v(xd.unused_tail)' in names or len(counts) != 1 or int(counts[0]) != len(w)
                or 'Total analysis time (seconds)' not in log
                or re.search(r'(?im)(?:timestep too small|simulation interrupted|run simulation\(s\) aborted)', log)):
            raise ValueError('Native case is not a complete successful missing-passive-probe trace')
        try:
            producer.measure(folder, task['spec'], devices, gates)
        except ValueError as error:
            if str(error) != KNOWN_ERROR:
                raise ValueError('Native reporter does not reproduce its retained failure') from error
        else:
            raise ValueError('Original reporter unexpectedly succeeds')
        result = measurement.measure(folder, task['spec'], devices, gates)
        if any(helper.sha(folder/n) != h for n, h in before.items()):
            raise ValueError('Native component-RC case changed during read-only recovery')
        rows.append(dict(task=task, result=result, original_report_error=KNOWN_ERROR))
        paths += [folder/'summary.json', *[folder/n for n in original['files']]]
    producer.bound(parent)
    binding = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), case_ids=[t['id'] for t in tasks],
                   inputs={str(p.relative_to(ROOT)): helper.sha(p) for p in paths}, terminal_cases_only=available)
    profile = next(p for p in producer.previous.proof.comparisons(rows) if p['profile'] == producer.previous.circuit.PROFILE)
    report = dict(identity=binding, rows=rows, profile=profile, all_consumed_complete_native_waveforms_verified=True,
                  all_declared_cases_consumed=len(tasks) == len(m['tasks']),
                  original_reporting_failure_preserved=True, passive_public_tail_range_available=False,
                  qualified_phy=False, electrical_qualification_passed=False, legal_code_table_admitted=False,
                  scope=producer.SCOPE+' Missing passive public tail voltage is not inferred; all native active-terminal/control checks are retained.')
    if any(helper.sha(ROOT/n) != h for n, h in binding['inputs'].items()):
        raise ValueError('Native component-RC recovery inputs changed')
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(binding, sort_keys=True).encode()).hexdigest()[:16]
    if out.exists():
        if json.loads((out/'summary.json').read_text()) != report:
            raise ValueError('Existing native component-RC recovery changed')
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
