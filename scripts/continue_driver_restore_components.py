#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run prepared driver component checks after their matched native owner succeeds."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
CASES = {'source_control', 'restore_64_24'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native_complete(comparison):
    summary = json.loads((comparison / 'summary.json').read_text())
    results = summary.get('results', [])
    if (summary.get('diagnostic_complete') is not True or summary.get('native_driver_only') is not True or
            summary.get('manifest_sha256') != digest(comparison / 'manifest.json') or
            len(results) != 2 or {r['task'] for r in results} != CASES):
        raise ValueError('Matched native driver evidence is incomplete or belongs to another manifest')
    for result in results:
        child = json.loads((comparison / result['task'] / 'summary.json').read_text())
        if child != result or child.get('diagnostic_complete') is not True:
            raise ValueError('Matched native driver child differs from aggregate evidence')
    return summary


def run(artifact, unit, jobs=2):
    if not artifact.is_relative_to(ROOT / 'build/diagnostics/driver_components') or type(jobs) is not int or jobs not in range(1, 7):
        raise ValueError('Use a prepared driver component campaign and the existing six-slot budget')
    manifest = artifact / 'manifest.json'
    component = json.loads(manifest.read_text())['identity']
    comparison = (ROOT / component['comparison']).resolve()
    if not comparison.is_relative_to(ROOT / 'build/diagnostics/driver_native_restore'):
        raise ValueError('Use an isolated matched native driver comparison')
    inputs = dict(component['inputs'])
    comparison_manifest = comparison / 'manifest.json'
    if inputs.get(str(comparison_manifest.relative_to(ROOT))) != digest(comparison_manifest):
        raise ValueError('Driver components do not capture this matched native comparison')
    native_identity = json.loads(comparison_manifest.read_text())['identity']
    if native_identity['layouts'].get(component['variant']) != component['layout']:
        raise ValueError('Driver components select another physical variant')
    inputs[str(manifest.relative_to(ROOT))] = digest(manifest)
    for name, stamp in component['code'].items():
        inputs['scripts/' + name] = stamp
    inputs['scripts/' + Path(__file__).name] = digest(Path(__file__))
    inputs['scripts/env.sh'] = digest(ROOT / 'scripts/env.sh')
    identity = dict(artifact=str(artifact.relative_to(ROOT)), comparison=str(comparison.relative_to(ROOT)),
                    producer_unit=unit, jobs=jobs, inputs=inputs)
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    folder = artifact / 'followup' / fingerprint
    folder.mkdir(parents=True, exist_ok=True)
    def save(status, **fields):
        temp = folder / 'state.json.tmp'
        temp.write_text(json.dumps(dict(status=status, qualified_phy=False, **fields), indent=2) + '\n')
        temp.replace(folder / 'state.json')
    def unchanged():
        if any(digest(ROOT / name) != stamp for name, stamp in inputs.items()):
            raise ValueError('Driver component follow-up inputs or producers changed')
    with (artifact / '.followup.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        capture = folder / 'manifest.json'
        if capture.exists() and json.loads(capture.read_text()) != identity:
            raise ValueError('Driver follow-up identity changed')
        capture.write_text(json.dumps(identity, indent=2) + '\n')
        (folder / 'producer.py').write_bytes(Path(__file__).read_bytes())
        try:
            while True:
                unchanged()
                try:
                    result = subprocess.run(['systemctl', '--user', 'show', unit, '-p', 'ActiveState',
                                             '-p', 'Result', '-p', 'ExecMainStatus'],
                                            check=True, capture_output=True, text=True)
                except (OSError, subprocess.CalledProcessError):
                    save('retrying_native_owner_observation');time.sleep(10);continue
                owner = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
                if owner.get('ActiveState') in ['active', 'activating', 'deactivating']:
                    save('waiting_for_matched_native_driver', owner=owner);time.sleep(10);continue
                if (owner.get('ActiveState') != 'inactive' or owner.get('Result') != 'success' or
                        owner.get('ExecMainStatus') != '0'):
                    raise ValueError('Matched native driver owner did not finish successfully')
                native_complete(comparison)
                break
            unchanged();save('running_driver_components')
            with (folder / 'components.log').open('w') as output:
                subprocess.run([str(ROOT / 'scripts/env.sh'), '--ngspice', 'python3',
                                'scripts/qualify_driver_restore_components.py', 'run',
                                str(artifact.relative_to(ROOT)), '--jobs', str(jobs)],
                               cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
            unchanged()
            report = artifact / 'summary.json'
            summary = json.loads(report.read_text())
            if summary.get('manifest_sha256') != digest(manifest) or summary.get('passed') is not True:
                raise ValueError('Driver component campaign failed or belongs to another manifest')
            save('components_passed', report=str(report.relative_to(ROOT)), report_sha256=digest(report),
                 next_gate='Selected analog integration, headroom/power, RC certificates and full-PHY link/release qualification')
        except Exception as error:
            save('held_for_diagnosis', error=str(error));raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('artifact', type=Path)
    parser.add_argument('--producer-unit', required=True)
    parser.add_argument('--jobs', type=int, choices=range(1, 7), default=2)
    args = parser.parse_args()
    run(args.artifact.resolve(), args.producer_unit, args.jobs)
