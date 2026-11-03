#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Score four new source clock buffers in the otherwise unchanged native link.

A complete, independently verified capture aperture is a preparation gate.
These are new source-circuit experiments, never physical or PHY admission.
"""
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
import restore_compensated_coupled as coupled
import rx_clock_skew as policy
import rx_candidate_aperture as aperture
import rx_aperture_evidence as evidence
import extend_rx_aperture as extended
from dll_campaign import atomic, bias_reference_count
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_probes import ProbeNetwork
from spice_scope import closure_hash

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'rx_clock_skew_source'
sha = coupled.sha
OUTPUTS = ('bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log')


def aperture_gate(folder, native):
    folder = folder.resolve()
    if not folder.is_relative_to(ROOT / 'build/characterization/rx_aperture'):
        raise ValueError('Require the complete original native capture aperture')
    m = json.loads((folder / 'manifest.json').read_text()); aperture.validate(folder, m)
    if closure_hash(native, 'openlvds_ddr_rx') != closure_hash((folder / 'library.spice').read_text(), 'openlvds_ddr_rx'):
        raise ValueError('Aperture capture circuit differs from the coupled native capture')
    receipt = evidence.read_table(folder / 'table.json', m['identity']['model']['netlist_sha256'], 'ss', 40)
    aperture.check_seeds(folder, m)
    # Strengthen the retained reader with complete binary/export agreement
    # and full-deck checks at every boundary before a new circuit is scored.
    files = {}
    for spec in m['conditions']:
        _, proof = extended.boundary(folder, m, spec); files.update(proof)
    for name in ('manifest.json', 'table.json', 'seed_summary.json', 'requirements.json', 'library.spice'):
        files[str((folder / name).relative_to(ROOT))] = sha(folder / name)
    return m, receipt, files


def fixture(deck, parent, out, variant):
    include = f'.include "{parent}/payload/library.spice"'
    original = 'XCR RCP RCN RXCLOCK VREF IREF_RX NBR VDDIO VDDD 0 openlvds_receiver_core'
    capture = 'XRX 0 VDDD RXCLOCK Q0 Q1 RESET_N RXDATA RXVALID openlvds_ddr_rx'
    if (deck.count(include) != 1 or deck.splitlines().count(original) != 1 or deck.splitlines().count(capture) != 1
            or re.findall(r'(?im)^\.tran[^\n]+', deck) != ['.tran 1p 188.049n 0 1p']):
        raise ValueError('Require the unchanged complete native link fixture')
    result = deck.replace(include, f'.include "{out}/{variant}.spice"').replace(
        original, original.replace(' RXCLOCK ', ' RXCLOCK_RAW ')).replace(capture,
        'XSH RXCLOCK_RAW RXCLOCK VDDD 0 ' + policy.TOP + '\n' + capture)
    result = result.replace('.tran 1p 188.049n 0 1p', '.tran 1p 120n 0 1p')
    prints = re.findall(r'(?im)^\.print tran[^\n]+', result)
    if len(prints) != 1:
        raise ValueError('Original observation statement changed')
    return result.replace(prints[0], prints[0] + ' V(RXCLOCK_RAW) V(XSH:MID) V(VDDD)')


def prepare(parent, capture):
    if coupled.verify(parent).get('payload_restored') is not True:
        raise ValueError('Require independently verified restored native payload')
    pm = json.loads((parent / 'manifest.json').read_text())
    native = (parent / 'payload/library.spice').read_text()
    if re.search(r'(?im)^\.subckt\s+' + policy.TOP + r'\b', native):
        raise ValueError('Clock skew prototype collides with an existing native block')
    am, receipt, proof = aperture_gate(capture, native)
    paths = [parent / 'manifest.json', parent / 'summary.json', parent / 'payload/summary.json']
    paths += [parent / 'payload' / n for n in ('library.spice', 'bench.cir', *OUTPUTS)]
    code = {**pm['identity']['code'], **am['identity']['code'], **am['identity']['candidate_code']}
    for name in (Path(__file__).name, 'rx_clock_skew.py', 'extend_rx_aperture.py', 'spice_dispatch.py', 'spice_probes.py'):
        code[name] = sha(ROOT / 'scripts' / name)
    identity = dict(parent=str(parent.relative_to(ROOT)), aperture=str(capture.relative_to(ROOT)), aperture_receipt=receipt,
        inputs={**pm['identity']['inputs'], **proof, **{str(p.relative_to(ROOT)): sha(p) for p in paths}},
        code=code, policy=policy.VERSION, variants=list(policy.VARIANTS), simulator=provenance(),
        stop_ns=120, maximum_step_ps=1, minimum_margin_ps=200,
        scope='Four bounded source receive-clock buffers, complete native SS40/410 MHz coupled link, '
        '45% duty, 100 ps skew/jitter, original load/channel/data path and endpoint references. '
        'Complete matched capture aperture, actual input slews, payload and all four new MOS stresses. '
        'No physical, all-PVT, actual DLL phase, long link or PHY admission.')
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    from expand_dll_slew_frontends import write_once
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        tasks = []
        for variant in policy.VARIANTS:
            model = native + '\n' + policy.circuit(variant)[0]
            deck = fixture((parent / 'payload/bench.cir').read_text(), parent, out, variant)
            if bias_reference_count(deck, model) != 2:
                raise ValueError('Receive-clock prototype changes endpoint reference count')
            ProbeNetwork(model).validate(deck, re.findall(r'V\(([^)]+)\)', re.search(r'(?im)^\.print tran[^\n]+', deck)[0]))
            folder = out / variant; folder.mkdir(exist_ok=True)
            write_once(out / (variant + '.spice'), model); write_once(folder / 'bench.cir', deck)
            tasks.append(dict(id=variant, files={'bench.cir': sha(folder / 'bench.cir'),
                variant + '.spice': sha(out / (variant + '.spice'))}))
        (out / 'producers').mkdir(exist_ok=True)
        for name in code:
            write_once(out / 'producers' / name, (ROOT / 'scripts' / name).read_text())
        capture_manifest(out / 'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Require an isolated receive-clock source experiment')
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']; parent = ROOT / i['parent']
    if (out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['policy'] != policy.VERSION or i['variants'] != list(policy.VARIANTS) or i['simulator'] != provenance()
            or i['stop_ns'] != 120 or i['maximum_step_ps'] != 1 or i['minimum_margin_ps'] != 200
            or m['qualified_phy'] is not False or any(sha(ROOT / n) != h for n, h in i['inputs'].items())
            or any(sha(ROOT / 'scripts' / n) != h or sha(out / 'producers' / n) != h for n, h in i['code'].items())
            or [t['id'] for t in m['tasks']] != list(policy.VARIANTS)):
        raise ValueError('Receive-clock source context changed')
    native = (parent / 'payload/library.spice').read_text()
    _, receipt, _ = aperture_gate(ROOT / i['aperture'], native)
    if receipt != i['aperture_receipt']:
        raise ValueError('Receive-clock aperture receipt changed')
    for task in m['tasks']:
        variant = task['id']; lib = out / (variant + '.spice'); deck = out / variant / 'bench.cir'
        if (task['files'] != {'bench.cir': sha(deck), variant + '.spice': sha(lib)}
                or lib.read_text() != native + '\n' + policy.circuit(variant)[0]
                or deck.read_text() != fixture((parent / 'payload/bench.cir').read_text(), parent, out, variant)):
            raise ValueError('Receive-clock model or fixture changed')
    return m


def measure(folder, task, receipt):
    wave, h = coupled.baseline.completed_export(folder, 120)
    t = wave[:, 1]; v = lambda n: np.zeros(len(t)) if n == '0' else wave[:, h['V(' + n.upper() + ')']]
    launch = coupled.baseline.original.edge_times(t, v('CLK0'), rising=True)
    launch = launch[launch >= 60e-9][:16] * 1e9
    if len(launch) != 16:
        raise ValueError('Missing original payload launch window')
    metrics = coupled.baseline.original.analyze(wave, coupled.baseline.original.word_stream(16), launch,
                                              1000 / 410, aperture=receipt)
    mapping = dict(IN='RXCLOCK_RAW', OUT='RXCLOCK', MID='XSH:MID', VDDD='VDDD', VSS='0')
    stress = []
    for device in policy.circuit(task['id'])[1]:
        terminals = [v(mapping[n]) for n in device['terminals']]
        maximum = max(float(np.max(abs(a - b))) for a, b in itertools.combinations(terminals, 2))
        stress.append(dict(device=device['name'], max_terminal_difference_v=maximum, limit_v=1.95, passed=maximum <= 1.95))
    valid = bool(metrics.get('passed') is True and metrics.get('checked_bits') == 32 and metrics.get('word_errors') == 0
        and metrics.get('capture_aperture_slew_passed') is True
        and metrics.get('setup_margin_ps') is not None and metrics['setup_margin_ps'] >= 200
        and metrics.get('hold_margin_ps') is not None and metrics['hold_margin_ps'] >= 200 and all(s['passed'] for s in stress))
    return dict(passed=valid, payload=metrics, stress=stress, qualified_phy=False)


def aggregate(m, rows):
    if (len(rows) != 4 or [r['variant'] for r in rows] != list(policy.VARIANTS)
            or [t['id'] for t in m['tasks']] != list(policy.VARIANTS)):
        raise ValueError('Missing, duplicate or foreign receive-clock variants')
    survivors = [r for r in rows if r['error'] is None and r['result'] and r['result']['passed'] is True]
    survivors.sort(key=lambda r: (-min(r['result']['payload']['setup_margin_ps'], r['result']['payload']['hold_margin_ps']),
                                  policy.VARIANTS[r['variant']]))
    return dict(clock_skew_source_passed=bool(survivors), ranked_survivors=[r['variant'] for r in survivors],
        results=rows, physical_admission=False, qualified_phy=False, scope=m['identity']['scope'])


def run(out):
    m = bound(out); stamp = sha(out / 'manifest.json')
    def unchanged(task):
        if (sha(out / 'manifest.json') != stamp or any(sha(ROOT / 'scripts' / n) != h for n, h in m['identity']['code'].items())
                or sha(out / task['id'] / 'bench.cir') != task['files']['bench.cir']
                or sha(out / (task['id'] + '.spice')) != task['files'][task['id'] + '.spice']):
            raise ValueError('Receive-clock execution context changed')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / t['id'] / n).exists() for t in m['tasks'] for n in (*OUTPUTS, 'summary.json')):
            raise ValueError('Prior receive-clock source output retained; no retry')
        atomic(out / 'state.json', dict(status='screening_clock_skew', qualified_phy=False))
        def worker(task):
            folder = out / task['id']; result = error = None
            try:
                with lease(ROOT, priority=2, label='rx_clock_skew_' + task['id']):
                    unchanged(task)
                    process = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'), cwd=folder, capture_output=True, text=True)
                (folder / 'console.log').write_text(process.stdout + process.stderr)
                process.check_returncode(); unchanged(task)
                result = measure(folder, task, m['identity']['aperture_receipt']); unchanged(task)
            except Exception as e:
                error = str(e)
            row = dict(variant=task['id'], result=result, error=error, manifest_sha256=stamp,
                       files={n: sha(folder / n) for n in OUTPUTS if (folder / n).exists()})
            capture_manifest(folder / 'summary.json', row)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(worker, m['tasks']))
        bound(out)
        report = dict(aggregate(m, rows), manifest_sha256=stamp)
        capture_manifest(out / 'summary.json', report)
        atomic(out / 'state.json', dict(status='clock_skew_screened' if report['clock_skew_source_passed'] else 'held_clock_skew_failed', qualified_phy=False))
    return report


def verify(out):
    m = bound(out); stamp = sha(out / 'manifest.json'); rows = []
    for task in m['tasks']:
        folder = out / task['id']; r = json.loads((folder / 'summary.json').read_text())
        if (r['variant'] != task['id'] or r['error'] is not None or r['manifest_sha256'] != stamp
                or set(r['files']) != set(OUTPUTS) or any(sha(folder / n) != h for n, h in r['files'].items())
                or r['result'] != measure(folder, task, m['identity']['aperture_receipt'])):
            raise ValueError('Receive-clock source result changed or incomplete')
        rows.append(r)
    report = dict(aggregate(m, rows), manifest_sha256=stamp)
    if report != json.loads((out / 'summary.json').read_text()):
        raise ValueError('Receive-clock aggregate changed')
    bound(out)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'bound', 'run', 'verify'])
    p.add_argument('artifact', type=Path); p.add_argument('--aperture', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        if not a.aperture: p.error('--aperture required')
        result = prepare(a.artifact.resolve(), a.aperture.resolve())
    else: result = globals()[a.action](a.artifact.resolve())
    print(result if a.action == 'prepare' else json.dumps(result, indent=2), flush=True)
