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
import probe_actual_nlvt_bank_v32 as original
import verify_actual_nlvt_bank_v32 as original_proof
import probe_tg_component_bank_v23 as source
import verify_tg_component_bank_v23 as baseline_proof
import recover_tg_component_rc_v8 as recovery
import measure_tg_component_rc_v8 as measurement

previous = recovery.producer
helper = previous.previous.previous.original
ROOT = previous.ROOT
VERSION = 'actual-low-vt-driver-guard2-component-rc-zero-screen-v36.1'
CONTEXT = 'nlvt_guard2_bank_v36'
SCOPE = ('Complete actual-component-RC 903-MOS bank with a real independently verified native 2x2 MIM guard '
         'on the fine driver or both data drivers; verified actual stacked TG/coarse-buffer/fine-unit RC retained; '
         'all 93 fine gates and 40 actual TG gates observed; zero SS/40 C only; no SC control/common/tail-cap '
         'routing extraction, complete sparse/dense/update/periodic-duty/all-PVT, whole-bank or PHY qualification')


def specifications():
    return [dict(original.specifications()[0],profile=p) for p in circuit.PROFILES]


def libraries(evidence, guard_evidence):
    receipt=json.loads((evidence/'summary.json').read_text());binding=receipt['identity'];parent=ROOT/binding['parent']
    if (evidence.parent != ROOT/'build/diagnostics'/original_proof.CONTEXT
            or not receipt['all_declared_cases_consumed'] or receipt['qualified_phy']
            or original_proof.verify(parent) != evidence):
        raise ValueError('Require independently verified actual-component-RC timing failure')
    pm=original.bound(parent);pi=pm['identity'];row=receipt['rows'][0]
    if (len(receipt['rows']) != 1 or row['task']['spec'] != original.specifications()[0]
            or row['result']['zero_code_fast_quarter_headroom_ps'] >= 0
            or not row['result']['terminal_screen_passed'] or not row['result']['control_settling_passed']):
        raise ValueError('Require timing-only zero-code failure before guard reduction')
    guard,paths,gi,provenance=circuit.witnesses(guard_evidence)
    if gi['evidence'] != pi['data_evidence']:
        raise ValueError('Smaller guard and data bank have different original physical components')
    cells={};banks={};devices={};gates={};changes={};tg_gates={}
    mapping={p:'0' if p=='VGND' else 'VDD' if p=='VPWR' else p for p in source.circuit.controls.dimensions.ports()}
    c0=(parent/'cells_actual_nlvt.spice').read_text();b0=(parent/'bank_actual_nlvt.spice').read_text()
    for profile in circuit.PROFILES:
        c,b,change=circuit.transform(c0,b0,guard,profile)
        ds=helper.circuit.native.mapped_mos(c+b,circuit.name(profile),mapping,'XD')
        if (len(ds) != 903 or len({d['name'] for d in ds}) != 903
                or Counter((d['model'],d['limit_v']) for d in ds) != Counter((d['model'],d['limit_v']) for d in pi['devices']['actual_nlvt'])):
            raise ValueError('Guard reduction changed native MOS models or voltage limits')
        g=pi['tg_control_gates']['actual_nlvt'];f=pi['fine_control_gates']['actual_nlvt'];mapped={d['name']:d for d in ds}
        if any(x['device'] not in mapped or mapped[x['device']]['terminals'][1] != x['gate_node'] for x in g+f):
            raise ValueError('Guard reduction changed actual control-gate coverage')
        cells[profile]=c;banks[profile]=b;devices[profile]=ds;gates[profile]=f;tg_gates[profile]=g
        changes[profile]=dict(pi['changes']['actual_nlvt'],**change,guard_provenance=provenance)
    paths += [evidence/'summary.json',*[ROOT/n for n in binding['inputs']]]
    paths += [parent/'manifest.json',*[parent/n for n in pm['libraries']],*[ROOT/n for n in pi['inputs']]]
    return cells,banks,devices,gates,changes,paths,circuit.baseline.merge_files(pi['pdk_files'],pi['external_files'],gi['external_files']),str(parent.relative_to(ROOT)),tg_gates


def fixture(out,spec,devices):
    text=original.fixture(out,dict(spec,profile='actual_nlvt'),devices)
    title='OpenLVDS '+original.VERSION+'\n';instance=' '+original.circuit.name('actual_nlvt')+'\n'
    if not text.startswith(title) or text.count(instance) != 1: raise ValueError('Matched smaller-guard fixture changed')
    text='OpenLVDS '+VERSION+'\n'+text[len(title):].replace(instance,' '+circuit.name(spec['profile'])+'\n',1)
    for kind in ('cells','bank'):
        old=f'.include "{out}/{kind}_actual_nlvt.spice"'
        if text.count(old) != 1: raise ValueError('Matched guard fixture include changed')
        text=text.replace(old,f'.include "{out}/{kind}_{spec["profile"]}.spice"',1)
    return text


def measure(folder,spec,devices,gates,tg_gates):
    result=original.measure(folder,spec,devices,gates,tg_gates)
    result.update(scope=SCOPE,actual_guard2_driver_instances=list(circuit.PROFILES[spec['profile']]),
                  guard2_component_rc_physically_equivalent=True,whole_bank_rc_retained=False,
                  electrical_qualification_passed=False,qualified_phy=False)
    return result


def prepare(evidence, guard_evidence):
    if helper.engine() != 'ngspice':
        raise ValueError('Require pinned native ngspice')
    cells, banks, devices, gates, changes, paths, pdk_files, baseline, tg_gates = libraries(evidence, guard_evidence)
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT/'scripts'})
    cad = changes[next(iter(circuit.PROFILES))]['component_provenance']['cad_python']
    tg_cad = changes[next(iter(circuit.PROFILES))]['tg_provenance']['cad_python']
    if tg_cad['path'] == cad['path'] and tg_cad['sha256'] != cad['sha256']:
        raise ValueError('CAD interpreter witnesses disagree')
    identity = dict(version=VERSION, evidence=str(evidence.relative_to(ROOT)), guard_evidence=str(guard_evidence.relative_to(ROOT)), parent=baseline,
                    external_files={cad['path']: cad['sha256'], tg_cad['path']: tg_cad['sha256']},
                    inputs={str(p.relative_to(ROOT)): helper.sha(p) for p in paths}, pdk_files=pdk_files,
                    simulator=helper.provenance(), devices=devices, fine_control_gates=gates, tg_control_gates=tg_gates, changes=changes,
                    specs=specifications(), max_workers=2, scope=SCOPE)
    out = ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    for profile in circuit.PROFILES:
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
            or any(len(i['devices'][p]) != 903 or len(i['fine_control_gates'][p]) != 93 or len(i['tg_control_gates'][p]) != 40 for p in circuit.PROFILES)
            or set(m['libraries']) != {f'{kind}_{profile}.spice' for kind in ('cells', 'bank') for profile in circuit.PROFILES}
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
    p.add_argument('--guard-evidence',type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        if a.guard_evidence is None: p.error('--guard-evidence is required')
        print(prepare(a.artifact.resolve(),a.guard_evidence.resolve()), flush=True)
    else:
        run(a.artifact.resolve())
