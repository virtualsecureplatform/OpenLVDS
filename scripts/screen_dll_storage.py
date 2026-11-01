#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Screen the 16 pF DLL source in unchanged SS0/TT25/FF0 acquisition fixtures."""
import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import re

import dll_campaign as campaign
import preset_dll_experiment as reference
from dll_design import native_block
from receiver_static_diagnosis import capture_manifest
from spice_engine import engine, provenance
from spice_library import replace
from spice_scope import closure_hash
from spice_dispatch import lease

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
VARIANT = 'ota_w8_c16'
TOP = 'openlvds_dll_analog'


def producer_code():
    return dict(reference.producer_code(), **{n: reference.digest(ROOT/'scripts'/n) for n in
        [NAME, 'dll_storage_compensation.py', 'spice_dispatch.py', 'spice_scope.py', 'receiver_static_diagnosis.py']})


def library(base, source):
    # Source fixtures flatten the delay chain into the analog macro. Protect
    # a separate delay definition only when this library actually has one;
    # prepare also proves the full source differs solely by the added caps.
    tops = ['lvds_bias', 'lvds_pfd']
    if re.search(r'(?im)^\.subckt\s+openlvds_delay_line\s', base):
        tops.append('openlvds_delay_line')
    protected = {n: closure_hash(base, n) for n in tops}
    result = replace(base, TOP, native_block(source, TOP))
    if any(closure_hash(result, n) != h for n, h in protected.items()):
        raise ValueError('Storage screen changes a protected bias/PFD/delay-line closure')
    return result


def validate(root, manifest):
    i = manifest['identity']
    if producer_code() != i['producer_code'] or provenance() != i['simulator_provenance']:
        raise ValueError('Storage source-screen producer or simulator changed')
    for name, stamp in i['inputs'].items():
        if reference.digest(ROOT/name) != stamp:
            raise ValueError('Storage source-screen input changed')
    if reference.digest(root/'inputs'/(VARIANT+'.spice')) != i['source_sha256']:
        raise ValueError('Storage screen source changed')
    for name, stamp in i['producer_code'].items():
        if reference.digest(root/'inputs/scripts'/name) != stamp:
            raise ValueError('Storage source-screen producer archive changed')
    if (len(manifest['tasks']) != 3 or
            {(t['spec']['corner'], t['spec']['temp']) for t in manifest['tasks']} != {('ss', 0), ('tt', 25), ('ff', 0)} or
            any(t['spec']['variant'] != VARIANT or t['spec']['kind'] != 'loop' for t in manifest['tasks'])):
        raise ValueError('Require exactly three original source-acquisition fixtures')
    for task in manifest['tasks']:
        campaign.validate(root, manifest, task)


def prepare(compensation, baseline):
    if (engine() != 'ngspice' or not compensation.is_relative_to(ROOT/'build/diagnostics/dll_compensation') or
            not baseline.is_relative_to(ROOT/'build/diagnostics/dll_architecture')):
        raise ValueError('Use captured storage correction and completed baseline source screen')
    cm = json.loads((compensation/'manifest.json').read_text())
    for name, stamp in cm['identity']['inputs'].items():
        if reference.digest(ROOT/name) != stamp:
            raise ValueError('Storage correction evidence changed')
    for name, stamp in cm['identity']['code'].items():
        if reference.digest(ROOT/'scripts'/name) != stamp:
            raise ValueError('Storage correction producer changed')
    source = (compensation/'candidate.spice').read_text()
    if reference.digest(compensation/'candidate.spice') != cm['files']['candidate.spice']:
        raise ValueError('Prepared storage correction source changed')
    old = json.loads((baseline/'manifest.json').read_text()); reference.validate(baseline, old)
    if (len(old['tasks']) != 3 or not (baseline/'summary.json').is_file() or
            any(not (baseline/t['id']/'summary.json').is_file() for t in old['tasks'])):
        raise ValueError('Complete all baseline acquisition controls first')
    # Cached scientific remeasurement cannot dispatch any missing baseline job.
    if reference.run(baseline, 1) != 0:
        raise ValueError('Baseline source-acquisition control failed')
    from dll_storage_compensation import transform
    if source != transform((baseline/'inputs/ota_w8_c4.spice').read_text()):
        raise ValueError('Storage correction differs from the matched baseline source')
    paths = [compensation/n for n in ['manifest.json', 'candidate.spice']]
    paths.extend(baseline/n for n in ['manifest.json', 'summary.json', 'inputs/requirements.json'])
    paths.extend(baseline/t['id']/n for t in old['tasks'] for n in ['summary.json', 'bench.cir', 'library.spice', 'bench.cir.prn'])
    identity = dict(code=campaign.dependencies(), producer_code=producer_code(), simulator_provenance=provenance(),
        source_sha256=hashlib.sha256(source.encode()).hexdigest(), reference=str(baseline.relative_to(ROOT)),
        compensation=str(compensation.relative_to(ROOT)),
        inputs={str(p.relative_to(ROOT)): reference.digest(p) for p in paths})
    root = ROOT/'build/diagnostics/dll_architecture'/hashlib.sha256(
        json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    if (root/'manifest.json').exists():
        validate(root, json.loads((root/'manifest.json').read_text())); return root
    archive = root/'inputs'; (archive/'scripts').mkdir(parents=True)
    (archive/(VARIANT+'.spice')).write_text(source)
    (archive/'requirements.json').write_bytes((baseline/'inputs/requirements.json').read_bytes())
    for name in identity['producer_code']:
        (archive/'scripts'/name).write_bytes((ROOT/'scripts'/name).read_bytes())
    tasks = []
    for task in old['tasks']:
        case = root/task['id'].replace('ota_w8_c4', VARIANT); case.mkdir()
        prior = baseline/task['id']; deck = (prior/'bench.cir').read_text()
        include = f'.include "{prior}/library.spice"'
        if deck.count(include) != 1:
            raise ValueError('Ambiguous baseline source library inclusion')
        deck = deck.replace(include, f'.include "{case}/library.spice"')
        (case/'bench.cir').write_text(deck)
        (case/'library.spice').write_text(library((prior/'library.spice').read_text(), source))
        tasks.append(dict(task, id=case.name, spec=dict(task['spec'], variant=VARIANT),
            files={n: reference.digest(case/n) for n in ['bench.cir', 'library.spice']}))
    manifest = dict(identity=identity, tasks=tasks, diagnostic=True, qualified_phy=False,
        change='Only CTRL storage grows from nominal 4 to 16 pF. Same three baseline full-duration acquisition stimuli, native PFD, reset, loads, numerical policy and measurement windows.')
    capture_manifest(root/'manifest.json', manifest); validate(root, manifest)
    campaign.atomic(root/'state.json', dict(status='prepared', qualified_phy=False))
    return root


@contextmanager
def profile():
    previous = reference.validate, reference.slot
    try:
        reference.validate = validate
        reference.slot = lambda: lease(ROOT, priority=1, label='dll-storage-source-acquisition')
        yield
    finally:
        reference.validate, reference.slot = previous


def run(root, jobs=1):
    if not root.is_relative_to(ROOT/'build/diagnostics/dll_architecture') or jobs not in [1, 2]:
        raise ValueError('Use a prepared storage acquisition screen with one or two workers')
    m = json.loads((root/'manifest.json').read_text()); validate(root, m)
    for task in m['tasks']:
        case = root/task['id']
        if not (case/'summary.json').exists() and any((case/n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
            raise ValueError('Partial storage acquisition output retained; use a fresh context')
    with profile():
        return reference.run(root, jobs)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    a = sub.add_parser('prepare'); a.add_argument('compensation', type=Path); a.add_argument('baseline', type=Path)
    a = sub.add_parser('run'); a.add_argument('artifact', type=Path); a.add_argument('--jobs', type=int, choices=[1, 2], default=1)
    a = p.parse_args()
    if a.action == 'prepare':
        print(prepare(a.compensation.resolve(), a.baseline.resolve()), flush=True)
    else:
        raise SystemExit(run(a.artifact.resolve(), a.jobs))
