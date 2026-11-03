#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Seed a selected native PFD repair with both known SS40 failures and controls."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import assemble_slew_dll as assembly
import dll_slew_coverage as coverage
import probe_dll_input_conditioning as original
from dll_campaign import atomic, bias_reference_count
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'dll_slew_native_pilot'
sha = original.sha
OUTPUTS = ('bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log')


def tasks():
    result = [dict(id=f'native_ss40_{sr}_{sf}_{o}ps', spec=coverage.phase('ss', 40, 400, (sr, sf), o))
              for (sr, sf), o in itertools.product(coverage.SLEWS, coverage.SOURCE_OFFSETS)]
    known = ['native_ss40_20_200_50ps', 'native_ss40_200_20_-50ps']
    return sorted(result, key=lambda t: (known.index(t['id']) if t['id'] in known else 2, t['id']))


def fixture(spec, analog_observations, gate_probes, prefix, library_path, model):
    body, aliases, stop, timing = original.admission.storage.native.phase_fixture(spec, analog_observations)
    if stop != 160 or timing != dict(start_ns=120, end_ns=160): raise ValueError('Native phase scoring windows changed')
    if set(aliases) & set(gate_probes): raise ValueError('Receiving gate observation aliases collide')
    aliases.update(gate_probes)
    prefix, count = re.subn(r'(?m)^\.include "[^"\n]+"$', lambda m: '.include "' + str(library_path) + '"', prefix)
    if count != 1: raise ValueError('Require one original native DLL include')
    deck = prefix + body + '.save i(VA) i(VD)\n.tran 5p 160n 0 20p\n.print tran ' + ' '.join('V(' + n + ')' for n in aliases.values()) + '\n.end\n'
    if bias_reference_count(deck, model) != 1: raise ValueError('Native pilot duplicates endpoint bias')
    ProbeNetwork(model).validate(deck, aliases.values())
    return deck, aliases


def prepare(parent):
    pm = assembly.verify(parent); pi = pm['identity']; q = ROOT / pi['qualification_reference']
    observed = json.loads((parent / 'clock_observations.json').read_text()); model = (parent / 'full.spice').read_text()
    inputs = dict(pi['inputs']); inputs.update({str((parent / n).relative_to(ROOT)): sha(parent / n) for n in ('manifest.json', *pm['files'])})
    template_path = q / 'slew_ss_40_0ps_20_200/bench.cir'
    qm = json.loads((q / 'manifest.json').read_text())
    donor = next(t for t in qm['tasks'] if t['id'] == template_path.parent.name)
    if sha(template_path) != donor['deck_sha256']: raise ValueError('Original native phase fixture changed')
    inputs[str(template_path.relative_to(ROOT))] = sha(template_path)
    code = dict(pi['code'])
    for n in (Path(__file__).name, 'probe_dll_input_conditioning.py', 'dll_slew_coverage.py', 'dll_native_evidence.py',
              'qualify_dll_candidate.py', 'dll_measurements.py', 'verify_phase_detector.py', 'run_ngspice.py', 'spice_engine.py',
              'spice_dispatch.py', 'receiver_static_diagnosis.py', 'dll_campaign.py'):
        code[n] = sha(ROOT / 'scripts' / n)
    identity = dict(parent=str(parent.relative_to(ROOT)), variant=pi['variant'], coverage_recipe=pi['coverage_recipe'],
                    simulator=provenance(), inputs=inputs, code=code, collateral=pi['collateral'],
                    scope='18 fresh SS40/400 MHz native cases: both unequal slew directions, 0, +/-20/50/150/300 ps. Known false-BAD cases first; actual receiving MOS gate observations, original health limits and zero-balance guard. No full-PVT, loop, stability, stress or PHY admission.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    template = template_path.read_text(); prefix = template[:template.index('XB PB NB VDDIO 0 lvds_bias')]
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assembly.extraction.physical.write_once(out / 'full.spice', model); prepared = []
        for t in tasks():
            folder = out / t['id']; folder.mkdir(exist_ok=True)
            deck, aliases = fixture(t['spec'], pi['analog_observation_nodes'], observed['phase_probes'], prefix, out / 'full.spice', model)
            assembly.extraction.physical.write_once(folder / 'bench.cir', deck)
            prepared.append(dict(t, aliases=aliases, deck_sha256=sha(folder / 'bench.cir')))
        capture_manifest(out / 'manifest.json', dict(identity=identity, model_sha256=sha(out / 'full.spice'), tasks=prepared, qualified_phy=False))
    return out


def bound(out):
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']
    if (not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE) or
            out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16] or provenance() != i['simulator'] or
            [{k: v for k, v in t.items() if k not in ('aliases', 'deck_sha256')} for t in m['tasks']] != tasks() or
            any(sha(ROOT / n) != h for n, h in i['inputs'].items()) or any(sha(ROOT / 'scripts' / n) != h for n, h in i['code'].items()) or
            any(sha(Path(n)) != h for n, h in i['collateral'].items()) or sha(out / 'full.spice') != m['model_sha256'] or
            any(sha(out / t['id'] / 'bench.cir') != t['deck_sha256'] for t in m['tasks'])):
        raise ValueError('Native slew pilot context changed')
    parent = ROOT / i['parent']; pm = json.loads((parent / 'manifest.json').read_text())
    if (out / 'full.spice').read_bytes() != (parent / 'full.spice').read_bytes(): raise ValueError('Native pilot changed the selected model')
    observed = json.loads((parent / 'clock_observations.json').read_text())
    q = ROOT / pm['identity']['qualification_reference']; template = (q / 'slew_ss_40_0ps_20_200/bench.cir').read_text()
    prefix = template[:template.index('XB PB NB VDDIO 0 lvds_bias')]; model = (out / 'full.spice').read_text()
    for t in m['tasks']:
        deck, aliases = fixture(t['spec'], pm['identity']['analog_observation_nodes'], observed['phase_probes'], prefix, out / 'full.spice', model)
        if deck != (out / t['id'] / 'bench.cir').read_text() or aliases != t['aliases']: raise ValueError('Native pilot probes or phase fixture changed')
    return m


def gate_transport(time, signals):
    result = {}; passed = True
    for side, source in [('REF_FF_CLK_', 'REF'), ('FB_FF_CLK_', 'FDB')]:
        names = sorted(n for n in signals if n.startswith(side))
        if not names: raise ValueError('Missing actual receiving gate observations')
        for name in names:
            delivered = signals[name]; delays = {}; valid = True
            for rising in (True, False):
                external = original.measurement.edges(time, signals[source], rising=rising)
                actual = original.measurement.edges(time, delivered, rising=rising)
                anchors = external[(external > 125e-9) & (external < 155e-9)]; matched = []; differences = []
                valid = valid and len(anchors) >= 10
                for at in anchors:
                    hits = np.flatnonzero(abs(actual - at) < 1.25e-9)
                    if len(hits) != 1: valid = False; continue
                    matched.append(int(hits[0])); differences.append(float((actual[hits[0]] - at) * 1e12))
                    window = (time > at - 1.25e-9) & (time < at + 1.25e-9)
                    valid = bool(valid and np.any(window) and delivered[window].min() < .36 and delivered[window].max() > 1.44)
                valid = valid and len(set(matched)) == len(anchors)
                delays['rising' if rising else 'falling'] = dict(mean_ps=float(np.mean(differences)) if differences else None,
                      min_ps=min(differences) if differences else None, max_ps=max(differences) if differences else None)
            result[name] = dict(passed=bool(valid), delivery_delay=delays); passed = passed and valid
    return dict(passed=bool(passed), gates=result)


def measure(folder, task):
    w, h = original.completed(folder)
    for alias, node in task['aliases'].items(): h['V(' + alias + ')'] = h['V(' + node.upper() + ')']
    phase = original.measurement.phase(w, h, task['spec']['offset_ps']); t = w[:, 1]
    signals = {n: original.measurement.column(w, h, n) for n in task['aliases'] if n in ('REF', 'FDB') or n.startswith(('REF_FF_CLK_', 'FB_FF_CLK_'))}
    clock = gate_transport(t, signals); names, raw = read_raw(folder / 'bench.raw'); keep = (t > 120e-9) & (t < 160e-9)
    power = -3.3 * raw[:, names.index('i(va)')] - 1.8 * raw[:, names.index('i(vd)')]
    return dict(passed=bool(phase['passed'] and clock['passed']), phase=phase, clock_transport=clock,
                mean_power_w=original.measurement.average(t[keep], power[keep]))


def aggregate(rows):
    expected = {t['id']: t for t in tasks()}
    if (len(rows) != len(expected) or len({r['task'] for r in rows}) != len(rows) or
            any(r['task'] not in expected or r['spec'] != expected[r['task']]['spec'] for r in rows)):
        raise ValueError('Native pilot results have missing, duplicate or unexpected cases')
    checks = []; passed = all(r['error'] is None and r['result'] and r['result']['passed'] for r in rows)
    for sr, sf in coverage.SLEWS:
        group = {r['spec']['offset_ps']: r['result'] for r in rows if (r['spec']['reference_slew_ps'], r['spec']['feedback_slew_ps']) == (sr, sf)}
        monotonic = balance = False; zero = None
        if all(group.values()):
            values = [group[o]['phase']['filtered_area_difference_v'] for o in coverage.SOURCE_OFFSETS]
            monotonic = bool(np.isfinite(values).all() and all(b > a for a, b in zip(values, values[1:])))
            lo = group[-20]['phase']['filtered_area_difference_v']; hi = group[20]['phase']['filtered_area_difference_v']; balance = bool(lo < 0 < hi)
            if balance: zero = float(-20 + 40 * (-lo) / (hi - lo))
        passed = passed and monotonic and balance
        checks.append(dict(slew=[sr, sf], monotonic=monotonic, zero_bracket_passed=balance, estimated_zero_offset_ps=zero))
    by_id = {r['task']: r for r in rows}
    restored = all(by_id[t['id']]['error'] is None and by_id[t['id']]['result'] and by_id[t['id']]['result']['passed'] for t in tasks()[:2])
    return dict(native_pilot_passed=bool(passed), known_false_bad_cases_restored=bool(restored), checks=checks,
                results=rows, physical_admission=False, qualified_phy=False)


def run(out):
    m = bound(out); stamp = sha(out / 'manifest.json')
    def unchanged(t):
        if (sha(out / 'manifest.json') != stamp or sha(out / 'full.spice') != m['model_sha256'] or
                sha(out / t['id'] / 'bench.cir') != t['deck_sha256'] or
                any(sha(ROOT / 'scripts' / n) != h for n, h in m['identity']['code'].items())):
            raise ValueError('Native pilot execution context changed')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / t['id'] / n).exists() for t in m['tasks'] for n in (*OUTPUTS, 'summary.json')):
            raise ValueError('Partial native pilot retained; no retry')
        atomic(out / 'state.json', dict(status='running_native_pilot', qualified_phy=False))
        def execute(t):
            folder = out / t['id']; result = error = None
            try:
                with lease(ROOT, priority=1, label='native_slew_pilot_' + t['id']):
                    unchanged(t); p = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'), cwd=folder, capture_output=True, text=True)
                (folder / 'console.log').write_text(p.stdout + p.stderr); p.check_returncode(); unchanged(t)
                result = measure(folder, t); unchanged(t)
            except Exception as e: error = str(e)
            r = dict(task=t['id'], spec=t['spec'], result=result, error=error, manifest_sha256=stamp,
                     files={n: sha(folder / n) for n in OUTPUTS if (folder / n).exists()})
            capture_manifest(folder / 'summary.json', r); return r
        with ThreadPoolExecutor(max_workers=2) as pool: rows = list(pool.map(execute, m['tasks']))
        bound(out)
        if sha(out / 'manifest.json') != stamp: raise ValueError('Native pilot manifest changed')
        report = dict(aggregate(rows), manifest_sha256=stamp); capture_manifest(out / 'summary.json', report)
        atomic(out / 'state.json', dict(status='native_pilot_passed' if report['native_pilot_passed'] else 'held_native_pilot_failed', qualified_phy=False))
    return report


def verify(out):
    m = bound(out); stamp = sha(out / 'manifest.json'); rows = []
    for t in m['tasks']:
        folder = out / t['id']; r = json.loads((folder / 'summary.json').read_text())
        if (r['manifest_sha256'] != stamp or r['task'] != t['id'] or r['spec'] != t['spec'] or r['error'] is not None or
                set(r['files']) != set(OUTPUTS) or any(sha(folder / n) != h for n, h in r['files'].items()) or measure(folder, t) != r['result']):
            raise ValueError('Native pilot output changed')
        rows.append(r)
    report = dict(aggregate(rows), manifest_sha256=stamp)
    if report != json.loads((out / 'summary.json').read_text()): raise ValueError('Native pilot aggregate changed')
    bound(out); return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run', 'verify']); p.add_argument('artifact', type=Path)
    a = p.parse_args(); r = globals()[a.action](a.artifact.resolve()); print(r if a.action == 'prepare' else json.dumps(r, indent=2), flush=True)
