#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Freeze one legacy coordinator, drain its children, retain a separate receipt.

Never signal the service cgroup or edit a bound scientific producer/artifact.
Run on the host: /proc PIDs and dispatcher ticket PIDs must share a namespace.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import time

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {'continue_dll_analog_expansion.py': 'build/diagnostics/dll_analog_frontend_expansion',
           'extend_rx_aperture.py': 'build/characterization/rx_aperture_extended'}


def proc(pid):
    try:
        base = Path('/proc') / str(pid)
        fields = (base / 'stat').read_text().rpartition(')')[2].split()
        return dict(pid=pid, ppid=int(fields[1]), state=fields[0], start=fields[19],
                    uid=base.stat().st_uid,
                    argv=(base / 'cmdline').read_bytes().decode().rstrip('\0').split('\0'))
    except (FileNotFoundError, ProcessLookupError):
        return None


def descendants(pid):
    records = {int(p.name): proc(int(p.name)) for p in Path('/proc').glob('[0-9]*')}
    found = {pid}
    while True:
        extra = {p for p, r in records.items() if r and r['ppid'] in found}
        if extra <= found:
            return [r for p, r in records.items() if p in found - {pid} and r and r['state'] != 'Z']
        found |= extra


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n'); tmp.replace(path)


def begin(pid, artifact, script):
    artifact = artifact.resolve()
    if script not in ALLOWED or not artifact.is_relative_to(ROOT / ALLOWED[script]):
        raise ValueError('Require an explicitly allowed legacy campaign')
    original = proc(pid)
    if (not original or original['uid'] != os.getuid()
            or not Path(original['argv'][0]).name.startswith('python')
            or script not in [Path(a).name for a in original['argv'][1:]]):
        raise ValueError('Coordinator identity mismatch')
    # Bind to its actual open execution lock, even for a parent followup whose
    # argv names a different upstream artifact. Checking argv alone is unsafe.
    lock_inode = (artifact / '.execution.lock').stat().st_ino
    if not any(p.stat().st_ino == lock_inode for p in (Path('/proc') / str(pid) / 'fd').iterdir()
               if p.exists()):
        raise ValueError('Coordinator does not own this artifact execution lock')
    out = ROOT / 'build/diagnostics/legacy_clocking_drain' / f'{pid}_{original["start"]}'
    out.mkdir(parents=True, exist_ok=False)
    save(out / 'identity.json', dict(coordinator=original, artifact=str(artifact.relative_to(ROOT)),
         manifest_sha256=digest(artifact / 'manifest.json'), producer_sha256=digest(Path(__file__))))
    os.kill(pid, signal.SIGSTOP)
    for _ in range(100):
        current = proc(pid)
        if current and current['start'] == original['start'] and current['state'] == 'T':
            break
        time.sleep(.01)
    else:
        raise RuntimeError('Coordinator did not stop; children were not signalled')
    save(out / 'children.json', descendants(pid))
    directory = ROOT / 'build/diagnostics/spice_dispatch'
    # Queued tickets can otherwise block unrelated jobs while their owner is
    # stopped. Keep exact bytes; never remove a lock inode or another PID ticket.
    archived = {}
    with (directory / '.queue.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for path in directory.glob('*.json'):
            if path.name == 'state.json':
                continue
            record = json.loads(path.read_text())
            if record.get('pid') == pid:
                archived[path.name] = record
                (out / path.name).write_bytes(path.read_bytes()); path.unlink()
    save(out / 'state.json', dict(status='draining_children', archived_tickets=archived,
         qualified_phy=False, original_artifact_unchanged=True))
    return out


def finish(out):
    identity = json.loads((out / 'identity.json').read_text()); expected = identity['coordinator']
    pid = expected['pid']; current = proc(pid)
    if not current or current['start'] != expected['start'] or current['state'] != 'T':
        raise ValueError('Stopped coordinator identity changed; refusing to signal')
    children = descendants(pid)
    if children:
        return dict(status='draining_children', children=children)
    artifact = ROOT / identity['artifact']
    if digest(artifact / 'manifest.json') != identity['manifest_sha256']:
        raise ValueError('Legacy context changed')
    # The original process cannot commit results while stopped. Preserve each
    # terminal export separately; these are evidence receipts, not timing passes.
    receipts = []
    for deck in sorted(artifact.rglob('bench.cir')):
        folder = deck.parent
        present = [p for p in folder.iterdir() if p.is_file() and
                   p.name in ('bench.cir', 'bench.raw', 'bench.cir.prn', 'summary.json', 'ngspice.log')]
        if not any(p.name in ('bench.raw', 'summary.json') for p in present):
            continue
        receipts.append(dict(case=str(folder.relative_to(artifact)),
            has_export=(folder / 'bench.cir.prn').exists(),
            has_original_summary=(folder / 'summary.json').exists(),
            files={p.name: digest(p) for p in present}))
    save(out / 'receipts.json', dict(cases=receipts, qualified_phy=False,
         scope='Partial evidence inventory; exports require independent remeasurement before admission.'))
    # Only the stopped coordinator is retired, after all solvers/exporters exit.
    # SIGTERM would stay pending on SIGSTOP; SIGCONT could dispatch new work.
    os.kill(pid, signal.SIGKILL)
    result = dict(status='archived_incomplete', completed_summaries=sum(r['has_original_summary'] for r in receipts),
         retained_cases=len(receipts), qualified_phy=False, original_artifact_unchanged=True)
    save(out / 'state.json', result)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest='action', required=True)
    b = sub.add_parser('begin'); b.add_argument('pid', type=int); b.add_argument('artifact', type=Path)
    b.add_argument('--script', choices=ALLOWED, required=True)
    f = sub.add_parser('finish'); f.add_argument('receipt', type=Path); f.add_argument('--watch', action='store_true')
    a = p.parse_args()
    if a.action == 'begin':
        print(begin(a.pid, a.artifact, a.script), flush=True)
    else:
        while True:
            result = finish(a.receipt.resolve())
            if not a.watch or result['status'] != 'draining_children':
                print(json.dumps(result, indent=2), flush=True); break
            time.sleep(10)
