#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolated degree-eight exact-R benchmark against a completed compensated pilot."""
import argparse
from copy import deepcopy
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import numpy as np
import exact_rc_candidate as exact
import probe_driver_compact_native as pilot
import driver_native_stress as stress
from dll_campaign import atomic, text_block
from dll_measurements import read_wave, edges
from receiver_static_diagnosis import capture_manifest
from reduce_rc import eliminate
from run_ngspice import read_raw
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_library import replace
from spice_probes import ProbeNetwork
from spice_scope import closure_hash

ROOT = Path(__file__).resolve().parents[1]
TOP = 'openlvds_driver_core'
CASE = 'tt_25_negative_op'
CODE = [Path(__file__).name, 'exact_rc_candidate.py', 'reduce_rc.py',
        'driver_native_stress.py', 'spice_scope.py']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate(model, deck):
    """Preserve every saved conductor as well as every physical R/C boundary."""
    original = exact.parse(text_block(model, TOP))
    observed = re.findall(r'V\(XD:XCORE:([^)]+)\)', deck, re.I)
    original['protected'].update(observed)
    reduced = deepcopy(original)
    removed = eliminate(reduced['graph'], reduced['protected'], 8)
    block = exact.render(reduced, 8)
    serialized = exact.parse(block)
    serialized['protected'].update(observed)
    if (exact.static_signature(original) != exact.static_signature(serialized) or
            original['protected'] != serialized['protected']):
        raise ValueError('Exact reduction changed a device, capacitor, port or directive')
    witness = exact.witness(original, serialized)
    if not witness['passed']:
        raise ValueError('Independent terminal-current witnesses failed')
    result = replace(model, TOP, block)
    if closure_hash(result, 'lvds_bias') != closure_hash(model, 'lvds_bias'):
        raise ValueError('Exact reduction changed native bias')
    probes = re.findall(r'V\(([^)]+)\)', deck, re.I)
    ProbeNetwork(result).validate(deck, probes)
    if stress.terminal_observations(model, deck) != stress.terminal_observations(result, deck):
        raise ValueError('Actual native MOS terminal observations changed')
    return result, dict(witness=witness, degree=8, algebraic_nodes_eliminated=removed,
        resistor_count_before=original['resistors'], resistor_count_after=serialized['resistors'],
        non_resistor_sha256=exact.static_signature(serialized),
        protected_observations=sorted(set(observed)))


def complete_raw(folder):
    wave, header = read_wave(folder / 'bench.cir.prn')
    names, raw = read_raw(folder / 'bench.raw')
    t = raw[:, names.index('time')]
    if (len(t) < 2 or not np.isfinite(raw).all() or t[0] > 1e-15 or
            t[-1] < 80e-9 - 1e-12 or np.any(np.diff(t) <= 0) or
            not np.array_equal(t, wave[:, 1]) or
            not np.array_equal(wave[:, 0], np.arange(len(t)))):
        raise ValueError('Require complete finite 80 ns raw/export data')
    for name, col in header.items():
        if name.startswith('V(') and not np.array_equal(
                wave[:, col], raw[:, names.index(name.replace(':', '.').lower())]):
            raise ValueError('Saved raw/export voltages differ')
    return names, raw


def agreement(a, b):
    na, ra = a; nb, rb = b
    if na != nb:
        raise ValueError('Saved observations changed')
    grid = np.linspace(0, 80e-9, 80001)
    ta, tb = ra[:, na.index('time')], rb[:, nb.index('time')]
    errors = {n: float(np.max(abs(np.interp(grid, ta, ra[:, col]) -
                                  np.interp(grid, tb, rb[:, col]))))
              for col, n in enumerate(na) if n.startswith('v(')}
    events = []
    for rising in [True, False]:
        ea, eb = [edges(t, raw[:, names.index('v(p)')] - raw[:, names.index('v(n)')],
                        level=0, rising=rising) for names, raw, t in [(na, ra, ta), (nb, rb, tb)]]
        same = len(ea) == len(eb) and len(ea) >= 20
        error = float(np.max(abs(ea - eb)) * 1e12) if same else None
        events.append(dict(rising=rising, reference_edges=len(ea), candidate_edges=len(eb),
                           maximum_error_ps=error, passed=bool(same and error <= 20)))
    return dict(passed=bool(errors and max(errors.values()) <= .02 and all(e['passed'] for e in events)),
        maximum_voltage_errors_v=errors, edges=events, voltage_tolerance_v=.02,
        edge_tolerance_ps=20, interpolation_step_ps=1, interval_ns=[0, 80])


def prepare(parent):
    report = pilot.verify(parent)
    pm = pilot.bound(parent)
    if (report['native_output_pilot_passed'] is not True or
            pm['identity'].get('view') != 'native_core_and_native_bias' or
            'source_readiness' not in pm['identity']):
        raise ValueError('Require complete passing compensated native core/bias pilots')
    old = parent / CASE
    paths = [parent / 'manifest.json', parent / 'summary.json']
    paths += [old / n for n in ['source.spice', 'bench.cir', 'summary.json',
                               'bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log',
                               'probes.json', 'mos_observations.json']]
    identity = dict(parent=str(parent.relative_to(ROOT)), case=CASE, degree=8,
        inputs={**pm['identity']['inputs'], **exact.math_runtime()['binaries'],
                **{str(p.relative_to(ROOT)): sha(p) for p in paths}},
        math_runtime=exact.math_runtime(), simulator=provenance(),
        code={**pm['identity']['code'], **{n: sha(ROOT / 'scripts' / n) for n in CODE}},
        scope='One matched TT25 negative-polarity 80 ns/1 ps diagnostic. Exact resistor-only '
        'elimination; all capacitors, PDK devices, MOS terminals, probes, native bias, rails, '
        'stimuli and loads retained. Completed reference reused. No active-model, PVT or PHY promotion.')
    out = ROOT / 'build/diagnostics/compensated_driver_exact' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'manifest.json').exists():
            bound(out)
            return out
        deck = (old / 'bench.cir').read_text()
        include = f'.include "{old}/source.spice"'
        if deck.count(include) != 1 or re.findall(r'(?im)^\.tran[^\n]+', deck) != ['.tran 1p 80n 0 1p']:
            raise ValueError('Original native pilot fixture changed')
        model, proof = candidate((old / 'source.spice').read_text(), deck)
        for name, body in [('source.spice', model), ('bench.cir', deck.replace(
                include, f'.include "{out}/source.spice"'))]:
            p = out / name
            if p.exists() and p.read_text() != body:
                raise ValueError('Prepared candidate changed')
            p.write_text(body)
        capture_manifest(out / 'admittance_witness.json', proof)
        capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False,
            files={n: sha(out / n) for n in ['source.spice', 'bench.cir', 'admittance_witness.json']}))
    return out


def bound(out):
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']
    if (not out.is_relative_to(ROOT / 'build/diagnostics/compensated_driver_exact') or
            out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16] or
            i['case'] != CASE or i['degree'] != 8 or provenance() != i['simulator'] or
            exact.math_runtime() != i['math_runtime'] or
            any(sha(ROOT / n) != h for n, h in i['inputs'].items()) or
            any(sha(ROOT / 'scripts' / n) != h for n, h in i['code'].items()) or
            any(sha(out / n) != h for n, h in m['files'].items())):
        raise ValueError('Exact benchmark context changed')
    return m


def compare(out):
    m = bound(out); receipt = json.loads((out / 'execution.json').read_text())
    if (receipt.get('returncode') != 0 or receipt.get('status') != 'process_completed' or
            receipt.get('manifest_sha256') != sha(out / 'manifest.json') or
            set(receipt['files']) != {'bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log'} or
            any(sha(out / n) != h for n, h in receipt['files'].items())):
        raise ValueError('Require bound complete numerical execution')
    old = ROOT / m['identity']['parent'] / CASE
    metric, dc = pilot.measure(out)
    reference = json.loads((old / 'summary.json').read_text())
    if pilot.measure(old) != (reference['metrics'], reference['initial_dc']):
        raise ValueError('Reference remeasurement changed')
    result = agreement(complete_raw(old), complete_raw(out))
    # This single-polarity benchmark establishes equivalence, never pilot admission.
    dc_error = abs(dc['differential_v'] - reference['initial_dc']['differential_v'])
    report = dict(passed=bool(result['passed'] and dc_error <= .02 and
                             metric['rising_output_edges'] == reference['metrics']['rising_output_edges']),
        waveform=result, metrics=metric, initial_dc=dc, dc_differential_error_v=dc_error,
        manifest_sha256=sha(out / 'manifest.json'), execution_sha256=sha(out / 'execution.json'),
        qualified_phy=False, scope=m['identity']['scope'])
    bound(out)
    capture_manifest(out / 'comparison.json', report)
    return report


def run(out):
    bound(out)
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if any((out / n).exists() for n in ['state.json', 'bench.raw', 'ngspice.log', 'execution.json']):
            raise ValueError('Prior or partial benchmark retained; no retry')
        atomic(out / 'state.json', dict(status='waiting_for_slot', qualified_phy=False))
        with lease(ROOT, priority=2, label='compensated_driver_exact_tt25'):
            bound(out)
            atomic(out / 'state.json', dict(status='running', qualified_phy=False))
            start = time.monotonic()
            p = subprocess.run(command(out / 'ngspice.log', out / 'bench.cir'),
                               cwd=out, capture_output=True, text=True)
            elapsed = time.monotonic() - start
        (out / 'console.log').write_text(p.stdout + p.stderr)
        bound(out)
        atomic(out / 'execution.json', dict(status='process_completed' if p.returncode == 0 else 'failed',
            returncode=p.returncode, wall_seconds=elapsed, manifest_sha256=sha(out / 'manifest.json'),
            files={n: sha(out / n) for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log']
                   if (out / n).exists()}))
        p.check_returncode()
        report = compare(out)
        atomic(out / 'state.json', dict(status='completed', passed=report['passed'], qualified_phy=False))
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run', 'compare'])
    p.add_argument('artifact', type=Path)
    a = p.parse_args()
    result = prepare(a.artifact.resolve()) if a.action == 'prepare' else globals()[a.action](a.artifact.resolve())
    print(result if a.action == 'prepare' else json.dumps(result, indent=2), flush=True)
