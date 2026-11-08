#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Capture unwrapped phase diagnostics from explicit completed native points."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import probe_tg2_four_bank_300_v1 as chain
import probe_dcc_chain_300_v1 as combined
import four_bank_phase_measure_300_v1 as phase
from native_binary_raw_v2 import validate

ROOT=chain.ROOT
VERSION='captured-four-section-native-phase-diagnostic-300-v1'
CONTEXT='four_section_phase_diagnostic_300_v1'
PRODUCERS={p.VERSION:p for p in (chain,combined)}


def run(parent,numbers):
    version=json.loads((parent/'manifest.json').read_text())['identity']['version']
    if version not in PRODUCERS:raise ValueError('Unsupported four-section phase producer')
    if not numbers or len(set(numbers))!=len(numbers) or any(n not in ('0','1') for n in numbers):
        raise ValueError('Require explicit unique native case IDs')
    for n in numbers:
        if not (parent/n/'summary.json').exists():raise ValueError('Native phase case is still pending: '+n)
    producer=PRODUCERS[version];m=producer.bound(parent);inputs=dict(m['identity']['inputs'])
    tasks={t['id']:t for t in m['tasks']};selected=[]
    def retain(path):inputs[str(path.relative_to(ROOT))]=producer.sha(path)
    retain(parent/'manifest.json');retain(parent/'bank.spice')
    if producer is combined:retain(parent/'dcc.spice')
    for n in numbers:
        folder=parent/n;row=json.loads((folder/'summary.json').read_text())
        if (row['task']!=tasks[n] or row['error'] is not None or not isinstance(row['result'],dict)
                or not {'bench.raw','bench.cir','bench.ngspice.cir','ngspice.log','observations.json'}<=set(row['files'])):
            raise ValueError('Require complete error-free native phase witnesses')
        retain(folder/'summary.json')
        for name,h in row['files'].items():
            if Path(name).name!=name or producer.sha(folder/name)!=h:raise ValueError('Native phase witness changed')
            retain(folder/name)
        selected.append(row)
    for mod in list(sys.modules.values()):
        name=getattr(mod,'__file__',None)
        if name and Path(name).resolve().parent==ROOT/'scripts':retain(Path(name).resolve())
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),cases=numbers,inputs=inputs)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);producer.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    producer.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        rows=[]
        for row in selected:
            task=row['task'];s=task['spec'];folder=parent/task['id']
            columns={n:'v('+n.lower()+')' for n in phase.NODES}
            names,w=validate(folder/'bench.raw',set(columns.values()),s['stop_ns']*1e-9)
            index={n:k for k,n in enumerate(names)};t=w[:,index['time']]*1e12
            if abs(t[0])>1e-6:raise ValueError('Native phase trace omits DC/startup sample')
            measured=phase.measure(t,lambda n:w[:,index[columns[n]]],s)
            point_key='four_section_transport_passed' if producer is chain else 'combined_loading_transport_passed'
            rows.append(dict(task=task,original_transport_passed=row['result'][point_key],phase=measured))
        if any(producer.sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Phase diagnostic inputs changed during analysis')
        producer.atomic(out/'summary.json',dict(rows=rows,parameters_changed=False,calibrated_phase_qualified=False,
            detector_fanout_qualified=False,shared_wire_rc_qualified=False,qualified_phy=False,
            scope='Direct native phase errors only; original transport decisions preserved, no calibration or PHY admission'))
        producer.atomic(out/'state.json',dict(status='complete',cases=len(rows),qualified_phy=False))
    except Exception as exc:
        producer.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path);p.add_argument('cases',nargs='+')
    a=p.parse_args();print(run(a.parent.resolve(),a.cases),flush=True)
