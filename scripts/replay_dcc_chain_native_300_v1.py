#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently replay explicit completed combined DCC-chain native cases."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import probe_dcc_chain_300_v1 as four
import dcc_chain_independent_measure_300_v1 as independent
from replay_bank_300_v2 import same

ROOT=four.ROOT
VERSION='independent-combined-dcc-chain-native-replay-300-v1'
PRODUCERS={p.VERSION:p for p in (four,)}


def select(parent):
    version=json.loads((parent/'manifest.json').read_text())['identity']['version']
    if version not in PRODUCERS:raise ValueError('Unsupported combined DCC-chain producer')
    return PRODUCERS[version]


def run(parent,numbers):
    producer=select(parent)
    if not numbers or len(set(numbers))!=len(numbers) or any(n not in ('0','1') for n in numbers):
        raise ValueError('Require explicit unique combined DCC-chain case IDs')
    for n in numbers:
        if not (parent/n/'summary.json').exists():raise ValueError('Combined DCC-chain native case is still pending: '+n)
    m=producer.bound(parent);i=m['identity'];tasks={t['id']:t for t in m['tasks']}
    inputs=dict(i['inputs'])
    def retain(path):inputs[str(path.relative_to(ROOT))]=producer.sha(path)
    retain(parent/'manifest.json');retain(parent/'bank.spice');retain(parent/'dcc.spice');selected=[]
    for number in numbers:
        folder=parent/number;row=json.loads((folder/'summary.json').read_text())
        if (row['task']!=tasks[number] or row['error'] is not None or not isinstance(row['result'],dict)
                or not {'bench.raw','bench.cir','bench.ngspice.cir','ngspice.log','observations.json'}<=set(row['files'])):
            raise ValueError('Require a complete error-free combined DCC-chain native point')
        retain(folder/'summary.json')
        for name,digest in row['files'].items():
            if Path(name).name!=name or producer.sha(folder/name)!=digest:
                raise ValueError('Combined DCC-chain native witness changed')
            retain(folder/name)
        selected.append(row)
    for mod in list(sys.modules.values()):
        name=getattr(mod,'__file__',None)
        if name and Path(name).resolve().parent==ROOT/'scripts':retain(Path(name).resolve())
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),cases=numbers,inputs=inputs)
    out=ROOT/'build/diagnostics/dcc_four_section_native_replay_300_v1'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    producer.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    producer.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        rows=[]
        for row in selected:
            task=row['task'];folder=parent/task['id']
            obs=json.loads((folder/'observations.json').read_text())
            original=producer.metrology.measure(folder,obs,task['spec'])
            if original!=row['result']:raise ValueError('Original complete combined DCC-chain measurement does not reproduce')
            witness=independent.measure(folder,obs,task['spec'])
            if not same(witness,original):raise ValueError('Independent combined DCC-chain timing, terminals or controls do not reproduce')
            maps=list(obs['sections'].values())+list(obs['dcc'].values())
            rows.append(dict(task=task,all_original_metrics_reproduced=True,
                independent_combined_metrics_reproduced=True,source_point_passed=witness['combined_loading_transport_passed'],
                native_mos=sum(len(o['devices']) for o in maps),
                controls=sum(len(o['controls']) for o in obs['sections'].values()),
                programming_gates=sum(len(o['programming_gates']) for o in obs['sections'].values()),
                independent_result=witness))
        if any(producer.sha(ROOT/n)!=digest for n,digest in inputs.items()):
            raise ValueError('Combined DCC-chain replay inputs changed during analysis')
        producer.atomic(out/'summary.json',dict(rows=rows,all_selected_combined_native_metrics_reproduced=True,
            parameters_changed=False,qualified_phy=False,whole_bank_admitted=False,detector_dcc_fanout_qualified=False,
            scope='Explicit combined native points only; fresh numerical pair, calibrated phase, detector fanout, shared RC, DLL/PVT and PHY remain required'))
        producer.atomic(out/'state.json',dict(status='complete',cases=len(rows),qualified_phy=False))
    except Exception as exc:
        producer.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('cases',nargs='+')
    a=p.parse_args();print(run(a.parent.resolve(),a.cases),flush=True)
