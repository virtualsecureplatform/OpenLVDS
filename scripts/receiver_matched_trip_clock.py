#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Screen admitted unit-matched differential-restoration changes against an attested identical P8/N8 source reference."""
import argparse
import copy
from contextlib import contextmanager
import fcntl
import hashlib
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import matrix_receiver_matched_trip as matrix
import screen_receiver_matched_trip as dc
import receiver_lvt_pair_experiment as original
import receiver_restore_threshold_clock as parent_clock
import receiver_clamp_experiment as engine
import receiver_decision_load_clock as clock
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
VARIANTS = ['matched_t8_r7', 'matched_t16_r7']


def source_variant(source, modified, variant):
    if variant not in VARIANTS:
        raise ValueError('Select a declared differential-restoration correction')
    base = original.source_variant(source, True)
    return dc.transform(base, variant if modified else 'control')


def static_gate(screen, variant):
    if variant not in VARIANTS or not screen.is_relative_to(ROOT/'build/diagnostics/receiver_matched_trip_matrix'):
        raise ValueError('Use the differential-restoration DC matrix and a declared correction')
    manifest = json.loads((screen/'manifest.json').read_text())
    children = manifest['identity']['children']
    matrix.coverage(children, json.loads((ROOT/'requirements.json').read_text()))
    if not (screen/'summary.json').is_file() or any(
            not (ROOT/c['root']/n).is_file() for c in children
            for n in ['summary.json']+[v+'/summary.json' for v in dc.VARIANTS]):
        raise ValueError('Complete all fifteen differential-restoration DC cases before source clocks')
    # No missing child can be launched by this cached remeasurement path.
    with (screen/'.clock_admission.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        # The producer writes its final report just before releasing this
        # lock. Wait for that release before requesting cached remeasurement.
        with (screen/'.execution.lock').open('a+') as producer:
            fcntl.flock(producer, fcntl.LOCK_EX)
        report = matrix.run(screen)
    gate = report['variants'][variant]
    expected_gate = dict(required=15, completed=15, passed_cases=15, source_dc_passed=True)
    if gate != expected_gate or report['variants']['control'] != expected_gate:
        raise ValueError('Selected correction must pass all fifteen original DC/current/stress cases')
    paths = [screen/'manifest.json', screen/'summary.json', screen/'source_dc_admission'/(variant+'.json')]
    candidate_hash = manifest['identity']['candidate_sha256'][variant]
    for c in children:
        child = ROOT/c['root']
        paths.extend(child/n for n in ['manifest.json', 'summary.json'])
        for v in ['control', variant]:
            folder = child/v
            paths.extend(folder/n for n in ['candidate.spice', 'source.spice', 'bench.cir', 'bench.cir.prn', 'summary.json'])
        if dc.sha(child/variant/'candidate.spice') != candidate_hash:
            raise ValueError('Selected PVT candidate circuit bytes changed')
    return {str(p.relative_to(ROOT)): dc.sha(p) for p in paths}


def prepare(parent, screen, variant):
    proofs = static_gate(screen, variant)
    if not parent.is_relative_to(ROOT/'build/diagnostics/receiver_clamp'):
        raise ValueError('Use the completed original LVT source-clock context')
    previous = json.loads((parent/'manifest.json').read_text())
    if (previous['identity'].get('first_restorer_variant') != 'restore_lvt_n8' or
            previous['identity']['code'].get('receiver_restore_threshold_clock.py') != dc.sha(ROOT/'scripts/receiver_restore_threshold_clock.py') or
            not (parent/'source_clock_admission.json').is_file()):
        raise ValueError('Require the original LVT clock producer and completed admission')
    admission = json.loads((parent/'source_clock_admission.json').read_text())
    if (admission.get('source_clock_passed') is not True or
            admission.get('manifest_sha256') != dc.sha(parent/'manifest.json') or
            admission.get('report_sha256') != dc.sha(parent/'summary.json') or
            not clock.admitted(json.loads((parent/'summary.json').read_text()))):
        raise ValueError('Original LVT source-clock admission is changed or failed')
    if len(previous['tasks']) != 3 or {t['id'] for t in previous['tasks']} != clock.CASES:
        raise ValueError('Require all three original clock fixtures')
    if any(not (parent/t['id']/'summary.json').is_file() for t in previous['tasks']):
        raise ValueError('Complete every original LVT source-clock control first')
    parent_clock.run(parent)  # All reports exist: cached scientific remeasurement only.
    identity = copy.deepcopy(previous['identity'])
    identity.pop('first_restorer_variant', None)
    reference = parent/'clamped_captured'
    identity['reference_adoption'] = dict(parent=str(parent.relative_to(ROOT)), task='clamped_captured',
        waveform_sha256=dc.sha(reference/'bench.cir.prn'), report_sha256=dc.sha(reference/'summary.json'))
    identity.update(matched_trip_variant=variant, static_screen=str(screen.relative_to(ROOT)),
        static_proofs=proofs, scope='Original three full 80 ns, 47-period source-clock controls for the declared differential-restoration correction; attested identical source-qualified P8/N8 reference, native shared bias and digital RX. No receiver wire RC or physical/native/PHY admission.')
    identity['inputs'].update(proofs)
    for n in ['manifest.json', 'summary.json', 'source_clock_admission.json',
              'clamped_captured/summary.json', 'clamped_captured/bench.cir.prn']:
        identity['inputs'][str((parent/n).relative_to(ROOT))] = dc.sha(parent/n)
    identity['code'].update({n: dc.sha(ROOT/'scripts'/n) for n in
        [NAME, 'matrix_receiver_matched_trip.py', 'screen_receiver_matched_trip.py', 'receiver_differential_restore.py', 'receiver_matched_trip_restore.py', 'receiver_gain_balance.py',
         'matrix_receiver_restore_threshold.py', 'receiver_restore_threshold.py',
         'receiver_soft_common_mode.py', 'receiver_lvt_restore_experiment.py']})
    for task in previous['tasks']:
        for n, h in task['files'].items():
            p = parent/task['id']/n
            if dc.sha(p) != h:
                raise ValueError('Original LVT clock fixture changed')
            identity['inputs'][str(p.relative_to(ROOT))] = h
    root = ROOT/'build/diagnostics/receiver_clamp'/hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    tasks = []; root.mkdir(parents=True, exist_ok=True)
    for old_id, new_id, modified in [('clamped_captured','unclamped_captured',False),
                                    ('clamped_captured','clamped_captured',True),
                                    ('clamped_sharp_control','clamped_sharp_control',True)]:
        task = copy.deepcopy(next(t for t in previous['tasks'] if t['id']==old_id))
        task.update(id=new_id, clamped=modified); tasks.append(task)
    source = (ROOT/'analog/openlvds.spice').read_text()
    candidate_hash = json.loads((screen/'manifest.json').read_text())['identity']['candidate_sha256'][variant]
    for task in tasks:
        old = parent/('clamped_captured' if task['mode']=='captured' else 'clamped_sharp_control')
        folder = root/task['id']; folder.mkdir(exist_ok=True)
        if (old/'candidate.spice').read_text() != parent_clock.source_variant(source, True, 'restore_lvt_n8'):
            raise ValueError('Original clock source differs from its declared LVT factory')
        candidate = source_variant(source, task['clamped'], variant)
        expected_hash = candidate_hash if task['clamped'] else json.loads(
            (screen/'manifest.json').read_text())['identity']['candidate_sha256']['control']
        if hashlib.sha256(candidate.encode()).hexdigest() != expected_hash:
            raise ValueError('Clock source differs from admitted DC candidate bytes')
        ports, devices = engine.flatten(engine.circuits(candidate), engine.TOP)
        model = engine.schematic_text(engine.TOP, ports, devices)
        if task['clamped']:
            library = engine.replace((old/'library.spice').read_text(), engine.TOP, model)
        else:
            library = (old/'library.spice').read_text()
            if engine.closure_hash(library, engine.TOP) != engine.closure_hash(model, engine.TOP):
                raise ValueError('Adopted reference differs from the exact declared control circuit')
        for protected in ['lvds_bias', 'openlvds_ddr_rx']:
            if engine.closure_hash(library, protected) != engine.closure_hash((old/'library.spice').read_text(), protected):
                raise ValueError('Differential-restoration clock correction changed an unrelated closure')
        deck = (old/'bench.cir').read_text(); before = f'.include "{old}/library.spice"'
        if deck.count(before) != 1 or clock.tighten(deck) != deck:
            raise ValueError('Original clock binding or numerical policy changed')
        deck = deck.replace(before, f'.include "{folder}/library.spice"')
        engine.ProbeNetwork(library).validate(deck, task['aliases'].values())
        for n, text in [('candidate.spice', candidate), ('library.spice', library), ('bench.cir', deck)]:
            p = folder/n
            if p.exists() and p.read_text() != text:
                raise ValueError('Prepared differential-restoration source-clock fixture changed')
            if not p.exists():
                p.write_text(text)
        task['files'] = {n: dc.sha(folder/n) for n in task['files']}
    tasks[0]['files']['bench.cir.prn'] = dc.sha(reference/'bench.cir.prn')
    capture_manifest(root/'manifest.json', dict(identity=identity, tasks=tasks, qualified_phy=False))
    adopt_reference(reference, root/'unclamped_captured', root)
    return root


def adopt_reference(old, new, root, create=True):
    """Retarget only an already validated identical reference, never a candidate.

    prepare first remeasures the complete parent with its original producer.
    The unchanged scientific runner remeasures this copied reference again.
    """
    manifest = json.loads((root/'manifest.json').read_text())
    task = next(t for t in manifest['tasks'] if t['id'] == 'unclamped_captured')
    if task['clamped'] is not False or new.name != 'unclamped_captured' or old.name != 'clamped_captured':
        raise ValueError('Reference adoption cannot fill a modified candidate task')
    reference = json.loads((old/'summary.json').read_text())
    old_manifest = json.loads((old.parent/'manifest.json').read_text())
    old_task = next(t for t in old_manifest['tasks'] if t['id'] == old.name)
    transport = reference['receiver_transport']
    if (old_task['clamped'] is not True or old_task['aliases'] != task['aliases'] or
            reference['manifest_sha256'] != dc.sha(old.parent/'manifest.json') or
            reference['waveform_sha256'] != dc.sha(old/'bench.cir.prn') or
            len(transport['pulses']) != 47 or transport['missing_output_edges'] != 0 or
            any(p['output_edges_in_next_input_period'] != 1 for p in transport['pulses'])):
        raise ValueError('Require the exact completed passing P8/N8 source reference')
    for name in ['candidate.spice', 'library.spice']:
        if (old/name).read_bytes() != (new/name).read_bytes():
            raise ValueError('Reference adoption changes circuit/library bytes')
    before = (old/'bench.cir').read_text(); include = f'.include "{old}/library.spice"'
    if before.count(include) != 1 or (new/'bench.cir').read_text() != before.replace(
            include, f'.include "{new}/library.spice"') or clock.tighten(before) != before:
        raise ValueError('Reference adoption changes stimulus or numerical policy')
    for name,h in old_task['files'].items():
        if dc.sha(old/name) != h:
            raise ValueError('Original reference input changed')
    waveform = new/'bench.cir.prn'
    if waveform.exists():
        if dc.sha(waveform) != reference['waveform_sha256']:
            raise ValueError('Existing reference waveform changed; retain it')
    elif create:
        shutil.copyfile(old/'bench.cir.prn', waveform)
    else:
        raise ValueError('Adopted reference waveform is missing')
    expected = dict(reference, task=task['id'], manifest_sha256=dc.sha(root/'manifest.json'))
    if create:
        capture_manifest(new/'summary.json', expected)
    elif json.loads((new/'summary.json').read_text()) != expected:
        raise ValueError('Adopted reference summary changed')
    proof = dict(parent=str(old.relative_to(ROOT)), qualified_phy=False,
        manifest_sha256=dc.sha(root/'manifest.json'), waveform_sha256=dc.sha(waveform),
        parent_report_sha256=dc.sha(old/'summary.json'),
        scope='Only the exact completed matched source-qualified P8/N8 captured reference is reused. Identical candidate/library bytes and fixture beyond include path; unchanged scientific runner remeasures it. Modified candidate captures and sharp controls are never adopted.')
    if create:
        capture_manifest(root/'reference_adoption.json', proof)
    elif json.loads((root/'reference_adoption.json').read_text()) != proof:
        raise ValueError('Reference-adoption proof changed')


@contextmanager
def profile(variant):
    if variant not in VARIANTS:
        raise ValueError('Select a declared differential-restoration correction')
    previous = clock.factory, clock.static_gate
    try:
        clock.factory = SimpleNamespace(source_variant=lambda s, changed: source_variant(s, changed, variant), experiment=engine)
        clock.static_gate = lambda screen: static_gate(screen, variant)
        yield
    finally:
        clock.factory, clock.static_gate = previous


def run(root, wait_slot=None):
    m = json.loads((root/'manifest.json').read_text())
    if m['identity']['code'].get(NAME) != dc.sha(Path(__file__)):
        raise ValueError('Differential-restoration source-clock producer changed')
    if not (root/'reference_adoption.json').is_file():
        raise ValueError('Require the explicit attested reference-adoption receipt')
    proof = m['identity']['reference_adoption']
    adopt_reference(ROOT/proof['parent']/proof['task'], root/'unclamped_captured', root, create=False)
    with profile(m['identity']['matched_trip_variant']):
        clock.run(root, wait_slot)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path); p.add_argument('--dc-matrix', type=Path)
    p.add_argument('--variant', choices=VARIANTS); p.add_argument('--wait-slot', type=int, choices=range(6)); a = p.parse_args()
    if a.action == 'prepare':
        if a.dc_matrix is None or a.variant is None:
            p.error('--dc-matrix and --variant are required')
        print(prepare(a.artifact.resolve(), a.dc_matrix.resolve(), a.variant), flush=True)
    else:
        run(a.artifact.resolve(), a.wait_slot)
