#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare exact resistor-only driver reduction with completed SF40/FF0 native pilots."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import numpy as np
import probe_driver_current as reference
from dll_campaign import atomic, text_block
from dll_measurements import read_wave
from exact_rc_candidate import parse, static_signature
from receiver_static_diagnosis import capture_manifest
from simulate_link import edge_times
from spice_dispatch import lease
from spice_engine import command, engine, provenance
from spice_library import replace
from spice_scope import closure_hash
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
CASES = ['native_driver_sf_40', 'native_driver_ff_0']
TOP = 'openlvds_driver_core'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def comparison(a, b):
    reference.complete_wave(a); reference.complete_wave(b)
    start, end = 2010e-9, 2530e-9
    diff = [w[:, 3]-w[:, 4] for w in [a, b]]
    cm = [(w[:, 3]+w[:, 4])*.5 for w in [a, b]]
    times = []
    for w, v in zip([a, b], diff):
        e = edge_times(w[:, 1], v, 0)
        times.append(e[(e > start) & (e < end)])
    ea, eb = times; equal = len(ea) == len(eb)
    error = float(np.max(abs(ea-eb))*1e12) if equal and len(ea) else None
    sample = np.linspace(start, end, 104001)
    keep = np.ones(len(sample), dtype=bool)
    for at in np.concatenate(times):
        keep &= abs(sample-at) > 300e-12
    sampled = [np.interp(sample, w[:, 1], v) for w, v in zip([a, b], diff)]
    voltage = float(np.max(abs(sampled[0][keep]-sampled[1][keep]))) if np.any(keep) else None
    common = [np.interp(sample, w[:, 1], v) for w, v in zip([a, b], cm)]
    cm_error = float(np.max(abs(common[0]-common[1])))
    return dict(passed=bool(equal and len(ea) >= 16 and error is not None and error <= 20 and
                voltage is not None and voltage <= .02 and cm_error <= .02),
        start_ns=2010, end_ns=2530, reference_edges=len(ea), candidate_edges=len(eb),
        maximum_edge_error_ps=error, differential_plateau_error_v=voltage, common_mode_error_v=cm_error,
        edge_tolerance_ps=20, voltage_tolerance_v=.02, edge_exclusion_ps=300,
        scope='All differential crossings and plateau voltage; common mode uses the complete waveform without excluding transitions. Full unchanged component metrics are checked separately.')


def substitute(source, candidate, signature):
    old = text_block(source, TOP)
    if static_signature(parse(old)) != signature or static_signature(parse(candidate)) != signature:
        raise ValueError('Exact driver changes a capacitor, device, port or directive')
    before = closure_hash(source, 'lvds_bias')
    result = replace(source, TOP, text_block(candidate, TOP))
    if closure_hash(result, 'lvds_bias') != before:
        raise ValueError('Exact driver benchmark changes shared bias')
    return result


def prepare(parent, observation):
    if (engine() != 'ngspice' or not parent.is_relative_to(ROOT/'build/diagnostics/driver_current') or
            not observation.is_relative_to(ROOT/'build/diagnostics/driver_layout')):
        raise ValueError('Use completed corrected-current pilots and bound exact-reduction observation')
    if not (parent/'summary.json').is_file() or any(not (parent/c/'summary.json').is_file() for c in reference.CASES):
        raise ValueError('Complete every original driver-current pilot first')
    if reference.run(parent)['passed'] is not True:
        raise ValueError('Original current-correction pilots failed')
    proof = json.loads((observation/'summary.json').read_text()); candidate = observation/'driver.exact.spice'
    if (proof.get('qualified_phy') is not False or proof['witness']['passed'] is not True or
            sha(candidate) != proof['exact_sha256']):
        raise ValueError('Exact driver lacks bound passing mathematical witnesses')
    for name, stamp in dict(proof['inputs'], **proof['math_runtime']['binaries']).items():
        if sha(ROOT/name) != stamp:
            raise ValueError('Exact driver mathematical witness context changed')
    pm = json.loads((parent/'manifest.json').read_text())
    if (pm['identity']['layout'] != str(observation.parent.relative_to(ROOT)) or
            proof['source_sha256'] not in pm['identity']['inputs'].values()):
        raise ValueError('Reference pilot uses another physical driver or resistor network')
    paths = [parent/n for n in ['manifest.json', 'summary.json']]
    paths.extend(observation/n for n in ['summary.json', 'driver.exact.spice'])
    paths.extend(parent/c/n for c in CASES for n in ['summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn'])
    names = set(pm['identity']['code']) | {NAME, 'exact_rc_candidate.py', 'reduce_rc.py', 'spice_scope.py', 'spice_library.py', 'spice_probes.py', 'simulate_link.py'}
    identity = dict(parent=str(parent.relative_to(ROOT)), observation=str(observation.relative_to(ROOT)),
        source_native_sha256=proof['source_sha256'], exact_sha256=proof['exact_sha256'],
        simulator_provenance=provenance(), inputs={str(p.relative_to(ROOT)): sha(p) for p in paths},
        code={n: sha(ROOT/'scripts'/n) for n in sorted(names)},
        scope='Same driver devices/capacitors/ports and full original 2540 ns SF40/FF0 fixtures. Only algebraic resistor nodes are eliminated. Native comparison and all original component metrics required. No catalog, active model, live campaign, full-PVT or PHY promotion.')
    root = ROOT/'build/diagnostics/driver_exact_benchmark'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True); tasks = []
    for c in CASES:
        old, new = parent/c, root/c; new.mkdir(exist_ok=True)
        body = substitute((old/'source.spice').read_text(), candidate.read_text(), proof['non_resistor_sha256'])
        include = f'.include "{old}/source.spice"'; deck = (old/'bench.cir').read_text()
        if deck.count(include) != 1:
            raise ValueError('Unexpected original driver benchmark inclusion')
        deck = deck.replace(include, f'.include "{new}/source.spice"')
        printed = re.findall(r'(?im)^\.print tran[^\n]*$', deck)
        if len(printed) != 1:
            raise ValueError('Expected one original driver observation statement')
        ProbeNetwork(body).validate(deck, re.findall(r'V\(([^)]+)\)', printed[0], re.I))
        for name, text in [('source.spice', body), ('bench.cir', deck)]:
            p = new/name
            if p.exists() and p.read_text() != text:
                raise ValueError('Prepared exact driver benchmark changed')
            if not p.exists():
                p.write_text(text)
        tasks.append(dict(id=c, files={n: sha(new/n) for n in ['source.spice', 'bench.cir']}))
    capture_manifest(root/'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/driver_exact_benchmark'):
        raise ValueError('Use a prepared exact driver comparison')
    m = json.loads((root/'manifest.json').read_text()); i = m['identity']; stamp = sha(root/'manifest.json')
    def unchanged():
        if (sha(root/'manifest.json') != stamp or provenance() != i['simulator_provenance'] or
                [t['id'] for t in m['tasks']] != CASES or
                any(sha(ROOT/'scripts'/n) != h for n, h in i['code'].items()) or
                any(sha(ROOT/n) != h for n, h in i['inputs'].items()) or
                any(sha(root/t['id']/n) != h for t in m['tasks'] for n, h in t['files'].items())):
            raise ValueError('Exact driver benchmark context changed')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged(); results = []
        for task in m['tasks']:
            out = root/task['id']; prior = ROOT/i['parent']/task['id']
            cached = json.loads((out/'summary.json').read_text()) if (out/'summary.json').exists() else None
            if cached is None:
                if any((out/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
                    raise ValueError('Partial exact driver benchmark retained; use a fresh context')
                atomic(root/'execution.json', dict(status='waiting_for_slot', task=task['id'], qualified_phy=False))
                with lease(ROOT, priority=1, label='exact-driver-'+task['id']):
                    unchanged(); atomic(root/'execution.json', dict(status='running', task=task['id'], qualified_phy=False))
                    started = time.monotonic()
                    p = subprocess.run(command(out/'ngspice.log', out/'bench.cir'), cwd=out, capture_output=True, text=True)
                    atomic(out/'runtime.json', dict(wall_seconds=time.monotonic()-started))
                (out/'console.log').write_text(p.stdout+p.stderr); p.check_returncode()
            elif sha(out/'bench.cir.prn') != cached['waveform_sha256']:
                raise ValueError('Completed exact driver waveform changed')
            unchanged(); a, _ = read_wave(prior/'bench.cir.prn'); b, _ = read_wave(out/'bench.cir.prn')
            metrics = reference.measurements(b); agree = comparison(a, b)
            r = dict(task=task['id'], qualified_phy=False, manifest_sha256=stamp,
                waveform_sha256=sha(out/'bench.cir.prn'), reference_waveform_sha256=sha(prior/'bench.cir.prn'),
                metrics=metrics, waveform_comparison=agree, passed=bool(metrics['passed'] and agree['passed']))
            unchanged()
            if cached is not None and cached != r:
                raise ValueError('Exact driver comparison remeasurement changed')
            capture_manifest(out/'summary.json', r); results.append(r)
        report = dict(diagnostic_complete=True, passed=all(r['passed'] for r in results), qualified_phy=False,
            manifest_sha256=stamp, results=results, scope=i['scope'])
        capture_manifest(root/'summary.json', report)
        atomic(root/'execution.json', dict(status='completed', passed=report['passed'], qualified_phy=False))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('prepare'); a.add_argument('parent', type=Path); a.add_argument('observation', type=Path)
    a = sub.add_parser('run'); a.add_argument('artifact', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.parent.resolve(), a.observation.resolve()), flush=True)
    else:
        run(a.artifact.resolve()); print(a.artifact.resolve()/'summary.json', flush=True)
