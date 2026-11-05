#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Independently verify a bounded-source convergence experiment, including aborts."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import time
import probe_dcdl_pwl_source_v2 as pilot
from run_native_binary_v2 import translate
from diagnose_dcdl_iterations_v3 import abort_time_agrees

ROOT=pilot.ROOT
VERSION='independent-native-dcdl-voltage-pwl-source-isolation-v2.1'
CONTEXT='dcdl_pwl_source_verification_v2'
REQUIRED={'bench.cir','bench.ngspice.cir','bench.raw','ngspice.log','console.log','cells.spice','bank.spice'}


def verdict(result,error):
    if error is None:
        if result is None or result.get('numerically_completed') is not True or result.get('actual_source_representation_passed') is not True:
            raise ValueError('Missing completed and source-validated waveform result')
        native=result.get('native_result')
        if native is None and result.get('native_measurement_error') is None:raise ValueError('Missing native measurement or explicit electrical failure')
        return dict(complete_waveform_verified=True,terminal_numerical_failure_verified=False,
            native_pulse_screen_passed=bool(native is not None and native['native_pulse_passed'] and result['native_measurement_error'] is None))
    if result is not None:raise ValueError('Numerical failure cannot retain a completed waveform verdict')
    return dict(complete_waveform_verified=False,terminal_numerical_failure_verified=True,native_pulse_screen_passed=False)


def verify(out):
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        m=pilot.bound(out);i=m['identity'];state=json.loads((out/'state.json').read_text());r=json.loads((out/'summary.json').read_text())
        if state['status']!='pwl_source_isolation_complete' or state['numerically_completed']!=(r['result'] is not None):
            raise ValueError('Require terminal native source-representation experiment')
        if not REQUIRED<=set(r['files']) or any(pilot.sha(out/n)!=h for n,h in r['files'].items()):
            raise ValueError('Native PWL experiment raw/deck/log evidence changed')
        baseline_case=ROOT/i['baseline_case'];bm,task,br=pilot.checked_baseline(baseline_case);bi=bm['identity'];parent=baseline_case.parent
        cells,bank,orders,devices,_=pilot.baseline.libraries(ROOT/bi['compound'],ROOT/bi['fine'],Path(bi['source_library']))
        if (cells!=(out/'cells.spice').read_text() or bank!=(out/'bank.spice').read_text() or devices!=i['devices']
            or cells!=(parent/'cells.spice').read_text() or bank!=(parent/'bank.spice').read_text() or orders!=bi['orders']
            or task['spec']!=i['spec']):raise ValueError('Native libraries, topology or terminal coverage changed')
        text,cert=pilot.fixture(out,i['spec'],devices);translated,_=translate(text)
        if text!=(out/'bench.cir').read_text() or translated!=(out/'bench.ngspice.cir').read_text() or cert!=i['source_certificate']:
            raise ValueError('Bounded source or translated native deck cannot be regenerated')
        assessment=verdict(r['result'],r['error']);terminal_failure=None
        if assessment['complete_waveform_verified']:
            measured=pilot.measure(out,i['spec'],devices)
            if measured!=r['result']:raise ValueError('Full native waveform/source remeasurement changed')
        else:
            log=(out/'ngspice.log').read_text();failure=pilot.failure.failure(log);prefix=pilot.failure.prefix(out/'bench.raw')
            if not abort_time_agrees(prefix['last_time_s'],log) or prefix['last_time_s']>=20e-9:
                raise ValueError('Terminal failure and incomplete native prefix do not agree')
            terminal_failure=dict(failure=failure,prefix=prefix)
        baseline_log=(baseline_case/'ngspice.log').read_text()
        old_failure=pilot.failure.failure(baseline_log);old_prefix=pilot.failure.prefix(baseline_case/'bench.raw')
        if not abort_time_agrees(old_prefix['last_time_s'],baseline_log):raise ValueError('Baseline abort metadata changed')
        paths=[out/n for n in ['manifest.json','state.json','summary.json',*r['files']]]
        paths += [baseline_case/n for n in ['summary.json',*br['files']]]
        paths += [Path(__file__),Path(pilot.__file__),Path(pilot.source.__file__),Path(pilot.baseline.__file__),
                  ROOT/'scripts/native_binary_raw_v2.py',ROOT/'scripts/run_native_binary_v2.py',ROOT/'scripts/diagnose_dcdl_iterations_v3.py']
        pilot.bound(out);identity=dict(version=VERSION,parent=str(out.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):pilot.sha(p) for p in paths})
        if any(pilot.sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Source isolation evidence changed during verification')
        receipt=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        receipt.mkdir(parents=True,exist_ok=False)
        pilot.atomic(receipt/'summary.json',dict(identity=identity,assessment=assessment,source_certificate=cert,
            new_terminal_failure=terminal_failure,baseline_terminal_failure=dict(failure=old_failure,prefix=old_prefix),
            complete_baseline_timing_comparison_available=False,qualified_phy=False,legal_code_table_admitted=False,
            scope='Matched native model with a bounded PWL approximation of the tanh stimulus; complete-trace/source verification or terminal-abort diagnosis only, no full-trajectory equivalence, speedup, ROM, all-PVT or PHY admission'))
        return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('artifact',type=Path);p.add_argument('--watch',action='store_true')
    a=p.parse_args();out=a.artifact.resolve()
    if a.watch:
        while not (out/'state.json').exists() or json.loads((out/'state.json').read_text())['status']=='running':time.sleep(10)
    print(verify(out),flush=True)
