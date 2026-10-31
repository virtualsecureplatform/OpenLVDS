#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Queue isolated native-RC DLL qualification after an architecture screen passes.

This produces DLL electrical evidence only. It never promotes a circuit or
qualifies the complete PHY, the six-fixture fast-RC certificate, or a link.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
from dll_campaign import atomic, bias_reference_count, validate as validate_screen
from dll_candidate_library import assemble
import dll_measurements as measure
from dll_qualification_measurements import marker_latency, compare
from run_ngspice import read_raw
from spice_engine import command, engine, provenance
from spice_probes import ProbeNetwork
from spice_slots import slot
from stability_evidence import verified as stability_verified
from verify_phase_detector import response_cases

ROOT = Path(__file__).resolve().parents[1]
CODE = ['qualify_dll_candidate.py', 'dll_candidate_library.py', 'dll_qualification_measurements.py',
        'dll_measurements.py', 'dll_campaign.py', 'digital_candidate_rc.py', 'dll_design.py',
        'layout.py', 'physical_policy.py', 'spice_library.py', 'spice_scope.py', 'rc_fast.py',
        'reduce_rc.py', 'run_ngspice.py', 'spice_engine.py', 'verify_phase_detector.py', 'lvs_utils.py', 'spice_probes.py', 'spice_slots.py','stability_evidence.py']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def code_hashes():
    return {n: sha((ROOT / 'scripts' / n).read_bytes()) for n in CODE}


def pulse(node, mhz, duty=.5, center_ns=5, slew_ps=100):
    period = 1000 / mhz
    ramp = slew_ps / 1000
    return f'V{node} {node} 0 PULSE(0 1.8 {center_ns-ramp/2:.12g}n {slew_ps}p {slew_ps}p {duty*period-ramp:.12g}n {period:.12g}n)\n'


def clock_wave(stop_ns, mhz, duty=.5, marker_ns=None, step_mhz=None, interruption=False):
    period = 1000 / mhz
    at = 5.
    rises = []
    while at < stop_ns:
        current = 1000 / step_mhz if step_mhz and at >= 1100-1e-6 else period
        rises.append((at, current))
        at += current
    marker = None if marker_ns is None else min(rises, key=lambda row:abs(row[0]-marker_ns))[0]
    points = [(0, 0)]
    for at, current in rises:
        omit = (marker is not None and abs(at-marker) < 1e-6) or (interruption and 1000 <= at < 1100)
        if not omit:
            points += [(at-.05, 0), (at+.05, 1.8), (at+duty*current-.05, 1.8), (at+duty*current+.05, 0)]
    text = 'VCLK CLK 0 PWL(' + ' '.join(f'{t:.12g}n {v:g}' for t, v in points) + ')\n'
    return text, marker


def clock_coverage(requirements):
    """All nine clock/duty points at nominal and the limiting fast/slow corners."""
    return list(itertools.product([('tt',25),('ss',0),('ff',0)],
                                 requirements['clock_test_mhz'],requirements['clock_duty']))


def recovery_coverage():
    return list(itertools.product([('tt',25),('ss',0),('ff',0)],[390,410,None]))


def loop_fixture(spec, observations=None):
    step = spec.get('step_mhz')
    recovery = spec.get('interruption', False)
    stop = 2700 if step or recovery else 1700
    marker_target = 2600 if step or recovery else 1600
    clock, marker = clock_wave(stop, spec['mhz'], spec['duty'],
                              marker_ns=marker_target,
                              step_mhz=step, interruption=recovery)
    pd_start=5+32*1000/spec['mhz']+.2
    enable = f'0 0 {pd_start:.12g}n 0 {pd_start+.02:.12g}n 1.8'
    if recovery:
        enable += ' 1010n 1.8 1010.02n 0 1180.2n 0 1180.22n 1.8'
    body = (clock + 'VRST RST 0 PWL(0 0 2n 0 2.02n 1.8)\n'
            f'VEN ENABLE 0 PWL({enable})\nVREF VREF 0 1.2\n'
            'XL CLK RST ENABLE PH0 PH90 PH180 PH270 FB BAD UP DN VREF PB VDDIO VDDD 0 openlvds_dll\n'
            'C0 PH0 0 40f\nC90 PH90 0 40f\nC180 PH180 0 20f\nC270 PH270 0 20f\nCFB FB 0 20f\n')
    probes = {n: n for n in ['CLK', 'PH0', 'PH90', 'PH180', 'PH270', 'FB', 'BAD', 'UP', 'DN']}
    probes['PD_REF'] = 'XL:XCORE:PD_REF'
    for n in ['CTRL', 'UF', 'DF']:
        probes[n] = 'XL:XCORE:XA:openlvds_dll_analog__' + n
    if spec['architecture'] == 'charge_pump':
        probes['COPY'] = 'XL:XCORE:XA:openlvds_dll_analog__VCOPY'
    if observations:
        for name, nodes in observations.items():
            for index, node in enumerate(nodes):
                alias = name if index == 0 else name+'_CAP_'+str(index)
                probes[alias] = 'XL:XCORE:XA:' + node
    return body, probes, stop, dict(marker_ns=marker, start_ns=2100 if step or recovery else 1200,
                                   end_ns=2400 if step or recovery else 1500)


def phase_fixture(spec, observations=None):
    body = ('XB PB NB VDDIO 0 lvds_bias\n'
            'XA 0 VDDD PH0 PH90 PH180 PH270 FB PD_REF BAD UP DN PB VDDIO VDDD 0 openlvds_dll_analog\nCB BAD 0 20f\n')
    probes = {n: n for n in ['UP', 'DN', 'BAD']}
    for n in ['CTRL', 'UF', 'DF']:
        probes[n] = 'XA:openlvds_dll_analog__' + n
    if observations:
        probes['CTRL'] = 'XA:' + observations['CTRL'][0]
    if spec['kind'] == 'logic':
        body += f'VU UP 0 {spec["up"]:g}\nVN DN 0 {spec["dn"]:g}\n'
    else:
        body += ('VRST RST 0 PWL(0 0 2n 0 2.1n 1.8)\n' +
                 pulse('REF', spec['mhz'], center_ns=5, slew_ps=spec['reference_slew_ps']) +
                 pulse('FDB', spec['mhz'], center_ns=5+spec['offset_ps']/1000, slew_ps=spec['feedback_slew_ps']) +
                 'XP REF FDB RST VDDD UP DN VDDD 0 lvds_pfd\n')
        probes.update(REF='REF', FDB='FDB')
    return body, probes, 160, dict(start_ns=120, end_ns=160)


def prepare(layout, pfd, screen, variant):
    if engine() != 'ngspice':
        raise ValueError('Use the pinned --ngspice environment')
    source = (layout/'candidate.spice').read_bytes()
    if source != (screen/'inputs'/(variant+'.spice')).read_bytes():
        raise ValueError('Physical candidate differs from the screened architecture')
    full, full_models = assemble(layout, pfd, False)
    fast, fast_models = assemble(layout, pfd, True)
    req = (ROOT/'requirements.json').read_bytes()
    requirements = json.loads(req)
    identity = dict(code=code_hashes(), simulator_provenance=provenance(), requirements_sha256=sha(req),
                    full_library_sha256=sha(full.encode()), fast_library_sha256=sha(fast.encode()),
                    full_models=full_models, fast_models=fast_models, variant=variant,
                    screen=str(screen.relative_to(ROOT)), screen_manifest_sha256=sha((screen/'manifest.json').read_bytes()))
    root = ROOT/'build/diagnostics/dll_qualification'/sha(json.dumps(identity, sort_keys=True).encode())[:16]
    if (root/'manifest.json').exists():
        return root
    root.mkdir(parents=True, exist_ok=True)
    for filename, text in [('full.spice', full), ('fast.spice', fast)]:
        (root/filename).write_text(text)
    (root/'requirements.json').write_bytes(req)
    for name in CODE:
        (root/name).write_bytes((ROOT/'scripts'/name).read_bytes())
    architecture = 'averaged_pfd_ota' if variant.startswith('ota_') else 'charge_pump'
    tasks = []
    verified_bias = set()
    probe_networks = {False: ProbeNetwork(full), True: ProbeNetwork(fast)}
    pdk = Path(os.environ['PDK_ROOT'])/'sky130A/libs.tech/ngspice/sky130.lib.spice'

    def add(name, spec, needs=(), fast_rc=False):
        out = root/name
        out.mkdir()
        if spec['kind'] == 'loop':
            body, probes, stop, timing = loop_fixture(spec, full_models['observation_nodes'])
        else:
            body, probes, stop, timing = phase_fixture(spec, full_models['observation_nodes'])
        text = (f'OpenLVDS native DLL qualification {name}\n.lib "{pdk}" {spec["process"]}\n'
                f'.include "{root}/{"fast" if fast_rc else "full"}.spice"\n'
                f'.options device temp={spec["temperature"]}\n'
                '.options timeint method=gear reltol=1e-4 abstol=1e-12\n'
                'VA VDDIO 0 3.3\nVD VDDD 0 1.8\nIB PB 0 35u\n' + body +
                f'.save i(VA) i(VD)\n.tran 5p {stop}n 0 20p\n.print tran ' +
                ' '.join('V('+node+')' for node in probes.values())+'\n.end\n')
        signature = (spec['kind'], fast_rc)
        if signature not in verified_bias:
            if bias_reference_count(text, fast if fast_rc else full) != 1:
                raise ValueError('DLL fixture duplicates its bias generator')
            verified_bias.add(signature)
        probe_networks[fast_rc].validate(text, probes.values())
        (out/'bench.cir').write_text(text)
        tasks.append(dict(id=name, spec=dict(spec, stop_ns=stop, **timing), aliases=probes,
                          needs=list(needs), fast_rc=fast_rc, deck_sha256=sha(text.encode())))
        return name

    # First catch gross physical regressions before dispatching the full matrix.
    basic = []
    for offset in [0, 150, -150, 50, -50]:
        basic.append(add(f'phase_tt_25_{offset}ps', dict(kind='phase', process='tt', temperature=25,
                         offset_ps=offset, mhz=400, reference_slew_ps=100, feedback_slew_ps=100)))
    full_faults = list(basic)
    # Qualify the historically limiting slow corner before expanding the matrix.
    early = {}
    ss_basic=[]
    for offset in [0,150,-150,50,-50,300,-300]:
        ss_basic.append(add(f'phase_ss_0_{offset}ps',dict(kind='phase',process='ss',temperature=0,
            offset_ps=offset,mhz=400,reference_slew_ps=100,feedback_slew_ps=100)))
    early['ss']=add('loop_ss_0',dict(kind='loop',process='ss',temperature=0,mhz=400,duty=.5,architecture=architecture),ss_basic)
    nominal = add('loop_tt_25', dict(kind='loop', process='tt', temperature=25, mhz=400, duty=.5, architecture=architecture), basic+[early['ss']])
    early['ff']=add('loop_ff_0',dict(kind='loop',process='ff',temperature=0,mhz=400,duty=.5,architecture=architecture),
        [nominal]+[f'phase_ff_0_{o}ps' for o in [0,50,-50,150,-150,300,-300]])
    full_faults+=ss_basic
    add('fast_loop_tt_25', dict(kind='loop', process='tt', temperature=25, mhz=400, duty=.5, architecture=architecture), [nominal], True)
    for process, temp, offset, sr, sf in response_cases(corners=True):
        name = f'phase_{process}_{temp}_{offset}ps'
        if name in basic+ss_basic:
            continue
        full_faults.append(add(name, dict(kind='phase', process=process, temperature=temp, offset_ps=offset,
                               mhz=400, reference_slew_ps=sr, feedback_slew_ps=sf), basic))
    for process, temp, offset, sr, sf in response_cases(slew_corners=True):
        full_faults.append(add(f'slew_{process}_{temp}_{offset}ps_{sr}_{sf}', dict(kind='phase', process=process,
                               temperature=temp, offset_ps=offset, mhz=400, reference_slew_ps=sr, feedback_slew_ps=sf), basic))
    for mhz, (process, temp), offset in itertools.product([390, 410], [('ss', 0), ('tt', 25), ('ff', 0)], [0, 50, -50, 150, -150, 300, -300]):
        full_faults.append(add(f'frequency_{mhz}_{process}_{temp}_{offset}ps', dict(kind='phase', process=process,
                               temperature=temp, offset_ps=offset, mhz=mhz, reference_slew_ps=100, feedback_slew_ps=100), basic))
    for process, temp, up, dn in itertools.product(requirements['process_corners'], requirements['temperatures_c'], [0, 1.8], [0, 1.8]):
        full_faults.append(add(f'stuck_{process}_{temp}_{up:g}_{dn:g}', dict(kind='logic', process=process,
                               temperature=temp, up=up, dn=dn, expected=True), basic))
    comparisons = [dict(full=nominal, fast='fast_loop_tt_25')]
    for (process, temp), offset in itertools.product([('ss', 0), ('tt', 25), ('ff', 0)], [0, 150, -150]):
        full_name = f'phase_{process}_{temp}_{offset}ps'
        fast_name = add('fast_'+full_name, dict(kind='phase', process=process, temperature=temp, offset_ps=offset,
                       mhz=400, reference_slew_ps=100, feedback_slew_ps=100), [full_name], True)
        comparisons.append(dict(full=full_name, fast=fast_name))
    for process, temp in itertools.product(requirements['process_corners'], requirements['temperatures_c']):
        if (process, temp) not in [('tt',25),('ss',0),('ff',0)]:
            add(f'loop_{process}_{temp}', dict(kind='loop', process=process, temperature=temp, mhz=400,
                duty=.5, architecture=architecture), [nominal]+full_faults)
    for (process,temp), mhz, duty in clock_coverage(requirements):
        if (mhz, duty) != (400, .5):
            suffix='' if (process,temp)==('tt',25) else f'_{process}_{temp}'
            add(f'clock_{mhz}_{duty}'+suffix, dict(kind='loop', process=process, temperature=temp, mhz=mhz,
                duty=duty, architecture=architecture), [nominal]+full_faults)
    for (process,temp), target in recovery_coverage():
        suffix='' if (process,temp)==('tt',25) else f'_{process}_{temp}'
        name='clock_loss_rearm' if target is None else f'step_400_to_{target}'
        add(name+suffix, dict(kind='loop', process=process, temperature=temp, mhz=400, duty=.5,
            step_mhz=target, interruption=target is None, architecture=architecture), [nominal]+full_faults)
    def dispatch_priority(task):
        name=task['id']
        for index,prefix in enumerate(['phase_ss_0_', 'loop_ss_0', 'phase_tt_25_', 'loop_tt_25', 'phase_ff_0_', 'loop_ff_0']):
            if name.startswith(prefix):return index
        return 6
    tasks.sort(key=dispatch_priority)
    atomic(root/'manifest.json', dict(identity=identity, tasks=tasks, comparisons=comparisons,
                                      diagnostic=True, qualified=False, complete_phy_suite=False))
    atomic(root/'state.json', dict(status='prepared', tasks={t['id']:dict(status='pending') for t in tasks}))
    return root


def validate(root, manifest):
    identity = manifest['identity']
    if code_hashes() != identity['code'] or provenance() != identity['simulator_provenance']:
        raise ValueError('DLL qualification producer or simulator changed')
    for filename, key in [('full.spice', 'full_library_sha256'), ('fast.spice', 'fast_library_sha256'), ('requirements.json', 'requirements_sha256')]:
        if sha((root/filename).read_bytes()) != identity[key]:
            raise ValueError('Captured qualification input changed')
    for path, stamp in identity['full_models']['physical_reports'].items():
        if sha((ROOT/path).read_bytes()) != stamp:
            raise ValueError('Physical candidate evidence changed')


def screen_status(manifest):
    identity = manifest['identity']
    folder = ROOT/identity['screen']
    if sha((folder/'manifest.json').read_bytes()) != identity['screen_manifest_sha256']:
        raise ValueError('Architecture-screen manifest changed')
    screen = json.loads((folder/'manifest.json').read_text())
    selected = [t for t in screen['tasks'] if t['spec'].get('variant') == identity['variant'] and t['spec']['kind'] == 'loop']
    if len(selected) != 3:
        raise ValueError('Need all three architecture-screen corners')
    state = json.loads((folder/'state.json').read_text()).get('tasks', {})
    waiting = False
    for task in selected:
        if state.get(task['id'], {}).get('status') in ['failed', 'skipped']:
            return 'failed'
        report = folder/task['id']/'summary.json'
        if not report.exists():
            waiting = True
            continue
        validate_screen(folder, screen, task)
        result = json.loads(report.read_text())
        if result.get('input_files') != task['files']:
            raise ValueError('Stale architecture-screen result')
        if not result.get('passed'):
            return 'failed'
        wave_file = report.parent/'bench.cir.prn'
        if sha(wave_file.read_bytes()) != result.get('waveform_sha256'):
            raise ValueError('Architecture-screen waveform changed')
        wave, header = measure.read_wave(wave_file)
        for alias, node in task['aliases'].items():
            header['V('+alias.upper()+')'] = header['V('+node.upper()+')']
        if not measure.loop(wave, header, 400, task['spec']['architecture'])['passed']:
            return 'failed'
    return 'waiting' if waiting else 'passed'


def evaluate(root, task):
    out = root/task['id']
    wave, header = measure.read_wave(out/'bench.cir.prn')
    for alias, node in task['aliases'].items():
        header['V('+alias.upper()+')'] = header['V('+node.upper()+')']
    spec = task['spec']
    if spec['kind'] == 'phase':
        result = measure.phase(wave, header, spec['offset_ps'])
    elif spec['kind'] == 'logic':
        result = measure.logic(wave, header, spec['expected'])
    else:
        result = measure.loop(wave, header, spec.get('step_mhz', spec['mhz']), spec['architecture'], spec['start_ns'], spec['end_ns'])
        keep = (wave[:, 1] >= spec['start_ns']*1e-9) & (wave[:, 1] <= spec['end_ns']*1e-9)
        storage = {name: np.array([measure.column(wave, header, alias)[keep] for alias in task['aliases']
                   if alias == name or alias.startswith(name+'_CAP_')]) for name in ['CTRL', 'COPY']}
        result['passed'] = bool(result['passed'] and np.all(storage['CTRL'] >= 0) and np.all(storage['CTRL'] <= 1.95))
        result['storage_plate_spread_max_mv'] = float(np.max(np.ptp(storage['CTRL'], axis=0))*1000)
        if spec['architecture'] == 'charge_pump':
            error = max(float(np.max(abs(a-b))*1000) for a in storage['CTRL'] for b in storage['COPY'])
            result.update(all_storage_copy_error_max_mv=error, passed=bool(result['passed'] and error < 50))
        else:
            ripple = max(float(np.ptp(v)*1000) for v in storage['CTRL'])
            result.update(all_storage_ripple_pp_max_mv=ripple, passed=bool(result['passed'] and ripple < 20))
        if spec['marker_ns'] is not None:
            result['marker'] = marker_latency(wave, header, spec.get('step_mhz', spec['mhz']), spec['marker_ns'])
            result['passed'] &= result['marker']['passed']
        if spec.get('interruption'):
            keep = (wave[:, 1] > 1050e-9) & (wave[:, 1] < 1095e-9)
            high = bool(np.any(keep) and np.all(measure.column(wave, header, 'BAD')[keep] > 1.44))
            result.update(clock_loss_detected=high, passed=bool(result['passed'] and high))
    result['complete'] = measure.complete(wave, spec['stop_ns'])
    result['passed'] = bool(result['passed'] and result['complete'])
    return result


def execute(root, manifest, task):
    validate(root, manifest)
    out = root/task['id']
    if sha((out/'bench.cir').read_bytes()) != task['deck_sha256']:
        raise ValueError('Captured DLL fixture changed')
    previous = out/'summary.json'
    if previous.exists():
        result = json.loads(previous.read_text())
        if result.get('waveform_sha256') != sha((out/'bench.cir.prn').read_bytes()) or result.get('task') != task['id']:
            raise ValueError('DLL qualification trace changed')
        if result['metrics'] != evaluate(root, task):
            raise ValueError('DLL qualification analysis changed')
        return result
    started = time.time()
    atomic(out/'execution.json',dict(status='waiting_for_slot'))
    with slot():
        atomic(out/'execution.json',dict(status='running',started_unix=time.time()))
        run = subprocess.run(command(out/(engine()+'.log'), out/'bench.cir'), cwd=out, capture_output=True, text=True)
    (out/'console.log').write_text(run.stdout+run.stderr)
    result = dict(passed=False, task=task['id'], deck_sha256=task['deck_sha256'], returncode=run.returncode,
                  diagnostic=True, qualified=False, wall_seconds=time.time()-started)
    if run.returncode == 0:
        try:
            result['metrics'] = evaluate(root, task)
            result['passed'] = result['metrics']['passed']
            result['waveform_sha256'] = sha((out/'bench.cir.prn').read_bytes())
            names, raw = read_raw(out/'bench.raw')
            columns = {n:i for i,n in enumerate(names)}
            keep = (raw[:, columns['time']] >= task['spec']['start_ns']*1e-9) & (raw[:, columns['time']] <= task['spec']['end_ns']*1e-9)
            power = -3.3*raw[keep,columns['i(va)']]-1.8*raw[keep,columns['i(vd)']]
            result['mean_power_mw'] = measure.average(raw[keep,columns['time']], power)*1000
            result['raw_sha256'] = sha((out/'bench.raw').read_bytes())
        except (ValueError, KeyError, OSError) as e:
            result.update(passed=False, error=str(e))
    validate(root, manifest)
    atomic(previous, result)
    print(task['id'], result['passed'], flush=True)
    return result


def screen_task(task):
    return task['id'] in ['loop_ss_0','loop_tt_25','loop_ff_0'] or any(task['id'].startswith(p) for p in ['phase_ss_0_','phase_tt_25_','phase_ff_0_'])


def run(root, jobs, stage='screen', stability=None):
    manifest = json.loads((root/'manifest.json').read_text())
    if stage=='full':
        if stability is None:raise ValueError('Full expansion requires a measured stability report')
        stability_verified(stability,manifest['identity']['full_models']['inputs'])
    atomic(root/'state.json', dict(status='waiting_for_architecture_screen', tasks={t['id']:dict(status='pending') for t in manifest['tasks']}))
    while True:
        status = screen_status(manifest)
        if status != 'waiting':
            break
        time.sleep(10)
    if status != 'passed':
        atomic(root/'state.json', dict(status='rejected_by_architecture_screen', passed=False, qualified=False))
        return 1
    # Per-worker slots coexist with the frozen legacy RX campaign. The old
    # whole-campaign lease remains untouched for that producer.
    lease = root/'.execution.lock'
    with lease.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        validate(root, manifest)
        state = {t['id']:dict(status='pending' if stage=='full' or screen_task(t) else 'held_for_stability') for t in manifest['tasks']}
        active = {}
        tasks = {t['id']:t for t in manifest['tasks']}
        results = {}
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            while True:
                for key, future in list(active.items()):
                    if not future.done():
                        execution=root/key/'execution.json'
                        if execution.exists():state[key].update(json.loads(execution.read_text()))
                        continue
                    try:
                        result = future.result()
                    except Exception as e:
                        result = dict(passed=False, error=str(e))
                    results[key] = result
                    state[key].update(status='passed' if result['passed'] else 'failed')
                    del active[key]
                for key, task in tasks.items():
                    if state[key]['status'] != 'pending':
                        continue
                    needed = [state[n]['status'] for n in task['needs']]
                    if any(s in ['failed', 'skipped'] for s in needed):
                        state[key].update(status='skipped', error='Prerequisite failed')
                        continue
                    if any(s != 'passed' for s in needed) or len(active) >= jobs:
                        continue
                    active[key] = pool.submit(execute, root, manifest, task)
                    state[key].update(status='running', started_unix=time.time())
                atomic(root/'state.json', dict(status='running', tasks=state, max_jobs=jobs))
                if not active and not any(r['status'] == 'pending' for r in state.values()):
                    break
                time.sleep(2)
        if stage=='screen':
            passed=all(v['status']=='passed' for k,v in state.items() if screen_task(tasks[k]))
            atomic(root/'screen_summary.json',dict(passed=passed,qualified=False,tasks=state,
                full_inputs=manifest['identity']['full_models']['inputs']))
            atomic(root/'state.json',dict(status='screen_passed' if passed else 'completed_with_failures',tasks=state))
            return 0 if passed else 1
        comparisons = []
        for pair in manifest['comparisons']:
            names = [pair['full'], pair['fast']]
            if not all(state[n]['status'] == 'passed' for n in names):
                comparisons.append(dict(pair=pair, passed=False, error='Missing passing full/fast pair'))
                continue
            traces = []
            for name in names:
                wave, header = measure.read_wave(root/name/'bench.cir.prn')
                for alias, node in tasks[name]['aliases'].items():
                    header['V('+alias.upper()+')'] = header['V('+node.upper()+')']
                traces.extend([wave, header])
            spec = tasks[names[0]]['spec']
            check = compare(*traces, list(tasks[names[0]]['aliases']), spec['start_ns'], spec['end_ns'])
            comparisons.append(dict(pair=pair, **check))
        passed = all(r['status'] == 'passed' for r in state.values()) and all(r['passed'] for r in comparisons)
        atomic(root/'summary.json', dict(passed=passed, qualified=False, complete_phy_suite=False,
                                        manifest_sha256=sha((root/'manifest.json').read_bytes()),
                                        tasks=state, dll_full_fast_comparisons=comparisons))
        atomic(root/'state.json', dict(status='completed' if passed else 'completed_with_failures', tasks=state))
        return 0 if passed else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', nargs='?', type=Path)
    p.add_argument('--layout', type=Path)
    p.add_argument('--pfd', type=Path)
    p.add_argument('--screen', type=Path)
    p.add_argument('--variant')
    p.add_argument('--jobs', type=int, choices=range(1,7), default=6)
    p.add_argument('--stage', choices=['screen','full'],default='screen')
    p.add_argument('--stability',type=Path)
    a = p.parse_args()
    if a.action == 'prepare':
        if not all([a.layout, a.pfd, a.screen, a.variant]):
            p.error('Prepare requires layout, PFD, architecture screen, and variant')
        root = prepare(a.layout.resolve(), a.pfd.resolve(), a.screen.resolve(), a.variant)
    else:
        if a.artifact is None:
            p.error('Run requires a prepared artifact')
        root = a.artifact.resolve()
    if not root.is_relative_to(ROOT):
        p.error('All artifacts must reside in OpenLVDS')
    print(root, flush=True)
    if a.action == 'run':
        with (root/'.run.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return run(root, a.jobs,a.stage,a.stability)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
