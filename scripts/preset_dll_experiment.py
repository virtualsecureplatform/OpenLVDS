#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Isolate a 2:1 passive startup preset; retain the matched fast-reset fixtures."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path

import dll_campaign as campaign
from dll_design import native_block
from dll_measurements import loop, read_wave
from layout import circuits
import screen_fast_reset_dll as reference_screen
from spice_engine import engine, provenance
from spice_library import replace
from spice_slots import slot

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preset_source(source):
    """Change only the preset divider, preserving every other source byte."""
    definitions = circuits(source)
    ports, rows = definitions['openlvds_dll_analog']
    selected = {r[0]: r for r in rows if r[0] in {'XRP0', 'XRP1'}}
    if set(selected) != {'XRP0', 'XRP1'} or len(rows) != len({r[0] for r in rows}):
        raise ValueError('Expected two unique preset resistors')
    for _, nodes, model, params in selected.values():
        if (nodes != ['VDDD', 'PRE', 'VSS'] or model != 'sky130_fd_pr__res_high_po_0p35'
                or set(params) != {'w', 'l'} or float(params['w']) != .35 or float(params['l']) != 1.25):
            raise ValueError('Unexpected preset topology or dimensions')
    if 'PREDIV' in {n for _, nodes, _, _ in rows for n in nodes} or 'XRPDIV' in {r[0] for r in rows}:
        raise ValueError('Preset divider already exists')
    old = campaign.text_block(source, 'openlvds_dll_analog')
    lines = old.splitlines()
    index = next(i for i, line in enumerate(lines) if line.split() and line.split()[0] == 'XRP1')
    lines[index:index+1] = [
        'XRP1 PRE PREDIV VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=1.25',
        'XRPDIV PREDIV VSS VSS sky130_fd_pr__res_high_po_0p35 w=.35 l=1.25']
    result = source.replace(old, '\n'.join(lines), 1)
    if circuits(result)['openlvds_dll_analog'][0] != ports:
        raise ValueError('Preset change altered the public ports')
    return result


def producer_code():
    return dict(reference_screen.producer_code(), **{Path(__file__).name: digest(Path(__file__))})


def prepare(reference, qualification):
    if engine() != 'ngspice':
        raise ValueError('Use the pinned ngspice environment')
    from qualify_dll_candidate import validate as validate_native
    qm = json.loads((qualification/'manifest.json').read_text()); validate_native(qualification, qm)
    original = json.loads((reference/'manifest.json').read_text()); reference_screen.validate(reference, original)
    reference_screen.capture_admission(reference, original)
    base = ROOT/qm['identity']['full_models']['layout']/'candidate.spice'
    if digest(base) != qm['identity']['full_models']['source_sha256']:
        raise ValueError('Physical source changed')
    source = preset_source(base.read_text())
    # The screen must model precisely the same pre-ECO analog source as the native run.
    expected = campaign.text_block(native_block(base.read_text(), 'openlvds_dll_analog'), 'openlvds_dll_analog')
    for task in original['tasks']:
        library = (reference/task['id']/'library.spice').read_text()
        if campaign.text_block(library, 'openlvds_dll_analog').strip() != expected.strip():
            raise ValueError('Source screen and native baseline differ')
    inputs = {str(p.relative_to(ROOT)): digest(p) for p in
              [reference/'manifest.json', qualification/'manifest.json', base]}
    identity = dict(code=campaign.dependencies(), producer_code=producer_code(), simulator_provenance=provenance(),
                    source_sha256=hashlib.sha256(source.encode()).hexdigest(), inputs=inputs,
                    reference=str(reference.relative_to(ROOT)), qualification=str(qualification.relative_to(ROOT)))
    root = ROOT/'build/diagnostics/dll_architecture'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    if (root/'manifest.json').exists():
        validate(root, json.loads((root/'manifest.json').read_text())); return root
    archive = root/'inputs'; archive.mkdir(parents=True)
    (archive/'ota_w8_c4.spice').write_text(source)
    (archive/'requirements.json').write_bytes((reference/'inputs/requirements.json').read_bytes())
    scripts = archive/'scripts'; scripts.mkdir()
    for name in identity['producer_code']:
        (scripts/name).write_bytes((ROOT/'scripts'/name).read_bytes())
    tasks = []
    for task in original['tasks']:
        folder = root/task['id']; folder.mkdir()
        old = reference/task['id']; deck = (old/'bench.cir').read_text()
        include = f'.include "{old}/library.spice"'
        if deck.count(include) != 1:
            raise ValueError('Ambiguous original library inclusion')
        deck = deck.replace(include, f'.include "{folder}/library.spice"')
        library = replace((old/'library.spice').read_text(), 'openlvds_dll_analog', native_block(source, 'openlvds_dll_analog'))
        (folder/'bench.cir').write_text(deck); (folder/'library.spice').write_text(library)
        tasks.append(dict(task, files={n: digest(folder/n) for n in ['bench.cir', 'library.spice']}))
    manifest = dict(identity=identity, tasks=tasks, diagnostic=True, qualified_phy=False,
                    change='Matched-unit R:2R preset, nominal 1.2 V at VDDD=1.8 V; unchanged OTA W8/C4 and stimuli')
    campaign.atomic(root/'manifest.json', manifest)
    validate(root, manifest)
    campaign.atomic(root/'state.json', dict(status='prepared', qualified_phy=False))
    return root


def validate(root, manifest):
    identity = manifest['identity']
    if producer_code() != identity['producer_code']:
        raise ValueError('Preset experiment producer changed')
    for path, value in identity['inputs'].items():
        if digest(ROOT/path) != value:
            raise ValueError('Preset experiment input changed: '+path)
    if digest(root/'inputs/ota_w8_c4.spice') != identity['source_sha256']:
        raise ValueError('Preset source changed')
    for name, value in identity['producer_code'].items():
        if digest(root/'inputs/scripts'/name) != value:
            raise ValueError('Preset producer archive changed')
    for task in manifest['tasks']:
        campaign.validate(root, manifest, task)


def run(root, jobs):
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = json.loads((root/'manifest.json').read_text()); validate(root, manifest)
        state = dict(status='running', qualified_phy=False, tasks={})
        campaign.atomic(root/'state.json', state)
        def execute(task):
            folder = root/task['id']; report = folder/'summary.json'
            if report.exists():
                result = json.loads(report.read_text())
                if result['input_files'] != task['files'] or digest(folder/'bench.cir.prn') != result['waveform_sha256']:
                    raise ValueError('Preset screen evidence changed')
                wave, header = read_wave(folder/'bench.cir.prn')
                for alias, node in task['aliases'].items(): header['V('+alias.upper()+')'] = header['V('+node.upper()+')']
                return dict(result, **loop(wave, header, 400, 'averaged_pfd_ota'))
            campaign.atomic(folder/'execution.json', dict(status='waiting_for_slot'))
            with slot():
                validate(root, manifest)
                campaign.atomic(folder/'execution.json', dict(status='running'))
                return campaign.execute(root, task)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {t['id']: pool.submit(execute, t) for t in manifest['tasks']}
            for name, future in futures.items():
                result = future.result(); state['tasks'][name] = dict(status='passed' if result['passed'] else 'failed')
                campaign.atomic(root/'state.json', state)
        validate(root, manifest)
        passed = all(t['status'] == 'passed' for t in state['tasks'].values())
        state['status'] = 'completed' if passed else 'completed_with_failures'
        campaign.atomic(root/'state.json', state)
        campaign.atomic(root/'summary.json', dict(passed=passed, qualified_phy=False, diagnostic=True, tasks=state['tasks']))
    return 0 if passed else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare'); p.add_argument('reference', type=Path); p.add_argument('qualification', type=Path)
    p = sub.add_parser('run'); p.add_argument('artifact', type=Path); p.add_argument('--jobs', type=int, choices=range(1, 4), default=2)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.reference.resolve(), args.qualification.resolve()), flush=True); return 0
    return run(args.artifact.resolve(), args.jobs)


if __name__ == '__main__':
    raise SystemExit(main())
