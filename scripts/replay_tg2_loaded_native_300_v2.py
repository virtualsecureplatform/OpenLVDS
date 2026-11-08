#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently remeasure explicit completed native actual-next-bank cases."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import probe_tg2_next_bank_300_v1 as strict
import probe_tg2_next_bank_early_300_v2 as early
import probe_tg2_entry_domain_300_v1 as entry
import two_bank_independent_measure_300_v1 as independent
from replay_bank_300_v2 import same

ROOT=early.ROOT
VERSION='independent-actual-next-bank-and-entry-native-replay-300-v2'
PRODUCERS={p.VERSION:p for p in (strict,early,entry)}


def select(parent):
    version=json.loads((parent/'manifest.json').read_text())['identity']['version']
    if version not in PRODUCERS:raise ValueError('Unsupported actual-next-bank producer')
    return PRODUCERS[version]


def run(parent,numbers):
    producer=select(parent)
    allowed={str(k) for k in range(8 if producer is entry else 4)}
    if not numbers or len(set(numbers))!=len(numbers) or any(n not in allowed for n in numbers):
        raise ValueError('Require explicit unique loaded case IDs')
    for n in numbers:
        if not (parent/n/'summary.json').exists():raise ValueError('Loaded native case is still pending: '+n)
    m=producer.bound(parent);i=m['identity'];tasks={t['id']:t for t in m['tasks']}
    inputs=dict(i['inputs'])
    def retain(path):inputs[str(path.relative_to(ROOT))]=producer.sha(path)
    retain(parent/'manifest.json');retain(parent/'bank.spice');selected=[]
    for number in numbers:
        folder=parent/number;row=json.loads((folder/'summary.json').read_text())
        if (row['task']!=tasks[number] or row['error'] is not None or not isinstance(row['result'],dict)
                or not {'bench.raw','bench.cir','bench.ngspice.cir','ngspice.log','observations.json'}<=set(row['files'])):
            raise ValueError('Require a complete error-free loaded native point')
        retain(folder/'summary.json')
        for name,digest in row['files'].items():
            if Path(name).name!=name or producer.sha(folder/name)!=digest:
                raise ValueError('Loaded native witness changed')
            retain(folder/name)
        selected.append(row)
    for mod in list(sys.modules.values()):
        name=getattr(mod,'__file__',None)
        if name and Path(name).resolve().parent==ROOT/'scripts':retain(Path(name).resolve())
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),cases=numbers,inputs=inputs)
    out=ROOT/'build/diagnostics/tg2_loaded_native_replay_300_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    producer.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    producer.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        rows=[]
        for row in selected:
            task=row['task'];folder=parent/task['id']
            obs=json.loads((folder/'observations.json').read_text())
            settings=dict(next_coarse=task['next_coarse'],next_fine=task['next_fine'])
            spec=task['spec'] if producer is entry else i['spec']
            original=producer.metrology.measure(folder,obs,spec,**settings)
            if original!=row['result']:raise ValueError('Original complete loaded measurement does not reproduce')
            witness=(entry.metrology.measure(folder,obs,spec,independent_reader=True,**settings)
                     if producer is entry else independent.measure(folder,obs,spec,**settings))
            if not same(witness,original):raise ValueError('Independent loaded timing, terminals or controls do not reproduce')
            rows.append(dict(task=task,all_original_metrics_reproduced=True,
                independent_two_bank_metrics_reproduced=True,source_point_passed=witness['two_bank_zero_pilot_passed'],
                native_mos=sum(len(o['devices']) for o in obs.values()),
                controls=sum(len(o['controls']) for o in obs.values()),
                programming_gates=sum(len(o['programming_gates']) for o in obs.values()),
                independent_result=witness))
        if any(producer.sha(ROOT/n)!=digest for n,digest in inputs.items()):
            raise ValueError('Loaded replay inputs changed during analysis')
        producer.atomic(out/'summary.json',dict(rows=rows,all_selected_loaded_native_metrics_reproduced=True,
            parameters_changed=False,qualified_phy=False,whole_bank_admitted=False,
            scope='Explicit native two-bank points only; both numerical pairs, source coverage, shared RC, DLL/PVT and PHY remain required'))
        producer.atomic(out/'state.json',dict(status='complete',cases=len(rows),qualified_phy=False))
    except Exception as exc:
        producer.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('cases',nargs='+')
    a=p.parse_args();print(run(a.parent.resolve(),a.cases),flush=True)
