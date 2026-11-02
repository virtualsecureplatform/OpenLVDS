#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Test the completed stronger taper with unchanged 30 um caps after an FF0 failure."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import qualify_driver_output_shape_source as matrix
from dll_campaign import atomic, text_block
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_library import replace

ROOT = Path(__file__).resolve().parents[1]
VARIANT = 'taper_16_64_128'
sha = matrix.sha


def tasks():
    return [dict(id=f'{p}_{t}_{op}', process=p, temperature=t, op=op)
            for p, t in [('tt', 25), ('ff', 0)] for op in matrix.shape.CASES]


def shaped(source):
    top = matrix.shape.pilot.circuit.TOP
    block = text_block(source, top)
    if matrix.shape.pilot.circuit.SHIFT + '_' + VARIANT not in block:
        raise ValueError('Require the completed stronger real-MOS taper')
    for name, pin in [('XCOUTP', 'OUTP'), ('XCOUTN', 'OUTN')]:
        old = f'{name} {pin} VSS sky130_fd_pr__cap_mim_m3_1 w=10 l=10'
        if block.splitlines().count(old) != 1:
            raise ValueError('Original symmetric output MIM changed')
        block = block.replace(old, old.replace('w=10 l=10', 'w=30 l=30'))
    return replace(source, top, block)


def bound(campaign):
    m = json.loads((campaign / 'manifest.json').read_text())
    i = m['identity']
    if (campaign.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or provenance() != i['simulator'] or
            any(sha(ROOT / n) != h for n, h in i['inputs'].items()) or
            any(sha(ROOT / 'scripts' / n) != h for n, h in i['code'].items())):
        raise ValueError('Stronger taper context changed')
    return m


def completed(campaign, task, variant):
    row = json.loads((campaign / task['id'] / 'summary.json').read_text())
    folder = campaign / task['id']
    if (row.get('returncode') != 0 or row.get('manifest_sha256') != sha(campaign / 'manifest.json') or
            row.get('metrics') is None or row['metrics']['rising_output_edges'] != 22):
        raise ValueError('Require a complete switching source case')
    files = dict(task['files'], **row['files'])
    if any(sha(folder / n) != h for n, h in files.items()):
        raise ValueError('Completed source evidence changed')
    if matrix.shape.pilot.measure(folder, variant) != row['metrics']:
        raise ValueError('Completed source remeasurement changed')
    return row, [folder / n for n in set(files) | {'summary.json'}]


def prepare(failed, taper):
    if (not failed.is_relative_to(ROOT / 'build/diagnostics/driver_shape_source') or
            not taper.is_relative_to(ROOT / 'build/diagnostics/driver_gate_taper')):
        raise ValueError('Use the source PVT failure and completed real tapers')
    fm, tm = bound(failed), bound(taper)
    failure = next(t for t in fm['tasks'] if t['id'] == 'ff_0_negative_op')
    fr, paths = completed(failed, failure, 'taper_16_32_64')
    if fr['metrics']['common_mode_pp_v'] <= .150:
        raise ValueError('Require the measured FF0 common-mode failure')
    task = next(t for t in tm['tasks'] if t['id'] == VARIANT)
    tr, extra = completed(taper, task, VARIANT)
    if tr['metrics']['common_mode_pp_v'] >= .150:
        raise ValueError('Stronger real taper does not support this pilot')
    paths += extra + [failed / 'manifest.json', taper / 'manifest.json']
    inputs = dict(fm['identity']['inputs'], **tm['identity']['inputs'])
    inputs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    code = dict(fm['identity']['code'], **tm['identity']['code'])
    code[Path(__file__).name] = sha(Path(__file__))
    identity = dict(failed=str(failed.relative_to(ROOT)), taper=str(taper.relative_to(ROOT)),
        inputs=inputs, code=code, simulator=provenance(), variant=VARIANT,
        scope='One bounded change after actual FF0 common-mode failure: completed '
              'stronger 1/4/8 taper with the same 30x30 um output MIMs. TT25 and FF0, '
              'both initial logic polarities, original 80 ns/1 ps alternating fixture, '
              'fixed supplies, bridge, 110:1 mirror, CMFB and load. Source pilot only; '
              'full fifteen-point source matrix, stress/power review and physical/native '
              'qualification required before selection.')
    out = ROOT / 'build/diagnostics/stronger_driver_shape' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    old = taper / VARIANT
    source = shaped((old / 'source.spice').read_text())
    cases = tasks()
    for case in cases:
        folder = out / case['id']
        folder.mkdir(exist_ok=True)
        deck = matrix.shape.stimulus_polarity((old / 'bench.cir').read_text(), case['op'] == 'positive_op')
        deck = matrix.fixture(deck, old, folder, case)
        matrix.shape.ProbeNetwork(source).validate(deck,
            re.findall(r'V\(([^)]+)\)', re.search(r'(?im)^\.print tran[^\n]+', deck)[0]))
        for name, body in [('source.spice', source), ('bench.cir', deck)]:
            p = folder / name
            if p.exists() and p.read_text() != body:
                raise ValueError('Prepared stronger shape changed')
            if not p.exists():
                p.write_text(body)
        case['files'] = {n: sha(folder / n) for n in ['source.spice', 'bench.cir']}
    capture_manifest(out / 'manifest.json', dict(identity=identity, tasks=cases, qualified_phy=False))
    return out


def run(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics/stronger_driver_shape'):
        raise ValueError('Use prepared stronger-driver pilot')
    m = bound(out)
    stamp = sha(out / 'manifest.json')

    def unchanged():
        bound(out)
        if sha(out / 'manifest.json') != stamp or any(sha(out / t['id'] / n) != h
                for t in m['tasks'] for n, h in t['files'].items()):
            raise ValueError('Stronger pilot manifest or fixture changed')

    if [{k: v for k, v in t.items() if k != 'files'} for t in m['tasks']] != tasks():
        raise ValueError('Require both polarities at TT25 and FF0')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / t['id'] / n).exists()
                for t in m['tasks'] for n in ['bench.raw', 'ngspice.log', 'summary.json']):
            raise ValueError('Prior or partial stronger pilot retained')
        atomic(out / 'state.json', dict(status='running_source_pilot', qualified_phy=False))

        def execute(task):
            folder = out / task['id']
            if any(sha(folder / n) != h for n, h in task['files'].items()):
                raise ValueError('Stronger pilot fixture changed')
            atomic(folder / 'state.json', dict(status='waiting_for_slot'))
            with lease(ROOT, priority=2, label='stronger_shape_' + task['id']):
                unchanged()
                atomic(folder / 'state.json', dict(status='running'))
                p = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'),
                                    cwd=folder, capture_output=True, text=True)
            (folder / 'console.log').write_text(p.stdout + p.stderr)
            unchanged()
            metrics = matrix.shape.pilot.measure(folder, VARIANT) if p.returncode == 0 else None
            dc = matrix.shape.initial_dc(*matrix.shape.read_wave(folder / 'bench.cir.prn')) if metrics else None
            row = dict(case=task['id'], task=task['op'], returncode=p.returncode,
                metrics=metrics, initial_dc=dc, manifest_sha256=stamp, qualified_phy=False,
                files={n: sha(folder / n) for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log'] if (folder / n).exists()})
            capture_manifest(folder / 'summary.json', row)
            atomic(folder / 'state.json', dict(status='completed' if metrics else 'held_numerical_failure'))
            return row

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(execute, m['tasks']))
        points = []
        for process, temp in [('tt', 25), ('ff', 0)]:
            rows = [r for r in results if r['case'].startswith(f'{process}_{temp}_')]
            waveforms = {}
            if all(r['metrics'] is not None for r in rows):
                low, high = [r['initial_dc']['differential_v'] for r in rows]
                waveforms = {r['task']: matrix.shape.transitions(
                    *matrix.shape.read_wave(out / r['case'] / 'bench.cir.prn'), low, high) for r in rows}
            points.append(dict(process=process, temperature=temp,
                passed=matrix.pair_checks(rows, waveforms, json.loads((ROOT / 'requirements.json').read_text())),
                calibrated_transitions=waveforms))
        unchanged()
        passed = all(p['passed'] for p in points)
        capture_manifest(out / 'summary.json', dict(results=results, pvt=points,
            source_pilot_passed=passed, manifest_sha256=stamp, qualified_phy=False,
            scope=m['identity']['scope']))
        atomic(out / 'state.json', dict(status='completed_source_pilot' if passed else 'held_source_checks_failed', qualified_phy=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run'])
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--taper', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        if args.taper is None:
            parser.error('--taper required')
        print(prepare(args.artifact.resolve(), args.taper.resolve()), flush=True)
    else:
        run(args.artifact.resolve())
