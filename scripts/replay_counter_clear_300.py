#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Replay fresh counter data with the original three-nanosecond clear deadline."""
import argparse,hashlib,json,sys
from pathlib import Path
import counter_pvt_300_v1 as producer
import counter_protocol_300_v2 as corrected
ROOT=producer.ROOT
VERSION='original-three-ns-counter-clear-replay-300-v1'
DIAGNOSIS=ROOT/'build/diagnostics/counter_reassertion_diagnosis_300/ba5c7205c882bcd2'
CHANGED={'stopped_clock_clear_and_reassert_passed','stopped_clock_arm_clear_passed',
         'stopped_clock_intermediate_clear_passed','timing_protocol_passed',
         'counter_feasibility_passed','hypothesis_point_checks_passed'}
ADDED={'stopped_clock_clear_start_ps','stopped_clock_clear_settling_ps'}


def legacy_allowance():
    """Bind the original clear check to its actual source and native stimulus."""
    old=ROOT/'scripts/probe_guarded_clock_prepare_v3.py'
    arm=ROOT/'scripts/probe_guarded_phase_clock_release_v2.py'
    phase=ROOT/'scripts/probe_static_phase_clock_release_v6.py'
    deck=producer.PARENT/'0/bench.cir'
    if ('final=t>=24000;' not in old.read_text()
            or "get('XD:XR:armed')[t>=24000]" not in arm.read_text()
            or "get('XD:XR:'+n)[t>=24000]" not in phase.read_text()
            or '20.99n 1.8 21.01n 0 22.99n 0 23.01n 1.8' not in deck.read_text()):
        raise ValueError('Original 21 ns REQUEST fall / 24 ns clear deadline changed')
    return 3000,[old,arm,phase,deck]


def unchanged_metrics(original,new):
    if set(new)!=set(original)|ADDED:raise ValueError('Unexpected new counter measurement fields')
    if any(new[k]!=v for k,v in original.items() if k not in CHANGED):
        raise ValueError('A metric outside the clear-settling predicate changed')
    if new['stopped_clock_clear_settling_ps']!=3000 or abs(new['stopped_clock_clear_start_ps']-31000)>.01:
        raise ValueError('Original three-nanosecond clear allowance was not restored')


def evidence():
    allowance,paths=legacy_allowance()
    m=json.loads((DIAGNOSIS/'manifest.json').read_text());i=m['identity']
    r=json.loads((DIAGNOSIS/'summary.json').read_text())
    if (i['version']!='fresh-counter-reassertion-window-diagnosis-300-v1' or i['case']!='1'
            or DIAGNOSIS.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
            or json.loads((DIAGNOSIS/'state.json').read_text())!=dict(status='complete',qualified_phy=False)
            or r['original_metrics_reproduced'] is not True or r['window_comparison_only'] is not True
            or r['original_gate_not_modified'] is not True):
        raise ValueError('Require complete unchanged native clear-window diagnosis')
    paths += [DIAGNOSIS/n for n in ('manifest.json','summary.json','state.json')]
    return {**i['inputs'],**{str(p.relative_to(ROOT)):producer.sha(p) for p in paths}}


def run(parent,numbers):
    m=producer.bound(parent,full=False)
    if not numbers or len(set(numbers))!=len(numbers):raise ValueError('Require unique explicit completed case IDs')
    by_id={t['id']:t for t in m['tasks']}
    if any(n not in by_id for n in numbers):raise ValueError('Unknown native counter case')
    inputs={**m['identity']['guards'],**m['identity']['pdk_files'],**m['identity']['external_files'],**evidence()}
    for path in (parent/'manifest.json',parent/'cells.spice',parent/'pair.spice'):
        inputs[str(path.relative_to(ROOT))]=producer.sha(path)
    selected=[]
    for number in numbers:
        folder=parent/number;row=json.loads((folder/'summary.json').read_text())
        if row['task']!=by_id[number] or row['error'] is not None or row['task']['mode']!='simulate':
            raise ValueError('Require completed fresh native counter cases, never historical timing')
        for name,digest in row['files'].items():
            key=str((folder/name).relative_to(ROOT))
            if key in inputs and inputs[key]!=digest:raise ValueError('Conflicting native evidence')
            inputs[key]=digest
        inputs[str((folder/'summary.json').relative_to(ROOT))]=producer.sha(folder/'summary.json');selected.append(row)
    inputs.update({str(Path(mod.__file__).resolve().relative_to(ROOT)):producer.sha(Path(mod.__file__).resolve())
        for mod in list(sys.modules.values()) if getattr(mod,'__file__',None) and Path(mod.__file__).resolve().parent==ROOT/'scripts'})
    if any(producer.sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Native replay input changed')
    identity=dict(version=VERSION,parent=str(parent.relative_to(ROOT)),cases=numbers,inputs=inputs,
                  clear_settling_ps=3000,original_results_preserved=True)
    out=ROOT/'build/diagnostics/counter_clear_replay_300'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);producer.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    producer.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        rows=[]
        for stored in selected:
            task=stored['task'];folder=parent/task['id'];s=task['spec']
            original=dict(producer.protocol.measure(folder,m['identity'],s),scope=producer.SCOPE)
            if original!=stored['result']:raise ValueError('Original strict counter metrics do not reproduce')
            result=dict(corrected.measure(folder,m['identity'],s),scope=producer.SCOPE)
            unchanged_metrics(original,result)
            rows.append(dict(task=task,original_metrics_reproduced=True,only_clear_settling_predicate_changed=True,
                original_recorded_gates={k:v for k,v in original.items() if k.endswith('_passed')},result=result,
                original_point_passed=producer.pilot.source.point_passed(original),
                original_three_ns_point_passed=producer.pilot.source.point_passed(result)))
        if any(producer.sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Replay evidence changed during measurement')
        producer.atomic(out/'summary.json',dict(rows=rows,all_selected_original_metrics_reproduced=True,
            all_selected_original_three_ns_points_passed=all(r['original_three_ns_point_passed'] for r in rows),
            all_270_counter_boundaries_present=False,all_15_counter_pvt_covered=False,
            qualified_phy=False,whole_clock_rc_qualified=False,
            scope='Selected fresh native traces with original 3 ns clear settling restored; original stricter failed records retained; no full matrix or PHY admission'))
        producer.atomic(out/'state.json',dict(status='complete',cases=len(rows),qualified_phy=False))
    except Exception as exc:
        producer.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('cases',nargs='+');a=p.parse_args()
    print(run(a.artifact.resolve(),a.cases),flush=True)
