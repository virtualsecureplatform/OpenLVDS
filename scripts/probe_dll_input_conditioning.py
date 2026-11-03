#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate slew-dependent PFD offset with two matched PDK input buffers."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

import numpy as np
import dll_measurements as measurement
import preflight_compensated_dll as admission
from dll_campaign import atomic, bias_reference_count, closure
from receiver_static_diagnosis import capture_manifest
from run_ngspice import read_raw
from selected_phy import pins
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_probes import ProbeNetwork, scope

ROOT = Path(__file__).resolve().parents[1]
CELL = 'sky130_fd_sc_hd__buf_4'
CASES = [f'slew_ss_40_{offset}ps_20_200' for offset in [50, 150, -150]]
REFERENCES = [f'slew_ss_40_{offset}ps_20_200' for offset in [0, 50, -50, 150, -150]]
CODE = [Path(__file__).name, 'preflight_compensated_dll.py', 'qualify_dll_storage.py',
        'qualify_dll_candidate.py', 'dll_measurements.py', 'verify_phase_detector.py',
        'dll_campaign.py', 'spice_probes.py', 'spice_dispatch.py', 'spice_engine.py',
        'run_ngspice.py', 'selected_phy.py', 'receiver_static_diagnosis.py']


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def completed(folder):
    w, h = measurement.read_wave(folder / 'bench.cir.prn')
    names, raw = read_raw(folder / 'bench.raw')
    if (len(w) < 2 or not np.isfinite(raw).all() or not np.isfinite(w).all() or
            w[0, 1] > 1e-15 or w[-1, 1] < 160e-9 - 1e-12 or
            np.any(np.diff(w[:, 1]) <= 0) or
            not np.array_equal(raw[:, names.index('time')], w[:, 1]) or
            not np.array_equal(w[:, 0], np.arange(len(w)))):
        raise ValueError('Require complete finite 160 ns raw/export data')
    for name, col in h.items():
        if name.startswith('V(') and not np.array_equal(
                raw[:, names.index(name.replace(':', '.').lower())], w[:, col]):
            raise ValueError('Conditioning raw/export voltages differ')
    return w, h


def fixture(deck, old, new, cell_ports):
    include = f'.include "{old}/full.spice"'
    original = 'XP REF FDB RST VDDD UP DN VDDD 0 lvds_pfd'
    if (deck.count(include) != 1 or deck.splitlines().count(original) != 1 or
            re.findall(r'(?im)^\.tran[^\n]+', deck) != ['.tran 5p 160n 0 20p'] or
            {'REF_FAST', 'FDB_FAST'} & {n.upper() for n in scope(deck)[0]} or
            set(cell_ports) != {'A', 'X', 'VPWR', 'VPB', 'VGND', 'VNB'} or len(cell_ports) != 6):
        raise ValueError('Original phase fixture or PDK buffer interface changed')
    extra = []
    for label, before, after in [('REF', 'REF', 'REF_FAST'), ('FDB', 'FDB', 'FDB_FAST')]:
        mapping = dict(A=before, X=after, VPWR='VDDD', VPB='VDDD', VGND='0', VNB='0')
        extra.append('XCOND_' + label + ' ' + ' '.join(mapping[p] for p in cell_ports) + ' ' + CELL)
    result = deck.replace(include, f'.include "{new}/library.spice"').replace(original,
        '\n'.join(extra + ['XP REF_FAST FDB_FAST RST VDDD UP DN VDDD 0 lvds_pfd']))
    printed = re.findall(r'(?im)^\.print tran[^\n]+', result)
    if len(printed) != 1:
        raise ValueError('Require the original diagnostic observation statement')
    return result.replace(printed[0], printed[0] + ' V(REF_FAST) V(FDB_FAST)')


def prepare(qualification):
    original = admission.dll_context(qualification)
    qm = json.loads((qualification / 'manifest.json').read_text())
    tasks = {t['id']: t for t in qm['tasks']}
    references = []; paths = [qualification / n for n in
        ['manifest.json', 'storage_source_admission.json', 'full.spice']]
    for name in REFERENCES:
        task = tasks[name]; folder = qualification / name
        r = json.loads((folder / 'summary.json').read_text())
        if (task['fast_rc'] or task['spec']['process'] != 'ss' or task['spec']['temperature'] != 40 or
                r.get('returncode') != 0 or r.get('deck_sha256') != task['deck_sha256'] or
                sha(folder / 'bench.cir') != task['deck_sha256'] or
                sha(folder / 'bench.cir.prn') != r['waveform_sha256'] or
                sha(folder / 'bench.raw') != r['raw_sha256']):
            raise ValueError('Require unchanged completed native slew controls')
        completed(folder)
        with admission.storage.profile():
            measured = admission.storage.native.evaluate(qualification, task)
        if (measured != r['metrics'] or measured.get('complete') is not True or
                r['passed'] is not measured['passed']):
            raise ValueError('Native slew control remeasurement changed')
        references.append(dict(task=name, offset_ps=task['spec']['offset_ps'], metrics=measured))
        paths += [folder / n for n in ['summary.json', 'bench.cir', 'bench.raw', 'bench.cir.prn',
                                       'ngspice.log', 'console.log']]
    failed = next(r for r in references if r['offset_ps'] == 50)
    if failed['metrics']['passed'] is not False or failed['metrics']['expected_bad'] is not False:
        raise ValueError('Require the completed native +50 ps false-BAD failure')
    pdk = Path(os.environ['PDK_ROOT']) / 'sky130A/libs.ref/sky130_fd_sc_hd/spice/sky130_fd_sc_hd.spice'
    buffer = closure(pdk.read_text(), [CELL]); ports = pins(buffer, CELL)
    lib = original + '\n' + buffer
    inputs = {**qm['identity']['full_models']['physical_reports'],
              **{str(p.relative_to(ROOT)): sha(p) for p in paths}}
    a = json.loads((qualification / 'storage_source_admission.json').read_text())
    inputs.update(a['proofs'])
    code = {**qm['identity']['code'], **{n: sha(ROOT / 'scripts' / n) for n in CODE}}
    identity = dict(qualification=str(qualification.relative_to(ROOT)), inputs=inputs, code=code,
        simulator=provenance(), cell=CELL, cell_ports=ports,
        pdk_source=dict(path=str(pdk), sha256=sha(pdk)),
        scope='Matched SS40 400 MHz +50/+150/-150 ps, reference/feedback slew 20/200 ps. '
        'Original native DLL/PFD/bias and complete 160 ns/5 ps print/20 ps maximum-step '
        'fixtures retained. Two matched source PDK buffers condition only PFD inputs. '
        'Original native failures reused, never rerun or waived. Added buffers have ideal '
        'routing: source diagnostic only, not a new physical PFD, all-PVT, loop, stability, '
        'training, RC or PHY qualification. No supply/temperature sweep or active-model change.')
    out = ROOT / 'build/diagnostics/dll_input_conditioning' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        capture_manifest(out / 'reference_analysis.json', dict(results=references, qualified_phy=False))
        prepared = []
        for name in CASES:
            task = tasks[name]; folder = out / name; folder.mkdir(exist_ok=True)
            deck = fixture((qualification / name / 'bench.cir').read_text(), qualification, folder, ports)
            probes = re.findall(r'V\(([^)]+)\)', re.search(r'(?im)^\.print tran[^\n]+', deck)[0])
            ProbeNetwork(lib).validate(deck, probes)
            if bias_reference_count(deck, lib) != 1:
                raise ValueError('Conditioning duplicated native bias reference')
            for n, body in [('library.spice', lib), ('bench.cir', deck)]:
                p = folder / n
                if p.exists() and p.read_text() != body:
                    raise ValueError('Prepared input-conditioning model changed')
                if not p.exists(): p.write_text(body)
            prepared.append(dict(id=name, spec=task['spec'], aliases=task['aliases'],
                files={n: sha(folder / n) for n in ['library.spice', 'bench.cir']}))
        capture_manifest(out / 'manifest.json', dict(identity=identity, tasks=prepared,
            reference_analysis_sha256=sha(out / 'reference_analysis.json'), qualified_phy=False))
    return out


def bound(out):
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']
    if (not out.is_relative_to(ROOT / 'build/diagnostics/dll_input_conditioning') or
            out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16] or
            [t['id'] for t in m['tasks']] != CASES or i['cell'] != CELL or
            i['simulator'] != provenance() or sha(Path(i['pdk_source']['path'])) != i['pdk_source']['sha256'] or
            sha(out / 'reference_analysis.json') != m['reference_analysis_sha256'] or
            any(sha(ROOT / n) != h for n, h in i['inputs'].items()) or
            any(sha(ROOT / 'scripts' / n) != h for n, h in i['code'].items()) or
            any(sha(out / t['id'] / n) != h for t in m['tasks'] for n, h in t['files'].items())):
        raise ValueError('Input-conditioning context changed')
    return m


def measure(folder, task):
    w, h = completed(folder)
    for alias, n in task['aliases'].items():
        h['V(' + alias.upper() + ')'] = h['V(' + n.upper() + ')']
    result = measurement.phase(w, h, task['spec']['offset_ps'])
    t = w[:, 1]
    events = []
    for name in ['REF_FAST', 'FDB_FAST']:
        at = measurement.edges(t, measurement.column(w, h, name))
        events.append(at[(at > 120e-9) & (at < 160e-9)])
    ref, fb = events
    if len(ref) < 15 or len(fb) < 15:
        raise ValueError('Conditioned input is missing clock cycles')
    delta = np.array([fb[np.argmin(abs(fb - x))] - x for x in ref[1:-1]]) * 1e12
    result['conditioned_phase_mean_ps'] = float(np.mean(delta))
    result['conditioned_phase_spread_ps'] = float(np.ptp(delta))
    result['conditioning_phase_shift_ps'] = float(np.mean(delta) - task['spec']['offset_ps'])
    return result


def aggregate(out, rows):
    return dict(input_conditioning_diagnostic_passed=[r['task'] for r in rows] == CASES and all(r['passed'] for r in rows),
        results=rows, manifest_sha256=sha(out / 'manifest.json'), qualified_phy=False,
        physical_admission=False, scope=json.loads((out / 'manifest.json').read_text())['identity']['scope'])


def run(out):
    m = bound(out); stamp = sha(out / 'manifest.json')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / t['id'] / n).exists()
                for t in m['tasks'] for n in ['bench.raw', 'ngspice.log', 'summary.json']):
            raise ValueError('Prior or partial input-conditioning output retained; no retry')
        atomic(out / 'state.json', dict(status='running', qualified_phy=False))
        def execute(task):
            folder = out / task['id']; p = None; metrics = None; error = None; numerical = False
            try:
                with lease(ROOT, priority=2, label='dll_input_conditioning_' + task['id']):
                    bound(out)
                    p = subprocess.run(command(folder / 'ngspice.log', folder / 'bench.cir'),
                                       cwd=folder, capture_output=True, text=True)
                (folder / 'console.log').write_text(p.stdout + p.stderr)
                p.check_returncode(); bound(out); completed(folder); numerical = True
                metrics = measure(folder, task)
            except Exception as e: error = str(e)
            row = dict(task=task['id'], returncode=None if p is None else p.returncode,
                metrics=metrics, error=error, numerically_completed=numerical,
                passed=error is None and metrics is not None and metrics['passed'],
                manifest_sha256=stamp, qualified_phy=False,
                files={n: sha(folder / n) for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log']
                       if (folder / n).exists()})
            capture_manifest(folder / 'summary.json', row)
            return row
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(execute, m['tasks']))
        bound(out); report = aggregate(out, rows); capture_manifest(out / 'summary.json', report)
        atomic(out / 'state.json', dict(status='completed_diagnostic' if
            report['input_conditioning_diagnostic_passed'] else 'held_for_diagnosis', qualified_phy=False))
    return report


def verify(out):
    m = bound(out); rows = []
    for task in m['tasks']:
        folder = out / task['id']; r = json.loads((folder / 'summary.json').read_text())
        if (r['task'] != task['id'] or r['returncode'] != 0 or r['error'] is not None or
                r.get('numerically_completed') is not True or
                r['manifest_sha256'] != sha(out / 'manifest.json') or
                set(r['files']) != {'bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log'} or
                any(sha(folder / n) != h for n, h in r['files'].items()) or
                measure(folder, task) != r['metrics'] or r['passed'] is not r['metrics']['passed']):
            raise ValueError('Input-conditioning numerical result changed')
        rows.append(r)
    report = aggregate(out, rows)
    if report != json.loads((out / 'summary.json').read_text()):
        raise ValueError('Input-conditioning aggregate changed')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run', 'verify']); p.add_argument('artifact', type=Path)
    a = p.parse_args()
    result = globals()[a.action](a.artifact.resolve())
    print(result if a.action == 'prepare' else json.dumps(result, indent=2), flush=True)
