#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Host service watchdog for the DLL campaign and its dependent coordinators."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import shutil
from run_dll_comparison import alive, process_identity
from dll_campaign import atomic

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = 'build/diagnostics/dll_architecture/6d99d42cf3eb5d31'


def group_alive(pgid):
    if pgid is None:
        return False
    for path in Path('/proc').glob('[0-9]*/stat'):
        try:
            tail = path.read_text().rpartition(')')[2].split()
            if tail[0] != 'Z' and int(tail[2]) == pgid:
                return True
        except (OSError, ValueError, IndexError):
            pass
    return False


def archive_unfinished(root):
    for raw in root.rglob('bench.raw'):
        if 'interrupted' in raw.relative_to(root).parts:
            continue
        if (raw.parent/'summary.json').exists():
            continue
        archive = raw.parent/'interrupted'/str(time.time_ns())
        archive.mkdir(parents=True)
        for path in list(raw.parent.iterdir()):
            if path.is_file() and path.name not in ['bench.cir', 'library.spice']:
                shutil.move(str(path), str(archive/path.name))
        atomic(archive/'reason.json', dict(reason='Coordinator died; incomplete evidence preserved'))


def snapshot(state, pid, heartbeat_age):
    status = state.get('status', 'unknown')
    if status == 'running' and not alive(pid, state.get('supervisor_identity')):
        return 'interrupted'
    if status == 'running' and heartbeat_age > 60:
        return 'unresponsive'
    return status


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign', default=DEFAULT)
    p.add_argument('--jobs', type=int, choices=range(1,7), default=6)
    a = p.parse_args()
    root = ROOT/a.campaign
    logs = ROOT/'build/diagnostics/resident_jobs'
    logs.mkdir(parents=True, exist_ok=True)
    with (logs/'.watchdog-v2.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        jobs = {
            'architecture': (root/'state.json', [sys.executable, 'scripts/run_dll_comparison.py', str(root), '--jobs', str(a.jobs), '--host']),
            'rx_aperture': (ROOT/'build/characterization/rx_aperture/e9ca7d2f2ae6d61b/state.json', ['scripts/env.sh', '--ngspice', 'python3', 'scripts/characterize_rx_aperture.py', 'run', 'build/characterization/rx_aperture/e9ca7d2f2ae6d61b', '--jobs', '4']),
            'qualify_cp': (ROOT/'build/diagnostics/dll_qualification/a62222a02a048ab0/state.json', ['scripts/env.sh', '--ngspice', 'python3', 'scripts/qualify_dll_candidate.py', 'run', 'build/diagnostics/dll_qualification/a62222a02a048ab0', '--jobs', '4']),
        }
        records = {}
        saved = logs/'watchdog.json'
        previous = json.loads(saved.read_text()).get('jobs', {}) if saved.exists() else {}
        for label in jobs:
            record = previous.get(label, {})
            pidfile = logs/(label+'.pid')
            if not record and pidfile.exists():
                pid = int(pidfile.read_text())
                if alive(pid):
                    record = dict(pid=pid, identity=process_identity(pid), pgid=os.getpgid(pid), adopted=True)
            records[label] = record
        children = {}
        while True:
            config_path=logs/'config.json'
            config=json.loads(config_path.read_text()) if config_path.exists() else {}
            if config.get('ota_qualification'):
                artifact=Path(config['ota_qualification'])
                if artifact.is_absolute() or '..' in artifact.parts:
                    raise ValueError('OTA artifact must be relative to OpenLVDS')
                jobs['qualify_ota']=(ROOT/artifact/'state.json', ['scripts/env.sh','--ngspice','python3',
                    'scripts/qualify_dll_candidate.py','run',str(artifact),'--jobs','6'])
                records.setdefault('qualify_ota',{})
            for label, (statefile, command) in jobs.items():
                state = json.loads(statefile.read_text()) if statefile.exists() else {}
                record = records[label]
                if label in config.get('disabled',[]):
                    record['state']='deferred_by_configuration'
                    continue
                proc = children.get(label)
                if proc is not None:
                    proc.poll()  # Reap exits so a zombie cannot appear live.
                if alive(record.get('pid'), record.get('identity')):
                    record['state'] = snapshot(state, record['pid'], time.time()-statefile.stat().st_mtime) if label == 'architecture' else state.get('status')
                    continue
                # Only one campaign may own live workers. Do not leave
                # dependent coordinators racing for a dead manager's lease.
                predecessors = ['architecture'] if label == 'rx_aperture' else ['architecture', 'rx_aperture'] if label == 'qualify_cp' else []
                if any(json.loads(jobs[key][0].read_text()).get('status') not in
                       ['completed', 'completed_with_failures', 'complete', 'rejected_by_architecture_screen'] for key in predecessors):
                    record['state'] = 'waiting_for_previous_campaign'
                    continue
                if state.get('status') in ['completed', 'completed_with_failures', 'complete', 'rejected_by_architecture_screen','screen_passed']:
                    record['state'] = state['status']
                    continue
                if label != 'architecture' and group_alive(record.get('pgid')):
                    record['state'] = 'orphan_workers_finishing'
                    continue
                # Back off crashes, including code/provenance validation failures.
                if time.time()-record.get('last_launch', 0) < 60:
                    record['state'] = 'restart_backoff'
                    continue
                env = os.environ.copy()
                env['OPENLVDS_SPICE'] = 'ngspice'
                if label != 'architecture':
                    archive_unfinished(statefile.parent)
                with (logs/(label+'.log')).open('ab') as log:
                    proc = subprocess.Popen(command, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                children[label] = proc
                record.update(pid=proc.pid, identity=process_identity(proc.pid), last_launch=time.time(),
                              pgid=proc.pid, launches=record.get('launches', 0)+1, state='starting')
                (logs/(label+'.pid')).write_text(str(proc.pid)+'\n')
            atomic(saved, dict(updated_unix=time.time(), pid=os.getpid(), jobs=records))
            time.sleep(5)


if __name__ == '__main__':
    main()
