#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Recompute every fresh native counter case before whole-matrix admission."""
import argparse,hashlib,json,sys
from pathlib import Path
import counter_pvt_300_v1 as producer
import counter_protocol_300_v2 as corrected
import replay_counter_clear_300 as replay
import watch_counter_clear_300 as watcher
ROOT=producer.ROOT
PARENT=watcher.PARENT
VERSION='fully-recomputed-native-counter-matrix-300-v1'


def coverage(rows,tasks):
    if (len(tasks)!=270 or len(rows)!=270 or set(rows)!=set(tasks)
            or {t['id'] for t in tasks.values()}!={str(k) for k in range(270)}):
        raise ValueError('Require all 270 distinct fresh counter replay cases')
    ordered=[tasks[str(k)] for k in range(270)]
    if [t['spec'] for t in ordered]!=producer.specifications() or any(t['mode']!='simulate' for t in ordered):
        raise ValueError('Require exact new 290/300/310 MHz, 15 PVT, duty and stopped-level matrix')
    for number,row in rows.items():
        if (row['task']!=tasks[number] or row['original_metrics_reproduced'] is not True
                or row['only_clear_settling_predicate_changed'] is not True
                or row['result']['stopped_clock_clear_settling_ps']!=3000
                or abs(row['result']['stopped_clock_clear_start_ps']-31000)>.01
                or row['result']['protocol_stop_ns']!=40
                or row['result']['counter_shared_wire_rc_qualified'] is not True):
            raise ValueError('Counter trace identity, complete protocol or original clear deadline changed')
    return ordered


def qualify():
    state=json.loads((PARENT/'state.json').read_text())
    if state!=dict(status='complete',cases=270,errors=0,qualified_phy=False):
        raise ValueError('Native counter campaign is not complete with 270 error-free cases')
    manifest=producer.bound(PARENT,full=False);tasks={t['id']:t for t in manifest['tasks']}
    rows,receipts,_=watcher.index_receipts(watcher.REPLAYS,str(PARENT.relative_to(ROOT)),tasks)
    ordered=coverage(rows,tasks);inputs={**manifest['identity']['guards'],**manifest['identity']['pdk_files'],**manifest['identity']['external_files'],**replay.evidence()}
    for receipt in receipts:
        folder=watcher.REPLAYS/receipt;m=json.loads((folder/'manifest.json').read_text())
        for name,digest in m['identity']['inputs'].items():
            if name in inputs and inputs[name]!=digest:raise ValueError('Conflicting captured counter inputs')
            inputs[name]=digest
        for name,digest in receipts[receipt].items():inputs[str((folder/name).relative_to(ROOT))]=digest
    for path in (PARENT/'manifest.json',PARENT/'state.json',PARENT/'cells.spice',PARENT/'pair.spice'):
        inputs[str(path.relative_to(ROOT))]=producer.sha(path)
    inputs.update({str(Path(m.__file__).resolve().relative_to(ROOT)):producer.sha(Path(m.__file__).resolve())
        for m in list(sys.modules.values()) if getattr(m,'__file__',None) and Path(m.__file__).resolve().parent==ROOT/'scripts'})
    if any(producer.sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Counter evidence changed before full matrix recomputation')
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),inputs=inputs,cases=[t['id'] for t in ordered],
                  profile_sha256=producer.sha(ROOT/'clocking_300mhz.json'),scope='Whole routed-counter PVT/clock matrix only; no whole-clock or PHY admission')
    out=ROOT/'build/diagnostics/counter_matrix_recomputed_300'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);producer.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    producer.atomic(out/'state.json',dict(status='running',qualified_phy=False))
    try:
        result=[]
        for task in ordered:
            number=task['id'];folder=PARENT/number;stored=json.loads((folder/'summary.json').read_text());observed=rows[number]
            if stored['task']!=task or stored['error'] is not None:raise ValueError('Original native case is incomplete')
            if not {'bench.raw','bench.cir'}<=set(stored['files']):raise ValueError('Native waveform or deck missing')
            for name,digest in stored['files'].items():
                if producer.sha(folder/name)!=digest:raise ValueError('Original native waveform/deck changed')
            original=dict(producer.protocol.measure(folder,manifest['identity'],task['spec']),scope=producer.SCOPE)
            if original!=stored['result']:raise ValueError('Original counter metrics do not reproduce')
            measured=dict(corrected.measure(folder,manifest['identity'],task['spec']),scope=producer.SCOPE)
            replay.unchanged_metrics(original,measured)
            if measured!=observed['result']:raise ValueError('Corrected replay no longer reproduces from actual native data')
            passed=producer.pilot.source.point_passed(measured)
            if passed is not observed['original_three_ns_point_passed']:raise ValueError('Counter classification changed')
            result.append(dict(task=task,passed=passed,
                minimum_remaining_low_window_ps=measured['low_windows']['minimum_remaining_low_window_ps'],
                maximum_terminal_difference_v=max(d['max_terminal_difference_v'] for d in measured['terminal_stress']),
                original_stricter_point_passed=observed['original_point_passed']))
            producer.atomic(out/'progress.json',dict(cases_recomputed=len(result),qualified_phy=False))
        if any(producer.sha(ROOT/n)!=h for n,h in inputs.items()):raise ValueError('Counter evidence changed during full recomputation')
        passed=all(r['passed'] for r in result)
        producer.atomic(out/'summary.json',dict(rows=result,all_270_counter_boundaries_present=True,
            all_15_counter_pvt_covered=True,all_cases_recomputed_from_native_raw=True,
            routed_counter_pvt_boundary_screen_passed=passed,
            minimum_remaining_low_window_ps=min(r['minimum_remaining_low_window_ps'] for r in result),
            maximum_terminal_difference_v=max(r['maximum_terminal_difference_v'] for r in result),
            failed_cases=[r['task']['id'] for r in result if not r['passed']],
            original_results_preserved=True,whole_clock_rc_qualified=False,electrical_qualification_passed=False,qualified_phy=False))
        producer.atomic(out/'state.json',dict(status='complete',cases=270,qualified_phy=False))
    except Exception as exc:
        producer.atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();print(qualify(),flush=True)
