#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Observe actual clock-mux and output-buffer receiving gates in the native TX.

Only observations, include location and the explicit 120 ns stop change.
The complete native model, loads, controls, stimuli and 1 ps step are retained.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
import diagnose_forwarded_clock as topology
import restore_compensated_coupled as coupled
from dll_campaign import atomic, text_block
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease
from spice_engine import command, provenance
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'tx_clock_path_observation'
sha = coupled.sha
OUTPUTS = ('bench.raw', 'bench.cir.prn', 'ngspice.log', 'console.log')
PORTS = dict(mux_select='clock_launch_output_logic.S', output_buffer_input='clock_launch_output_drive.A',
             constant_low='clock_launch_output_logic.A1', constant_high='clock_launch_output_logic.A0')


def observations(library):
    rows = []
    for line in text_block(library, 'openlvds_tx_core').splitlines():
        w = line.split()
        if len(w) >= 6 and w[0].startswith('X') and ('nfet' in w[5] or 'pfet' in w[5]):
            rows.append(dict(device=w[0], model=w[5], terminals=dict(zip(('D', 'G', 'S', 'B'), w[1:5]))))
    result = {}
    for role, prefix in PORTS.items():
        gates_only = role in ('mux_select', 'output_buffer_input')
        nodes = sorted({n for r in rows for pin, n in r['terminals'].items()
            if (not gates_only or pin == 'G') and (n == prefix or re.fullmatch(re.escape(prefix) + r'\.t\d+', n))})
        expected = dict(mux_select=4, output_buffer_input=2).get(role)
        if not nodes or (expected is not None and len(nodes) != expected):
            raise ValueError('Missing actual native TX terminal observations: ' + role)
        result[role] = [dict(node='XTX:' + n, devices=[dict(device=r['device'], model=r['model'], terminal=pin)
            for r in rows for pin, actual in r['terminals'].items() if actual == n and (not gates_only or pin == 'G')]) for n in nodes]
    return result


def fixture(parent_deck, parent, out, probes):
    include = f'.include "{parent}/payload/library.spice"'
    if parent_deck.count(include) != 1 or re.findall(r'(?im)^\.tran[^\n]+', parent_deck) != ['.tran 1p 188.049n 0 1p']:
        raise ValueError('Require the original completed payload fixture')
    prints = re.findall(r'(?im)^\.print tran[^\n]+', parent_deck)
    if len(prints) != 1:
        raise ValueError('Require one original voltage observation statement')
    existing = re.findall(r'V\(([^)]+)\)', prints[0])
    added = sorted({r['node'] for group in probes.values() for r in group} - set(existing))
    return parent_deck.replace(include, f'.include "{out}/library.spice"').replace(
        '.tran 1p 188.049n 0 1p', '.tran 1p 120n 0 1p').replace(prints[0], prints[0] + ' ' + ' '.join('V(' + n + ')' for n in added))


def prepare(parent):
    verified = coupled.verify(parent)
    if verified.get('payload_restored') is not True:
        raise ValueError('Require independently verified restored coupled payload')
    function, physical = topology.topology(parent)
    pm = json.loads((parent / 'manifest.json').read_text())
    library = (parent / 'payload/library.spice').read_text(); probes = observations(library)
    paths = [parent / 'manifest.json', parent / 'summary.json', parent / 'payload/summary.json']
    paths += [parent / 'payload' / n for n in ('library.spice', 'bench.cir', *OUTPUTS)]
    code = dict(pm['identity']['code'])
    for name in (Path(__file__).name, 'diagnose_forwarded_clock.py', 'diagnose_compensated_clock.py',
                 'digital_candidate_rc.py', 'physical_policy.py', 'spice_dispatch.py', 'spice_probes.py'):
        code[name] = sha(ROOT / 'scripts' / name)
    identity = dict(parent=str(parent.relative_to(ROOT)), inputs={**pm['identity']['inputs'], **physical,
        **{str(p.relative_to(ROOT)): sha(p) for p in paths}}, code=code, topology=function,
        simulator=provenance(), stop_ns=120, maximum_step_ps=1, public_reproduction_limit_v=1e-6)
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    from expand_dll_slew_frontends import write_once
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        write_once(out / 'library.spice', library)
        deck = fixture((parent / 'payload/bench.cir').read_text(), parent, out, probes)
        ProbeNetwork(library).validate(deck, re.findall(r'V\(([^)]+)\)', re.search(r'(?im)^\.print tran[^\n]+', deck)[0]))
        write_once(out / 'bench.cir', deck)
        (out / 'producers').mkdir(exist_ok=True)
        for name in code:
            write_once(out / 'producers' / name, (ROOT / 'scripts' / name).read_text())
        capture_manifest(out / 'manifest.json', dict(identity=identity, observations=probes,
            files={n: sha(out / n) for n in ('bench.cir', 'library.spice')}, qualified_phy=False))
    return out


def bound(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Require an isolated native TX clock observation')
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']; parent = ROOT / i['parent']
    if (out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['simulator'] != provenance() or i['stop_ns'] != 120 or i['maximum_step_ps'] != 1
            or i['public_reproduction_limit_v'] != 1e-6 or m['qualified_phy'] is not False
            or any(sha(ROOT / n) != h for n, h in i['inputs'].items())
            or any(sha(ROOT / 'scripts' / n) != h or sha(out / 'producers' / n) != h for n, h in i['code'].items())
            or set(m['files']) != {'bench.cir', 'library.spice'} or any(sha(out / n) != h for n, h in m['files'].items())
            or (out / 'library.spice').read_bytes() != (parent / 'payload/library.spice').read_bytes()
            or m['observations'] != observations((out / 'library.spice').read_text())
            or (out / 'bench.cir').read_text() != fixture((parent / 'payload/bench.cir').read_text(), parent, out, m['observations'])):
        raise ValueError('Native TX clock observation context changed')
    function, _ = topology.topology(parent)
    if function != i['topology']:
        raise ValueError('Native forwarded-clock topology changed')
    return m


def reproduction(wave, header, reference, rh):
    # The new explicit stop introduces its own final integration endpoint.
    # Compare the entire common prefix before the final ten picoseconds.
    keep = wave[:, 1] < 119.99e-9
    errors = {}
    for name, col in rh.items():
        if name.startswith('V('):
            if name not in header:
                raise ValueError('An original observation was removed')
            expected = np.interp(wave[keep, 1], reference[:, 1], reference[:, col])
            errors[name] = float(np.max(abs(wave[keep, header[name]] - expected)))
    if not errors:
        raise ValueError('Missing original public observations')
    return dict(passed=max(errors.values()) <= 1e-6, maximum_error_v=max(errors.values()), errors_v=errors,
                comparison_end_ns=119.99, limit_v=1e-6)


def measure(out, m):
    wave, header = coupled.baseline.completed_export(out, 120)
    parent = ROOT / m['identity']['parent']
    reference, rh = coupled.baseline.completed_export(parent / 'payload', 188.049)
    reproduced = reproduction(wave, header, reference, rh)
    t = wave[:, 1]; v = lambda node: wave[:, header['V(' + node.upper() + ')']]
    keep = (t >= 60e-9) & (t <= 119.99e-9)
    constants = []
    for role, high in (('constant_low', False), ('constant_high', True)):
        for row in m['observations'][role]:
            values = v(row['node'])[keep]
            constants.append(dict(role=role, node=row['node'], min_v=float(values.min()), max_v=float(values.max()),
                                  passed=bool(values.min() > 1.44 if high else values.max() < .36)))
    mux = [(r['node'], 1.8 - v(r['node'])) for r in m['observations']['mux_select']]
    output = [(r['node'], v(r['node'])) for r in m['observations']['output_buffer_input']]
    stages = {name: topology.original.stage(t, values, .9, 60e-9, 119.99e-9)
              for name, values in [('intended_inverted_clk0', 1.8 - v('CLK0')), *mux, *output, ('TXCLOCK', v('TXCLOCK'))]}
    hops = []
    for label, first, last in [('select_distribution_and_buffer', [('CLK0_INVERTED', 1.8 - v('CLK0'))], mux),
            ('clock_mux_and_route', mux, output), ('output_buffer_and_route', output, [('TXCLOCK', v('TXCLOCK'))])]:
        for a, source in first:
            for b, target in last:
                hops.append(dict(stage=label, source=a, target=b,
                    result=topology.original.transport(t, source, .9, target, .9, 60e-9, 119.99e-9)))
    launch = coupled.baseline.original.edge_times(t, v('CLK0'), rising=True)
    launch = launch[launch >= 60e-9][:16] * 1e9
    if len(launch) != 16:
        raise ValueError('Missing original payload launch window')
    payload = coupled.baseline.original.analyze(wave, coupled.baseline.original.word_stream(16), launch, 1000 / 410)
    return dict(observation_passed=bool(reproduced['passed'] and all(r['passed'] for r in constants)
        and all(r['result']['at_least_twenty_per_polarity'] for r in hops) and payload['passed']
        and payload['checked_bits'] == 32 and payload['word_errors'] == 0),
        reproduction=reproduced, constants=constants, stages=stages, propagation=hops, payload=payload,
        qualified_phy=False, scope='Complete 120 ns / 1 ps observation-only native coupled diagnostic. '
        'Actual MOS gate endpoints and constant-data terminals, unchanged original circuit and loads. '
        'Clock inversion follows the verified constant-pair mux topology. No circuit change or PHY admission.')


def run(out):
    m = bound(out); stamp = sha(out / 'manifest.json')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists() or any((out / n).exists() for n in (*OUTPUTS, 'summary.json')):
            raise ValueError('Prior native clock observation retained; no retry')
        atomic(out / 'state.json', dict(status='waiting_for_observation_lease', qualified_phy=False))
        with lease(ROOT, priority=2, label='native_tx_clock_observation'):
            bound(out)
            atomic(out / 'state.json', dict(status='observing_native_clock_path', qualified_phy=False))
            process = subprocess.run(command(out / 'ngspice.log', out / 'bench.cir'), cwd=out, capture_output=True, text=True)
        (out / 'console.log').write_text(process.stdout + process.stderr)
        result = error = None
        try:
            process.check_returncode(); bound(out); result = measure(out, m)
        except Exception as e:
            error = str(e)
        report = dict(returncode=process.returncode, error=error, result=result, manifest_sha256=stamp,
                      files={n: sha(out / n) for n in OUTPUTS if (out / n).exists()}, qualified_phy=False)
        capture_manifest(out / 'summary.json', report)
        atomic(out / 'state.json', dict(status='observation_complete' if error is None else 'held_for_diagnosis', qualified_phy=False))
    return report


def verify(out):
    m = bound(out); r = json.loads((out / 'summary.json').read_text())
    if (r['manifest_sha256'] != sha(out / 'manifest.json') or r['returncode'] != 0 or r['error'] is not None
            or set(r['files']) != set(OUTPUTS) or any(sha(out / n) != h for n, h in r['files'].items())
            or r['result'] != measure(out, m)):
        raise ValueError('Native TX clock observation changed or incomplete')
    return r


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'bound', 'run', 'verify'])
    p.add_argument('artifact', type=Path); a = p.parse_args(); result = globals()[a.action](a.artifact.resolve())
    print(result if a.action == 'prepare' else json.dumps(result, indent=2), flush=True)
