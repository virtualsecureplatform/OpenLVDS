#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Expand a fully verified analog timing survivor without changing its circuit.

This is source-front-end qualification on the retained native phase fixture.
It grants no physical, reset/disable, closed-loop or PHY admission.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import subprocess

import numpy as np
import dll_slew_coverage as coverage
import probe_dll_analog_frontend_timing_v2 as screen
from expand_dll_slew_frontends import corner_prefix, write_once
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'dll_analog_frontend_expansion'
VERSION = 'dll-analog-native-source-expansion-v1'
sha = screen.sha
OUTPUTS = screen.original.OUTPUTS
SCOPE = ('Unchanged source analog frontend with retained full native PFD, bias and analog loading. '
         'All fifteen PVT, 390/400/410 MHz, matched and both extreme slews, '
         '0 and +/-20/50/150/300 ps. Actual four receiving MOS clock gates, '
         'all frontend MOS voltage stresses and reference limits remain mandatory. '
         'No physical, reset/disable, closed-loop, stability or PHY admission.')


def tasks(requirements, variant):
    if variant not in screen.revision.policy.VARIANTS:
        raise ValueError('Unknown bounded analog variant')
    result = []
    for spec in coverage.source_specs(requirements):
        p, t, f, sr, sf, offset = (spec[k] for k in ('process', 'temperature', 'mhz',
            'reference_slew_ps', 'feedback_slew_ps', 'offset_ps'))
        result.append(dict(id=f'{variant}_{p}_{t}_{f}mhz_{sr}_{sf}_{offset}ps', variant=variant, spec=spec))
    return result


def admission(parent, variant=None):
    if not parent.is_relative_to(ROOT / 'build/diagnostics' / screen.NAMESPACE):
        raise ValueError('Require the corrected-circuit native timing screen')
    with (parent / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        report = screen.verify(parent)
        manifest = screen.bound(parent)
        survivors = report['ranked_survivors']
        if not survivors or report['analog_source_screen_passed'] is not True:
            raise ValueError('No fully verified analog timing survivor')
        selected = survivors[0] if variant is None else variant
        if selected not in survivors:
            raise ValueError('Selected analog variant did not pass the complete screen')
    return manifest, report, selected


def fixture(task, identity, out):
    with screen.profile():
        observations, gates, prefix = screen.original.context(identity)
        prefix = corner_prefix(prefix, task['spec']['process'], task['spec']['temperature'])
        library = out / (task['variant'] + '.spice')
        return screen.original.fixture(task, observations, gates, prefix, library, library.read_text())


def prepare(parent, variant=None):
    pm, report, selected = admission(parent, variant)
    pi = pm['identity']
    req = ROOT / 'requirements.json'
    pending = tasks(json.loads(req.read_text()), selected)
    paths = [req, parent / 'manifest.json', parent / 'summary.json', parent / (selected + '.spice')]
    for task in pm['tasks']:
        paths += [parent / task['id'] / n for n in (*OUTPUTS, 'summary.json')]
    code = dict(pi['code'])
    for name in (Path(__file__).name, 'dll_slew_coverage.py', 'dll_native_evidence.py',
                 'expand_dll_slew_frontends.py', 'spice_dispatch.py'):
        code[name] = sha(ROOT / 'scripts' / name)
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), variant=selected,
        qualification_reference=pi['qualification_reference'], clock_baseline=pi['clock_baseline'],
        policy=pi['policy'], requirements_sha256=sha(req), coverage_version=coverage.VERSION,
        inputs={**pi['inputs'], **{str(p.relative_to(ROOT)): sha(p) for p in paths}},
        code=code, simulator=provenance(), pdk=pi['pdk'], lef=pi['lef'], scope=SCOPE)
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        library = out / (selected + '.spice')
        write_once(library, (parent / library.name).read_text())
        prepared = []
        for task in pending:
            folder = out / task['id']; folder.mkdir(exist_ok=True)
            deck, aliases = fixture(task, identity, out)
            write_once(folder / 'bench.cir', deck)
            prepared.append(dict(task, aliases=aliases, deck_sha256=sha(folder / 'bench.cir')))
        (out / 'producers').mkdir(exist_ok=True)
        for name in code:
            write_once(out / 'producers' / name, (ROOT / 'scripts' / name).read_text())
        capture_manifest(out / 'manifest.json', dict(identity=identity, libraries={library.name: sha(library)},
            tasks=prepared, physical_admission=False, qualified_phy=False))
    return out


def preflight(parent):
    """Compile all new fixtures from a bound model, without timing admission."""
    pm = screen.bound(parent)
    req = ROOT / 'requirements.json'; variant = pm['identity']['variants'][0]
    pending = tasks(json.loads(req.read_text()), variant)
    # Use the existing immutable library path in memory. No source-screen
    # files, running decks or scientific result files are written here.
    aliases = None; decks = {}
    for task in pending:
        deck, observed = fixture(task, pm['identity'], parent)
        if aliases is not None and aliases != observed:
            raise ValueError('Analog expansion observations vary across fixtures')
        aliases = observed
        decks[task['id']] = hashlib.sha256(deck.encode()).hexdigest()
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), variant=variant,
        manifest_sha256=sha(parent / 'manifest.json'), library_sha256=sha(parent / (variant + '.spice')),
        requirements_sha256=sha(req), producer_sha256=sha(Path(__file__)))
    out = ROOT / 'build/diagnostics/analog_source_expansion_preflight' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'summary.json', dict(identity=identity, compiled_cases=len(decks), decks=decks,
        actual_gate_observations={k: v for k, v in aliases.items() if k.startswith(('REF_FF_CLK_', 'FB_FF_CLK_'))},
        timing_screen_admitted=False, electrical_admission=False, physical_admission=False, qualified_phy=False,
        scope='In-memory fixture/model/probe compilation only. A bound source library is not a passing timing screen.'))
    return out


def bound(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Require an isolated analog source expansion')
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']
    if (out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['version'] != VERSION or i['scope'] != SCOPE or i['coverage_version'] != coverage.VERSION
            or i['simulator'] != provenance() or m['physical_admission'] is not False or m['qualified_phy'] is not False
            or any(sha(ROOT / n) != h for n, h in i['inputs'].items())
            or any(sha(ROOT / 'scripts' / n) != h or sha(out / 'producers' / n) != h for n, h in i['code'].items())
            or sha(ROOT / 'requirements.json') != i['requirements_sha256']
            or any(sha(Path(i[k]['path'])) != i[k]['sha256'] for k in ('pdk', 'lef'))
            or set(m['libraries']) != {i['variant'] + '.spice'}
            or any(sha(out / n) != h or (out / n).read_bytes() != (ROOT / i['parent'] / n).read_bytes()
                   for n, h in m['libraries'].items())
            or [{k: v for k, v in t.items() if k not in ('aliases', 'deck_sha256')} for t in m['tasks']]
               != tasks(json.loads((ROOT / 'requirements.json').read_text()), i['variant'])):
        raise ValueError('Analog source expansion context changed')
    pm, _, _ = admission(ROOT / i['parent'], i['variant'])
    if any(i[k] != pm['identity'][k] for k in ('policy', 'qualification_reference', 'clock_baseline', 'pdk', 'lef')):
        raise ValueError('Analog source expansion parent changed')
    for task in m['tasks']:
        deck, aliases = fixture(task, i, out)
        if (deck != (out / task['id'] / 'bench.cir').read_text() or aliases != task['aliases']
                or sha(out / task['id'] / 'bench.cir') != task['deck_sha256']):
            raise ValueError('Analog expansion fixture or receiving-gate observations changed')
    return m


def aggregate(m, rows):
    expected = tasks(json.loads((ROOT / 'requirements.json').read_text()), m['identity']['variant'])
    if ([{k: v for k, v in t.items() if k not in ('aliases', 'deck_sha256')} for t in m['tasks']] != expected
            or len(rows) != len(expected) or len({r['task'] for r in rows}) != len(rows)
            or {r['task']: dict(id=r['task'], variant=r['variant'], spec=r['spec']) for r in rows}
               != {t['id']: t for t in expected}):
        raise ValueError('Analog expansion coverage missing, duplicated or unexpected')
    checks = []; powers = []
    passed = all(r['error'] is None and r['result'] and r['result']['passed'] is True for r in rows)
    for p, t, f, slew in itertools.product(coverage.PROCESSES, coverage.TEMPERATURES,
            coverage.FREQUENCIES, ((100, 100), *coverage.SLEWS)):
        group = {r['spec']['offset_ps']: r['result'] for r in rows if
            (r['spec']['process'], r['spec']['temperature'], r['spec']['mhz'],
             r['spec']['reference_slew_ps'], r['spec']['feedback_slew_ps']) == (p, t, f, *slew)}
        monotonic = balance = False; zero = None
        if all(group.values()):
            values = [group[o]['native_phase']['phase']['filtered_area_difference_v'] for o in coverage.SOURCE_OFFSETS]
            monotonic = bool(np.isfinite(values).all() and all(b > a for a, b in zip(values, values[1:])))
            lo, hi = (group[o]['native_phase']['phase']['filtered_area_difference_v'] for o in (-20, 20))
            balance = bool(np.isfinite([lo, hi]).all() and lo < 0 < hi)
            if balance:
                zero = float(-20 + 40 * (-lo) / (hi - lo))
            powers.extend(r['native_phase']['mean_power_w'] for r in group.values())
        passed = passed and monotonic and balance
        checks.append(dict(process=p, temperature=t, mhz=f, slew=list(slew), monotonic=monotonic,
            zero_bracket_passed=balance, estimated_zero_offset_ps=zero))
    passed = bool(passed and powers and np.isfinite(powers).all())
    worst = max(checks, key=lambda c: abs(c['estimated_zero_offset_ps'])) if all(c['estimated_zero_offset_ps'] is not None for c in checks) else None
    return dict(analog_source_expansion_passed=passed, variant=m['identity']['variant'],
        required_cases=len(expected), required_pvt=15, checks=checks, results=rows,
        worst_screened_pvt=[worst['process'], worst['temperature']] if worst else None,
        estimated_zero_offset_max_abs_ps=abs(worst['estimated_zero_offset_ps']) if worst else None,
        mean_power_w=float(np.mean(powers)) if powers and np.isfinite(powers).all() else None,
        physical_admission=False, qualified_phy=False, scope=SCOPE)


def measure(folder, task):
    # The campaign owns one profile for the whole worker pool. Entering and
    # restoring a process-global profile independently in each worker races.
    if screen.original.dc.policy is not screen.revision.policy:
        raise ValueError('Measure analog expansion inside its campaign profile')
    return screen.original.measure(folder, task)


@screen.profile()
def run(out):
    m = bound(out); stamp = sha(out / 'manifest.json')
    def unchanged(task):
        if (sha(out / 'manifest.json') != stamp
                or any(sha(ROOT / 'scripts' / n) != h for n, h in m['identity']['code'].items())
                or sha(out / (task['variant'] + '.spice')) != m['libraries'][task['variant'] + '.spice']
                or sha(out / task['id'] / 'bench.cir') != task['deck_sha256']):
            raise ValueError('Analog expansion execution context changed')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / t['id'] / n).exists() for t in m['tasks'] for n in (*OUTPUTS, 'summary.json')):
            raise ValueError('Partial analog expansion retained; no retry')
        atomic(out / 'state.json', dict(status='expanding_analog_source', qualified_phy=False))
        def execute(task):
            folder = out / task['id']; result = error = None
            try:
                with lease(ROOT, priority=2, label='dll_analog_expand_' + task['id']):
                    unchanged(task)
                    process = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'),
                        cwd=folder, capture_output=True, text=True)
                (folder / 'console.log').write_text(process.stdout + process.stderr)
                process.check_returncode(); unchanged(task)
                result = measure(folder, task); unchanged(task)
            except Exception as e:
                error = str(e)
            row = dict(task=task['id'], variant=task['variant'], spec=task['spec'], result=result,
                error=error, manifest_sha256=stamp, files={n: sha(folder / n) for n in OUTPUTS if (folder / n).exists()})
            capture_manifest(folder / 'summary.json', row)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(execute, m['tasks']))
        bound(out)
        if sha(out / 'manifest.json') != stamp:
            raise ValueError('Analog expansion manifest changed')
        report = dict(aggregate(m, rows), manifest_sha256=stamp)
        capture_manifest(out / 'summary.json', report)
        atomic(out / 'state.json', dict(status='analog_source_expanded' if report['analog_source_expansion_passed']
            else 'held_analog_source_expansion_failed', qualified_phy=False))
    return report


@screen.profile()
def verify(out):
    m = bound(out); stamp = sha(out / 'manifest.json'); rows = []
    for task in m['tasks']:
        folder = out / task['id']; row = json.loads((folder / 'summary.json').read_text())
        if (row['task'] != task['id'] or row['variant'] != task['variant'] or row['spec'] != task['spec']
                or row['error'] is not None or row['manifest_sha256'] != stamp or set(row['files']) != set(OUTPUTS)
                or any(sha(folder / n) != h for n, h in row['files'].items())
                or measure(folder, task) != row['result']):
            raise ValueError('Analog expansion result changed or incomplete')
        rows.append(row)
    report = dict(aggregate(m, rows), manifest_sha256=stamp)
    if report != json.loads((out / 'summary.json').read_text()):
        raise ValueError('Analog expansion aggregate changed')
    bound(out)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'preflight', 'bound', 'run', 'verify'])
    p.add_argument('artifact', type=Path); p.add_argument('--variant')
    a = p.parse_args()
    if a.variant and a.action != 'prepare':
        p.error('--variant applies only to prepare')
    result = prepare(a.artifact.resolve(), a.variant) if a.action == 'prepare' else globals()[a.action](a.artifact.resolve())
    print(result if a.action in ('prepare', 'preflight') else json.dumps(result, indent=2), flush=True)
