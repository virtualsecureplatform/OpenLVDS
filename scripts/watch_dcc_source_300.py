#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Serially replay newly completed native cases; never alter or restart SPICE."""
import argparse,fcntl,hashlib,json,os,subprocess,time
import replay_dcc_source_300 as replay
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT/'build/diagnostics/dcc_source_300_v1/1a4f4e8eabb896e4'
REPLAYS=ROOT/'build/diagnostics/dcc_source_native_replay_300'
SOURCE_UNIT='openlvds-dcc-source-300-v1'
VERSION='completed-dcc-source-native-replay-watcher-300-v1'

def sha(path):return replay.sha(path)
def atomic(path,value):
    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,indent=2)+'\n');tmp.replace(path)


def index_receipts(root,parent,tasks,checked=None):
    checked=checked if checked is not None else set()
    covered={};records={};partial=set()
    resolve=lambda n:Path(n) if Path(n).is_absolute() else ROOT/n
    for folder in sorted(root.glob('*')):
        manifest=folder/'manifest.json';state=folder/'state.json'
        if not manifest.is_file() or not state.is_file():continue
        m=json.loads(manifest.read_text());i=m['identity']
        if i.get('parent')!=parent:continue
        if (m.get('qualified_phy') is not False or i.get('version')!=replay.VERSION
                or type(i.get('full_matrix')) is not bool or not i.get('cases')
                or len(i['cases'])!=len(set(i['cases']))
                or any(n not in tasks for n in i['cases'])
                or folder.name!=hashlib.sha256(json.dumps(i,sort_keys=True).encode()).hexdigest()[:16]):
            raise ValueError('Unexpected DCC replay identity or case coverage')
        s=json.loads(state.read_text())
        if s['status']!='complete':partial.update(i['cases']);continue
        report=json.loads((folder/'summary.json').read_text())
        if (report['qualified_phy'] is not False or report['source_only'] is not True
                or s!=dict(status='complete',cases=len(i['cases']),qualified_phy=False)
                or [r['case'] for r in report['rows']]!=i['cases']):
            raise ValueError('Invalid completed DCC replay receipt')
        inputs={str(resolve(n)):h for n,h in i['inputs'].items()}
        for name,digest in inputs.items():
            key=(name,digest)
            if key not in checked:
                if sha(Path(name))!=digest:raise ValueError('DCC receipt native/model/code input changed: '+name)
                checked.add(key)
        passed=True
        for number,row in zip(i['cases'],report['rows']):
            source=resolve(parent)/number;path=source/'summary.json'
            if str(path) not in inputs:raise ValueError('Missing bound native summary')
            native=json.loads(path.read_text())
            if (native['task']!=tasks[number] or native['error'] is not None
                    or not replay.REQUIRED<=set(native['files'])
                    or row['original_metrics_reproduced'] is not True
                    or row['original_source_passed']!=replay.producer.passed(native['result'],tasks[number]['spec'])
                    or type(row['independent']['independent_source_screen_passed']) is not bool):
                raise ValueError('DCC replay/native case mismatch')
            for name,digest in native['files'].items():
                if Path(name).name!=name or inputs.get(str(source/name))!=digest:
                    raise ValueError('Native DCC witness omitted from receipt')
            if number in covered and covered[number]!=row:raise ValueError('Conflicting native DCC replay')
            covered[number]=row
            passed=passed and row['original_source_passed'] and row['independent']['independent_source_screen_passed']
        if (report['all_selected_source_screens_passed']!=passed
                or report['complete_810_source_matrix_admitted']!=bool(i['full_matrix'] and len(i['cases'])==810 and passed)):
            raise ValueError('DCC receipt aggregate changed')
        records[folder.name]=dict(files={n:sha(folder/n) for n in ('manifest.json','summary.json','state.json')},
            full_matrix=i['full_matrix'],source_admitted=report['complete_810_source_matrix_admitted'])
    return covered,records,partial


def batch_cases(pending,partial,terminal):
    if partial.intersection(pending):raise ValueError('Partial replay evidence exists; inspect before retrying')
    return pending[:18] if len(pending)>=18 or terminal else []


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
    manifest=replay.producer.bound(PARENT,full=False);tasks={t['id']:t for t in manifest['tasks']}
    if (manifest['identity']['version']!=replay.producer.VERSION or len(tasks)!=810):
        raise ValueError('Require original fresh 810-case DCC source campaign')
    files=[Path(__file__),PARENT/'manifest.json',ROOT/'scripts/env.sh',ROOT/'scripts/replay_dcc_source_300.py',
           ROOT/'scripts/dcc_source_300.py']
    identity=dict(version=VERSION,parent=str(PARENT.relative_to(ROOT)),inputs={str(p.relative_to(ROOT)):sha(p) for p in files},
                  batch_size=18,poll_seconds=30,maximum_replay_workers=1)
    out=ROOT/'build/diagnostics/dcc_source_watch_300'/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()[:16]
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
                    command=[str(ROOT/'scripts/env.sh'),'--tools','--ngspice','build/tools/exact-rc-venv/bin/python',
                             'scripts/replay_dcc_source_300.py',str(PARENT.relative_to(ROOT)),
                             *(['--full'] if full_request else batch)]
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
