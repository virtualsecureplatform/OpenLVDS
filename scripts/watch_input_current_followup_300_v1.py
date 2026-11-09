#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Consume one terminal input-current trial, then run its gated combined test."""
import fcntl
import hashlib
import json
from pathlib import Path
import sys
import time
import replay_input_current_origin_300_v1 as replay
import probe_dcc_chain_300_v2 as combined

ROOT=combined.ROOT
TRIAL=combined.TRIAL
VERSION='single-input-current-combined-followup-300-v1'
CONTEXT='input_current_combined_followup_300_v1'


def followup(trial,record):
    # The replay rejects native errors, missing files and nonterminal receipts.
    # The combined producer independently rechecks this passing receipt.
    proof=replay.run(trial)
    record('reference_replayed',reference_proof=str(proof.relative_to(ROOT)))
    summary=json.loads((proof/'summary.json').read_text())
    if summary['numerical_origin_passed_for_reference_case'] is not True:
        record('reference_rejected',reference_proof=str(proof.relative_to(ROOT)))
        return
    out=combined.prepare(proof)
    record('combined_prepared',reference_proof=str(proof.relative_to(ROOT)),combined_artifact=str(out.relative_to(ROOT)))
    combined.run(out)
    result=json.loads((out/'summary.json').read_text())
    record('complete',reference_proof=str(proof.relative_to(ROOT)),combined_artifact=str(out.relative_to(ROOT)),
        combined_loading_pilot_passed=result['combined_loading_pilot_passed'])


def run():
    # Stable lock path: never unlink or replace the inode, even after exit.
    control=ROOT/'build/control';control.mkdir(parents=True,exist_ok=True)
    with (control/'input-current-combined-followup-300-v1.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        combined.reference.producer.bound(TRIAL,full=False)
        scripts={str(Path(mod.__file__).resolve().relative_to(ROOT)):combined.sha(Path(mod.__file__).resolve())
                 for mod in list(sys.modules.values()) if getattr(mod,'__file__',None)
                 and Path(mod.__file__).resolve().parent==ROOT/'scripts'}
        identity=dict(version=VERSION,trial=str(TRIAL.relative_to(ROOT)),inputs=scripts,poll_seconds=30,
                      max_native_workers=1,global_native_limit=6,qualified_phy=False)
        out=ROOT/'build/diagnostics'/CONTEXT/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
        out.mkdir(parents=True,exist_ok=False)
        combined.atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
        def record(status,**kwargs):
            combined.atomic(out/'state.json',dict(status=status,qualified_phy=False,**kwargs))
            print(json.dumps(dict(status=status,**kwargs),sort_keys=True),flush=True)
        record('waiting_for_native_trial')
        try:
            while True:
                if any(combined.sha(ROOT/n)!=h for n,h in scripts.items()):
                    raise ValueError('Captured follow-up code changed')
                state=TRIAL/'state.json'
                if state.exists() and json.loads(state.read_text()).get('status')=='complete':break
                # No lease held while waiting; never restart or alter the source.
                time.sleep(30)
            followup(TRIAL,record)
        except Exception as exc:
            record('failed',error=str(exc));raise
        return out


if __name__=='__main__':print(run(),flush=True)
