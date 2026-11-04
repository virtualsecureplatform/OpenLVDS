#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently remeasure completed clock-repair candidates and health gates."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import probe_tag_arbiter_v2 as tag
import probe_preconditioned_arbiter_v2 as pre
import probe_analog_conditioned_arbiter_v2 as analog
import probe_arbiter_reference_cap_v2 as reference
import probe_dcdl_control_restore_v2 as control
import probe_dcc_clock_hold_v2 as hold
import verify_digital_clocking_v2 as reader

ROOT=tag.ROOT
base=tag.base
MODULES={'tag_arbiter_v2':(tag,'phase'),'preconditioned_arbiter_v2':(pre,'phase'),
    'analog_conditioned_arbiter_v2':(analog,'analog'),'arbiter_reference_cap_v2':(reference,'analog'),
    'dcdl_control_restore_v2':(control,'control'),'dcc_clock_hold_v2':(hold,'dcc')}

@contextmanager
def profile(namespace,module,kind):
    previous=reader.MODULES.copy(),base.measure,reader.dcdl.measure
    reader.MODULES[namespace]=module
    if kind=='control':
        def measure(folder):
            m=json.loads((folder.parent/'manifest.json').read_text())
            task=next(t for t in m['tasks'] if t['id']==folder.name)
            return control.measure(folder,task)
        reader.dcdl.measure=measure
    else:base.measure=analog.measure if module is reference else module.measure
    try:yield
    finally:
        old,m,d=previous;reader.MODULES.clear();reader.MODULES.update(old);base.measure=m;reader.dcdl.measure=d


def report(out):
    out=out.resolve()
    if out.parent.name not in MODULES:raise ValueError('Require a versioned clock-repair context')
    module,kind=MODULES[out.parent.name]
    with profile(out.parent.name,module,kind):m,rows,files=reader.remeasure(out)
    groups=[]
    if kind in ('phase','analog'):
        fields=['drive','swap','reference_slew_ps','feedback_slew_ps']
        keys=sorted({tuple(r['task']['spec'][n] for n in fields) for r in rows})
        for key in keys:
            selected=sorted([r for r in rows if tuple(r['task']['spec'][n] for n in fields)==key],key=lambda r:r['task']['spec']['offset_ps'])
            has_bracket={-20,20}<={r['task']['spec']['offset_ps'] for r in selected}
            passed=has_bracket and all(r['error'] is None and (r['task']['spec']['offset_ps']==0 or r['result']['correct_sign_fraction']==1)
                and (kind!='analog' or (r['result']['frontend_stress_passed'] and r['result']['common_mode_passed'])) for r in selected)
            groups.append(dict(zip(fields,key),source_sign_and_health_passed=bool(passed),
                points=[dict(offset_ps=r['task']['spec']['offset_ps'],result=r['result'],error=r['error']) for r in selected]))
    elif kind=='dcc':
        for drive in sorted({r['task']['spec']['reset_drive'] for r in rows}):
            selected=[r for r in rows if r['task']['spec']['reset_drive']==drive]
            passed=all(r['error'] is None and r['result']['event_integrity_passed'] and r['result']['pulse_generator_integrity_passed']
                and (r['task']['spec']['phase_error_ps']!=0 or r['result']['symmetric_timing_passed']) for r in selected)
            groups.append(dict(reset_drive=drive,cases=len(selected),source_event_and_timing_passed=bool(passed),
                worst_balanced_half_cycle_error_ps=max((r['result']['mean_half_cycle_error_ps'] for r in selected if r['result'] and r['task']['spec']['phase_error_ps']==0 and r['result']['mean_half_cycle_error_ps'] is not None),default=None)))
    else:
        for row in rows:
            d=row['result']
            groups.append(dict(restore=row['task']['spec']['restore'],source_stress_passed=bool(row['error'] is None and d['custom_mos_stress_passed']),
                maximum_custom_mos_difference_v=max((q['max_terminal_difference_v'] for q in d['custom_mos_stress']),default=None) if d else None))
    return dict(artifact=str(out.relative_to(ROOT)),kind=kind,cases=len(rows),rows=rows,groups=groups,witness_files=files,
        numerical_errors=sum(r['error'] is not None for r in rows),qualified_phy=False,detector_admitted=False,legal_code_table_admitted=False,
        scope='Independent bounded source repair evidence; no complete PVT, physical or PHY admission')


def verify(out):
    result=report(out)
    identity=dict(artifact=result['artifact'],manifest_sha256=base.sha(out/'manifest.json'),summary_sha256=base.sha(out/'summary.json'),
        consumer_sha256=base.sha(Path(__file__)),reader_sha256=base.sha(Path(reader.__file__)))
    receipt=ROOT/'build/diagnostics/clock_repairs_v2_verification'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    receipt.mkdir(parents=True,exist_ok=True);body=json.dumps(dict(identity=identity,**result),indent=2)+'\n'
    if (receipt/'summary.json').exists() and (receipt/'summary.json').read_text()!=body:raise ValueError('Prior clock-repair receipt changed')
    if not (receipt/'summary.json').exists():base.write(receipt/'summary.json',body)
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args()
    print(verify(a.artifact.resolve()),flush=True)
