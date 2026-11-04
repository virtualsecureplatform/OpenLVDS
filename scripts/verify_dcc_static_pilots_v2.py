#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently regenerate static DCC decks and remeasure immutable raw data.

Check every half-cycle against 50 ps. A passing mean cannot hide alternating
short/long cycles. These bounded source receipts never admit a physical PHY.
"""
import argparse
import fcntl
import hashlib
import json
import math
from pathlib import Path
import dcc_nand_mid_shunt_v2 as devices
from measure_dcc_native_events_v2 import measure
import probe_dcc_nand_latch_v2 as nand
import probe_dcc_nand_mid_shunt_v2 as mid
import probe_dcc_nand_node_shunt_v2 as node
import probe_dcc_tg_combiner_v2 as tg
from probe_digital_dcc_v2 import sha

ROOT=nand.ROOT
MODULES={'dcc_nand_latch_v2':nand,'dcc_nand_mid_shunt_v2':mid,'dcc_nand_node_shunt_v2':node,'dcc_tg_combiner_v2':tg}
VERSION='independent-static-dcc-all-half-cycle-source-verification-v2.1'
FIELDS=['output_event_checks','event_integrity_passed','startup_passed','half_cycle_error_ps',
    'half_cycle_width_ranges_ps','maximum_individual_half_cycle_error_ps','output_latency_range_ps',
    'terminal_abs_peak_v','terminal_screen_passed']


def same(a,b):
    if type(a) is bool or type(b) is bool:return type(a) is type(b) and a==b
    if isinstance(a,(int,float)) and isinstance(b,(int,float)):
        return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=1e-7
    if isinstance(a,list) and isinstance(b,list):return len(a)==len(b) and all(same(x,y) for x,y in zip(a,b))
    if isinstance(a,dict) and isinstance(b,dict):return set(a)==set(b) and all(same(a[k],b[k]) for k in a)
    return a==b


def candidates(key,producer,library):
    if key=='dcc_nand_latch_v2':return {'nand'+str(d):producer.circuit.source(d,library) for d in [1,2]}
    if key=='dcc_tg_combiner_v2':return {v:producer.circuit.source(v,library)[0] for v in producer.circuit.VARIANTS}
    prefix='mid' if key=='dcc_nand_mid_shunt_v2' else 'loaded'
    return {prefix+str(d):producer.circuit.source(d,library)[0] for d in [1,2]}


def requirements(result):
    error=result['maximum_individual_half_cycle_error_ps']
    return dict(startup_passed=result['startup_passed'],event_integrity_passed=result['event_integrity_passed'],
        mean_half_cycle_passed=result['half_cycle_passed'],every_half_cycle_passed=bool(error is not None and error<=50),
        terminal_screen_passed=result['terminal_screen_passed'])


def verify(out):
    key=out.parent.name
    if key not in MODULES or not out.is_relative_to(ROOT/'build/diagnostics'/key):raise ValueError('Unknown static DCC context')
    producer=MODULES[key]
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=producer.bound(out);i=m['identity'];summary=json.loads((out/'summary.json').read_text());state=json.loads((out/'state.json').read_text())
        expected_state='real_tg_source_pilot_complete' if key=='dcc_tg_combiner_v2' else 'static_gate_source_pilot_complete'
        if state['status']!=expected_state or state['cases']!=len(i['specs']) or state['errors']:
            raise ValueError('Require a complete numerical-error-free source cohort')
        if len(m['tasks'])!=len(i['specs']) or len(summary['rows'])!=len(m['tasks']):raise ValueError('Incomplete task matrix')
        if m['interface']!=dict(ports=producer.circuit.PORTS):raise ValueError('Source interface differs from the circuit')
        source=candidates(key,producer,Path(i['pdk']).read_text())
        if set(m['libraries'])!={v+'.spice' for v in source}:raise ValueError('Source candidate set changed')
        files=[out/n for n in ['manifest.json','summary.json','state.json']]
        for variant,text in source.items():
            path=out/(variant+'.spice')
            if path.read_text()!=text:raise ValueError('Source differs from exact native regeneration')
            files.append(path)
        rows=[]
        for n,task in enumerate(m['tasks']):
            if task['id']!=str(n) or task['spec']!=i['specs'][n]:raise ValueError('Task metadata differs from bound matrix')
            folder=out/str(n);retained=json.loads((folder/'summary.json').read_text());text=source[task['spec']['variant']]
            if retained!=summary['rows'][n] or retained['task']!=task or retained['error'] is not None:
                raise ValueError('Task/aggregate/numerical result mismatch')
            if (folder/'bench.cir').read_text()!=producer.fixture(out,task['spec'],m['interface'],text):
                raise ValueError('Stimulus differs from exact source/deck regeneration')
            for name in ['bench.cir','bench.raw']:
                if sha(folder/name)!=retained['files'][name]:raise ValueError('Changed native raw/deck witness')
            files += [folder/n for n in ['summary.json','bench.cir','bench.raw']]
            measured=measure(folder,task['spec'],devices.devices(text),'Independent complete source-cohort raw remeasurement')
            if any(not same(measured[k],retained['result'][k]) for k in FIELDS):raise ValueError('Native raw remeasurement disagrees with producer')
            gates=requirements(measured)
            rows.append(dict(id=task['id'],spec=task['spec'],requirements=gates,source_case_passed=all(gates.values()),
                mean_half_cycle_error_ps=measured['half_cycle_error_ps'],worst_half_cycle_error_ps=measured['maximum_individual_half_cycle_error_ps'],
                terminal_abs_peak_v=measured['terminal_abs_peak_v'],qualified_phy=False))
        producer.bound(out)
        witnesses={str(p.relative_to(ROOT)):sha(p) for p in files}
        code=[Path(__file__),ROOT/'scripts/measure_dcc_native_events_v2.py',Path(devices.__file__),Path(producer.__file__)]
        identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),witnesses=witnesses,code={str(p.relative_to(ROOT)):sha(p) for p in code})
        report=[]
        for variant in source:
            group=[r for r in rows if r['spec']['variant']==variant]
            report.append(dict(variant=variant,cases=len(group),pvt_count=len({(r['spec']['process'],r['spec']['temperature']) for r in group}),
                source_candidate_screen_passed=all(r['source_case_passed'] for r in group),
                failed_requirements={k:sum(not r['requirements'][k] for r in group) for k in rows[0]['requirements']},
                worst_half_cycle_error_ps=max(r['worst_half_cycle_error_ps'] for r in group if r['worst_half_cycle_error_ps'] is not None),
                maximum_terminal_difference_v=max(r['terminal_abs_peak_v'] for r in group)))
        receipt=ROOT/'build/diagnostics/dcc_static_verification_v2'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        body=json.dumps(dict(identity=identity,rows=rows,candidates=report,source_only=True,qualified_phy=False,physical_admitted=False,
            scope='Exact native-library/deck regeneration, binary raw witnesses and every-half-cycle source screening only; no full-PVT, RC or PHY admission'),indent=2)+'\n'
        if any(sha(ROOT/n)!=h for n,h in witnesses.items()):raise ValueError('Source witnesses changed during verification')
        receipt.mkdir(parents=True,exist_ok=True);path=receipt/'summary.json'
        if path.exists() and path.read_text()!=body:raise ValueError('Retain prior independent verification')
        if not path.exists():path.write_text(body)
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);a=p.parse_args();print(verify(a.artifact.resolve()),flush=True)
