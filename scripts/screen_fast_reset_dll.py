#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Screen the fast-reset PFD in the source-matched W8/C4 DLL; no PHY qualification."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
from pathlib import Path
import re

import dll_campaign as campaign
from digital_candidate_rc import captured_inputs
from dll_design import block, native_block, PFD_PORTS
from dll_measurements import average, column, complete, loop, read_wave
from pfd_fast_reset_policy import pfd_fast_reset_paths_retained
from spice_engine import engine, provenance
from spice_library import checked_netlist, replace
from spice_probes import ProbeNetwork
from spice_slots import slot

ROOT = Path(__file__).resolve().parents[1]
VARIANT = 'ota_w8_c4'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_source(source):
    # PDK cell terminal order follows the archived HD SPICE definitions.
    rows = [
        ('XDISABLE', ['RESET_N','PD_ENABLE','VSS','VSS','VDDD','VDDD','DISALLOW'], 'sky130_fd_sc_hd__nand2_1', {}),
        ('XRESET', ['RU','RD','DISALLOW','VDDD','VSS','VSS','VDDD','VDDD','CLEAR_B'], 'sky130_fd_sc_hd__a22oi_4', {}),
        ('XU', ['REF','VDDD','CLEAR_B','VSS','VSS','VDDD','VDDD','RU'], 'sky130_fd_sc_hd__dfrtp_4', {}),
        ('XD', ['FB','VDDD','CLEAR_B','VSS','VSS','VDDD','VDDD','RD'], 'sky130_fd_sc_hd__dfrtp_4', {}),
        ('XUPBUF', ['RU','VSS','VSS','VDDD','VDDD','UP'], 'sky130_fd_sc_hd__buf_8', {}),
        ('XDNBUF', ['RD','VSS','VSS','VDDD','VDDD','DN'], 'sky130_fd_sc_hd__buf_8', {})]
    result = replace(source, 'lvds_pfd', block('lvds_pfd', PFD_PORTS, rows))
    if native_block(source, 'openlvds_dll_analog') != native_block(result, 'openlvds_dll_analog'):
        raise ValueError('Reset change altered the analog macro')
    for name in ['lvds_bias', 'openlvds_dll_core', 'openlvds_dll']:
        if campaign.text_block(source, name) != campaign.text_block(result, name):
            raise ValueError('Reset change altered ' + name)
    return result


def producer_code():
    names = {Path(p).name for p in campaign.CODE} | {
        Path(__file__).name, 'digital_candidate_rc.py', 'pfd_fast_reset_policy.py',
        'physical_policy.py', 'spice_engine.py', 'run_ngspice.py', 'spice_probes.py', 'spice_slots.py',
        'harden.py', 'harden_fast_reset_pfd.py', 'probe_pfd_fast_reset.py', 'probe_pfd_physical_candidate.py'}
    return {name: digest(ROOT / 'scripts' / name) for name in names}


def physical_inputs(capture):
    manifest = json.loads((capture / 'manifest.json').read_text())
    identity = manifest['identity']; proofs = dict(identity['physical_proofs'])
    if (digest(ROOT / 'scripts/probe_pfd_fast_reset.py') != identity['producer_sha256'] or
            digest(ROOT / 'scripts/probe_pfd_physical_candidate.py') != identity['adapter_sha256'] or
            digest(ROOT / 'scripts/pfd_fast_reset_policy.py') != identity['policy_sha256']):
        raise ValueError('Capture producer changed')
    if len(manifest['tasks']) != 3 or {t['offset_ps'] for t in manifest['tasks']} != {-850,0,850}:
        raise ValueError('Need all three matched capture controls')
    for name, value in proofs.items():
        if digest(ROOT / name) != value:
            raise ValueError('Capture physical input changed: ' + name)
    physical = ROOT / identity['physical']; summary = json.loads((physical / 'summary.json').read_text())
    if summary.get('pfd_policy') != 'pulse-area-fast-reset' or captured_inputs(physical, summary) != 'lvds_pfd':
        raise ValueError('Expected the physical single-AOI reset PFD')
    for name, value in summary['fast_reset_producer_code'].items():
        if digest(ROOT / 'scripts' / name) != value or digest(physical / 'producer_archive' / name) != value:
            raise ValueError('Physical producer changed')
    nl = ROOT / summary['run'] / 'final/nl/lvds_pfd.nl.v'
    if not pfd_fast_reset_paths_retained(nl.read_text()):
        raise ValueError('Physical reset topology changed')
    return manifest, proofs


def prepare(capture):
    capture = capture.resolve()
    if engine() != 'ngspice' or not capture.is_relative_to(ROOT / 'build/diagnostics/pfd_physical_capture'):
        raise ValueError('Use a native capture artifact in the pinned ngspice environment')
    cm, proofs = physical_inputs(capture)
    reference = ROOT / cm['identity']['reference']; original = json.loads((reference / 'manifest.json').read_text())
    if digest(reference / 'manifest.json') != cm['identity']['reference_sha256']:
        raise ValueError('Capture reference changed')
    qualification = ROOT / original['identity']['qualification']; qm = json.loads((qualification / 'manifest.json').read_text())
    if digest(qualification / 'manifest.json') != original['identity']['manifest_sha256']:
        raise ValueError('Source reference changed')
    base = ROOT / qm['identity']['full_models']['layout'] / 'candidate.spice'
    if digest(base) != original['identity']['source_sha256']:
        raise ValueError('Analog source changed')
    source = candidate_source(base.read_text())
    captured_task = next(t for t in cm['tasks'] if t['offset_ps'] == -850)
    library_path = capture / captured_task['id'] / 'library.spice'
    if digest(library_path) != captured_task['files']['library.spice']:
        raise ValueError('Native capture library changed')
    library = library_path.read_text()
    if campaign.text_block(library, 'openlvds_dll_analog').strip() != campaign.text_block(native_block(source, 'openlvds_dll_analog'), 'openlvds_dll_analog').strip():
        raise ValueError('Captured analog devices differ from the proposed source')
    physical = ROOT / cm['identity']['physical']; info = json.loads((physical / 'extraction.json').read_text())
    expected = re.sub(r'(?im)^(\.subckt\s+)lvds_pfd\b', r'\1lvds_pfd_physical', checked_netlist(info))
    expected = re.sub(r'(?im)^(\.ends\s+)lvds_pfd\b', r'\1lvds_pfd_physical', expected)
    if campaign.text_block(library, 'lvds_pfd_physical').strip() != campaign.text_block(expected, 'lvds_pfd_physical').strip():
        raise ValueError('Captured PFD differs from the actual extraction')
    previous = ROOT / qm['identity']['screen']
    if digest(previous / 'manifest.json') != qm['identity']['screen_manifest_sha256']:
        raise ValueError('Original architecture manifest changed')
    templates = json.loads((previous / 'manifest.json').read_text())
    selected = [t for t in templates['tasks'] if t['spec'].get('variant') == VARIANT and t['spec']['kind'] == 'loop']
    if {(t['spec']['corner'], t['spec']['temp']) for t in selected} != {('ss',0), ('tt',25), ('ff',0)} or len(selected) != 3:
        raise ValueError('Need the three original architecture fixtures')
    requirements = previous / 'inputs/requirements.json'
    if requirements.read_bytes() != (ROOT / 'requirements.json').read_bytes():
        raise ValueError('Reference requirements changed')
    inputs = {str(p.relative_to(ROOT)): digest(p) for p in [capture / 'manifest.json', library_path, base, requirements,
              reference / 'manifest.json', qualification / 'manifest.json', previous / 'manifest.json']}
    inputs.update(proofs)
    for task in selected:
        path = previous / task['id'] / 'bench.cir'
        if digest(path) != task['files']['bench.cir']:
            raise ValueError('Original architecture fixture changed')
        inputs[str(path.relative_to(ROOT))] = digest(path)
    identity = dict(code=campaign.dependencies(), producer_code=producer_code(), simulator_provenance=provenance(),
                    source_sha256=hashlib.sha256(source.encode()).hexdigest(), inputs=inputs,
                    capture=str(capture.relative_to(ROOT)), full_library_sha256=digest(library_path),
                    requirements_sha256=digest(requirements))
    root = ROOT / 'build/diagnostics/dll_architecture' / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    if (root / 'manifest.json').exists():
        validate(root, json.loads((root / 'manifest.json').read_text()))
        print(root, flush=True); return root
    root.mkdir(parents=True, exist_ok=True); archive = root / 'inputs'; archive.mkdir(exist_ok=True)
    (archive / (VARIANT + '.spice')).write_text(source)
    (archive / 'requirements.json').write_bytes(requirements.read_bytes())
    scripts = archive / 'scripts'; scripts.mkdir(exist_ok=True)
    for name in identity['producer_code']:
        (scripts / name).write_bytes((ROOT / 'scripts' / name).read_bytes())
    tasks = []
    for original_task in selected:
        name = original_task['id']; folder = root / name; folder.mkdir(exist_ok=True)
        old = previous / name; deck = (old / 'bench.cir').read_text()
        include = f'.include "{old}/library.spice"'
        if deck.count(include) != 1:
            raise ValueError('Unexpected original library inclusion')
        deck = deck.replace(include, f'.include "{folder}/library.spice"')
        _, body = deck.split('\n', 1); deck = 'OpenLVDS single-AOI PFD source-specific DLL screen\n' + body
        if campaign.bias_reference_count(deck, library) != 1:
            raise ValueError('Duplicated bias reference')
        ProbeNetwork(library).validate(deck, original_task['aliases'].values())
        (folder / 'bench.cir').write_text(deck); (folder / 'library.spice').write_text(library)
        tasks.append(dict(original_task, files={n: digest(folder / n) for n in ['bench.cir', 'library.spice']}))
    campaign.atomic(root / 'manifest.json', dict(identity=identity, tasks=tasks, diagnostic=True, qualified=False,
                    analog_view='Native-finger schematic DLL/delay; actual single-AOI PFD GDS and extracted bias'))
    campaign.atomic(root / 'state.json', dict(status='prepared', tasks={t['id']: dict(status='pending') for t in tasks}))
    print(root, flush=True); return root


def validate(root, manifest):
    identity = manifest['identity']
    if producer_code() != identity['producer_code'] or provenance() != identity['simulator_provenance']:
        raise ValueError('Screen producer or backend changed')
    for name, value in identity['producer_code'].items():
        if digest(root / 'inputs/scripts' / name) != value:
            raise ValueError('Screen producer archive changed')
    if digest(root / 'inputs' / (VARIANT + '.spice')) != identity['source_sha256']:
        raise ValueError('Screen source changed')
    for name, value in identity['inputs'].items():
        if digest(ROOT / name) != value:
            raise ValueError('Screen input changed: ' + name)
    for task in manifest['tasks']:
        campaign.validate(root, manifest, task)


def capture_admission(root, manifest):
    capture = ROOT / manifest['identity']['capture']; cm = json.loads((capture / 'manifest.json').read_text())
    if len(cm['tasks']) != 3 or {t['offset_ps'] for t in cm['tasks']} != {-850,0,850}:
        raise ValueError('Need all three matched capture controls')
    for task in cm['tasks']:
        path = capture / task['id'] / 'summary.json'
        if not path.resolve().is_relative_to(capture):
            raise ValueError('Capture result outside its artifact')
        if not path.exists():
            raise ValueError('Capture controls are still pending')
        report = json.loads(path.read_text())
        if report['manifest_sha256'] != digest(capture / 'manifest.json'):
            raise ValueError('Capture result is stale')
        if any(report['files'].get(name) != value for name, value in task['files'].items()):
            raise ValueError('Capture result differs from its fixture')
        for name, value in report['files'].items():
            if digest(path.parent / name) != value:
                raise ValueError('Capture result changed')
        wave, header = read_wave(path.parent / 'bench.cir.prn')
        if not complete(wave, 80):
            raise ValueError('Incomplete capture control')
        for alias, node in task['aliases'].items():
            header['V(' + alias.upper() + ')'] = header['V(' + node.upper() + ')']
        t = wave[:, 1]; keep = (t >= 60e-9) & (t <= 80e-9)
        difference = average(t[keep], column(wave, header, 'UP')[keep]) - average(t[keep], column(wave, header, 'DN')[keep])
        correct = difference * task['offset_ps'] > 0 if task['offset_ps'] else abs(difference) < .02
        if abs(difference - report['raw_difference_v']) > 1e-12 or bool(correct) != report['correct_area_sign']:
            raise ValueError('Capture analysis differs from its waveform')
        if task['offset_ps'] and not correct:
            raise ValueError('Physical PFD still has the wrong correction sign')


def run(root, jobs):
    with (root / '.source_screen.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = json.loads((root / 'manifest.json').read_text()); validate(root, manifest); capture_admission(root, manifest)
        state = dict(status='running', tasks={t['id']: dict(status='pending') for t in manifest['tasks']})
        campaign.atomic(root / 'state.json', state)
        def execute(task):
            folder = root / task['id']; path = folder / 'summary.json'
            if path.exists():
                result = json.loads(path.read_text())
                if result['input_files'] != task['files'] or digest(folder / 'bench.cir.prn') != result['waveform_sha256']:
                    raise ValueError('Captured architecture result changed')
                wave, header = read_wave(folder / 'bench.cir.prn')
                for alias, node in task['aliases'].items():
                    header['V(' + alias.upper() + ')'] = header['V(' + node.upper() + ')']
                return dict(result, **loop(wave, header, 400, 'averaged_pfd_ota'))
            campaign.atomic(folder / 'execution.json', dict(status='waiting_for_slot'))
            with slot():
                campaign.atomic(folder / 'execution.json', dict(status='running'))
                return campaign.execute(root, task)
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {t['id']: pool.submit(execute, t) for t in manifest['tasks']}
            for name, future in futures.items():
                result = future.result(); state['tasks'][name] = dict(status='passed' if result['passed'] else 'failed')
                campaign.atomic(root / 'state.json', state)
        validate(root, manifest)
        passed = all(t['status'] == 'passed' for t in state['tasks'].values())
        state['status'] = 'completed' if passed else 'completed_with_failures'
        campaign.atomic(root / 'state.json', state)
        campaign.atomic(root / 'summary.json', dict(passed=passed, diagnostic=True, qualified_phy=False, tasks=state['tasks']))
    print(root, flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare','run']); parser.add_argument('artifact', type=Path)
    parser.add_argument('--jobs', type=int, choices=range(1,7), default=3)
    args = parser.parse_args()
    if args.action == 'prepare': prepare(args.artifact)
    else: run(args.artifact.resolve(), args.jobs)
