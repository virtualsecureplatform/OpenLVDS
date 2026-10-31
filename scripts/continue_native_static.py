#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Expand native static diagnostics only after the three initial SS probes pass."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
from pathlib import Path
import time

from dll_campaign import atomic
from dll_native_evidence import architecture_sources
from probe_native_dll import digest, select
from qualify_dll_candidate import validate, evaluate, execute
from spice_engine import engine

ROOT=Path(__file__).resolve().parents[1]
SEEDS=['phase_ss_0_150ps','phase_ss_0_0ps','phase_ss_0_-150ps']


def admission(root,manifest):
    validate(root,manifest);architecture_sources(root,manifest)
    if digest(root/'requirements.json')!=digest(ROOT/'requirements.json'):raise ValueError('Native requirements changed')
    for name in SEEDS:
        task=select(manifest,name);folder=root/name;report=json.loads((folder/'summary.json').read_text())
        if (not report.get('passed') or report['returncode']!=0 or report['task']!=name or
            report['deck_sha256']!=task['deck_sha256'] or digest(folder/'bench.cir')!=task['deck_sha256'] or
            digest(folder/'bench.cir.prn')!=report['waveform_sha256'] or digest(folder/'bench.raw')!=report['raw_sha256'] or
            report['metrics']!=evaluate(root,task)):
            raise ValueError('Native SS seed has not passed intact: '+name)
    names=[f'phase_{corner}_{offset}ps' for corner in ['ss_0','tt_25','ff_0'] for offset in [0,150,-150,50,-50,300,-300]]
    return [select(manifest,name) for name in names if name not in SEEDS]


def run(root,jobs=3):
    root=root.resolve()
    if not root.is_relative_to(ROOT/'build/diagnostics/dll_qualification') or jobs not in [1,2,3]:
        raise ValueError('Use an isolated native artifact and 1–3 workers')
    if engine()!='ngspice':raise ValueError('Use the pinned --ngspice environment')
    manifest=json.loads((root/'manifest.json').read_text());producer=digest(Path(__file__))
    record=root/'static_followup.json'
    context=dict(diagnostic=True,qualified_phy=False,manifest_sha256=digest(root/'manifest.json'),producer_sha256=producer)
    # Waiting for the real campaign lease preserves the live seed coordinator.
    # Admission remeasures its terminal artifacts after obtaining that lease.
    with (root/'.static_followup.lock').open('a') as coordinator:
        fcntl.flock(coordinator,fcntl.LOCK_EX|fcntl.LOCK_NB)
        atomic(record,dict(context,status='waiting_for_seed_coordinator'))
        with (root/'.execution.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            try:tasks=admission(root,manifest)
            except (ValueError,KeyError,OSError) as error:
                atomic(record,dict(context,status='held_by_seed_evidence',reason=str(error)));return 1
            atomic(record,dict(context,status='running',started_unix=time.time(),cases=[t['id'] for t in tasks]))
            with ThreadPoolExecutor(max_workers=jobs) as pool:
                results=list(pool.map(lambda task:execute(root,manifest,task),tasks))
            validate(root,manifest)
            if digest(Path(__file__))!=producer:raise ValueError('Static follow-up producer changed')
            atomic(record,dict(context,status='complete',passed=all(r['passed'] for r in results),
                case_reports={t['id']:digest(root/t['id']/'summary.json') for t in tasks},finished_unix=time.time()))
    return 0 if all(r['passed'] for r in results) else 1


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('qualification',type=Path);p.add_argument('--jobs',type=int,default=3)
    a=p.parse_args();raise SystemExit(run(a.qualification,a.jobs))
