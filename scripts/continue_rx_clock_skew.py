#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Host-side aperture-owner handoff; scientific children use pinned Apptainer."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import subprocess
import time

import probe_rx_clock_skew as probe
from continue_receiver_spec_rc import owner
from dll_campaign import atomic
from receiver_static_diagnosis import capture_manifest

ROOT = Path(__file__).resolve().parents[1]
NAMESPACE = 'rx_clock_skew_followup'
sha = probe.sha


def ready(capture):
    state = json.loads((capture / 'state.json').read_text())
    return state.get('status') == 'complete' and state.get('passed') is True and (capture / 'table.json').exists()


def same_owner(expected, live):
    return (live.get('MainPID', '0') != '0' and live.get('ActiveState') == 'active'
            and all(live.get(k) == expected.get(k) for k in ('MainPID', 'InvocationID', 'ExecStart')))


def invoke(out, args, label):
    # systemctl belongs on the host. PDK paths, simulator provenance and
    # scientific source roots belong in the existing pinned container.
    log = out / (label + '.log')
    with log.open('x') as handle:
        result = subprocess.run([str(ROOT / 'scripts/env.sh'), '--ngspice', '/usr/bin/python3',
            'scripts/probe_rx_clock_skew.py', *args], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT)
    result.check_returncode()
    return log.read_text()


def prepared_child(output):
    value = Path(output.strip().splitlines()[-1])
    base = Path('/work/OpenLVDS')
    if '..' in value.parts or not value.is_relative_to(base / 'build/diagnostics' / probe.NAMESPACE):
        raise ValueError('Unexpected prepared receive-clock artifact')
    return ROOT / value.relative_to(base)


def prepare(parent, capture, unit):
    if (not parent.is_relative_to(ROOT / 'build/diagnostics' / probe.coupled.NAMESPACE)
            or not capture.is_relative_to(ROOT / 'build/characterization/rx_aperture')):
        raise ValueError('Require the restored native link and original aperture context')
    live = owner(unit)
    if (not same_owner(live, live) or not live.get('InvocationID')
            or 'scripts/continue_rx_aperture_fair.py ' + str(capture.relative_to(ROOT)) not in live.get('ExecStart', '')):
        raise ValueError('Require the exact live aperture producer')
    paths = [parent / 'manifest.json', capture / 'manifest.json', ROOT / 'requirements.json']
    paths += [ROOT / 'scripts' / n for n in ('continue_rx_clock_skew.py', 'probe_rx_clock_skew.py', 'rx_clock_skew.py',
        'continue_receiver_spec_rc.py', 'continue_rx_aperture_fair.py', 'rx_aperture_evidence.py', 'extend_rx_aperture.py', 'env.sh')]
    identity = dict(parent=str(parent.relative_to(ROOT)), aperture=str(capture.relative_to(ROOT)), unit=unit, owner=live,
        inputs={str(p.relative_to(ROOT)): sha(p) for p in paths}, no_outer_lease=True)
    out = ROOT / 'build/diagnostics' / NAMESPACE / hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True, exist_ok=True)
    capture_manifest(out / 'manifest.json', dict(identity=identity, qualified_phy=False))
    return out


def run(out):
    if not out.is_relative_to(ROOT / 'build/diagnostics' / NAMESPACE):
        raise ValueError('Require the prepared receive-clock handoff')
    m = json.loads((out / 'manifest.json').read_text()); i = m['identity']; stamp = sha(out / 'manifest.json')
    capture = ROOT / i['aperture']
    def unchanged():
        if (out.name != hashlib.sha256(json.dumps(i, sort_keys=True).encode()).hexdigest()[:16]
                or sha(out / 'manifest.json') != stamp or any(sha(ROOT / n) != h for n, h in i['inputs'].items())):
            raise ValueError('Receive-clock handoff context changed')
    with (out / '.execution.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB); unchanged()
        if (out / 'state.json').exists():
            raise ValueError('Prior receive-clock handoff retained; no retry')
        while not ready(capture):
            unchanged()
            state = json.loads((capture / 'state.json').read_text())
            if state.get('status', '').startswith('held') or state.get('status') == 'complete':
                atomic(out / 'state.json', dict(status='held_aperture_not_passed', qualified_phy=False))
                return
            try:
                live = owner(i['unit'])
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
                # Observation failure is not producer termination. Retry the
                # same read-only handle without restarting any producer.
                atomic(out / 'state.json', dict(status='waiting_for_owner_observation', error=str(error), qualified_phy=False))
                time.sleep(20); continue
            if not same_owner(i['owner'], live):
                if ready(capture): break  # Normal terminal receipt/owner race.
                atomic(out / 'state.json', dict(status='held_aperture_owner_changed_without_complete_result', qualified_phy=False))
                return
            atomic(out / 'state.json', dict(status='waiting_for_complete_aperture', qualified_phy=False))
            time.sleep(20)
        unchanged()
        atomic(out / 'state.json', dict(status='independently_admitting_aperture', qualified_phy=False))
        try:
            child = prepared_child(invoke(out, ['prepare', i['parent'], '--aperture', i['aperture']], 'prepare'))
            unchanged()
            atomic(out / 'state.json', dict(status='screening_receive_clock_skew', artifact=str(child.relative_to(ROOT)), qualified_phy=False))
            invoke(out, ['run', str(child.relative_to(ROOT))], 'run'); unchanged()
            invoke(out, ['verify', str(child.relative_to(ROOT))], 'verify'); unchanged()
            report = json.loads((child / 'summary.json').read_text())
            capture_manifest(out / 'summary.json', dict(artifact=str(child.relative_to(ROOT)),
                report_sha256=sha(child / 'summary.json'), clock_skew_source_passed=report['clock_skew_source_passed'],
                ranked_survivors=report['ranked_survivors'], qualified_phy=False))
            atomic(out / 'state.json', dict(status='clock_skew_verified', artifact=str(child.relative_to(ROOT)),
                passed=report['clock_skew_source_passed'], qualified_phy=False))
        except Exception as error:
            atomic(out / 'state.json', dict(status='held_for_diagnosis', error=str(error), qualified_phy=False))
            raise


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('action', choices=['prepare', 'run'])
    p.add_argument('artifact', type=Path); p.add_argument('--aperture', type=Path); p.add_argument('--producer-unit')
    a = p.parse_args()
    if a.action == 'prepare':
        if not a.aperture or not a.producer_unit: p.error('--aperture and --producer-unit required')
        print(prepare(a.artifact.resolve(), a.aperture.resolve(), a.producer_unit), flush=True)
    else: run(a.artifact.resolve())
