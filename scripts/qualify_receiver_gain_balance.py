#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Admit a passing gain/balance native receiver to all sixty original component cases."""
import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path

import qualify_receiver_components as components
import probe_receiver_candidate_link as replay_gate
import probe_receiver_gain_balance as native
import spice_slots
from spice_dispatch import lease

ROOT = Path(__file__).resolve().parents[1]
NAME = Path(__file__).name
sha = native.native.digest


def selected(replay):
    if not replay.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):
        raise ValueError('Use the isolated gain/balance native receiver replay')
    i = json.loads((replay/'manifest.json').read_text())['identity']
    expected = native.physical.profile(i.get('gain_balance_variant'))
    if (any(i.get(k) != v for k,v in expected.items()) or
            i['code'].get('probe_receiver_gain_balance.py') != sha(Path(native.__file__))):
        raise ValueError('Require the exact current gain/balance native profile')
    return i


def recheck(replay):
    selected(replay)
    with (replay/'.cached_verification.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if any(not (replay/n).is_file() for n in ['summary.json','captured/summary.json','sharp_control/summary.json']):
            raise ValueError('Complete both gain/balance native controls before component admission')
        with (replay/'.execution.lock').open('a+') as producer:
            fcntl.flock(producer,fcntl.LOCK_EX)
        native.run(replay)  # All controls already exist: scientific cached remeasurement only.
        r = json.loads((replay/'summary.json').read_text())
        if (r.get('diagnostic_complete') is not True or r.get('native_clock_passed') is not True or
                r.get('manifest_sha256') != sha(replay/'manifest.json')):
            raise ValueError('Weaker-bias native clock admission failed or changed')


@contextmanager
def selection(replay):
    selected(replay)
    names = {NAME,'probe_receiver_gain_balance.py','layout_receiver_gain_balance.py',
        'receiver_gain_balance_clock.py','receiver_restore_threshold_clock.py','receiver_restore_threshold.py','receiver_gain_balance.py','matrix_receiver_gain_balance.py',
        'receiver_soft_frontend_geometry.py','receiver_soft_common_mode.py','receiver_lvt_restore_experiment.py','spice_dispatch.py'}
    previous = components.CODE,replay_gate.recheck_replay,spice_slots.slot
    try:
        components.CODE = sorted(set(components.CODE)|names)
        replay_gate.recheck_replay = recheck
        # The frozen component worker imports this function at execution time.
        spice_slots.slot = lambda: lease(ROOT,priority=1,label='gain_balance_receiver_components')
        yield
    finally:
        components.CODE,replay_gate.recheck_replay,spice_slots.slot = previous


def run(action, artifact, replay=None, jobs=2):
    if action not in ['prepare','run'] or type(jobs) is not int or jobs not in [1,2,3]:
        raise ValueError('Use prepare/run and one to three independent component workers')
    if action == 'prepare':
        if replay is None:
            raise ValueError('Preparation requires the selected native replay')
        recheck(replay)
        with selection(replay):
            return components.prepare(artifact,replay)
    if not artifact.is_relative_to(ROOT/'build/diagnostics/receiver_components'):
        raise ValueError('Use the prepared gain/balance receiver component matrix')
    m = json.loads((artifact/'manifest.json').read_text()); i = m['identity']
    if i['code'].get(NAME) != sha(Path(__file__)):
        raise ValueError('Component matrix lacks the current gain/balance selector')
    replay = ROOT/i['replay']
    for t in m['tasks']:
        folder = artifact/t['id']
        if not (folder/'summary.json').exists() and any((folder/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log']):
            raise ValueError('Partial gain/balance component output retained; use a fresh context')
    with selection(replay):
        components.run(artifact,jobs)
    r = json.loads((artifact/'summary.json').read_text())
    if r.get('required') != 60 or r.get('passed_cases') != 60 or r.get('passed') is not True:
        raise ValueError('Weaker-bias receiver must pass all sixty original component conditions')
    return artifact/'summary.json'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['prepare','run'])
    p.add_argument('artifact',type=Path);p.add_argument('--replay',type=Path)
    p.add_argument('--jobs',type=int,choices=[1,2,3],default=2);a=p.parse_args()
    print(run(a.action,a.artifact.resolve(),a.replay.resolve() if a.replay else None,a.jobs),flush=True)
