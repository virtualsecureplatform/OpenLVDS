#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Compare 100:1/110:1 native drivers with the same admitted schematic LVT RX."""
import argparse
from contextlib import contextmanager, nullcontext
import fcntl
import hashlib
import json
from pathlib import Path
import re

import driver_current_native as current
import selected_analog_pilot as pilot
from dll_campaign import atomic
from dll_measurements import read_wave
from diagnose_link_clock import pulse_transport
from probe_receiver_lvt_compact import source_gate
from receiver_static_diagnosis import capture_manifest
from spice_dispatch import lease

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
LEAVES = ['PP', 'PN', 'CO', 'CL', 'CT', 'RESTORE0', 'RESTORE1']
PROBES = ['X'+instance+':openlvds_receiver_core__'+leaf
          for instance in ['DR', 'CR'] for leaf in LEAVES]


def instrument(deck):
    rows = list(re.finditer(r'(?im)^\.tran[^\n]*$', deck))
    if len(rows) != 1 or rows[0][0].split()[1:] != ['20p', '188.049n', '0', '100p']:
        raise ValueError('Use the unchanged full 188.049 ns parent fixture')
    deck = deck[:rows[0].start()]+'.tran 20p 188.049n 0 20p'+deck[rows[0].end():]
    rows = list(re.finditer(r'(?im)^\.print tran[^\n]*$', deck))
    if len(rows) != 1:
        raise ValueError('Expected one original link print statement')
    at = rows[0].end()
    return deck[:at]+' '+' '.join('V('+n+')' for n in PROBES)+deck[at:]


@contextmanager
def profile(corrected):
    # Sequential children: these frozen producer adapters are process globals.
    previous = pilot.NAME, pilot.rebind, pilot.slot
    original = pilot.rebind
    try:
        with current.profile() if corrected else nullcontext():
            pilot.NAME = NAME
            pilot.rebind = lambda *a, **kw: instrument(original(*a, **kw))
            pilot.slot = lambda: lease(ROOT, priority=1, label='native-driver-schematic-lvt-link')
            yield
    finally:
        pilot.NAME, pilot.rebind, pilot.slot = previous


def prepare(reference, control, corrected, source, matrix, clock):
    proofs = source_gate(matrix, clock)
    source_hashes = {v for k, v in proofs.items() if k.endswith('/source.spice')}
    if source_hashes != {pilot.digest(source/'source.spice')}:
        raise ValueError('Selected LVT source differs from the admitted matrix')
    children = []
    paths = [ROOT/'scripts'/NAME, ROOT/'scripts/spice_dispatch.py',
             ROOT/'scripts/probe_receiver_lvt_compact.py']
    for changed, comparison in [(False, control), (True, corrected)]:
        m = json.loads((comparison/'manifest.json').read_text())
        if (not (comparison/'summary.json').is_file() or
                any(not (comparison/t['id']/'summary.json').is_file() for t in m['tasks'])):
            raise ValueError('Complete both native driver comparisons before this experiment')
        # Full cached scientific remeasurement; no missing cases may dispatch.
        if changed:
            current.run(comparison)
        else:
            current.native.run(comparison)
        with profile(changed):
            child = pilot.prepare(reference, comparison, source)
        children.append(dict(current_ratio=110 if changed else 100,
            root=str(child.relative_to(ROOT)), manifest_sha256=pilot.digest(child/'manifest.json')))
        paths.extend(comparison/n for n in ['manifest.json', 'summary.json'])
    identity = dict(children=children, source_proofs=proofs,
        inputs={str(p.relative_to(ROOT)): pilot.digest(p) for p in paths},
        maximum_step_ps=20, original_training_ns=60, original_payload_bits=32,
        scope='Matched early diagnostic with identical schematic LVT receiver, native P64/N24 drivers, original full channel and native digital RX. Only current ratio differs between children. Short training, ideal clock phase and schematic analog RX cannot qualify the PHY.')
    root = ROOT/'build/diagnostics/current_lvt_link'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True)
    capture_manifest(root/'manifest.json', dict(identity=identity, qualified_phy=False))
    return root


def run(root):
    if not root.is_relative_to(ROOT/'build/diagnostics/current_lvt_link'):
        raise ValueError('Use a prepared matched current/LVT link experiment')
    m = json.loads((root/'manifest.json').read_text()); i = m['identity']; stamp = pilot.digest(root/'manifest.json')
    def unchanged():
        if (pilot.digest(root/'manifest.json') != stamp or
                any(pilot.digest(ROOT/n) != h for n, h in dict(i['inputs'], **i['source_proofs']).items()) or
                [c['current_ratio'] for c in i['children']] != [100, 110] or
                any(pilot.digest(ROOT/c['root']/'manifest.json') != c['manifest_sha256'] for c in i['children'])):
            raise ValueError('Matched current/LVT comparison context changed')
    with (root/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged()
        cached = json.loads((root/'summary.json').read_text()) if (root/'summary.json').exists() else None
        results = []
        for c in i['children']:
            child = ROOT/c['root']
            atomic(root/'execution.json', dict(status='running_child', current_ratio=c['current_ratio'], qualified_phy=False))
            with profile(c['current_ratio'] == 110):
                pilot.run(child)
            unchanged(); report = json.loads((child/'summary.json').read_text())
            w, h = read_wave(child/'bench.cir.prn'); t = w[:, 1]
            col = lambda n: w[:, h['V('+n.upper()+')']]
            transport = pulse_transport(t, col('RCP')-col('RCN'), col('RXCLOCK'), 60e-9, 120e-9)
            results.append(dict(current_ratio=c['current_ratio'], root=c['root'],
                report_sha256=pilot.digest(child/'summary.json'), waveform_sha256=pilot.digest(child/'bench.cir.prn'),
                decoder=report['metrics'], clock_transport=transport))
        result = dict(diagnostic_complete=True, qualified_phy=False, manifest_sha256=stamp,
                      results=results, scope=i['scope'])
        unchanged()
        if cached is not None and cached != result:
            raise ValueError('Completed current/LVT comparison changed')
        capture_manifest(root/'summary.json', result)
        atomic(root/'execution.json', dict(status='completed', qualified_phy=False))
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); s = p.add_subparsers(dest='action', required=True)
    a = s.add_parser('prepare')
    for n in ['reference', 'control', 'corrected', 'source', 'matrix', 'clock']:
        a.add_argument(n, type=Path)
    a = s.add_parser('run'); a.add_argument('artifact', type=Path); a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(*(getattr(a, n).resolve() for n in ['reference', 'control', 'corrected', 'source', 'matrix', 'clock'])), flush=True)
    else:
        run(a.artifact.resolve()); print(a.artifact.resolve()/'summary.json', flush=True)
