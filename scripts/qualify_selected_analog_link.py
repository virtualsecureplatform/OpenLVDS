#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Gate a matched native driver comparison on the selected receiver's loaded link."""
import argparse
import fcntl
import json
import math
from pathlib import Path

import probe_native_driver_restore as native
import qualify_driver_restore_components as driver
import qualify_receiver_components as receiver
import qualify_scaled_receiver as selected
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name


def complete_components(folder, kind):
    """Check every report before invoking any producer capable of simulation."""
    expected = 'driver_components' if kind == 'driver' else 'receiver_components'
    if not folder.is_relative_to(ROOT / 'build/diagnostics' / expected):
        raise ValueError('Use the selected component campaign')
    manifest = json.loads((folder / 'manifest.json').read_text())
    requirements = json.loads((ROOT / 'requirements.json').read_text())
    (driver if kind == 'driver' else receiver).check_coverage(manifest['tasks'], requirements)
    count = 30 if kind == 'driver' else 60
    if len(manifest['tasks']) != count or any(not (folder / t['id'] / 'summary.json').is_file() for t in manifest['tasks']):
        raise ValueError('Complete all selected ' + kind + ' component cases first')
    report = json.loads((folder / 'summary.json').read_text())
    if (report.get('passed') is not True or report.get('required') != count or
        report.get('manifest_sha256') != native.digest(folder / 'manifest.json')):
        raise ValueError('Selected component campaign failed or changed')
    if any(json.loads((folder / t['id'] / 'summary.json').read_text()).get('passed') is not True for t in manifest['tasks']):
        raise ValueError('Selected component child failed')
    return manifest


def prepare(driver_components, receiver_components, link):
    d = complete_components(driver_components, 'driver')
    r = complete_components(receiver_components, 'receiver')
    if d['identity']['variant'] != 'restore_64_24':
        raise ValueError('Expected the selected P64/N24 driver')
    if not link.is_relative_to(ROOT / 'build/diagnostics/receiver_candidate_link') or not (link / 'summary.json').is_file():
        raise ValueError('Complete the selected receiver reference-link diagnostic first')
    capture = json.loads((link / 'manifest.json').read_text())
    if (capture['identity']['replay'] != r['identity']['replay'] or
        capture['identity']['receiver'] != r['identity']['layout']):
        raise ValueError('Reference link and components select different receivers')
    selected.selected_replay(ROOT / r['identity']['replay'])
    # Both suites are complete. These calls remeasure cached traces and verify
    # all original fixtures/model/runtime proofs; no missing case can launch.
    with (driver_components / '.cached_verification.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        driver.run(driver_components, 1)
        complete_components(driver_components, 'driver')
    selected.run('run-components', receiver_components, jobs=1)
    complete_components(receiver_components, 'receiver')
    selected.run('run-link', link)
    link_report = json.loads((link / 'summary.json').read_text())
    if link_report.get('manifest_sha256') != native.digest(link / 'manifest.json'):
        raise ValueError('Receiver reference link manifest binding changed')
    # A failed receiver-only reference remains useful: the old driver may be
    # its limiting component. The new matched comparison measures both driver
    # alternatives with the same now-qualified receiver and original fixture.
    comparison = ROOT / d['identity']['comparison']
    layouts = json.loads((comparison / 'manifest.json').read_text())['identity']['layouts']
    if layouts['restore_64_24'] != d['identity']['layout']:
        raise ValueError('Driver components select another physical candidate')
    proofs = {str(p.relative_to(ROOT)): native.digest(p) for p in
              [driver_components / 'manifest.json', driver_components / 'summary.json',
               receiver_components / 'manifest.json', receiver_components / 'summary.json',
               link / 'manifest.json', link / 'summary.json', ROOT / 'requirements.json', ROOT / 'scripts' / NAME]}
    for folder, manifest in [(driver_components, d), (receiver_components, r)]:
        for name, sha in manifest['identity']['code'].items(): proofs['scripts/' + name] = sha
        proofs.update(manifest['identity']['inputs'])
        for task in manifest['tasks']:
            for name in ['source.spice', 'bench.cir', 'bench.cir.prn', 'summary.json']:
                path = folder / task['id'] / name
                proofs[str(path.relative_to(ROOT))] = native.digest(path)
    out = native.prepare(link, ROOT / layouts['source_control'], ROOT / layouts['restore_64_24'])
    if any(native.digest(ROOT / name) != sha for name, sha in proofs.items()):
        raise ValueError('Selected analog admission changed during preparation')
    capture_manifest(out / 'selected_analog_admission.json', dict(inputs=proofs,
        comparison_manifest_sha256=native.digest(out / 'manifest.json'),
        driver_components=str(driver_components.relative_to(ROOT)), receiver_components=str(receiver_components.relative_to(ROOT)),
        receiver_reference_link_passed=link_report['passed'], qualified_phy=False,
        scope='Matched exact-RC driver alternatives with the selected qualified receiver; original full loaded ideal-phase diagnostic, not a full PHY release'))
    return out


def run(folder):
    if not folder.is_relative_to(ROOT / 'build/diagnostics/driver_native_restore'):
        raise ValueError('Use a prepared selected-analog matched link')
    admission_path = folder / 'selected_analog_admission.json'
    admission = json.loads(admission_path.read_text()); stamp = native.digest(admission_path)
    def unchanged():
        if (native.digest(admission_path) != stamp or
            native.digest(folder / 'manifest.json') != admission['comparison_manifest_sha256'] or
            any(native.digest(ROOT / name) != sha for name, sha in admission['inputs'].items())):
            raise ValueError('Selected analog admission changed')
    with (folder / '.selected_analog.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        unchanged()
        for case in native.CASES:
            child = folder / case
            if not (child / 'summary.json').exists() and any((child / n).exists() for n in ['bench.raw', 'bench.cir.prn', 'ngspice.log']):
                raise ValueError('Partial combined link evidence retained; use a fresh retry context')
        native.run(folder)
        unchanged()
        report = json.loads((folder / 'summary.json').read_text())
        if (report.get('diagnostic_complete') is not True or
            report.get('manifest_sha256') != native.digest(folder / 'manifest.json') or
            {r['task'] for r in report['results']} != set(native.CASES) or len(report['results']) != 2):
            raise ValueError('Incomplete matched selected-analog link')
        candidate = next(r for r in report['results'] if r['task'] == 'restore_64_24')
        threshold = json.loads((ROOT / 'requirements.json').read_text())['rx_threshold_v']
        eyes = candidate['clock_centers']
        sensitivity = all(math.isfinite(eyes[name]['min_center_abs_v']) and
            eyes[name]['min_center_abs_v'] >= threshold and eyes[name]['below_rx_threshold'] == 0
            for name in ['tx_clock', 'rx_clock'])
        decoded = candidate['decoder']['passed'] is True and candidate['decoder'].get('sampling_margin_passed') is True
        capture_manifest(folder / 'selected_analog_result.json', dict(qualified_phy=False, diagnostic_complete=True,
            selected_link_passed=decoded and sensitivity, decoder_passed=decoded,
            clock_center_sensitivity_passed=sensitivity, admission_sha256=stamp,
            report_sha256=native.digest(folder / 'summary.json'),
            scope='Selected analog pair in one original full-RC ideal-phase diagnostic; full selected DLL/digital PHY qualification remains'))
    return folder / 'selected_analog_result.json'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('prepare'); p.add_argument('driver', type=Path); p.add_argument('receiver', type=Path); p.add_argument('link', type=Path)
    p = sub.add_parser('run'); p.add_argument('artifact', type=Path)
    args = parser.parse_args()
    print(prepare(args.driver.resolve(), args.receiver.resolve(), args.link.resolve()) if args.action == 'prepare' else run(args.artifact.resolve()), flush=True)
