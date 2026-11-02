# SPDX-License-Identifier: GPL-3.0-only
"""Bound source pilot/full campaigns with reusable analysis and no partial retries."""
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import itertools
import json
from pathlib import Path
import subprocess
import numpy as np

import qualify_driver_output_shape_source as reference
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance

ROOT = Path(__file__).resolve().parents[1]
sha = reference.sha


def completed_wave(folder):
    wave, headers = reference.shape.read_wave(folder / 'bench.cir.prn')
    if (wave.ndim != 2 or len(wave) < 2 or not np.isfinite(wave).all() or
            wave[0, 1] > 1e-15 or wave[-1, 1] < 80e-9 - 1e-12 or
            np.any(np.diff(wave[:, 1]) <= 0)):
        raise ValueError('Incomplete or invalid full 80 ns source trace')
    return wave, headers


def tasks(points):
    return [dict(id=f'{p}_{t}_{op}', process=p, temperature=t, op=op)
            for p, t in points for op in reference.shape.CASES]


def context(out, recipe):
    m = json.loads((out / 'manifest.json').read_text())
    i = m['identity']
    for path in [Path(__file__), Path(recipe.__file__)]:
        if i['code'].get(path.name) != sha(path):
            raise ValueError('Declared source analysis/recipe changed')
    stage = i['stage']
    namespace = 'driver_source_pilot' if stage == 'pilot' else 'driver_shape_source'
    if stage not in ['pilot', 'full'] or not out.is_relative_to(ROOT / 'build/diagnostics' / namespace):
        raise ValueError('Use the declared source campaign namespace/stage')
    req = json.loads((ROOT / 'requirements.json').read_text())
    points = recipe.POINTS if stage == 'pilot' else list(itertools.product(req['process_corners'], req['temperatures_c']))
    if (i['recipe'] != recipe.NEW or i['points'] != [list(p) for p in points] or
            [{k: v for k, v in t.items() if k != 'files'} for t in m['tasks']] != tasks(points) or
            out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]):
        raise ValueError('Source recipe or coverage changed')
    if (provenance() != i['simulator'] or any(sha(ROOT / n) != h for n, h in i['inputs'].items()) or
            any(sha(ROOT / 'scripts' / n) != h for n, h in i['code'].items()) or
            any(sha(out / t['id'] / n) != h for t in m['tasks'] for n, h in t['files'].items())):
        raise ValueError('Source campaign evidence changed')
    models = {(out / t['id'] / 'source.spice').read_bytes() for t in m['tasks']}
    if len(models) != 1:
        raise ValueError('Source circuits differ across cases')
    return m


def aggregate(out, m, rows):
    req = json.loads((ROOT / 'requirements.json').read_text())
    points = []
    for process, temp in m['identity']['points']:
        pair = [r for r in rows if r['case'].startswith(f'{process}_{temp}_')]
        waveforms = {}
        error = None
        try:
            if len(pair) != 2 or any(r['metrics'] is None or r['error'] is not None for r in pair):
                raise ValueError('Source pair incomplete')
            low, high = [r['initial_dc']['differential_v'] for r in pair]
            waveforms = {r['task']: reference.shape.transitions(
                *reference.shape.read_wave(out / r['case'] / 'bench.cir.prn'), low, high) for r in pair}
        except (ValueError, OSError, KeyError) as caught:
            error = str(caught)
        points.append(dict(process=process, temperature=temp,
            passed=error is None and reference.pair_checks(pair, waveforms, req),
            calibrated_transitions=waveforms, error=error))
    passed = all(p['passed'] for p in points)
    stage = m['identity']['stage']
    return dict(results=rows, pvt=points, required_cases=len(m['tasks']), required_pvt=len(points),
        passed_pvt=sum(p['passed'] for p in points), qualified_phy=False,
        source_pilot_passed=passed if stage == 'pilot' else None,
        source_waveform_matrix_passed=passed if stage == 'full' else None,
        manifest_sha256=sha(out / 'manifest.json'), scope=m['identity']['scope'])


def run(out, recipe):
    m = context(out, recipe)
    stamp = sha(out / 'manifest.json')

    def unchanged():
        if sha(out / 'manifest.json') != stamp:
            raise ValueError('Source manifest changed during execution')
        context(out, recipe)

    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / t['id'] / n).exists()
                for t in m['tasks'] for n in ['bench.raw', 'ngspice.log', 'summary.json']):
            raise ValueError('Prior or partial source output retained')
        atomic(out / 'state.json', dict(status='running_source_' + m['identity']['stage'], qualified_phy=False))

        def execute(task):
            folder = out / task['id']
            atomic(folder / 'state.json', dict(status='waiting_for_slot'))
            metrics = dc = None
            result = None
            error = None
            try:
                with lease(ROOT, priority=2 if m['identity']['stage'] == 'pilot' else 1,
                           label='source_' + task['id']):
                    unchanged()
                    atomic(folder / 'state.json', dict(status='running'))
                    result = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'),
                                            cwd=folder, capture_output=True, text=True)
                (folder / 'console.log').write_text(result.stdout + result.stderr)
                result.check_returncode()
                unchanged()
                wave, headers = completed_wave(folder)
                metrics = recipe.measure(folder)
                dc = reference.shape.initial_dc(wave, headers)
            except Exception as caught:
                error = str(caught)
            row = dict(case=task['id'], task=task['op'], returncode=None if result is None else result.returncode,
                metrics=metrics, initial_dc=dc, error=error, qualified_phy=False, manifest_sha256=stamp,
                files={n: sha(folder / n) for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log'] if (folder / n).exists()})
            capture_manifest(folder / 'summary.json', row)
            atomic(folder / 'state.json', dict(status='completed' if error is None else 'held_for_diagnosis'))
            return row

        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(execute, m['tasks']))
        unchanged()
        report = aggregate(out, m, rows)
        capture_manifest(out / 'summary.json', report)
        atomic(out / 'state.json', dict(status='completed_source_checks' if all(p['passed'] for p in report['pvt']) else 'held_source_checks_failed', qualified_phy=False))


def verified(out, recipe):
    m = context(out, recipe)
    paths = [out / 'manifest.json', out / 'summary.json']
    paths += [out / t['id'] / 'summary.json' for t in m['tasks']]
    if any(not p.is_file() for p in paths):
        raise ValueError('Complete every source case before admission')
    proofs = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    rows = []
    for task in m['tasks']:
        folder = out / task['id']
        row = json.loads((folder / 'summary.json').read_text())
        if (row.get('returncode') != 0 or row.get('error') is not None or row.get('manifest_sha256') != sha(out / 'manifest.json') or
                row.get('case') != task['id'] or row.get('task') != task['op'] or
                set(row['files']) != {'bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log'} or
                any(sha(folder / n) != h for n, h in row['files'].items())):
            raise ValueError('Source case failed or changed')
        if (recipe.measure(folder) != row['metrics'] or reference.shape.initial_dc(
                *completed_wave(folder)) != row['initial_dc']):
            raise ValueError('Source remeasurement changed')
        proofs.update({str((folder / n).relative_to(ROOT)): h for n, h in dict(task['files'], **row['files']).items()})
        rows.append(row)
    report = aggregate(out, m, rows)
    if report != json.loads((out / 'summary.json').read_text()) or not all(p['passed'] for p in report['pvt']):
        raise ValueError('Source aggregate differs or reference checks failed')
    if any(sha(ROOT / n) != h for n, h in proofs.items()):
        raise ValueError('Source evidence changed during verification')
    context(out, recipe)
    return m, proofs
