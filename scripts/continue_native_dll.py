#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Continue a standalone native screen through measured model and native gates."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

from advance_ota_candidate import cached_model, tool_command
from dll_campaign import atomic
from dll_native_evidence import verify as verify_native
from qualify_dll_candidate import CODE, validate
from stability_evidence import PRODUCERS, verified

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def screen_ready(receipt, qualification, active):
    status = receipt['status']
    if status == 'held_for_diagnosis':
        raise ValueError('Native handoff held: ' + receipt.get('error', 'inspect handoff'))
    if status == 'native_screen_passed':
        if receipt['qualification'] != qualification:
            raise ValueError('Native handoff selected another qualification')
        return not active
    if not active:
        raise ValueError('Native handoff ended before passing its screen')
    return False


def progression(qualification, model, execute, check_native):
    """Never expand a failed model or proceed past failed native evidence."""
    report = model(False)
    execute('native_full', 'qualify_dll_candidate.py', [
        'run', str(qualification.relative_to(ROOT)), '--stage', 'full',
        '--jobs', '3', '--stability', str(report.relative_to(ROOT))])
    check_native(qualification)
    return model(True)


def run(qualification, handoff, producer_unit, after_screen=False):
    inside = ROOT == Path('/work/OpenLVDS')
    if inside != after_screen:
        raise ValueError('Start the waiting job on the host; evidence runs in the pinned container')
    if not qualification.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Use a prepared native qualification')
    if not handoff.is_relative_to(ROOT/'build/diagnostics/dll_layout'):
        raise ValueError('Use a captured physical native handoff')
    manifest = json.loads((qualification/'manifest.json').read_text())
    if not manifest['identity']['variant'].startswith('ota_'):
        raise ValueError('Expected an OTA native qualification')
    folder = qualification/'continuation'
    folder.mkdir(exist_ok=True)
    names = set(CODE) | PRODUCERS | {
        Path(__file__).name, 'advance_ota_candidate.py', 'dll_native_evidence.py'}
    identity = dict(qualification_manifest_sha256=digest(qualification/'manifest.json'),
                    handoff=str(handoff.relative_to(ROOT)), producer_unit=producer_unit,
                    code={name:digest(ROOT/'scripts'/name) for name in sorted(names)})
    initial = json.loads(handoff.read_text())['identity']
    identity['handoff_identity'] = initial
    captured = folder/'manifest.json'

    def unchanged():
        if digest(qualification/'manifest.json') != identity['qualification_manifest_sha256']:
            raise ValueError('Native qualification manifest changed')
        if json.loads(handoff.read_text())['identity'] != initial:
            raise ValueError('Native handoff identity changed')
        if any(digest(ROOT/'scripts'/name) != value for name,value in identity['code'].items()):
            raise ValueError('Native continuation producer changed')
        if inside:
            validate(qualification, manifest)

    def save(status, **fields):
        atomic(folder/'state.json', dict(status=status, qualified_phy=False,
                                       qualification=str(qualification.relative_to(ROOT)), **fields))

    def execute(label, script, arguments):
        unchanged()
        save('running_' + label)
        log = folder/(label+'.log')
        with log.open('w') as output:
            result = subprocess.run(tool_command(script, arguments), cwd=ROOT,
                                    stdout=output, stderr=subprocess.STDOUT)
        result.check_returncode()
        unchanged()
        return log

    def model(all_pvt):
        unchanged()
        inputs = manifest['identity']['full_models']['inputs']
        corners = ('ss_0', 'tt_25', 'ff_0')
        if all_pvt:
            req = json.loads((qualification/'requirements.json').read_text())
            corners = tuple(f'{p}_{t}' for p in req['process_corners'] for t in req['temperatures_c'])
        label = 'stability_all_pvt' if all_pvt else 'stability_screen'
        report = cached_model(qualification/label, inputs, corners)
        if report is None:
            execute(label, 'measure_dll_stability.py', [str(qualification.relative_to(ROOT))] +
                    (['--all-pvt'] if all_pvt else []))
            report = cached_model(qualification/label, inputs, corners)
        if report is None:
            raise ValueError('Measured model produced no verified report')
        verified(report, inputs, corners)
        return report

    lease = '.native_model_progression.lock' if inside else '.native_progression.lock'
    with (qualification/lease).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if captured.exists():
            if json.loads(captured.read_text()) != identity:
                raise ValueError('Native continuation context changed')
        else:
            atomic(captured, identity)
        try:
            while not after_screen:
                unchanged()
                receipt = json.loads(handoff.read_text())
                result = subprocess.run(['systemctl','--user','show',producer_unit,
                                         '-p','ActiveState','--value'],
                                        capture_output=True,text=True,check=True)
                active = result.stdout.strip() in ['active','activating']
                if screen_ready(receipt, str(qualification.relative_to(ROOT)), active):
                    break
                save('waiting_for_native_screen', observed=receipt['status'])
                time.sleep(10)
            if not inside:
                # Service discovery belongs on the host; simulator provenance,
                # cached-model verification and all evidence work belong in the
                # same pinned container that produced the scientific fixtures.
                execute('pinned_progression', Path(__file__).name, [
                    str(qualification.relative_to(ROOT)), str(handoff.relative_to(ROOT)),
                    '--producer-unit', producer_unit, '--after-screen'])
                return
            receipt = json.loads(handoff.read_text())
            if not screen_ready(receipt, str(qualification.relative_to(ROOT)), False):
                raise ValueError('Native screening has not passed')
            # Recheck cached native screening after its owner exits. The native
            # runner validates and remeasures the captured waveforms itself.
            execute('screen_recheck','qualify_dll_candidate.py',[
                'run',str(qualification.relative_to(ROOT)),'--stage','screen','--jobs','3'])
            report = progression(qualification, model, execute, verify_native)
            unchanged()
            save('native_and_all_pvt_model_complete', report=str(report.relative_to(ROOT)),
                 next_gate='Operating points, recovery, readiness, aperture, RC and full link signoff')
        except Exception as error:
            save('held_for_diagnosis', error=str(error))
            raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('qualification', type=Path)
    parser.add_argument('handoff', type=Path)
    parser.add_argument('--producer-unit', required=True)
    parser.add_argument('--after-screen', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    run(args.qualification.resolve(), args.handoff.resolve(), args.producer_unit, args.after_screen)
