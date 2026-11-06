#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Reduce REQUEST first-stage feedthrough using already qualified P10/N8 RC."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import probe_counter_matched_buffers_v306 as source
import probe_tapered_regenerated_bank_v310 as tapered
from native_binary_raw_v2 import validate
from diagnose_shared_counter_v200 import terminal_peak
from spice_dispatch import lease
from spice_engine import engine, provenance

ROOT = source.ROOT
sha = source.sha
atomic = source.atomic
VERSION = 'request-only-p10n8-first-stage-native-counter-overvoltage-repair-v317.1'
CONTEXT = 'request_taper_counter_v317'
SMALL = tapered.MODELS['p10n8']
BUFFER = 'openlvds_request_taper_p10n8_p20n16_v317'
VARIANT = 'request_taper'
REQUEST_ROLES = ('request_driver', 'request_driver_parallel')
PREFIXES = tuple('XD:XR:X' + name + ':Xrestore0:' for name in REQUEST_ROLES)
NATIVE_MOS = 808
SCOPE = ('Qualified P10/N8 first inverter only in both REQUEST buffers; original matched '
         'P20/N16 final REQUEST and CLK stages, unchanged counter logic/loads/20ps REQUEST, '
         'component RC with ideal new shared wires, no whole-counter RC/all-PVT/DCC/PHY admission')


def specifications():
    sample = source.specifications()[0]
    return [dict(sample, temperature=t, stop_level=level, buffer_variant=VARIANT)
            for t in (0, 40) for level in (0, 1)]


def transform(cells, module, previous, small):
    native = source.source.native
    before = native.definitions(cells)
    added = native.definitions(small)
    if (SMALL in before or BUFFER in before or set(added) != {SMALL}
            or added[SMALL][0] != ['A', 'Y', 'VGND', 'VPWR']
            or before[source.PN][0] != ['A', 'Y', 'VGND', 'VPWR']):
        raise ValueError('Qualified driver namespace or port order changed')
    expected_wrapper = [['Xrestore0', 'A', 'internal_b', 'VGND', 'VPWR', source.PN],
                        ['Xrestore1', 'internal_b', 'X', 'VGND', 'VPWR', source.PN]]
    if before[source.BUFFER] != (['A', 'X', 'VGND', 'VPWR'], expected_wrapper):
        raise ValueError('Original matched two-inverter wrapper changed')
    body = before[source.CORE][1]
    if len(body) != 22 or len({w[0] for w in body}) != 22:
        raise ValueError('Require the original 22 counter macros')
    for role in source.ROLES:
        calls = [w for w in body if w[0] == 'X' + role]
        if len(calls) != 1 or calls[0][-1] != source.BUFFER:
            raise ValueError('Original matched buffer roles changed')
    old_core = source.cell_definition(cells, source.CORE)
    new_core = old_core
    for role in REQUEST_ROLES:
        old = ['X' + role, 'REQUEST', 'request_i', 'VGND', 'VPWR', source.BUFFER]
        if [w for w in body if w[0] == old[0]] != [old]:
            raise ValueError('REQUEST role pins or supply changed')
        new_core = new_core.replace(' '.join(old) + '\n', ' '.join(old[:-1] + [BUFFER]) + '\n', 1)
    wrapper = '\n'.join(['.subckt ' + BUFFER + ' A X VGND VPWR',
        'Xrestore0 A internal_b VGND VPWR ' + SMALL,
        'Xrestore1 internal_b X VGND VPWR ' + source.PN, '.ends ' + BUFFER, ''])
    result = cells.replace(old_core, new_core, 1) + '\n' + small + '\n' + wrapper
    for name in before:
        if name != source.CORE and source.cell_definition(cells, name) != source.cell_definition(result, name):
            raise ValueError('Unrelated qualified native macro changed')
    devices = source.observations(result, module)
    old_map = {d['name']: d for d in previous}
    new_map = {d['name']: d for d in devices}
    removed = [d for d in previous if d['name'].startswith(PREFIXES)]
    added_mos = [d for d in devices if d['name'].startswith(PREFIXES)]
    if (len(previous) != 844 or len(old_map) != 844 or len(devices) != NATIVE_MOS
            or len(new_map) != NATIVE_MOS or len(removed) != 72 or len(added_mos) != 36
            or any(new_map.get(n) != d for n, d in old_map.items() if not n.startswith(PREFIXES))):
        raise ValueError('Non-REQUEST-first-stage native terminals or exact MOS census changed')
    _, old_leaves = tapered.source.inventory.native_leaves(tapered.collapse(cells + module), source.source.HARNESS)
    _, new_leaves = tapered.source.inventory.native_leaves(tapered.collapse(result + module), source.source.HARNESS)
    mims = lambda leaves: sum('cap_mim' in d['model'] for d in leaves)
    if mims(old_leaves) != mims(new_leaves):
        raise ValueError('Native MIM inventory changed')
    proof = dict(native_mos=NATIVE_MOS, native_mims=mims(new_leaves),
        removed_request_first_stage_mos=72, added_request_first_stage_mos=36,
        changed_prefixes=list(PREFIXES), all_other_native_terminal_maps_preserved=True,
        all_original_noncore_macros_preserved=True, all_clock_and_final_request_stages_preserved=True,
        shared_wire_rc_qualified=False, qualified_phy=False)
    return result, module, devices, proof


def validate_pair(rows):
    if (len(rows) != 2 or [r['task']['spec'] for r in rows] != source.specifications()[:2]
            or any(r['error'] is not None or r['result'] is None for r in rows)):
        raise ValueError('Require both exact completed first matched-buffer controls')
    baseline, matched = [r['result'] for r in rows]
    gates = ('held_before_request_passed', 'stopped_clock_clear_and_reassert_passed',
             'phase_arming_passed', 'stopped_clock_arm_clear_passed',
             'alternating_phase_order_passed', 'stopped_clock_intermediate_clear_passed')
    if (baseline['hypothesis_point_checks_passed'] is not True
            or matched['terminal_screen_passed'] is not False
            or matched['hypothesis_point_checks_passed'] is not False
            or not all(matched[k] is True for k in gates)
            or matched['low_windows']['all_three_assertions_in_original_low_windows'] is not True
            or matched['low_windows']['minimum_remaining_low_window_ps'] <= 0):
        raise ValueError('Require isolated terminal failure with preserved startup/clear timing')


def require_cause(parent, manifest, evidence):
    rows = [json.loads((parent / str(k) / 'summary.json').read_text()) for k in (0, 1)]
    validate_pair(rows)
    paths = [parent / 'manifest.json', evidence / 'summary.json']
    for k, row in enumerate(rows):
        folder = parent / str(k)
        if (row['task'] != manifest['tasks'][k]
                or any(sha(folder / n) != h for n, h in row['files'].items())
                or source.measure(folder, manifest['identity'], row['task']['spec']) != row['result']):
            raise ValueError('Complete first-pair native metrics or hashes do not reproduce')
        paths += [folder / 'summary.json', *[folder / n for n in row['files']]]
    report = json.loads((evidence / 'summary.json').read_text())
    folder = parent / '1'
    failed = {d['device']: d for d in rows[1]['result']['terminal_stress'] if not d['passed']}
    faults = report['failed_devices']
    if (report.get('all_stored_failed_peaks_reproduced') is not True
            or report.get('parameters_changed') is not False or report.get('qualified_phy') is not False
            or report['case'] != str(folder.relative_to(ROOT))
            or len(faults) != 80 or len({d['device'] for d in faults}) != 80
            or {d['device'] for d in faults} != set(failed)
            or any(sha(ROOT / n) != h for n, h in report['inputs'].items())):
        raise ValueError('Require unchanged exact-sample 80-device REQUEST stress diagnosis')
    devices = {d['name']: d for d in manifest['identity']['devices']['matched']}
    column = lambda n: 'v(' + n.replace(':', '.').lower() + ')'
    required = {column(n) for name in failed for n in devices[name]['terminals'] if n != '0'}
    names, data = validate(folder / 'bench.raw', required, 26e-9)
    idx = {n: k for k, n in enumerate(names)}
    times = data[:, idx['time']] * 1e12
    zero = np.zeros(len(times))
    groups = {'request': 0, 'setter': 0}
    for fault in faults:
        d = devices[fault['device']]
        values = [zero if n == '0' else data[:, idx[column(n)]] for n in d['terminals']]
        peak, sample, a, b = terminal_peak(values)
        observed = {label: dict(node=n, voltage_v=float(values[k][sample]))
                    for k, (label, n) in enumerate(zip(('D', 'G', 'S', 'B'), d['terminals']))}
        if (fault['model'] != d['model'] or abs(peak - fault['peak_v']) > 1e-12
                or abs(peak - failed[d['name']]['max_terminal_difference_v']) > 1e-12
                or fault['terminals'] != observed or fault['time_ps'] != float(times[sample])
                or fault['worst_pair'] != [('D', 'G', 'S', 'B')[k] for k in (a, b)]
                or fault['limit_v'] != d['limit_v']):
            raise ValueError('Exact original failed terminal sample does not reproduce')
        if any(d['name'].startswith('XD:XR:X' + role + ':Xrestore1:') for role in REQUEST_ROLES):
            groups['request'] += 1
        elif d['name'].startswith('XD:XR:Xlow0_set_pair:'):
            groups['setter'] += 1
        else:
            raise ValueError('Failure is not isolated to REQUEST restoration/setter nodes')
    if groups != dict(request=72, setter=8):
        raise ValueError('Original REQUEST/setter failure census changed')
    paths += [ROOT / n for n in report['inputs']]
    return rows, paths


def fixture(out, spec, devices):
    text = source.fixture(out, spec, devices)
    if not text.startswith('OpenLVDS ' + source.VERSION + '\n'):
        raise ValueError('Original native counter fixture changed')
    return text.replace('OpenLVDS ' + source.VERSION + '\n', 'OpenLVDS ' + VERSION + '\n', 1)


def guard_inputs(inputs):
    # Historical raw traces gate preparation and the final receipt. They are
    # not inputs to the new simulator. Every other captured input is checked
    # on each lease, including all circuit/code/model/geometry/proof files.
    return {n: h for n, h in inputs.items()
            if not (Path(n).suffix == '.raw' and Path(n).parts[:2] == ('build', 'diagnostics'))}


def prepare(parent, drivers, evidence):
    manifest = source.bound(parent)
    previous = manifest['identity']
    controls, paths = require_cause(parent, manifest, evidence)
    libraries, driver_paths, driver_identity = tapered.driver_materials(drivers)
    cells, module, devices, proof = transform((parent / 'matched/cells.spice').read_text(),
        (parent / 'matched/pair.spice').read_text(), previous['devices']['matched'], libraries['p10n8'])
    paths += driver_paths + [parent / n for n in manifest['libraries']]
    paths += [ROOT / n for n in previous['inputs']]
    paths += sorted({Path(m.__file__).resolve() for m in list(sys.modules.values())
                     if getattr(m, '__file__', None) and Path(m.__file__).resolve().parent == ROOT / 'scripts'})
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in sorted(set(paths))}
    identity = dict(version=VERSION, parent=str(parent.relative_to(ROOT)), drivers=str(drivers.relative_to(ROOT)),
        diagnosis=str(evidence.relative_to(ROOT)), source_controls=controls,
        devices={VARIANT: devices}, native_revision=proof, specs=specifications(),
        simulator=previous['simulator'], pdk_files=previous['pdk_files'],
        external_files=driver_identity['external_files'], inputs=inputs, guards=guard_inputs(inputs),
        library_sha256={n: hashlib.sha256(text.encode()).hexdigest()
                        for n, text in (('cells.spice', cells), ('pair.spice', module))},
        max_workers=1, priority=1, scope=SCOPE)
    out = ROOT / 'build/diagnostics' / CONTEXT / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=False)
    (out / 'cells.spice').write_text(cells)
    (out / 'pair.spice').write_text(module)
    tasks = []
    for k, spec in enumerate(identity['specs']):
        folder = out / str(k)
        folder.mkdir()
        (folder / 'bench.cir').write_text(fixture(out, spec, devices))
        tasks.append(dict(id=str(k), spec=spec, deck_sha256=sha(folder / 'bench.cir')))
    atomic(out / 'manifest.json', dict(identity=identity, tasks=tasks,
        libraries={n: sha(out / n) for n in ('cells.spice', 'pair.spice')}, qualified_phy=False))
    return out


def bound(out, *, full=True):
    manifest = json.loads((out / 'manifest.json').read_text())
    i = manifest['identity']
    if (out.parent != ROOT / 'build/diagnostics' / CONTEXT or i['version'] != VERSION
            or out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
            or i['specs'] != specifications() or i['max_workers'] != 1 or i['priority'] != 1
            or manifest['qualified_phy'] is not False or i['scope'] != SCOPE
            or manifest['libraries'] != i['library_sha256']
            or i['guards'] != guard_inputs(i['inputs']) or engine() != 'ngspice'
            or provenance() != i['simulator']
            or any(sha(ROOT / n) != h for n, h in (i['inputs'] if full else i['guards']).items())
            or any(sha(Path(n)) != h for n, h in {**i['pdk_files'], **i['external_files']}.items())
            or any(sha(out / n) != h for n, h in manifest['libraries'].items())
            or len(manifest['tasks']) != 4):
        raise ValueError('REQUEST taper native context changed')
    devices = source.observations((out / 'cells.spice').read_text(), (out / 'pair.spice').read_text())
    if devices != i['devices'][VARIANT] or len(devices) != NATIVE_MOS:
        raise ValueError('REQUEST taper native terminal observations changed')
    for k, task in enumerate(manifest['tasks']):
        path = out / str(k) / 'bench.cir'
        if (task != dict(id=str(k), spec=i['specs'][k], deck_sha256=sha(path))
                or path.read_text() != fixture(out, task['spec'], devices)):
            raise ValueError('Original four-case full native fixture changed')
    return manifest


def measure(folder, identity, spec):
    return dict(source.measure(folder, identity, spec), scope=SCOPE,
                component_rc_only=True, counter_shared_wire_rc_qualified=False,
                whole_clock_rc_qualified=False, all_pvt_covered=False,
                electrical_qualification_passed=False, qualified_phy=False)


def assess(rows):
    if len(rows) != 4 or any(r['error'] is not None or r['result'] is None for r in rows):
        return None
    if [r['task']['spec'] for r in rows] != specifications():
        raise ValueError('Require exact SS0/40 sixty-percent both-stopped-level coverage')
    passed = all(r['result']['hypothesis_point_checks_passed']
        and r['result']['counter_feasibility_passed'] and r['result']['terminal_screen_passed']
        and r['result']['low_windows']['all_three_assertions_in_original_low_windows']
        and np.isfinite(r['result']['minimum_clock_low_voltage_margin_v'])
        and r['result']['minimum_clock_low_voltage_margin_v'] >= 0
        and np.isfinite(r['result']['low_windows']['minimum_remaining_low_window_ps'])
        and r['result']['low_windows']['minimum_remaining_low_window_ps'] > 0 for r in rows)
    return dict(request_taper_component_hypothesis_passed=passed,
        all_four_native_points_present=True, counter_shared_wire_rc_qualified=False,
        whole_clock_rc_qualified=False, all_pvt_covered=False, electrical_qualification_passed=False, qualified_phy=False)


def run(out):
    if (out / 'state.json').exists():
        raise ValueError('Retain previous or partial REQUEST taper experiment')
    manifest = bound(out)
    identity = manifest['identity']
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if (out / 'state.json').exists():
            raise ValueError('Retain previous or partial REQUEST taper experiment')
        atomic(out / 'state.json', dict(status='running', qualified_phy=False))
        rows = []
        try:
            for task in manifest['tasks']:
                folder = out / task['id']
                result = error = None
                try:
                    with lease(ROOT, priority=1, label=CONTEXT + '_' + task['id']):
                        bound(out, full=False)
                        process = subprocess.run([sys.executable, str(ROOT / 'scripts/run_native_binary_v2.py'),
                            '-l', str(folder / 'ngspice.log'), str(folder / 'bench.cir')], capture_output=True, text=True)
                    (folder / 'console.log').write_text(process.stdout + process.stderr)
                    process.check_returncode()
                    result = measure(folder, identity, task['spec'])
                except Exception as exception:
                    error = str(exception)
                row = dict(task=task, result=result, error=error,
                    files={p.name: sha(p) for p in folder.iterdir() if p.is_file()})
                atomic(folder / 'summary.json', row)
                rows.append(row)
            bound(out)
            atomic(out / 'summary.json', dict(rows=rows, comparison=assess(rows), scope=SCOPE, qualified_phy=False))
            atomic(out / 'state.json', dict(status='complete', cases=4,
                errors=sum(r['error'] is not None for r in rows), qualified_phy=False))
        except Exception as exception:
            atomic(out / 'state.json', dict(status='failed', error=str(exception), qualified_phy=False))
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    prepare_parser = sub.add_parser('prepare')
    prepare_parser.add_argument('parent', type=Path)
    prepare_parser.add_argument('drivers', type=Path)
    prepare_parser.add_argument('diagnosis', type=Path)
    run_parser = sub.add_parser('run')
    run_parser.add_argument('artifact', type=Path)
    args = parser.parse_args()
    if args.action == 'prepare':
        print(prepare(args.parent.resolve(), args.drivers.resolve(), args.diagnosis.resolve()), flush=True)
    else:
        run(args.artifact.resolve())
