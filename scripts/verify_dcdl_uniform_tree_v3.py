#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Regenerate uniform-bank libraries/decks and remeasure retained native traces."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import time
import probe_dcdl_uniform_tree_v3 as pilot
from run_native_binary_v2 import translate
from native_binary_raw_v2 import read

VERSION = 'independent-uniform-tap-balanced-tree-static-code-v3.1'
CONTEXT = 'dcdl_uniform_tree_verification_v3'


def compare(rows):
    by_code = {(r['task']['spec']['coarse'], r['task']['spec']['fine']): r['result'] for r in rows}
    expected = {(s['coarse'], s['fine']) for s in pilot.specifications()}
    if set(by_code) != expected or len(rows) != len(expected):
        raise ValueError('Require every declared static-code trace exactly once')
    steps = []
    overlaps = {}
    for edge in ('rise', 'fall'):
        def delay(c, f):
            return by_code[c, f]['samples'][1][edge+'_delay_ps']
        for coarse in (0, 1):
            for a, b in ((0, 1), (1, 15), (15, 16), (16, 31)):
                step = delay(coarse, b)-delay(coarse, a)
                steps.append(dict(edge=edge, coarse=coarse, from_fine=a, to_fine=b,
                                  delay_change_ps=step, sampled_order_passed=bool(step > 0),
                                  adjacent_gap_passed=bool(0 < step <= 20) if b-a == 1 else None))
        overlaps[edge+'_ps'] = delay(0, 31)-delay(1, 0)
    return dict(fine_steps=steps, coarse_overlap=overlaps,
                sampled_fine_order_passed=all(s['sampled_order_passed'] for s in steps),
                coarse_overlap_passed=all(v > 0 for v in overlaps.values()),
                dense_legal_code_coverage_proven=False)


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        m = pilot.bound(out); i = m['identity']
        state = json.loads((out/'state.json').read_text())
        aggregate = json.loads((out/'summary.json').read_text())
        if (state != dict(status='complete', cases=10, errors=0, qualified_phy=False)
                or aggregate['qualified_phy'] is not False or len(aggregate['rows']) != 10):
            raise ValueError('Require all ten complete numerical traces')
        sc = next(Path(n) for n in i['pdk_files'] if n.endswith('/sky130_fd_sc_hd.spice'))
        cells, bank, devices, paths = pilot.libraries(pilot.ROOT/i['compound'], pilot.ROOT/i['fine'], pilot.ROOT/i['clock'], sc)
        if (cells != (out/'cells.spice').read_text() or bank != (out/'bank.spice').read_text()
                or devices != i['devices']):
            raise ValueError('Native topology, component RC or MOS coverage changed')
        paths += [out/n for n in ('manifest.json', 'state.json', 'summary.json', 'cells.spice', 'bank.spice')]
        paths += [Path(__file__), Path(pilot.__file__)]
        rows = []
        for task, retained in zip(m['tasks'], aggregate['rows']):
            folder = out/task['id']
            row = json.loads((folder/'summary.json').read_text())
            required = {'bench.cir', 'bench.ngspice.cir', 'bench.raw', 'ngspice.log', 'console.log'}
            before = {n: pilot.sha(folder/n) for n in row['files']}
            if (row != retained or row['task'] != task or row['error'] is not None
                    or not required <= set(row['files']) or before != row['files']
                    or (folder/'bench.ngspice.cir').read_text() != translate((folder/'bench.cir').read_text())[0]):
                raise ValueError('Retained native task/deck/raw binding changed')
            log = (folder/'ngspice.log').read_text()
            counts = re.findall(r'No\. of Data Rows\s*:\s*(\d+)', log)
            _, waveform = read(folder/'bench.raw')
            if (len(counts) != 1 or int(counts[0]) != len(waveform)
                    or 'Total analysis time (seconds)' not in log
                    or re.search(r'(?im)(?:timestep too small|simulation interrupted|run simulation\(s\) aborted)', log)):
                raise ValueError('Native log does not attest a complete successful transient')
            result = pilot.measure(folder, task['spec'], devices)
            if result != row['result'] or any(pilot.sha(folder/n) != h for n, h in before.items()):
                raise ValueError('Native waveform remeasurement or input stability failed')
            rows.append(dict(task=task, result=result))
            paths += [folder/'summary.json', *[folder/n for n in row['files']]]
        pilot.bound(out)
        identity = dict(version=VERSION, parent=str(out.relative_to(pilot.ROOT)),
                        inputs={str(p.relative_to(pilot.ROOT)): pilot.sha(p) for p in paths})
        receipt = pilot.ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
        report = dict(identity=identity, rows=rows, comparison=compare(rows), all_declared_raw_waveforms_verified=True,
                      all_terminal_screens_passed=all(r['result']['terminal_screen_passed'] for r in rows),
                      all_control_screens_passed=all(r['result']['control_settling_passed'] for r in rows),
                      electrical_qualification_passed=False, legal_code_table_admitted=False, qualified_phy=False, scope=pilot.SCOPE)
        if receipt.exists():
            if json.loads((receipt/'summary.json').read_text()) != report:
                raise ValueError('Existing independent receipt changed')
        else:
            receipt.mkdir(parents=True)
            pilot.atomic(receipt/'summary.json', report)
        return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('artifact', type=Path); p.add_argument('--watch', action='store_true'); a = p.parse_args()
    out = a.artifact.resolve()
    if a.watch:
        while not (out/'state.json').exists() or json.loads((out/'state.json').read_text())['status'] == 'running':
            time.sleep(10)
    print(verify(out), flush=True)
