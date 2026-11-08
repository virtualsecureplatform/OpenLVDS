#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Observe native pre/fine recovery voltages without inferring capacitor charge."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import replay_distributed_native_300_v2 as family
from diagnose_distributed_recovery_300_v2 import switch_nodes, samples
from bank_stage_history_300_v2 import stages, NODES
from native_binary_raw_v2 import validate

ROOT = family.ROOT
VERSION = 'registered-distributed-native-voltage-recovery-300-v3'



def run(parent, numbers):
    producer=family.select_producer(parent)
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
        if not (folder/'summary.json').is_file():raise ValueError('Native case is still pending: '+number)
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
    out = ROOT / 'build/diagnostics/distributed_voltage_recovery_300_v3' / token
    out.mkdir(parents=True, exist_ok=False)
    producer.atomic(out / 'manifest.json', dict(identity=evidence, qualified_phy=False))
    producer.atomic(out / 'state.json', dict(status='running', qualified_phy=False))
    try:
        rows = []
        for row in selected:
            task = row['task']
            folder = parent / task['id']
            column = lambda n: 'v(' + n.replace(':', '.').lower() + ')'
            cap_nodes=switch_nodes(identity['observations'][task['variant']],
                (parent/task['variant']/'bank.spice').read_text(),identity['revisions'][task['variant']]['macro_top'])
            names, wave = validate(folder / 'bench.raw', {column(n) for n in (*NODES,*cap_nodes)}, 40e-9)
            t = wave[:, names.index('time')] * 1e12
            signals = {n: wave[:, names.index(column(n))] for n in (*NODES,*cap_nodes)}
            proof = stages(t, {n:signals[n] for n in NODES}, task['spec'], row['result'])
            recovery={}
            for stage,trigger,output in (('pre','XD:selected','XD:pre_out'),('fine','XD:pre_out','XD:fine_node')):
                nodes={n:signals[n] for n,meta in cap_nodes.items() if meta['stage']==stage}
                nodes[output]=signals[output]
                recovery[stage]=dict(trigger_node=trigger,output_node=output,
                    **samples(t,signals[trigger],nodes))
            rows.append(dict(case=str(folder.relative_to(ROOT)), task=task,
                history=proof, observed_switch_side_nodes=cap_nodes, voltage_recovery=recovery,
                capacitor_charge_not_measured=True, original_outer_delays_reproduced=True,
                original_recorded_gates={k: v for k, v in row['result'].items()
                                         if k.endswith('_passed')}))
        if any(producer.sha(ROOT / name) != digest for name, digest in inputs.items()):
            raise ValueError('Replay inputs changed during analysis')
        producer.atomic(out / 'summary.json', dict(rows=rows,
            all_selected_outer_delays_reproduced=True, parameters_changed=False,
            qualified_phy=False, whole_bank_admitted=False,
            scope='Native stage and switch-side voltages before all eight causal input edges; no capacitor charge inference, mechanism proof, component or PHY admission'))
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
