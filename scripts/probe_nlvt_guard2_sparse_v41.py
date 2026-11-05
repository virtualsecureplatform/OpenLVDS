#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Legal NMOS-low-Vt isolation with every original component R/C retained."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from collections import Counter
import nlvt_guard2_bank_v36 as circuit
import probe_nlvt_guard2_bank_v36 as zero
import verify_nlvt_guard2_bank_v36 as zero_proof
import math
import probe_tg_component_bank_v23 as source
import verify_tg_component_bank_v23 as baseline_proof
import recover_tg_component_rc_v8 as recovery
import measure_tg_component_rc_v8 as measurement

previous = recovery.producer
helper = previous.previous.previous.original
ROOT = previous.ROOT
VERSION = 'actual-nlvt-guard2-sparse-with-reused-zero-v41.1'
CONTEXT = 'nlvt_guard2_sparse_v41'
PROFILES = ('both2',)
CODES = ((0,1),(0,15),(0,16),(0,31),(1,0))
SCOPE = ('Five additional SS/40 C static codes using the identical both2 actual-component-RC bank, combined '
         'with its independently verified complete zero-code waveform; all 903 MOS, 93 fine gates and 40 TG '
         'gates retained; original bare tail MIM and SC control/common wiring unchanged; no new tail RC, '
         'whole-bank wiring, dense/update/periodic-duty/all-PVT, electrical or PHY qualification')


def specifications():
    base=next(s for s in zero.specifications() if s['profile']=='both2')
    return [dict(base,coarse=c,fine=f) for c,f in CODES]


def require_zero_pass(report):
    rows=[r for r in report.get('rows',[]) if r['task']['spec']['profile']=='both2']
    profiles=[p for p in report.get('profiles',[]) if p['profile']=='both2']
    if (not report.get('all_consumed_complete_native_waveforms_verified')
            or not report.get('all_declared_cases_consumed') or report.get('qualified_phy') is not False
            or report.get('component_rc_physically_equivalent') is not True
            or report.get('whole_bank_rc_retained') is not False
            or report.get('identity',{}).get('terminal_cases_only') is not False
            or len(report.get('rows',[])) != 2 or len(rows) != 1 or len(profiles) != 1):
        raise ValueError('Require complete independent both2 native zero verification')
    row=rows[0];p=profiles[0];r=row['result']
    expected=next(s for s in zero.specifications() if s['profile']=='both2')
    if (row['task']['spec'] != expected or not p['zero_code_native_gate_passed']
            or p['completed_sparse_points'] != 1 or p['all_sparse_points_present']
            or not all(r[k] for k in ('terminal_screen_passed','control_settling_passed','onehot_control_settling_passed'))
            or not math.isfinite(r['zero_code_fast_quarter_headroom_ps']) or r['zero_code_fast_quarter_headroom_ps'] <= 0
            or set(r['repeated_delay_difference_ps']) != {'rise','fall'}
            or not all(math.isfinite(v) and 0 <= v <= 20 for v in r['repeated_delay_difference_ps'].values())):
        raise ValueError('Selected both2 zero timing, voltage, control or repeatability gate failed')
    return row


def inherited(evidence):
    receipt=json.loads((evidence/'summary.json').read_text());binding=receipt['identity'];row=require_zero_pass(receipt)
    if (evidence.parent != ROOT/'build/diagnostics'/zero_proof.CONTEXT or binding['version'] != zero_proof.VERSION
            or evidence.name != hashlib.sha256(json.dumps(binding,sort_keys=True).encode()).hexdigest()[:16]
            or binding['case_ids'] != ['0','1'] or any(helper.sha(ROOT/n) != h for n,h in binding['inputs'].items())):
        raise ValueError('Independent native zero receipt or its complete input closure changed')
    parent=ROOT/binding['parent'];m=zero.bound(parent);i=m['identity']
    if json.loads((parent/'state.json').read_text()) != dict(status='complete',cases=2,errors=0,qualified_phy=False):
        raise ValueError('Both zero diagnostics must be numerically complete')
    task=row['task'];folder=parent/task['id'];original=json.loads((folder/'summary.json').read_text())
    if task != m['tasks'][int(task['id'])] or original['task'] != task or original['error'] is not None or original['result'] != row['result']:
        raise ValueError('Inherited zero task or measured result changed')
    # Reuse the immutable independent proof, then remeasure the selected full
    # zero waveform. Do not recursively rerun upstream proof creation or SPICE.
    if zero.measure(folder,task['spec'],i['devices']['both2'],i['fine_control_gates']['both2'],i['tg_control_gates']['both2']) != row['result']:
        raise ValueError('Selected complete zero waveform cannot be remeasured')
    zero.bound(parent)
    if any(helper.sha(ROOT/n) != h for n,h in binding['inputs'].items()):
        raise ValueError('Independent zero inputs changed during remeasurement')
    return receipt,row,parent,m


def libraries(evidence):
    receipt,row,parent,m=inherited(evidence);i=m['identity'];profile='both2'
    cells={profile:(parent/'cells_both2.spice').read_text()};banks={profile:(parent/'bank_both2.spice').read_text()}
    paths=[evidence/'summary.json',*[ROOT/n for n in receipt['identity']['inputs']]]
    paths += [parent/'manifest.json',*[parent/n for n in m['libraries']],*[ROOT/n for n in i['inputs']]]
    return (cells,banks,{profile:i['devices'][profile]},{profile:i['fine_control_gates'][profile]},
            {profile:i['changes'][profile]},paths,circuit.baseline.merge_files(i['pdk_files'],i['external_files']),
            str(parent.relative_to(ROOT)),{profile:i['tg_control_gates'][profile]})


def fixture(out,spec,devices):
    text=zero.fixture(out,spec,devices);title='OpenLVDS '+zero.VERSION+'\n'
    if not text.startswith(title):raise ValueError('Matched sparse continuation fixture changed')
    return 'OpenLVDS '+VERSION+'\n'+text[len(title):]


def measure(folder,spec,devices,gates,tg_gates):
    result=zero.measure(folder,spec,devices,gates,tg_gates)
    result.update(scope=SCOPE,reused_zero_case=False)
    return result


def prepare(evidence):
    if helper.engine() != 'ngspice':
        raise ValueError('Require pinned native ngspice')
    cells, banks, devices, gates, changes, paths, pdk_files, baseline, tg_gates = libraries(evidence)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    cad = changes[next(iter(PROFILES))]['component_provenance']['cad_python']
    tg_cad = changes[next(iter(PROFILES))]['tg_provenance']['cad_python']
    if tg_cad['path'] == cad['path'] and tg_cad['sha256'] != cad['sha256']:
        raise ValueError('CAD interpreter witnesses disagree')
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)), parent=baseline,
                    external_files={cad['path']: cad['sha256'], tg_cad['path']: tg_cad['sha256']},
                    inputs={str(p.relative_to(ROOT)): helper.sha(p) for p in paths}, pdk_files=pdk_files,
                    simulator=helper.provenance(), devices=devices, fine_control_gates=gates, tg_control_gates=tg_gates, changes=changes,
                    specs=specifications(), max_workers=2, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    for profile in PROFILES:
        helper.write(out/f'cells_{profile}.spice', cells[profile]); helper.write(out/f'bank_{profile}.spice', banks[profile])
    tasks = []
    for n, spec in enumerate(identity['specs']):
        folder = out/str(n); folder.mkdir()
        helper.write(folder/'bench.cir', fixture(out, spec, devices[spec['profile']]))
        tasks.append(dict(id=str(n), spec=spec, deck_sha256=helper.sha(folder/'bench.cir')))
    helper.atomic(out/'manifest.json', dict(identity=identity, tasks=tasks,
                  libraries={p.name: helper.sha(p) for p in out.glob('*.spice')}, qualified_phy=False))
    return out


def bound(out):
    m = json.loads((out/'manifest.json').read_text()); i = m['identity']
    if (out.parent != ROOT/'build/diagnostics'/CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['specs'] != specifications() or i['max_workers'] != 2
            or any(len(i['devices'][p]) != 903 or len(i['fine_control_gates'][p]) != 93 or len(i['tg_control_gates'][p]) != 40 for p in PROFILES)
            or set(m['libraries']) != {f'{kind}_{profile}.spice' for kind in ('cells', 'bank') for profile in PROFILES}
            or helper.engine() != 'ngspice' or helper.provenance() != i['simulator']
            or any(helper.sha(ROOT/n) != h for n, h in i['inputs'].items())
            or any(helper.sha(Path(n)) != h for n, h in i['pdk_files'].items())
            or any(helper.sha(Path(n)) != h for n, h in i['external_files'].items())
            or any(helper.sha(out/n) != h for n, h in m['libraries'].items()) or len(m['tasks']) != len(i['specs'])):
        raise ValueError('Native driver/selector context changed')
    for n, task in enumerate(m['tasks']):
        if (task['id'] != str(n) or task['spec'] != i['specs'][n]
                or helper.sha(out/str(n)/'bench.cir') != task['deck_sha256']
                or (out/str(n)/'bench.cir').read_text() != fixture(out, task['spec'], i['devices'][task['spec']['profile']])):
            raise ValueError('Native driver/selector task changed')
    return m


def run(out):
    m = bound(out)
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out/'state.json').exists():
            raise ValueError('Retain prior native driver/selector campaign')
        helper.atomic(out/'state.json', dict(status='running', qualified_phy=False))
        def execute(task):
            folder = out/task['id']; result = error = wall = None; profile = task['spec']['profile']
            try:
                with helper.lease(ROOT, priority=0, label=CONTEXT+'_'+task['id']):
                    bound(out); start = time.monotonic()
                    p = subprocess.run([sys.executable, str(ROOT/'scripts/run_native_binary_v2.py'), '-l', str(folder/'ngspice.log'), str(folder/'bench.cir')], capture_output=True, text=True)
                    wall = time.monotonic()-start
                helper.write(folder/'console.log', p.stdout+p.stderr); p.check_returncode()
                result = measure(folder, task['spec'], m['identity']['devices'][profile], m['identity']['fine_control_gates'][profile], m['identity']['tg_control_gates'][profile])
            except Exception as e:
                error = str(e)
            row = dict(task=task, result=result, error=error, solver_wall_seconds=wall,
                       files={p.name: helper.sha(p) for p in folder.iterdir() if p.is_file()})
            helper.atomic(folder/'summary.json', row)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(execute, m['tasks']))
        bound(out); helper.atomic(out/'summary.json', dict(rows=rows, qualified_phy=False, scope=SCOPE))
        helper.atomic(out/'state.json', dict(status='complete', cases=len(rows), errors=sum(r['error'] is not None for r in rows), qualified_phy=False))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run']); p.add_argument('artifact', type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.artifact.resolve()), flush=True)
    else:
        run(a.artifact.resolve())
