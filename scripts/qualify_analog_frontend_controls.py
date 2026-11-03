#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Qualify the admitted analog source frontend's reset/disable and recovery.

Requires the complete independently verified 1,215-case source expansion.
No source, physical, native-loop or PHY gate is replaced by protocol success.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import expand_dll_analog_frontend as expansion
import pfd_control_protocol as protocol
import probe_native_pfd_controls as baseline
from qualify_slew_frontend_controls import points
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'analog_frontend_controls'
sha = expansion.sha
OUTPUTS = expansion.OUTPUTS


def task_plan(report, manifest):
    variant = manifest['identity']['variant']
    expected = expansion.tasks(json.loads((ROOT / 'requirements.json').read_text()), variant)
    tasks = [{k: v for k, v in t.items() if k not in ('aliases', 'deck_sha256')} for t in manifest['tasks']]
    rows = {r['task']: r for r in report['results']}
    if (report.get('analog_source_expansion_passed') is not True or report.get('variant') != variant
            or tasks != expected or len(report['results']) != len(expected) or set(rows) != {t['id'] for t in expected}):
        raise ValueError('Require the complete passing analog source expansion')
    indexed = {(t['spec']['process'], t['spec']['temperature'], t['spec']['mhz'], t['spec']['reference_slew_ps'],
                t['spec']['feedback_slew_ps'], t['spec']['offset_ps']): t for t in manifest['tasks']}
    result = []
    for p, temperature, frequency in points(report['worst_screened_pvt']):
        for sr, sf in ((100, 100), *expansion.coverage.SLEWS):
            donors = [indexed[p, temperature, frequency, sr, sf, offset] for offset in (0, -20, 20)]
            if any(rows[d['id']]['error'] is not None or rows[d['id']]['result']['passed'] is not True for d in donors):
                raise ValueError('Control donor did not pass source electrical checks')
            limits = [rows[d['id']]['result']['native_phase']['phase']['filtered_area_difference_v'] for d in donors[1:]]
            if not np.isfinite(limits).all() or not limits[0] < 0 < limits[1]:
                raise ValueError('Analog source recovery donor lacks the +/-20 ps zero bracket')
            result.append(dict(id=donors[0]['id'] + '_controls', variant=variant,
                spec=donors[0]['spec'], donor=donors[0]['id'], area_limits_v=limits))
    return result


def fixture(deck, aliases, model):
    aliases = dict(aliases)
    gates = [n for n in aliases if n.startswith(('REF_FF_CLK_', 'FB_FF_CLK_'))]
    if len(gates) != 4 or not {'REF_FAST', 'FDB_FAST'} <= set(aliases):
        raise ValueError('Require both conditioned clocks and all four native receiving gates')
    deck = protocol.apply(deck); aliases.update(RST='RST', ENABLE='ENABLE')
    ProbeNetwork(model).validate(deck, aliases.values())
    return deck, aliases


def prepared_fixture(parent, task):
    pm = json.loads((parent / 'manifest.json').read_text())
    donor = next(t for t in pm['tasks'] if t['id'] == task['donor'])
    deck = (parent / donor['id'] / 'bench.cir').read_text()
    if sha(parent / donor['id'] / 'bench.cir') != donor['deck_sha256']:
        raise ValueError('Analog phase donor changed')
    return fixture(deck, donor['aliases'], (parent / (task['variant'] + '.spice')).read_text())


def admission(parent):
    if not parent.is_relative_to(ROOT / 'build/diagnostics' / expansion.NAMESPACE):
        raise ValueError('Require the complete analog source expansion')
    with (parent / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = expansion.verify(parent); manifest = expansion.bound(parent)
        pending = task_plan(report, manifest)
    control_baseline = ROOT / manifest['identity']['clock_baseline']
    if baseline.verify(control_baseline)['baseline_protocol_passed'] is not True:
        raise ValueError('Require the complete native control-protocol baseline')
    return manifest, pending, control_baseline


def prepare(parent):
    pm, pending, control_baseline = admission(parent); pi = pm['identity']
    paths = [parent / 'manifest.json', parent / 'summary.json', parent / (pi['variant'] + '.spice')]
    for task in pm['tasks']:
        paths += [parent / task['id'] / n for n in (*OUTPUTS, 'summary.json', 'bench.cir')]
    paths += [control_baseline / n for n in ('manifest.json', 'summary.json', *OUTPUTS)]
    code = dict(pi['code'])
    for name in (Path(__file__).name, 'pfd_control_protocol.py', 'qualify_slew_frontend_controls.py'):
        code[name] = sha(ROOT / 'scripts' / name)
    identity = dict(parent=str(parent.relative_to(ROOT)), variant=pi['variant'], protocol=protocol.VERSION,
        worst_screened_pvt=json.loads((parent / 'summary.json').read_text())['worst_screened_pvt'],
        inputs={**pi['inputs'], **{str(p.relative_to(ROOT)): sha(p) for p in paths}}, code=code,
        simulator=provenance(), pdk=pi['pdk'], lef=pi['lef'],
        scope='Analog source controls after all 1215 source cases pass: all 15 PVT at 400 MHz, '
        '390/410 MHz at TT25/SS40/measured worst PVT, matched and both extreme slews. '
        'Unchanged native PFD/bias/loading, observed controls, eight clock observations, '
        'all frontend MOS stresses/reference limits and recovery within source +/-20 ps bracket. '
        'No physical, native closed-loop/stability or PHY admission.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); prepared = []
        for task in pending:
            folder = out / task['id']; folder.mkdir(exist_ok=True)
            deck, aliases = prepared_fixture(parent, task)
            expansion.write_once(folder / 'bench.cir', deck)
            prepared.append(dict(task, aliases=aliases, deck_sha256=sha(folder / 'bench.cir')))
        (out / 'producers').mkdir(exist_ok=True)
        for name in code:
            expansion.write_once(out / 'producers' / name, (ROOT / 'scripts' / name).read_text())
        capture_manifest(out / 'manifest.json', dict(identity=identity, tasks=prepared, physical_admission=False, qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Require an isolated analog source-control context')
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']; parent = ROOT / i['parent']
    if (out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['protocol'] != protocol.VERSION or i['simulator'] != provenance()
            or m['physical_admission'] is not False or m['qualified_phy'] is not False
            or any(sha(ROOT / n) != h for n, h in i['inputs'].items())
            or any(sha(ROOT / 'scripts' / n) != h or sha(out / 'producers' / n) != h for n, h in i['code'].items())
            or any(sha(Path(i[k]['path'])) != i[k]['sha256'] for k in ('pdk', 'lef'))):
        raise ValueError('Analog source-control context changed')
    report = json.loads((parent / 'summary.json').read_text()); pm = json.loads((parent / 'manifest.json').read_text())
    if (i['variant'] != pm['identity']['variant'] or i['worst_screened_pvt'] != report['worst_screened_pvt']
            or [{k: v for k, v in t.items() if k not in ('aliases', 'deck_sha256')} for t in m['tasks']] != task_plan(report, pm)):
        raise ValueError('Analog source-control coverage or source admission changed')
    for task in m['tasks']:
        deck, aliases = prepared_fixture(parent, task)
        if (deck != (out / task['id'] / 'bench.cir').read_text() or aliases != task['aliases']
                or sha(out / task['id'] / 'bench.cir') != task['deck_sha256']):
            raise ValueError('Analog control fixture or observations changed')
    return m


def measure(folder, task):
    phase = expansion.measure(folder, task)
    wave, header = expansion.screen.original.pilot.original.completed(folder)
    for alias, node in task['aliases'].items():
        header['V(' + alias + ')'] = header['V(' + node.upper() + ')']
    gates = [n for n in task['aliases'] if n.startswith(('REF_FF_CLK_', 'FB_FF_CLK_'))]
    control = protocol.measure(wave, header, task['spec']['mhz'], ('REF', 'FDB', 'REF_FAST', 'FDB_FAST', *gates))
    area = phase['native_phase']['phase']['filtered_area_difference_v']; low, high = task['area_limits_v']
    recovery = bool(np.isfinite(area) and low <= area <= high)
    return dict(passed=bool(phase['passed'] and control['passed'] and recovery), phase=phase, controls=control,
                recovered_area_within_source_twenty_ps_bracket=recovery)


def aggregate(m, rows):
    expected = {t['id']: t for t in m['tasks']}
    if (not expected or len(expected) != len(m['tasks']) or len(rows) != len(expected)
            or len({r['task'] for r in rows}) != len(rows)
            or any(r['task'] not in expected or r['spec'] != expected[r['task']]['spec']
                   or r['variant'] != expected[r['task']]['variant'] for r in rows)):
        raise ValueError('Analog control results missing, duplicated or unexpected')
    passed = sum(bool(r['error'] is None and r['result'] and r['result']['passed']) for r in rows)
    return dict(analog_source_controls_passed=passed == len(expected), passed_cases=passed, required_cases=len(expected),
        variant=m['identity']['variant'], results=rows, physical_admission=False, qualified_phy=False, scope=m['identity']['scope'])


@expansion.screen.profile()
def run(out):
    m = bound(out); stamp = sha(out / 'manifest.json'); parent = ROOT / m['identity']['parent']
    def unchanged(task):
        library = parent / (task['variant'] + '.spice')
        if (sha(out / 'manifest.json') != stamp or sha(out / task['id'] / 'bench.cir') != task['deck_sha256']
                or sha(library) != m['identity']['inputs'][str(library.relative_to(ROOT))]
                or any(sha(ROOT / 'scripts' / n) != h for n, h in m['identity']['code'].items())):
            raise ValueError('Analog source-control execution context changed')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / t['id'] / n).exists() for t in m['tasks'] for n in (*OUTPUTS, 'summary.json')):
            raise ValueError('Prior analog control output retained; no retry')
        atomic(out / 'state.json', dict(status='qualifying_analog_controls', qualified_phy=False))
        def worker(task):
            folder = out / task['id']; result = error = None
            try:
                with lease(ROOT, priority=2, label='analog_source_controls_' + task['id']):
                    unchanged(task)
                    p = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'), cwd=folder, capture_output=True, text=True)
                (folder / 'console.log').write_text(p.stdout + p.stderr); p.check_returncode()
                unchanged(task); result = measure(folder, task); unchanged(task)
            except Exception as e:
                error = str(e)
            row = dict(task=task['id'], variant=task['variant'], spec=task['spec'], error=error, result=result,
                manifest_sha256=stamp, files={n: sha(folder / n) for n in OUTPUTS if (folder / n).exists()})
            capture_manifest(folder / 'summary.json', row)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(worker, m['tasks']))
        bound(out)
        if sha(out / 'manifest.json') != stamp:
            raise ValueError('Analog control manifest changed')
        report = dict(aggregate(m, rows), manifest_sha256=stamp)
        capture_manifest(out / 'summary.json', report)
        atomic(out / 'state.json', dict(status='analog_controls_verified' if report['analog_source_controls_passed']
            else 'held_analog_controls_failed', qualified_phy=False))
    return report


@expansion.screen.profile()
def verify(out):
    m = bound(out); stamp = sha(out / 'manifest.json'); rows = []
    for task in m['tasks']:
        folder = out / task['id']; row = json.loads((folder / 'summary.json').read_text())
        if (row['task'] != task['id'] or row['variant'] != task['variant'] or row['spec'] != task['spec']
                or row['error'] is not None or row['manifest_sha256'] != stamp or set(row['files']) != set(OUTPUTS)
                or any(sha(folder / n) != h for n, h in row['files'].items()) or row['result'] != measure(folder, task)):
            raise ValueError('Analog control result changed or incomplete')
        rows.append(row)
    report = dict(aggregate(m, rows), manifest_sha256=stamp)
    if report != json.loads((out / 'summary.json').read_text()):
        raise ValueError('Analog control aggregate changed')
    bound(out)
    return report


def preflight(parent):
    pm = expansion.screen.bound(parent); variant = pm['identity']['variants'][0]
    # A declared hypothetical worst corner exercises the maximum 63 fixtures;
    # it is not a measured ranking and never creates qualification evidence.
    hypothetical_worst = ['tt', 0]; decks = {}
    for p, temperature, frequency in points(hypothetical_worst):
        for sr, sf in ((100, 100), *expansion.coverage.SLEWS):
            spec = expansion.coverage.phase(p, temperature, frequency, (sr, sf), 0)
            task = dict(variant=variant, spec=spec)
            deck, aliases = expansion.fixture(task, pm['identity'], parent)
            deck, _ = fixture(deck, aliases, (parent / (variant + '.spice')).read_text())
            decks[f'{p}_{temperature}_{frequency}_{sr}_{sf}'] = hashlib.sha256(deck.encode()).hexdigest()
    identity = dict(parent=str(parent.relative_to(ROOT)), manifest_sha256=sha(parent / 'manifest.json'),
        library_sha256=sha(parent / (variant + '.spice')), producer_sha256=sha(Path(__file__)), hypothetical_worst_pvt=hypothetical_worst)
    out = ROOT / 'build/diagnostics/analog_controls_preflight' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'summary.json', dict(identity=identity, compiled_cases=len(decks), decks=decks,
        electrical_admission=False, source_expansion_admitted=False, physical_admission=False, qualified_phy=False))
    return out


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'bound', 'run', 'verify', 'preflight'])
    p.add_argument('artifact', type=Path); a = p.parse_args(); result = globals()[a.action](a.artifact.resolve())
    print(result if a.action in ('prepare', 'preflight') else json.dumps(result, indent=2), flush=True)
