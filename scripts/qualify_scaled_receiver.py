#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Select uniform decision scaling for the original receiver component and link gates."""
import argparse
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path

import qualify_receiver_components as components
import probe_receiver_candidate_link as link
import probe_receiver_scaled_decision_candidate as native
from receiver_scaled_decision_experiment import source_variant

ROOT=Path(__file__).resolve().parents[1]
NAME=Path(__file__).name
ACTIONS={'prepare-components','prepare-link','run-components','run-link'}


def preserve_partial(folder):
    if not (folder/'summary.json').exists() and any((folder/n).exists() for n in ['bench.raw','bench.cir.prn','ngspice.log']):
        raise ValueError('Incomplete integration execution retained; use a fresh retry context')


def selected_replay(replay):
    if not replay.is_relative_to(ROOT/'build/diagnostics/receiver_replay'):
        raise ValueError('Use an isolated uniform-decision native replay')
    identity=json.loads((replay/'manifest.json').read_text())['identity']
    native.validate_profile(identity)
    return identity


def recheck(replay):
    selected_replay(replay)
    with (replay/'.cached_verification.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if any(not (replay/n).is_file() for n in ['summary.json','captured/summary.json','sharp_control/summary.json']):
            raise ValueError('Complete both uniform-decision native controls before integration')
        selected_replay(replay)
        native.run(replay)  # Every case is cached; remeasurement cannot start a missing case.
        report=json.loads((replay/'summary.json').read_text())
        if (report.get('diagnostic_complete') is not True or report.get('native_clock_passed') is not True or
                report.get('manifest_sha256')!=native.digest(replay/'manifest.json')):
            raise ValueError('Uniform-decision native clock admission failed or changed')


@contextmanager
def selection(replay):
    selected_replay(replay)
    names={NAME}|set(native.CODE)
    changes=[(components,'CODE',sorted(set(components.CODE)|names)),
             (link,'CODE',sorted(set(link.CODE)|names)),
             (link,'source_variant',source_variant),(link,'recheck_replay',recheck)]
    previous=[(module,name,getattr(module,name)) for module,name,_ in changes]
    try:
        for module,name,value in changes:setattr(module,name,value)
        yield
    finally:
        for module,name,value in reversed(previous):setattr(module,name,value)


def run(action,artifact,replay=None,jobs=2):
    if action not in ACTIONS:raise ValueError('Unknown uniform-decision qualification action')
    if type(jobs) is not int or jobs not in range(1,7):raise ValueError('Keep workers within the six-slot budget')
    if action.startswith('prepare-'):
        if replay is None:raise ValueError('Preparation needs the selected uniform-decision replay')
    else:
        kind='receiver_components' if action=='run-components' else 'receiver_candidate_link'
        if not artifact.is_relative_to(ROOT/'build/diagnostics'/kind):raise ValueError('Use prepared uniform-decision diagnostics')
        capture=json.loads((artifact/'manifest.json').read_text());identity=capture['identity']
        if identity['code'].get(NAME)!=native.digest(Path(__file__)):
            raise ValueError('Diagnostic lacks the current uniform-decision selector')
        replay=ROOT/identity['replay']
        if action=='run-components':
            for task in capture['tasks']:preserve_partial(artifact/task['id'])
        else:preserve_partial(artifact)
    with selection(replay):
        if action=='prepare-components':result=components.prepare(artifact,replay)
        elif action=='prepare-link':result=link.prepare(artifact,replay)
        elif action=='run-components':return components.run(artifact,jobs)
        else:return link.run(artifact)
    print(result,flush=True)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=sorted(ACTIONS));parser.add_argument('artifact',type=Path)
    parser.add_argument('--replay',type=Path);parser.add_argument('--jobs',type=int,choices=range(1,7),default=2);args=parser.parse_args()
    run(args.action,args.artifact.resolve(),args.replay.resolve() if args.replay else None,args.jobs)
