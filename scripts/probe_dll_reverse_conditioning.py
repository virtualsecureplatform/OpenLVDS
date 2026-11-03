#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Extend the frozen input-buffer experiment to reversed 200/20 ps slew."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
from pathlib import Path
import re

import probe_dll_input_conditioning as original
from dll_campaign import bias_reference_count
from receiver_static_diagnosis import capture_manifest
from spice_probes import ProbeNetwork

ROOT = Path(__file__).resolve().parents[1]
CASES = [f'slew_ss_40_{offset}ps_200_20' for offset in [-50, 150, -150]]
CONTROLS = [f'slew_ss_40_{offset}ps_200_20' for offset in [0, 50, -50]]
ORIGINAL_BOUND = original.bound
sha = original.sha


def bound(out):
    with profile():
        m = ORIGINAL_BOUND(out)
    if (m['identity'].get('conditioning_profile') != 'reverse_slew_200_20' or
            Path(__file__).name not in m['identity']['code'] or
            any({k:t['spec'].get(k) for k in ['kind', 'process', 'temperature', 'mhz',
                 'reference_slew_ps', 'feedback_slew_ps']} !=
                dict(kind='phase', process='ss', temperature=40, mhz=400,
                     reference_slew_ps=200, feedback_slew_ps=20) for t in m['tasks'])):
        raise ValueError('Reversed-slew conditioning profile changed')
    return m


@contextmanager
def profile():
    previous = original.CASES, original.bound
    try:
        original.CASES, original.bound = CASES, bound
        yield
    finally:
        original.CASES, original.bound = previous


def prepare(parent):
    pm = ORIGINAL_BOUND(parent)
    q = ROOT / pm['identity']['qualification']
    original.admission.dll_context(q)
    qm = json.loads((q / 'manifest.json').read_text()); tasks = {t['id']:t for t in qm['tasks']}
    controls = []; inputs = dict(pm['identity']['inputs'])
    paths = [parent / 'manifest.json', parent / 'reference_analysis.json']
    paths += [parent / t['id'] / n for t in pm['tasks'] for n in t['files']]
    for name in CONTROLS:
        t = tasks[name]; folder = q / name; r = json.loads((folder / 'summary.json').read_text())
        if (r['returncode'] != 0 or r['deck_sha256'] != t['deck_sha256'] or
                sha(folder / 'bench.cir') != t['deck_sha256'] or
                sha(folder / 'bench.raw') != r['raw_sha256'] or
                sha(folder / 'bench.cir.prn') != r['waveform_sha256']):
            raise ValueError('Require unchanged completed reversed-slew controls')
        original.completed(folder)
        with original.admission.storage.profile():
            measured = original.admission.storage.native.evaluate(q, t)
        expected = t['spec']['offset_ps'] != -50
        if (measured != r['metrics'] or r['passed'] is not measured['passed'] or
                measured['complete'] is not True or measured['passed'] is not expected):
            raise ValueError('Reversed-slew native control remeasurement changed')
        controls.append(dict(task=name, metrics=measured))
        paths += [folder / n for n in ['summary.json', 'bench.cir', 'bench.raw', 'bench.cir.prn',
                                       'ngspice.log', 'console.log']]
    # Fault templates are immutable prepared inputs. Their native unconditioned
    # simulations may still be running; they are never restarted or classified
    # from a partial trace. The new candidate must independently detect both.
    for name in CASES:
        t = tasks[name]
        if t['fast_rc'] or sha(q / name / 'bench.cir') != t['deck_sha256']:
            raise ValueError('Reversed fault template changed')
        paths.append(q / name / 'bench.cir')
    inputs.update({str(p.relative_to(ROOT)):sha(p) for p in paths})
    i = dict(pm['identity'], conditioning_profile='reverse_slew_200_20', inputs=inputs,
        code={**pm['identity']['code'], Path(__file__).name:sha(Path(__file__))},
        parent=str(parent.relative_to(ROOT)), scope=
        'Matched SS40 400 MHz -50/+150/-150 ps, reversed reference/feedback slew 200/20 ps. '
        'Reuse the frozen experiment library with identical PDK buf_4 conditioning. '
        'Original native -50 ps false-BAD and completed zero/+50 ps controls remeasured; '
        'unfinished native fault controls are not rerun or admitted. Original external '
        'clocks, native DLL/PFD/bias, fixed rails/load, 160 ns/5 ps print/20 ps maximum '
        'step and health thresholds preserved. Source diagnostic with ideal buffer '
        'routing only; no physical, all-PVT, stability, phase-replay or PHY admission.')
    out = ROOT / 'build/diagnostics/dll_input_conditioning' / hashlib.sha256(
        json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    with (out / '.preparation.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        capture_manifest(out / 'reference_analysis.json', dict(results=controls, qualified_phy=False))
        lib = (parent / pm['tasks'][0]['id'] / 'library.spice').read_text(); prepared = []
        for name in CASES:
            t = tasks[name]; folder = out / name; folder.mkdir(exist_ok=True)
            deck = original.fixture((q / name / 'bench.cir').read_text(), q, folder, i['cell_ports'])
            probes = re.findall(r'V\(([^)]+)\)', re.search(r'(?im)^\.print tran[^\n]+', deck)[0])
            ProbeNetwork(lib).validate(deck, probes)
            if bias_reference_count(deck, lib) != 1:
                raise ValueError('Reversed conditioning duplicates native bias')
            for n, text in [('library.spice', lib), ('bench.cir', deck)]:
                p = folder / n
                if p.exists() and p.read_text() != text:
                    raise ValueError('Prepared reversed conditioning changed')
                if not p.exists(): p.write_text(text)
            prepared.append(dict(id=name, spec=t['spec'], aliases=t['aliases'],
                files={n:sha(folder / n) for n in ['library.spice', 'bench.cir']}))
        capture_manifest(out / 'manifest.json', dict(identity=i, tasks=prepared,
            reference_analysis_sha256=sha(out / 'reference_analysis.json'), qualified_phy=False))
    return out


def run(out):
    m=bound(out)
    parent=ROOT/m['identity']['parent']
    if not (parent/'summary.json').is_file():
        raise ValueError('Complete the forward conditioning experiment before reverse dispatch')
    report=original.verify(parent)
    if report.get('input_conditioning_diagnostic_passed') is not True:
        raise ValueError('Forward conditioning failed; reverse dispatch held')
    with profile():
        return original.run(out)


def verify(out):
    with profile():
        return original.verify(out)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['prepare', 'run', 'verify']); p.add_argument('artifact', type=Path)
    a = p.parse_args(); result = globals()[a.action](a.artifact.resolve())
    print(result if a.action == 'prepare' else json.dumps(result, indent=2), flush=True)
