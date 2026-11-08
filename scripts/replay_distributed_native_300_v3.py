#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently replay explicit completed cases from registered distributed-bank producers."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

import probe_distributed_fine_300 as distributed
import probe_medium_pre_distributed_300 as medium
import probe_p40n32_pre_distributed_300 as p40n32
import probe_tg2_p40n32_300 as tg2
from replay_bank_300_v2 import independent

ROOT = p40n32.ROOT
PRODUCERS = {m.VERSION: m for m in (distributed, medium, p40n32, tg2)}
VERSION = 'distributed-family-independent-native-replay-300-v3'


def select_producer(parent):
    version=json.loads((parent/'manifest.json').read_text())['identity']['version']
    if version not in PRODUCERS:raise ValueError('Unsupported captured bank producer')
    return PRODUCERS[version]


def run(parent, numbers):
    producer = select_producer(parent)
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
        if not (folder / 'summary.json').is_file():
            raise ValueError('Native case is still pending: ' + number)
        row = json.loads((folder / 'summary.json').read_text())
        if (row['error'] is not None or row['task'] != tasks[number]
                or not isinstance(row.get('result'), dict)
                or not {'bench.raw', 'bench.cir', 'ngspice.log'} <= set(row['files'])):
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
    out = ROOT / 'build/diagnostics/distributed_family_native_replay_300_v3' / token
    out.mkdir(parents=True, exist_ok=False)
    producer.atomic(out / 'manifest.json', dict(identity=evidence, qualified_phy=False))
    producer.atomic(out / 'state.json', dict(status='running', qualified_phy=False))
    try:
        rows = []
        original = producer.prior.PARENTS['restored'][0]
        for row in selected:
            task = row['task']
            folder = parent / task['id']
            source = deepcopy(identity['source_identity'])
            source['observations'] = identity['observations'][task['variant']]
            again = producer.prior.contract(original.measure(folder, source, task['spec']), task['spec'])
            if again != row['result']:
                raise ValueError('Full original measurement no longer reproduces')
            proof = independent(folder, source, task['spec'], again)
            rows.append(dict(case=str(folder.relative_to(ROOT)), task=task,
                             all_original_metrics_reproduced=True, **proof))
        if any(producer.sha(ROOT / name) != digest for name, digest in inputs.items()):
            raise ValueError('Replay inputs changed during analysis')
        producer.atomic(out / 'summary.json', dict(rows=rows,
            all_selected_native_metrics_reproduced=True, parameters_changed=False,
            qualified_phy=False, whole_bank_admitted=False,
            scope='Explicit completed cases only; active parity, coverage, actual loading, routed RC and full PVT remain required'))
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
