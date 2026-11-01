# SPDX-License-Identifier: GPL-3.0-only
"""Priority/aging queue over the existing six SPICE lock-file inodes."""
from contextlib import contextmanager
import fcntl,json,os,time,uuid
from pathlib import Path
from spice_slots import ROOT,reserved_slots
BUDGET=6
AGING_SECONDS=180.
LEGACY_HANDOFF_SECONDS=.1


def key(record,now):
    return (record['priority']-int(max(0.,now-record['created'])/AGING_SECONDS),record['created'],record['id'])


@contextmanager
def registry(directory):
    with (directory/'.queue.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX);yield


def active(directory):
    records=[]
    for path in directory.glob('*.json'):
        if path.name=='state.json':continue
        record=json.loads(path.read_text())
        with (directory/(record['id']+'.owner')).open('a+') as owner:
            try:fcntl.flock(owner,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:records.append(record)
            else:path.unlink()  # An abandoned ticket cannot block the queue.
    return records


def save(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,sort_keys=True)+'\n');temp.replace(path)


def event(directory,record,kind,slot):
    with (directory/'events.jsonl').open('a') as out:
        out.write(json.dumps(dict(ticket=record['id'],label=record['label'],pid=record['pid'],kind=kind,slot=slot,time=time.time()))+'\n')


@contextmanager
def lease(root=ROOT,priority=1,label='spice'):
    if type(priority) is not int or priority not in range(3):raise ValueError('Use a priority from zero through two')
    root=Path(root);directory=root/'build/diagnostics/spice_dispatch';directory.mkdir(parents=True,exist_ok=True)
    slots=root/'build/diagnostics/spice_slots';slots.mkdir(parents=True,exist_ok=True)
    record=dict(id=uuid.uuid4().hex,pid=os.getpid(),created=time.monotonic(),priority=priority,label=str(label))
    path=directory/(record['id']+'.json');handle=None;index=None
    with (directory/(record['id']+'.owner')).open('a+') as owner:
        fcntl.flock(owner,fcntl.LOCK_EX)
        try:
            with registry(directory):save(path,record)
            while handle is None:
                with registry(directory):
                    now=time.monotonic();queue=active(directory)
                    if min(queue,key=lambda r:key(r,now))['id']==record['id']:
                        state=json.loads((directory/'state.json').read_text()) if (directory/'state.json').exists() else {}
                        for i in range(reserved_slots(root),BUDGET):
                            if now<state.get(str(i),0):continue
                            candidate=(slots/str(i)).open('a')
                            try:fcntl.flock(candidate,fcntl.LOCK_EX|fcntl.LOCK_NB)
                            except BlockingIOError:candidate.close();continue
                            if i<reserved_slots(root):candidate.close();continue
                            handle,index=candidate,i;path.unlink();event(directory,record,'acquired',i);break
                if handle is None:time.sleep(.025)
            yield index
        finally:
            with registry(directory):
                path.unlink(missing_ok=True)
                if handle is not None:
                    state=json.loads((directory/'state.json').read_text()) if (directory/'state.json').exists() else {}
                    state[str(index)]=time.monotonic()+LEGACY_HANDOFF_SECONDS;save(directory/'state.json',state)
                    # Give older blocking flock users an opportunity before
                    # another dispatcher worker can reacquire this same slot.
                    handle.close();event(directory,record,'released',index)
