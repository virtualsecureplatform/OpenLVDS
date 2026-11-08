#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Observe native pre/fine recovery voltages without inferring capacitor charge."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import replay_distributed_native_300_v3 as family
from diagnose_distributed_recovery_300_v2 import samples
from native_clock_components_v2 import definitions, mapped_mos
from bank_stage_history_300_v2 import stages, NODES
from native_binary_raw_v2 import validate

ROOT = family.ROOT
VERSION = 'topology-derived-transmission-gate-recovery-300-v4'



def switch_nodes(observations,library,top):
    """Find CAP/NODE MOS terminals from actual resistor connectivity, not leaf IDs."""
    defs=definitions(library)
    calls=[w for w in defs[top][1] if w[0].startswith('Xfine_mim')]
    if not calls:raise ValueError('Missing actual native fine-cell attachments')
    devices={d['name']:d for d in observations['devices']};result={}
    for call in calls:
        head,copy_text=call[0].split('_c');unit=int(head.removeprefix('Xfine_mim'))
        if unit not in (0,15,30):continue
        if call[1] not in ('pre_out','fine_node'):
            raise ValueError('Unrecognized actual fine-cell signal attachment')
        model=call[-1];ports,body=defs[model]
        if ports!=['NODE','EN','ENB','VDD','VSS']:
            raise ValueError('Require exact five-port native switched-MIM unit')
        graph={}
        for w in body:
            if w[0][0].upper()=='R':
                graph.setdefault(w[1],set()).add(w[2]);graph.setdefault(w[2],set()).add(w[1])
        def reachable(start):
            seen={start};todo=[start]
            while todo:
                for node in graph.get(todo.pop(),()):
                    if node not in seen:seen.add(node);todo.append(node)
            return seen
        networks={p:reachable(p) for p in ports}
        public=set().union(*networks.values())
        if any(networks[a]&networks[b] for k,a in enumerate(ports) for b in ports[k+1:]):
            raise ValueError('Switched-MIM public resistor networks shorted')
        caps=[w for w in body if w[0][0].upper()=='X' and len(w)>3 and 'cap_mim' in w[3]]
        internal=[node for w in caps for node in w[1:3] if node not in public]
        if len(caps)!=2 or len(internal)!=1:
            raise ValueError('Require one internal main-MIM plate and the control shunt')
        cap_network=reachable(internal[0]);leaves=[]
        for d in mapped_mos(library,model,{p:p for p in ports},'UNIT'):
            terminals=[n.removeprefix('UNIT:') for n in d['terminals']]
            matches=[k for k,other in ((0,2),(2,0))
                     if terminals[k] in cap_network and terminals[other] in networks['NODE']]
            if len(matches)>1:raise ValueError('Ambiguous native transmission-switch terminals')
            if not matches:continue
            k=matches[0];leaf=d['name'].removeprefix('UNIT:');name=f'XD:{call[0]}:{leaf}'
            if name not in devices:raise ValueError('Missing actual native transmission switch')
            node=devices[name]['terminals'][k]
            if node!=f'XD:{call[0]}:'+terminals[k]:
                raise ValueError('Actual capacitor-side native terminal differs from library')
            result[node]=dict(device=name,terminal=('D','G','S','B')[k],copy=int(copy_text),
                fine_index=unit,stage='pre' if call[1]=='pre_out' else 'fine',signal_node='XD:'+call[1])
            leaves.append(d)
        if len(leaves)!=2 or sum('pfet_' in d['model'] for d in leaves)!=1 or sum('nfet_' in d['model'] for d in leaves)!=1:
            raise ValueError('Require both actual native transmission-gate switches')
    if not result:raise ValueError('No representative native transmission-gate observations')
    return result


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
    out = ROOT / 'build/diagnostics/distributed_voltage_recovery_300_v4' / token
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
