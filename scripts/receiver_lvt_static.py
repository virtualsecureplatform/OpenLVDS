#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Check unclamped LVT first-stage restoration in an original receiver static fixture."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import re
import subprocess

import numpy as np
from dll_campaign import atomic, text_block
from dll_measurements import read_wave
from qualify_receiver_components import static_metrics, rebind
from spice_engine import command, engine, provenance
from spice_library import replace
from spice_slots import slot
from receiver_static_diagnosis import remove_clamps as remove_only_clamps
from receiver_lvt_restore_experiment import lower_first_nfet

ROOT = Path(__file__).resolve().parents[1]
TOP = 'openlvds_receiver_core'
CODE = ['receiver_lvt_static.py', 'receiver_static_diagnosis.py',
        'receiver_lvt_restore_experiment.py', 'receiver_unclamped_restore_experiment.py', 'qualify_receiver_components.py', 'dll_campaign.py',
        'dll_measurements.py', 'spice_library.py', 'spice_engine.py', 'spice_slots.py', 'run_ngspice.py']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture_manifest(path, value):
    # Re-preparation must preserve the exact bytes bound by cached reports.
    # Compare canonical JSON so dictionary insertion order cannot rewrite an
    # otherwise identical capture; retain JSON type distinctions as well.
    if path.exists():
        canonical = lambda item: json.dumps(item, sort_keys=True, allow_nan=False)
        if canonical(json.loads(path.read_text())) != canonical(value):
            raise ValueError('Static diagnosis manifest changed')
    else:
        atomic(path, value)


def intervention(source):
    return lower_first_nfet(remove_only_clamps(source))


def samples(wave, headers):
    return [dict(time_ns=i * 12 + 10, values={n: float(np.interp((i * 12 + 10) * 1e-9,
                    wave[:, 1], wave[:, col])) for n, col in headers.items() if n not in ['INDEX', 'TIME']})
            for i in range(12)]


def prepare(parent, case):
    if engine() != 'ngspice' or not parent.is_relative_to(ROOT / 'build/diagnostics/receiver_components'):
        raise ValueError('Use a completed component case in the pinned ngspice environment')
    manifest = json.loads((parent / 'manifest.json').read_text())
    tasks = [t for t in manifest['tasks'] if t['id'] == case and t['view'] == 'schematic' and t['test'] == 'receiver']
    if len(tasks) != 1:
        raise ValueError('Select one schematic static receiver case')
    task = tasks[0]
    folder = parent / case
    report = json.loads((folder / 'summary.json').read_text())
    if (report['manifest_sha256'] != digest(parent / 'manifest.json') or
            report['waveform_sha256'] != digest(folder / 'bench.cir.prn') or
            report['deck_sha256'] != digest(folder / 'bench.cir')):
        raise ValueError('Parent static result changed')
    if provenance() != manifest['identity']['simulator_provenance']:
        raise ValueError('Parent simulator differs')
    for name, stamp in task['files'].items():
        if digest(folder / name) != stamp:
            raise ValueError('Parent static fixture changed')
    for name, stamp in manifest['identity']['code'].items():
        if digest(ROOT / 'scripts' / name) != stamp:
            raise ValueError('Parent producer changed')
    for name, stamp in manifest['identity']['inputs'].items():
        if digest(ROOT / name) != stamp:
            raise ValueError('Parent component input changed')
    wave, _ = read_wave(folder / 'bench.cir.prn')
    metrics = static_metrics(wave)
    if any(report[k] != v for k, v in metrics.items()):
        raise ValueError('Parent static analysis differs from its waveform')
    paths = [parent / 'manifest.json', ROOT / 'requirements.json'] + [folder / n for n in
             ['summary.json', 'source.spice', 'bench.cir', 'bench.cir.prn']]
    identity = dict(parent=str(parent.relative_to(ROOT)), case=case, operation='remove_CO_clamps_and_use_LVT_first_restoration_NFET',
                    simulator_provenance=provenance(), qualified_phy=False,
                    inputs={str(p.relative_to(ROOT)): digest(p) for p in paths},
                    code={n: digest(ROOT / 'scripts' / n) for n in sorted(set(CODE) | set(manifest['identity']['code']))})
    root = ROOT / 'build/diagnostics/receiver_lvt_static' / hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    root.mkdir(parents=True, exist_ok=True)
    source = intervention((folder / 'source.spice').read_text())
    deck = rebind((folder / 'bench.cir').read_text(), folder, root)
    for name, text in [('source.spice', source), ('bench.cir', deck)]:
        target = root / name
        if target.exists() and target.read_text() != text:
            raise ValueError('Static diagnosis fixture changed')
        target.write_text(text)
    capture_manifest(root / 'manifest.json', dict(identity=identity, qualified_phy=False,
           files={n: digest(root / n) for n in ['source.spice', 'bench.cir']}))
    return root


def run(root):
    if not root.is_relative_to(ROOT / 'build/diagnostics/receiver_lvt_static'):
        raise ValueError('Use an isolated static diagnosis')
    manifest = json.loads((root / 'manifest.json').read_text())
    identity = manifest['identity']

    def unchanged():
        if provenance() != identity['simulator_provenance']:
            raise ValueError('Static diagnosis runtime changed')
        for name, stamp in identity['inputs'].items():
            if digest(ROOT / name) != stamp:
                raise ValueError('Static diagnosis input changed')
        for name, stamp in identity['code'].items():
            if digest(ROOT / 'scripts' / name) != stamp:
                raise ValueError('Static diagnosis producer changed')
        if any(digest(root / n) != h for n, h in manifest['files'].items()):
            raise ValueError('Static diagnosis deck changed')
        parent = ROOT / identity['parent'] / identity['case']
        if ((root / 'source.spice').read_text() != intervention((parent / 'source.spice').read_text()) or
                (root / 'bench.cir').read_text() != rebind((parent / 'bench.cir').read_text(), parent, root)):
            raise ValueError('Static diagnosis differs from the declared LVT intervention')

    with (root / '.execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        cached = json.loads((root / 'summary.json').read_text()) if (root / 'summary.json').exists() else None
        if cached is None:
            atomic(root / 'execution.json', dict(status='waiting_for_slot', qualified_phy=False))
            with slot():
                unchanged()
                atomic(root / 'execution.json', dict(status='running', qualified_phy=False))
                process = subprocess.run(command(root / 'ngspice.log', root / 'bench.cir'),
                                         cwd=root, capture_output=True, text=True)
            (root / 'console.log').write_text(process.stdout + process.stderr)
            process.check_returncode()
        unchanged()
        wave, headers = read_wave(root / 'bench.cir.prn')
        parent = ROOT / identity['parent'] / identity['case']
        control, control_headers = read_wave(parent / 'bench.cir.prn')
        result = dict(diagnostic_complete=True, qualified_phy=False,
            manifest_sha256=digest(root / 'manifest.json'), waveform_sha256=digest(root / 'bench.cir.prn'),
            original=dict(metrics=static_metrics(control), samples=samples(control, control_headers)),
            lvt_first_stage=dict(metrics=static_metrics(wave), samples=samples(wave, headers)),
            scope='Unclamped LVT first-restoration source static fixture; original supplies, common modes, load and sampling times; no clock or PHY qualification')
        if cached is not None and cached != result:
            raise ValueError('Static diagnosis saved analysis differs from waveform')
        atomic(root / 'summary.json', result)
        atomic(root / 'execution.json', dict(status='completed', qualified_phy=False))
    print(root / 'summary.json', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('parent', type=Path)
    p.add_argument('--case', default='schematic_receiver_tt_25')
    p = sub.add_parser('run')
    p.add_argument('artifact', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.parent.resolve(), args.case), flush=True)
    else:
        run(args.artifact.resolve())
