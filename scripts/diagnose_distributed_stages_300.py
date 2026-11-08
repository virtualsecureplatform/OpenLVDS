#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Decompose complete distributed-fine native delays without changing qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import probe_distributed_fine_300 as producer
from bank_stage_history_300_v2 import stages, NODES
from native_binary_raw_v2 import validate

ROOT = producer.ROOT
VERSION = 'distributed-fine-native-stage-diagnosis-300-v1'


def run(parent, numbers):
    manifest = producer.bound(parent)
    identity = manifest['identity']
    if not numbers or len(set(numbers)) != len(numbers):
        raise ValueError('Require explicit unique completed case IDs')
    tasks = {t['id']: t for t in manifest['tasks']}
    if any(n not in tasks for n in numbers):
        raise ValueError('Unknown captured case')
    inputs = {**identity['inputs'], **identity['source_identity']['pdk_files'],
              **identity['source_identity']['external_files']}

    def retain(path):
        inputs[str(path.relative_to(ROOT))] = producer.sha(path)

    retain(parent / 'manifest.json')
    for variant in manifest['libraries']:
        retain(parent / variant / 'bank.spice')
    selected = []
    for number in numbers:
        folder = parent / number
        row = json.loads((folder / 'summary.json').read_text())
        if (row['error'] is not None or row['task'] != tasks[number]
                or not {'bench.raw', 'bench.cir'} <= set(row['files'])):
            raise ValueError('Require complete error-free captured native case')
        for name, digest in row['files'].items():
            path = folder / name
            if producer.sha(path) != digest:
                raise ValueError('Completed native case changed: ' + str(path))
            retain(path)
        retain(folder / 'summary.json')
        selected.append(row)
    for module in list(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).resolve().parent == ROOT / 'scripts':
            retain(Path(name).resolve())
    evidence = dict(version=VERSION, parent=str(parent.relative_to(ROOT)),
                    cases=numbers, inputs=inputs)
    token = hashlib.sha256(json.dumps(evidence, sort_keys=True).encode()).hexdigest()[:16]
    out = ROOT / 'build/diagnostics/distributed_bank_stage_diagnosis_300' / token
    out.mkdir(parents=True, exist_ok=False)
    producer.atomic(out / 'manifest.json', dict(identity=evidence, qualified_phy=False))
    producer.atomic(out / 'state.json', dict(status='running', qualified_phy=False))
    try:
        rows = []
        for row in selected:
            task = row['task']
            folder = parent / task['id']
            column = lambda n: 'v(' + n.replace(':', '.').lower() + ')'
            names, wave = validate(folder / 'bench.raw', {column(n) for n in NODES}, 40e-9)
            t = wave[:, names.index('time')] * 1e12
            signals = {n: wave[:, names.index(column(n))] for n in NODES}
            proof = stages(t, signals, task['spec'], row['result'])
            rows.append(dict(case=str(folder.relative_to(ROOT)), task=task,
                history=proof, original_outer_delays_reproduced=True,
                original_recorded_gates={k: v for k, v in row['result'].items()
                                         if k.endswith('_passed')}))
        if any(producer.sha(ROOT / name) != digest for name, digest in inputs.items()):
            raise ValueError('Replay inputs changed during analysis')
        producer.atomic(out / 'summary.json', dict(rows=rows,
            all_selected_outer_delays_reproduced=True, parameters_changed=False,
            qualified_phy=False, whole_bank_admitted=False,
            scope='All eight fixed native epochs, including startup; stage diagnosis only, original gates retained; no component or PHY admission'))
        producer.atomic(out / 'state.json', dict(status='complete', cases=len(rows), qualified_phy=False))
    except Exception as exc:
        producer.atomic(out / 'state.json', dict(status='failed', error=str(exc), qualified_phy=False))
        raise
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    parser.add_argument('cases', nargs='+')
    args = parser.parse_args()
    print(run(args.artifact.resolve(), args.cases), flush=True)
