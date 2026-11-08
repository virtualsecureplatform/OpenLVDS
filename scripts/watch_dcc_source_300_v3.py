#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Serially replay newly completed native cases; never alter or restart SPICE."""
import argparse,fcntl,hashlib,json,os,subprocess,time,sys
import watch_dcc_source_300_v2 as legacy
replay=legacy.replay
index_receipts=legacy.index_receipts
completed_cases=legacy.completed_cases
batch_cases=legacy.batch_cases
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'build/diagnostics/dcc_source_300_v1/1a4f4e8eabb896e4'
REPLAYS=ROOT/'build/diagnostics/dcc_source_native_replay_300'
SOURCE_UNIT='openlvds-dcc-source-300-v1'
VERSION='completed-dcc-source-native-replay-watcher-300-v3'

def sha(path):return replay.sha(path)
def atomic(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


source_live=legacy.source_live


def replay_command(batch,full_request):
    return [sys.executable,str(ROOT/'scripts/replay_dcc_source_300.py'),str(PARENT),
            *(['--full'] if full_request else batch)]


def run():
    manifest=replay.producer.bound(PARENT,full=False);tasks={t['id']:t for t in manifest['tasks']}
    if (manifest['identity']['version']!=replay.producer.VERSION or len(tasks)!=810):
        raise ValueError('Require original fresh 810-case DCC source campaign')
    files=[Path(__file__),Path(legacy.__file__),Path(legacy.legacy.__file__),PARENT/'manifest.json',ROOT/'scripts/env.sh',ROOT/'scripts/replay_dcc_source_300.py',
           ROOT/'scripts/dcc_source_300.py']
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
                  batch_size=18,poll_seconds=30,maximum_replay_workers=1)
    out=ROOT/'build/diagnostics/dcc_source_watch_300_v3'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        atomic(out/'state.json',dict(status='watching',pid=os.getpid(),qualified_phy=False))
        try:
            checked=set()
            while True:
                if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Captured watcher/consumer inputs changed')
                covered,receipts,partial=index_receipts(REPLAYS,identity['parent'],tasks,checked)
                done,errors=completed_cases(PARENT,tasks);pending=[n for n in done if n not in covered]
                source_state=json.loads((PARENT/'state.json').read_text())
                terminal=source_state.get('status')=='complete'
                snapshot=dict(native_completed=len(done),replayed=len(covered),pending=pending,native_errors=errors,
                    partial_replay_cases=sorted(partial,key=int),
                    failed_replayed_cases=sorted((n for n,r in covered.items() if not (r['original_source_passed'] and r['independent']['independent_source_screen_passed'])),key=int),
                    receipts=receipts,source_only=True,qualified_phy=False,
                    scope='Receipt index and replay scheduling only; final full matrix evidence validation remains required')
                atomic(out/'progress.json',snapshot)
                if terminal and errors:raise ValueError('Native campaign completed with errors; retain and inspect')
                full=[token for token,record in receipts.items() if record['full_matrix']]
                if terminal and len(covered)==810 and full:
                    atomic(out/'summary.json',dict(snapshot,all_810_receipts_indexed=True,
                        full_source_receipts=full,complete_source_matrix_admitted=any(receipts[t]['source_admitted'] for t in full),
                        physical_dcc_and_phy_admitted=False,
                        scope='Fresh full source-cell replay indexed; physical DCC, loaded DLL and PHY remain required'))
                    atomic(out/'state.json',dict(status='complete_source_only',cases=810,qualified_phy=False));break
                if terminal and len(covered)==810 and partial:
                    raise ValueError('Partial full-source replay exists; inspect before retrying')
                batch=batch_cases(pending,partial,terminal)
                full_request=terminal and len(covered)==810
                if batch or full_request:
                    command=replay_command(batch,full_request)
                    p=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
                    log='full_source.log' if full_request else 'batch_'+'_'.join(batch)+'.log'
                    (out/log).write_text(p.stdout+p.stderr);p.check_returncode()
                    new_covered,new_records,_=index_receipts(REPLAYS,identity['parent'],tasks,checked)
                    if not set(batch)<=new_covered.keys() or full_request and not any(r['full_matrix'] for r in new_records.values()):
                        raise ValueError('Child replay did not publish the requested source receipts')
                    continue
                if not terminal and source_live() is False:
                    raise ValueError('Native DCC coordinator is terminal while cases remain; no solver was stopped or restarted')
                time.sleep(30)
        except Exception as exc:
            atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();print(run(),flush=True)
