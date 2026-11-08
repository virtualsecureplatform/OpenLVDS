#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Retain complete active-pair parity without mutating a live bank campaign."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import probe_distributed_fine_300 as producer

ROOT=producer.ROOT
VERSION='distributed-fine-complete-active-pair-parity-300-v1'


def pair_tasks(manifest,variant):
    variants=list(producer.architecture.VARIANTS)
    if variant not in variants:raise ValueError('Unknown captured variant')
    index=2*variants.index(variant)
    tasks=manifest['tasks'][index:index+2]
    if (len(tasks)!=2 or [t['id'] for t in tasks]!=[str(index),str(index+1)]
        or any(t['variant']!=variant for t in tasks)
        or [t['centered'] for t in tasks]!=[False,True]
        or tasks[0]['spec']!=tasks[1]['spec']):
        raise ValueError('Require exact unshifted/centered same-circuit same-stimulus pair')
    return tasks


def run(parent,variant):
    manifest=producer.bound(parent);identity=manifest['identity'];tasks=pair_tasks(manifest,variant)
    inputs={**identity['inputs'],**identity['source_identity']['pdk_files'],
            **identity['source_identity']['external_files']}
    def retain(path):inputs[str(path.relative_to(ROOT))]=producer.sha(path)
    retain(parent/'manifest.json')
    for v in manifest['libraries']:retain(parent/v/'bank.spice')
    rows={}
    for task in tasks:
        folder=parent/task['id'];path=folder/'summary.json';row=json.loads(path.read_text())
        if (row['task']!=task or row['error'] is not None or row['result'] is None
            or not {'bench.cir','bench.raw','bench.ngspice.cir','ngspice.log','console.log'}<=set(row['files'])):
            raise ValueError('Require complete error-free native pair')
        for name,digest in row['files'].items():
            if Path(name).name!=name or producer.sha(folder/name)!=digest:
                raise ValueError('Changed active-pair witness '+name)
            retain(folder/name)
        retain(path);rows[int(task['id'])]=row
    for module in list(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name and Path(name).resolve().parent==ROOT/'scripts':retain(Path(name).resolve())
    evidence=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),variant=variant,
        cases=[t['id'] for t in tasks],inputs=inputs,
        maximum_all_vector_error_v=.002,maximum_absolute_crossing_error_ps=.25,
        all_gate_classifications_must_match=True)
    out=ROOT/'build/diagnostics/distributed_bank_active_parity_300'/hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    producer.atomic(out/'manifest.json',dict(identity=evidence,qualified_phy=False))
    producer.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        original=producer.prior.PARENTS['restored'][0]
        for task in tasks:
            source=deepcopy(identity['source_identity']);source['observations']=identity['observations'][variant]
            again=producer.prior.contract(original.measure(parent/task['id'],source,task['spec']),task['spec'])
            if again!=rows[int(task['id'])]['result']:raise ValueError('Original complete pair metrics do not reproduce')
        comparison=producer.parity(parent,rows,*[int(t['id']) for t in tasks])
        if any(producer.sha(ROOT/n)!=digest for n,digest in inputs.items()):raise ValueError('Active-pair inputs changed')
        producer.atomic(out/'summary.json',dict(active_numerical_parity=comparison,
            all_original_metrics_reproduced=True,
            original_point_passed={t['id']:rows[int(t['id'])]['result']['current_clock_interface_screen_passed'] for t in tasks},
            parameters_changed=False,qualified_phy=False,whole_bank_admitted=False,
            scope='Exact complete active numerical pair only; physical point failures preserved; coverage, actual loading, routed RC, PVT and full PHY remain required'))
        producer.atomic(out/'state.json',dict(status='complete',cases=2,qualified_phy=False))
    except Exception as exc:
        producer.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path)
    p.add_argument('variant',choices=tuple(producer.architecture.VARIANTS));a=p.parse_args()
    print(run(a.artifact.resolve(),a.variant),flush=True)
