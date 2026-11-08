#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Serially replay newly completed native cases; never alter or restart SPICE."""
import argparse,fcntl,hashlib,json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'build/diagnostics/counter_pvt_300_v1/eec2546717d211ee'
REPLAYS=ROOT/'build/diagnostics/counter_clear_replay_300'
SOURCE_UNIT='openlvds-counter-pvt-300-v1'
VERSION='completed-counter-clear-replay-watcher-300-v1'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def atomic(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def index_receipts(root,parent,tasks):
    covered={};records={};partial=set()
    for folder in sorted(root.glob('*')):
        manifest=folder/'manifest.json';state=folder/'state.json'
        if not manifest.is_file() or not state.is_file():continue
        m=json.loads(manifest.read_text());i=m['identity']
        if i.get('parent')!=parent:continue
        if (i.get('version')!='original-three-ns-counter-clear-replay-300-v1'
                or folder.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]
                or i.get('clear_settling_ps')!=3000 or i.get('original_results_preserved') is not True):
            raise ValueError('Unexpected counter replay context')
        s=json.loads(state.read_text())
        if s['status']!='complete':partial.update(i['cases']);continue
        summary=folder/'summary.json';report=json.loads(summary.read_text())
        if (report['all_selected_original_metrics_reproduced'] is not True
                or report['qualified_phy'] is not False or report['all_270_counter_boundaries_present'] is not False
                or s.get('cases')!=len(i['cases']) or len(report['rows'])!=len(i['cases'])):
            raise ValueError('Invalid completed counter replay receipt')
        for number,row in zip(i['cases'],report['rows']):
            if (number not in tasks or row['task']!=tasks[number]
                    or row['original_metrics_reproduced'] is not True
                    or row['only_clear_settling_predicate_changed'] is not True):
                raise ValueError('Counter replay case coverage changed')
            if number in covered and covered[number]!=row:
                raise ValueError('Conflicting repeated native counter replay')
            covered[number]=row
        records[folder.name]={n:sha(folder/n) for n in ('manifest.json','summary.json','state.json')}
    return covered,records,partial


def completed_cases(parent,tasks):
    done=[];errors=[]
    for number,task in tasks.items():
        path=parent/number/'summary.json'
        if not path.is_file():continue
        row=json.loads(path.read_text())
        if row['task']!=task:raise ValueError('Native case task changed')
        if row['error'] is not None:errors.append(number)
        else:done.append(number)
    return sorted(done,key=int),errors


def source_live():
    p=subprocess.run(['systemctl','--user','show',SOURCE_UNIT,'-p','ActiveState','-p','MainPID'],capture_output=True,text=True)
    if p.returncode:return None
    fields=dict(line.split('=',1) for line in p.stdout.splitlines() if '=' in line)
    if fields.get('ActiveState')=='active' and int(fields.get('MainPID','0'))>0:return True
    if fields.get('ActiveState') in ('inactive','failed') and fields.get('MainPID')=='0':return False
    return None


def run():
    manifest=json.loads((PARENT/'manifest.json').read_text());tasks={t['id']:t for t in manifest['tasks']}
    if (manifest['identity']['version']!='fresh-profile-bound-300mhz-actual-rc-counter-v1'
            or len(tasks)!=270 or any(t['mode']!='simulate' for t in tasks.values())):
        raise ValueError('Require original fresh 270-case native campaign')
    files=[Path(__file__),PARENT/'manifest.json',ROOT/'scripts/env.sh',ROOT/'scripts/replay_counter_clear_300.py',
           ROOT/'scripts/counter_protocol_300_v2.py']
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
                  batch_size=6,poll_seconds=30,maximum_replay_workers=1)
    out=ROOT/'build/diagnostics/counter_clear_watch_300'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
    out.mkdir(parents=True,exist_ok=False);atomic(out/'manifest.json',dict(identity=identity,qualified_phy=False))
    with (out/'.execution.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        atomic(out/'state.json',dict(status='watching',pid=os.getpid(),qualified_phy=False))
        try:
            while True:
                if any(sha(ROOT/n)!=h for n,h in identity['inputs'].items()):raise ValueError('Captured watcher/consumer inputs changed')
                covered,receipts,partial=index_receipts(REPLAYS,identity['parent'],tasks)
                done,errors=completed_cases(PARENT,tasks);pending=[n for n in done if n not in covered]
                source_state=json.loads((PARENT/'state.json').read_text())
                terminal=source_state.get('status')=='complete'
                snapshot=dict(native_completed=len(done),replayed=len(covered),pending=pending,native_errors=errors,
                    failed_replayed_cases=sorted((n for n,r in covered.items() if not r['original_three_ns_point_passed']),key=int),
                    receipts=receipts,qualified_phy=False,
                    scope='Receipt index and replay scheduling only; final full matrix evidence validation remains required')
                atomic(out/'progress.json',snapshot)
                if terminal and errors:raise ValueError('Native campaign completed with errors; retain and inspect')
                if terminal and len(covered)==270:
                    atomic(out/'summary.json',dict(snapshot,all_270_receipts_indexed=True,whole_matrix_admitted=False))
                    atomic(out/'state.json',dict(status='complete_unqualified',cases=270,qualified_phy=False));break
                if pending and partial.intersection(pending):
                    raise ValueError('A pending case already has partial replay evidence; inspect its live helper before retrying')
                if pending:
                    batch=pending[:6]
                    command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/counter-physical-venv/bin/python',
                             'scripts/replay_counter_clear_300.py',str(PARENT.relative_to(ROOT)),*batch]
                    p=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
                    (out/('batch_'+'_'.join(batch)+'.log')).write_text(p.stdout+p.stderr)
                    p.check_returncode()
                    new_covered,_,_=index_receipts(REPLAYS,identity['parent'],tasks)
                    if not set(batch)<=new_covered.keys():raise ValueError('Child replay did not publish the requested completed receipts')
                    continue
                if not terminal and source_live() is False:
                    raise ValueError('Native coordinator is terminal while cases remain; no solver was stopped or restarted')
                time.sleep(30)
        except Exception as exc:
            atomic(out/'state.json',dict(status='failed',error=str(exc),qualified_phy=False));raise
    return out


if __name__=='__main__':
    argparse.ArgumentParser(description=__doc__).parse_args();print(run(),flush=True)
