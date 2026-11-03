#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare a 5 ps maximum step with the completed 1 ps native coupled trace.

No native model, stimulus or requirement changes. This single SS40 diagnostic
can justify further numerical experiments, not a different circuit's solver
settings, full-PVT qualification or PHY release.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

import numpy as np
import restore_compensated_coupled as coupled
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest
from simulate_link import edge_times
from spice_dispatch import lease
from spice_engine import command, provenance

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'coupled_step_benchmark'
VERSION = 'native-coupled-maxstep-5ps-v1'
sha = coupled.sha
OUTPUTS = ('bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log')
IO = ('RP', 'RN', 'RCP', 'RCN', 'TP', 'TN', 'CP', 'CN')
DIGITAL = ('CLK0', 'CLK90', 'TXCLOCK', 'TXDATA', 'RXCLOCK', 'RXDATA', 'Q0', 'Q1', 'RXVALID', 'TXREADY')


def fixture(deck, parent, out):
    include = f'.include "{parent}/payload/library.spice"'
    if deck.count(include) != 1 or re.findall(r'(?im)^\.tran[^\n]+', deck) != ['.tran 1p 188.049n 0 1p']:
        raise ValueError('Require the completed native 188.049 ns / 1 ps fixture')
    # Preserve TSTEP; only the explicit maximum integration step changes.
    return deck.replace(include, f'.include "{out}/library.spice"').replace(
        '.tran 1p 188.049n 0 1p', '.tran 1p 188.049n 0 5p')


def prepare(parent):
    if coupled.verify(parent).get('payload_restored') is not True:
        raise ValueError('Require the independently verified restored native reference')
    pm = json.loads((parent / 'manifest.json').read_text())
    paths = [parent / 'manifest.json', parent / 'summary.json', parent / 'payload/summary.json']
    paths += [parent / 'payload' / n for n in ('library.spice', 'bench.cir', *OUTPUTS)]
    code = dict(pm['identity']['code']); code[Path(__file__).name] = sha(Path(__file__))
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), simulator=provenance(),
        inputs={**pm['identity']['inputs'], **{str(p.relative_to(ROOT)): sha(p) for p in paths}}, code=code,
        maximum_step_ps=5, reference_maximum_step_ps=1, io_error_limit_v=.01, edge_error_limit_ps=2.5,
        margin_error_limit_ps=2.5, stop_ns=188.049)
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    from expand_dll_slew_frontends import write_once
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        write_once(out / 'library.spice', (parent / 'payload/library.spice').read_text())
        write_once(out / 'bench.cir', fixture((parent / 'payload/bench.cir').read_text(), parent, out))
        (out / 'producers').mkdir(exist_ok=True)
        for name in code:
            write_once(out / 'producers' / name, (ROOT / 'scripts' / name).read_text())
        capture_manifest(out / 'manifest.json', dict(identity=identity,
            files={n: sha(out / n) for n in ('bench.cir', 'library.spice')}, qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Require an isolated numerical-step benchmark')
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']; parent = ROOT / i['parent']
    if (out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['version'] != VERSION or i['simulator'] != provenance() or m['qualified_phy'] is not False
            or i['maximum_step_ps'] != 5 or i['reference_maximum_step_ps'] != 1 or i['stop_ns'] != 188.049
            or i['io_error_limit_v'] != .01 or i['edge_error_limit_ps'] != 2.5 or i['margin_error_limit_ps'] != 2.5
            or any(sha(ROOT / n) != h for n, h in i['inputs'].items())
            or any(sha(ROOT / 'scripts' / n) != h or sha(out / 'producers' / n) != h for n, h in i['code'].items())
            or set(m['files']) != {'bench.cir', 'library.spice'} or any(sha(out / n) != h for n, h in m['files'].items())
            or (out / 'library.spice').read_bytes() != (parent / 'payload/library.spice').read_bytes()
            or (out / 'bench.cir').read_text() != fixture((parent / 'payload/bench.cir').read_text(), parent, out)):
        raise ValueError('Numerical-step benchmark context changed')
    return m


def crossings(reference_t, reference, candidate_t, candidate, level):
    result = {}; passed = True
    for rising, label in ((True, 'rising'), (False, 'falling')):
        a = edge_times(reference_t, reference, level, rising)
        b = edge_times(candidate_t, candidate, level, rising)
        a = a[(a >= 60e-9) & (a <= 120e-9)]; b = b[(b >= 60e-9) & (b <= 120e-9)]
        error = float(np.max(abs(a - b)) * 1e12) if len(a) == len(b) and len(a) else (0. if len(a) == len(b) else None)
        valid = error is not None and error <= 2.5
        result[label] = dict(reference_events=len(a), candidate_events=len(b), max_error_ps=error, passed=valid)
        passed = passed and valid
    return dict(passed=passed, polarities=result)


def compare(reference, rh, candidate, ch):
    if set(rh) != set(ch):
        raise ValueError('Numerical comparison dropped or changed original observations')
    if (not np.isfinite(reference).all() or not np.isfinite(candidate).all()
            or reference[0, 1] > 1e-15 or candidate[0, 1] > 1e-15
            or min(reference[-1, 1], candidate[-1, 1]) < 188.049e-9 - 1e-12
            or np.any(np.diff(reference[:, 1]) <= 0) or np.any(np.diff(candidate[:, 1]) <= 0)):
        raise ValueError('Require both complete finite numerical traces')
    rt, ct = reference[:, 1], candidate[:, 1]
    all_errors = {n: float(np.max(abs(candidate[:, ch[n]] - np.interp(ct, rt, reference[:, col]))))
                  for n, col in rh.items() if n.startswith('V(')}
    io = {n: all_errors['V(' + n + ')'] for n in IO}
    edges = {n: crossings(rt, reference[:, rh['V(' + n + ')']], ct, candidate[:, ch['V(' + n + ')']], .9) for n in DIGITAL}
    levels = {}
    for name in DIGITAL:
        source = reference[:, rh['V(' + name + ')']]
        expected = np.interp(ct, rt, source); actual = candidate[:, ch['V(' + name + ')']]
        keep = (ct >= 60e-9) & (ct <= 120e-9) & ((expected < .18) | (expected > 1.62))
        for at in edge_times(rt, source):
            keep &= abs(ct - at) > 20e-12
        high = expected[keep] > .9
        valid = bool(np.any(keep) and np.all(actual[keep][high] > 1.44) and np.all(actual[keep][~high] < .36))
        levels[name] = dict(passed=valid, observed_plateau_samples=int(keep.sum()), edge_exclusion_ps=20)
    for label, positive, negative in (('data_differential', 'RP', 'RN'), ('clock_differential', 'RCP', 'RCN')):
        edges[label] = crossings(rt, reference[:, rh['V(' + positive + ')']] - reference[:, rh['V(' + negative + ')']],
            ct, candidate[:, ch['V(' + positive + ')']] - candidate[:, ch['V(' + negative + ')']], 0)
    return dict(passed=max(io.values()) <= .01 and all(r['passed'] for r in edges.values()) and all(r['passed'] for r in levels.values()),
        io_error_v=io, io_error_limit_v=.01, edge_checks=edges, edge_error_limit_ps=2.5,
        digital_level_checks=levels, all_observation_errors_v=all_errors,
        scope='Whole-trace I/O voltage comparison; both-polarity event counts and ordered crossings in 60-120 ns. '
              'Internal/digital switching-point voltage errors are reported; their timing is checked separately.')


def measure(out, m):
    parent = ROOT / m['identity']['parent']
    a, ah = coupled.baseline.completed_export(parent / 'payload', 188.049)
    b, bh = coupled.baseline.completed_export(out, 188.049)
    comparison = compare(a, ah, b, bh)
    reference = coupled.payload(parent / 'payload'); candidate = coupled.payload(out)
    margin_errors = {}
    for kind in ('setup', 'hold'):
        a_margin = reference['payload'].get(kind + '_margin_ps'); b_margin = candidate['payload'].get(kind + '_margin_ps')
        margin_errors[kind] = (abs(a_margin - b_margin) if a_margin is not None and b_margin is not None
                              and np.isfinite([a_margin, b_margin]).all() else None)
    passed = bool(comparison['passed'] and reference['payload_restored'] and candidate['payload_restored']
        and reference['payload']['checked_bits'] == candidate['payload']['checked_bits'] == 32
        and all(error is not None and error <= 2.5 for error in margin_errors.values()))
    return dict(coupled_step_equivalence_passed=passed, comparison=comparison, reference=reference, candidate=candidate,
        margin_error_ps=margin_errors, margin_error_limit_ps=2.5, qualified_phy=False,
        scope='One unchanged native SS40/410 MHz 188.049 ns diagnostic with complete 1 ps reference. '
              'Only maximum step is 5 ps. No change to healthy jobs, model/circuit, PVT, training, '
              'slew-domain requirements, production runner or release gates. A different circuit/PVT '
              'and any downstream timing-error allowance need separate evidence.')


def run(out):
    m = bound(out); stamp = sha(out / 'manifest.json')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / n).exists() for n in (*OUTPUTS, 'summary.json')):
            raise ValueError('Prior numerical benchmark output retained; no retry')
        atomic(out / 'state.json', dict(status='waiting_for_step_benchmark', qualified_phy=False))
        with lease(ROOT, priority=2, label='coupled_native_maxstep_5ps'):
            bound(out); started = time.monotonic()
            atomic(out / 'state.json', dict(status='benchmarking_5ps_maximum_step', qualified_phy=False))
            process = subprocess.run(command(out / 'ngspice.log', out / 'bench.cir'), cwd=out, capture_output=True, text=True)
            elapsed = time.monotonic() - started
        (out / 'console.log').write_text(process.stdout + process.stderr)
        result = error = None
        try:
            process.check_returncode(); bound(out); result = measure(out, m)
        except Exception as e:
            error = str(e)
        report = dict(result=result, error=error, returncode=process.returncode, simulation_wall_seconds=elapsed,
            manifest_sha256=stamp, files={n: sha(out / n) for n in OUTPUTS if (out / n).exists()}, qualified_phy=False)
        capture_manifest(out / 'summary.json', report)
        atomic(out / 'state.json', dict(status='step_benchmarked' if error is None else 'held_for_diagnosis', qualified_phy=False))
    return report


def verify(out):
    m = bound(out); r = json.loads((out / 'summary.json').read_text())
    if (r['manifest_sha256'] != sha(out / 'manifest.json') or r['returncode'] != 0 or r['error'] is not None
            or set(r['files']) != set(OUTPUTS) or any(sha(out / n) != h for n, h in r['files'].items()) or r['result'] != measure(out, m)):
        raise ValueError('Numerical-step benchmark changed or incomplete')
    return r


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'bound', 'run', 'verify'])
    p.add_argument('artifact', type=Path); a = p.parse_args(); result = globals()[a.action](a.artifact.resolve())
    print(result if a.action == 'prepare' else json.dumps(result, indent=2), flush=True)
