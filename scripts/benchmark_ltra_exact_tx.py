#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Benchmark resistor-only TX elimination against the unchanged restored LTRA chain."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import numpy as np
import recover_baseline_payload as baseline
from dll_campaign import atomic, text_block
from exact_rc_candidate import parse, static_signature
from receiver_static_diagnosis import capture_manifest
from simulate_link import edge_times
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_library import replace
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
TOP = 'openlvds_tx_core'
sha = baseline.sha


def substitute(library, raw, reduced):
    if text_block(library, TOP) != text_block(raw, TOP):
        raise ValueError('Reference does not use the bound raw TX')
    if static_signature(parse(raw)) != static_signature(parse(reduced)):
        raise ValueError('Exact TX changes devices, capacitors, ports or directives')
    return replace(library, TOP, text_block(reduced, TOP))


def prepare(parent, witness):
    if (not parent.is_relative_to(ROOT / 'build/diagnostics/baseline_payload_recovery') or
            not witness.is_relative_to(ROOT / 'build/diagnostics/tx_exact_current_witness')):
        raise ValueError('Use restored payload reference and exact TX witnesses')
    original = baseline.original.context(parent)
    if provenance() != original['identity']['simulator']:
        raise ValueError('Reference simulator changed')
    if any(sha(parent / n) != h for n, h in original['files'].items()):
        raise ValueError('Reference fixture changed')
    proof = json.loads((witness / 'summary.json').read_text())
    wi = proof['identity']
    if (witness.name != hashlib.sha256(json.dumps(wi, sort_keys=True).encode()).hexdigest()[:16]
            or proof['witness']['passed'] is not True or proof['resistors_before'] != 22909
            or proof['resistors_after'] != 5757):
        raise ValueError('Require the complete canonical TX current witness')
    inputs = dict(original['identity']['inputs'], **wi['inputs'])
    inputs.update(wi['math_runtime']['binaries'])
    for name, value in wi['code'].items():
        inputs['scripts/' + name] = value
    if any(sha(ROOT / n) != h for n, h in inputs.items()):
        raise ValueError('Exact TX mathematical evidence changed')
    info = json.loads((ROOT / wi['physical'] / 'extraction.json').read_text())
    raw, reduced = [(ROOT / info[key]).read_text() for key in ['raw_netlist', 'netlist']]
    if static_signature(parse(raw)) != proof['non_resistor_sha256']:
        raise ValueError('Exact TX signature differs from mathematical witness')
    library = substitute((parent / 'library.spice').read_text(), raw, reduced)
    deck = (parent / 'bench.cir').read_text()
    include = f'.include "{parent}/library.spice"'
    if deck.count(include) != 1 or re.findall(r'(?im)^\.tran[^\n]+', deck) != ['.tran 1p 188.049n 0 1p']:
        raise ValueError('Require unchanged 188.049 ns / 1 ps LTRA fixture')
    probes = re.findall(r'V\(([^)]+)\)', re.search(r'(?im)^\.print tran[^\n]+', deck)[0])
    ProbeNetwork(library).validate(deck, probes)
    paths = [parent / n for n in ['manifest.json', 'bench.cir', 'library.spice']]
    paths += [witness / 'summary.json']
    inputs.update({str(p.relative_to(ROOT)): sha(p) for p in paths})
    code = dict(original['identity']['code'])
    for name in [Path(__file__).name, 'exact_rc_candidate.py', 'spice_library.py', 'spice_probes.py']:
        code[name] = sha(ROOT / 'scripts' / name)
    identity = dict(reference=str(parent.relative_to(ROOT)), inputs=inputs, code=code,
        simulator=provenance(), scope='Matched full 188.049 ns LTRA diagnostic, raw versus '
        'existing exact resistor-only TX reduction. All devices, capacitors, probes, '
        'rails, native bias/RX, channel, stimuli and solver settings remain identical. '
        'Reuse the running raw reference; no raw rerun or retry. Numerical equivalence '
        'and performance experiment only; matching a failing payload cannot qualify a PHY.')
    out = ROOT / 'build/diagnostics/ltra_exact_tx_benchmark' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    deck = deck.replace(include, f'.include "{out}/library.spice"')
    for name, body in [('library.spice', library), ('bench.cir', deck)]:
        path = out / name
        if path.exists() and path.read_text() != body:
            raise ValueError('Prepared benchmark fixture changed')
        if not path.exists():
            path.write_text(body)
    capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False,
        files={name: sha(out / name) for name in ['bench.cir', 'library.spice']}))
    return out


def context(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics/ltra_exact_tx_benchmark'):
        raise ValueError('Use prepared LTRA exact TX benchmark')
    m = baseline.original.context(out)
    if provenance() != m['identity']['simulator'] or any(sha(out / n) != h for n, h in m['files'].items()):
        raise ValueError('Benchmark runtime or fixture changed')
    return m


def run(out):
    m = context(out)
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if any((out / n).exists() for n in ['state.json', 'bench.raw', 'ngspice.log', 'summary.json']):
            raise ValueError('Prior or partial benchmark output retained')
        atomic(out / 'state.json', dict(status='waiting_for_exact_tx_slot', qualified_phy=False))
        with lease(ROOT, priority=2, label='ltra_exact_tx_payload'):
            context(out)
            atomic(out / 'state.json', dict(status='running_exact_tx', qualified_phy=False))
            start = time.monotonic()
            result = subprocess.run(command(out / 'ngspice.log', out / 'bench.cir'),
                                    cwd=out, capture_output=True, text=True)
            elapsed = time.monotonic() - start
        (out / 'console.log').write_text(result.stdout + result.stderr)
        context(out)
        metrics = transport = None
        if result.returncode == 0:
            metrics, transport = baseline.payload_metrics(out)
        capture_manifest(out / 'summary.json', dict(returncode=result.returncode,
            numerically_completed=metrics is not None, metrics=metrics, clock_transport=transport,
            elapsed_simulator_s=elapsed, manifest_sha256=sha(out / 'manifest.json'),
            qualified_phy=False, electrical_verdict=None, comparison_pending=True,
            files={n: sha(out / n) for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log']
                   if (out / n).exists()}, scope=m['identity']['scope']))
        atomic(out / 'state.json', dict(status='completed_diagnostic' if metrics is not None
                                       else 'held_numerical_failure', qualified_phy=False))


def wave_comparison(a, ha, b, hb):
    if ha != hb or any(w.ndim != 2 or len(w) < 2 or not np.isfinite(w).all() or
            w[0, 1] > 1e-15 or w[-1, 1] < 188.049e-9 - 1e-12 or
            np.any(np.diff(w[:, 1]) <= 0) for w in [a, b]):
        raise ValueError('Require both complete matched exports')
    grid = np.linspace(0, 188.049e-9, 188050)
    voltage = {name: float(np.max(abs(np.interp(grid, a[:, 1], a[:, col]) -
                                    np.interp(grid, b[:, 1], b[:, col]))))
               for name, col in ha.items() if name.startswith('V(')}
    signals = [(name, .9) for name in ['TXCLOCK', 'TXDATA', 'RXCLOCK', 'RXDATA', 'Q0', 'Q1', 'RXVALID']]
    edges = []
    for name, level in signals:
        for rising in [True, False]:
            events = [edge_times(w[:, 1], w[:, h['V(' + name + ')']], level, rising)
                      for w, h in [(a, ha), (b, hb)]]
            error = float(max(abs(events[0] - events[1])) * 1e12) if len(events[0]) == len(events[1]) and len(events[0]) else None
            edges.append(dict(signal=name, rising=rising, reference_edges=len(events[0]),
                              candidate_edges=len(events[1]), maximum_error_ps=error))
    counts = all(r['reference_edges'] == r['candidate_edges'] for r in edges)
    timing = all(r['maximum_error_ps'] is None or r['maximum_error_ps'] <= 20 for r in edges)
    switching = sum(r['reference_edges'] for r in edges if r['signal'] == 'TXCLOCK') >= 32
    return dict(passed=bool(counts and timing and switching and voltage and max(voltage.values()) <= .02),
                maximum_voltage_error_v=voltage, edges=edges, edge_tolerance_ps=20,
                voltage_tolerance_v=.02, interpolation_step_ps=1, interval_ns=[0, 188.049])


def compare(out):
    m = context(out)
    reference = ROOT / m['identity']['reference']
    baseline.original.context(reference)
    rows = []
    for folder in [reference, out]:
        receipt = folder / 'summary.json'
        if not receipt.is_file():
            raise ValueError('Wait for both original full runs; no retry or partial comparison')
        row = json.loads(receipt.read_text())
        if (row.get('numerically_completed') is not True or row.get('returncode') != 0 or
                row.get('manifest_sha256') != sha(folder / 'manifest.json') or
                any(sha(folder / n) != h for n, h in row['files'].items())):
            raise ValueError('Completed benchmark evidence changed or failed')
        metrics, transport = baseline.payload_metrics(folder)
        if metrics != row['metrics'] or transport != row['clock_transport']:
            raise ValueError('Original diagnostic remeasurement changed')
        rows.append(row)
    a, ha = baseline.completed_export(reference, 188.049)
    b, hb = baseline.completed_export(out, 188.049)
    result = wave_comparison(a, ha, b, hb)
    outcome = all(rows[0]['metrics'].get(k) == rows[1]['metrics'].get(k)
                  for k in ['passed', 'error', 'observed', 'word_errors', 'checked_bits'])
    files = {str((p / n).relative_to(ROOT)): sha(p / n) for p in [reference, out]
             for n in ['manifest.json', 'summary.json', 'bench.raw', 'bench.cir.prn']}
    capture_manifest(out / 'comparison.json', dict(exact_tx_comparison_passed=result['passed'] and outcome,
        waveform=result, diagnostic_outcome_agrees=outcome, files=files, qualified_phy=False,
        reference_payload_passed=rows[0]['metrics']['passed'],
        scope='Full matched numerical comparison only; no electrical failure is waived.'))
    return out / 'comparison.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'run', 'compare'])
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--witness', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        if args.witness is None:
            parser.error('--witness required')
        print(prepare(args.artifact.resolve(), args.witness.resolve()), flush=True)
    elif args.action == 'run':
        run(args.artifact.resolve())
    else:
        print(compare(args.artifact.resolve()), flush=True)
