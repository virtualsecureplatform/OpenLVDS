#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Resume the immutable DLL campaign, prioritizing OTA/CP architecture comparison."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from dll_campaign import BASE, ROOT, atomic, digest, validate


def priority(task):
    spec = task['spec']
    kind = spec['kind']
    if kind in ['phase', 'logic']:
        return (0, 0, task['id'])
    if task['id'] == 'cp_b2_c2_loop_ss_0':
        return (1, -1, 0)
    if kind == 'loop' and spec['architecture'] == 'averaged_pfd_ota':
        variants = ['ota_w4_c8', 'ota_w8_c8', 'ota_w4_c4', 'ota_w8_c4']
        pvt = [('ss', 0), ('tt', 25), ('ff', 0)]
        return (1, variants.index(spec['variant']), pvt.index((spec['corner'], spec['temp'])))
    if kind == 'follower':
        return (2, 0 if spec['load'] == 'loaded' else 1, task['id'])
    return (3, 0, task['id'])


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, TypeError):
        return False


def result_status(root, manifest, task):
    """Completed traces must still match their captured task and waveform hashes."""
    validate(root, manifest, task)
    path = root / task['id'] / 'summary.json'
    result = json.loads(path.read_text())
    if result.get('input_files') != task['files'] or result.get('task') != task['id']:
        raise ValueError('Stale DLL task result')
    if result.get('waveform_sha256'):
        if digest((path.parent / 'bench.cir.prn').read_bytes()) != result['waveform_sha256']:
            raise ValueError('Changed DLL waveform')
    elif result.get('passed'):
        raise ValueError('Passed DLL result lacks a complete waveform')
    return 'passed' if result.get('passed') else 'failed'


def run(root, jobs, host=False):
    with (BASE / '.supervisor.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = json.loads((root / 'manifest.json').read_text())
        tasks = {t['id']: t for t in sorted(manifest['tasks'], key=priority)}
        state = json.loads((root / 'state.json').read_text())
        state.update(status='running', supervisor_pid=os.getpid(), max_jobs=jobs,
                     scheduling_policy='compare_ota_before_remaining_pump_matrix',
                     pid_domain='host' if host else 'container')
        active = {}
        for key, record in state['tasks'].items():
            if (root / key / 'summary.json').exists():
                record.update(status=result_status(root, manifest, tasks[key]))
            elif record['status'] == 'running':
                if alive(record.get('pid')):
                    active[key] = None
                else:
                    record.update(status='failed', error='Worker exited without result')
        while True:
            for key, proc in list(active.items()):
                if proc is not None and proc.poll() is None:
                    continue
                path = root / key / 'summary.json'
                if proc is None and not path.exists() and alive(state['tasks'][key].get('pid')):
                    continue
                if path.exists():
                    state['tasks'][key].update(status=result_status(root, manifest, tasks[key]), result=str(path))
                else:
                    state['tasks'][key].update(status='failed', error='Worker exited without result')
                active.pop(key)
            for key, task in tasks.items():
                record = state['tasks'][key]
                if record['status'] != 'pending':
                    continue
                needed = [state['tasks'][n]['status'] for n in task['needs']]
                if any(s in ['failed', 'skipped'] for s in needed):
                    record.update(status='skipped', error='Prerequisite failed')
                    continue
                if any(s != 'passed' for s in needed) or len(active) >= jobs:
                    continue
                validate(root, manifest, task)
                with (root / key / 'worker.log').open('a') as log:
                    command = [sys.executable, str(Path(__file__).with_name('dll_campaign.py')),
                               'worker', str(root), '--task', key]
                    if host:
                        command = [str(ROOT / 'scripts/env.sh'), '--ngspice', 'python3',
                                   'scripts/dll_campaign.py', 'worker', str(root.relative_to(ROOT)), '--task', key]
                    proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, cwd=ROOT)
                active[key] = proc
                record.update(status='running', pid=proc.pid, started_unix=time.time())
            state['updated_unix'] = time.time()
            atomic(root / 'state.json', state)
            if not active and not any(r['status'] == 'pending' for r in state['tasks'].values()):
                break
            time.sleep(2)
        state['status'] = 'completed' if all(r['status'] == 'passed' for r in state['tasks'].values()) else 'completed_with_failures'
        atomic(root / 'state.json', state)
        return 0 if state['status'] == 'completed' else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('campaign', type=Path)
    p.add_argument('--jobs', type=int, choices=range(1, 7), default=4)
    p.add_argument('--host', action='store_true', help='Host PID accounting; launch each new worker in Apptainer')
    a = p.parse_args()
    return run(a.campaign.resolve(), a.jobs, a.host)


if __name__ == '__main__':
    raise SystemExit(main())
