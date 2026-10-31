#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Run immutable static monitor fixtures without claiming campaign qualification."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from dll_campaign import atomic
from qualify_dll_candidate import validate,execute
from spice_engine import engine

ROOT=Path(__file__).resolve().parents[1]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def select(manifest,name):
    matches=[task for task in manifest['tasks'] if task['id']==name]
    if len(matches)!=1:raise ValueError('Select one unambiguous captured native fixture')
    task=matches[0]
    if task['fast_rc'] or task['spec']['kind'] not in ['phase','logic']:
        raise ValueError('Early probes are limited to full-RC static monitor fixtures')
    return task


def run(root,names,jobs=1):
    if isinstance(names,str):names=[names]
    if not names or len(set(names))!=len(names):raise ValueError('Select distinct native fixtures')
    if not 1<=jobs<=3:raise ValueError('Use one to three static probe workers')
    root=Path(root).resolve()
    if not root.is_relative_to(ROOT/'build/diagnostics/dll_qualification'):
        raise ValueError('Use an isolated native qualification artifact')
    if engine()!='ngspice':raise ValueError('Use the pinned --ngspice environment')
    manifest=json.loads((root/'manifest.json').read_text());validate(root,manifest)
    tasks=[select(manifest,name) for name in names]
    for task in tasks:
        if not (root/task['id']).resolve().is_relative_to(root):raise ValueError('Invalid native fixture path')
    if digest(root/'requirements.json')!=digest(ROOT/'requirements.json'):raise ValueError('Native requirements changed')
    # The same lease excludes a concurrent campaign coordinator. execute() owns
    # its normal global SPICE slot and validates the unchanged deck and trace.
    with (root/'.execution.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        folder=root/'probe_requests';folder.mkdir(exist_ok=True)
        def worker(task):
            record=folder/(task['id']+'.json')
            context=dict(task=task['id'],manifest_sha256=digest(root/'manifest.json'),producer_sha256=digest(Path(__file__)),
                coordinator_pid=os.getpid(),pid_domain='container',started_unix=time.time(),qualified_phy=False,
                scope='Static detector response only; architecture, model and complete native campaign gates remain mandatory')
            atomic(record,dict(context,status='submitted'))
            result=execute(root,manifest,task)
            atomic(record,dict(context,status='passed' if result['passed'] else 'failed',
                summary_sha256=digest(root/task['id']/'summary.json'),finished_unix=time.time()))
            print(json.dumps(dict(task=task['id'],passed=result['passed'],qualified_phy=False,
                metrics=result.get('metrics')),indent=2),flush=True)
            return result
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            results=list(pool.map(worker,tasks))
    return 0 if all(result['passed'] for result in results) else 1


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('qualification',type=Path);p.add_argument('case',nargs='+');p.add_argument('--jobs',type=int,default=1)
    a=p.parse_args();return run(a.qualification,a.case,a.jobs)


if __name__=='__main__':sys.exit(main())
