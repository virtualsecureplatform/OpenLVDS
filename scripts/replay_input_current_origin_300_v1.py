#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Remeasure a completed input-current trial without admitting another circuit."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import probe_input_current_origin_300_v1 as producer
from replay_bank_300_v2 import same

ROOT=producer.ROOT
VERSION='independent-input-current-origin-replay-300-v1'
CONTEXT='input_current_origin_native_replay_300_v1'


def run(parent):
    # A state file alone cannot prove completion; require the terminal receipts
    # before binding and reading every native witness below.
    for name in ('state.json','summary.json','0/summary.json'):
        if not (parent/name).is_file():raise ValueError('Input-current trial is still pending')
    m=producer.bound(parent);spec=m['identity']['spec']
    state=json.loads((parent/'state.json').read_text())
    summary=json.loads((parent/'summary.json').read_text())
    row=json.loads((parent/'0/summary.json').read_text())
    if (state!=dict(status='complete',cases=1,errors=0,qualified_phy=False)
            or row['task']!=m['tasks'][0] or row['error'] is not None
            or summary['error'] is not None or not isinstance(row['result'],dict)
            or not isinstance(row['independent_result'],dict) or not isinstance(row['parity'],dict)
            or not {'bench.raw','bench.cir','bench.ngspice.cir','ngspice.log','observations.json'}<=set(row['files'])):
        raise ValueError('Require complete error-free input-current native witnesses')
    inputs=dict(m['identity']['inputs'])
    def retain(path):inputs[str(path.relative_to(ROOT))]=producer.sha(path)
    for name in ('manifest.json','state.json','summary.json','bank.spice','0/summary.json'):
        retain(parent/name)
    for name,digest in row['files'].items():
        if Path(name).name!=name or producer.sha(parent/'0'/name)!=digest:
            raise ValueError('Input-current native witness changed')
        retain(parent/'0'/name)
    for mod in list(sys.modules.values()):
        name=getattr(mod,'__file__',None)
        if name and Path(name).resolve().parent==ROOT/'scripts':retain(Path(name).resolve())
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),inputs=inputs)
    out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False)
    producer.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    producer.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        obs=json.loads((parent/'0/observations.json').read_text())
        old=json.loads((producer.PARENT/'0/summary.json').read_text())['result']
        reference=producer.metrology.measure(producer.PARENT/'0',obs,spec,next_coarse=0,next_fine=0)
        if reference!=old:raise ValueError('Original complete reference does not reproduce')
        original=producer.metrology.measure(parent/'0',obs,spec,next_coarse=0,next_fine=0)
        independent=producer.independent.measure(parent/'0',obs,spec,next_coarse=0,next_fine=0)
        if (original!=row['result'] or independent!=row['independent_result']
                or not same(original,independent)):
            raise ValueError('Complete original/independent input-current metrics do not reproduce')
        parity=producer.compare(producer.PARENT/'0',parent/'0',old,original)
        if parity!=row['parity'] or summary['result']!=original or summary['parity']!=parity:
            raise ValueError('Complete input-current numerical comparison does not reproduce')
        accepted=bool(parity['passed'])
        if (summary['numerical_origin_passed_for_reference_case'] is not accepted
                or summary['combined_circuit_admitted'] is not False or summary['qualified_phy'] is not False):
            raise ValueError('Input-current reference classification changed')
        if any(producer.sha(ROOT/n)!=digest for n,digest in inputs.items()):
            raise ValueError('Input-current replay inputs changed during analysis')
        producer.atomic(out/'summary.json',dict(all_original_metrics_reproduced=True,
            independent_metrics_reproduced=True,numerical_comparison_reproduced=True,
            numerical_origin_passed_for_reference_case=accepted,parity=parity,
            parameters_changed=False,combined_circuit_admitted=False,qualified_phy=False,
            scope='One complete two-bank reference only; every new circuit requires its own fresh parity and physical gates'))
        producer.atomic(out/'state.json',dict(status='complete',cases=1,qualified_phy=False))
    except Exception as exc:
        producer.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('parent',type=Path)
    a=p.parse_args();print(run(a.parent.resolve()),flush=True)
