# SPDX-License-Identifier: GPL-3.0-only
import fcntl,json,multiprocessing,sys,tempfile,time,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import spice_dispatch as dispatch


def acquire(root,result,release):
    with dispatch.lease(Path(root),priority=0,label='test') as slot:
        result.put(slot);release.wait(5)

class Dispatch(unittest.TestCase):
    def test_aging_and_arrival_order_prevent_priority_starvation(self):
        new=dict(id='new',created=500.,priority=0);old=dict(id='old',created=0.,priority=2)
        self.assertLess(dispatch.key(old,500.),dispatch.key(new,500.))
        self.assertLess(dispatch.key(dict(old,created=490.,priority=0),500.),dispatch.key(new,500.))

    def test_abandoned_ticket_is_removed_and_live_owner_is_retained(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);orphan=dict(id='orphan',created=0.,priority=0);live=dict(id='live',created=1.,priority=0)
            (root/'orphan.json').write_text(json.dumps(orphan))
            with (root/'live.owner').open('a') as owner:
                fcntl.flock(owner,fcntl.LOCK_EX);(root/'live.json').write_text(json.dumps(live))
                self.assertEqual(dispatch.active(root),[live]);self.assertFalse((root/'orphan.json').exists())

    def test_all_six_legacy_locks_are_respected_and_the_same_inode_is_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);slots=root/'build/diagnostics/spice_slots';slots.mkdir(parents=True);handles=[]
            for i in range(6):
                h=(slots/str(i)).open('a');fcntl.flock(h,fcntl.LOCK_EX);handles.append(h)
            inode=(slots/'3').stat().st_ino;context=multiprocessing.get_context('spawn');result=context.Queue();release=context.Event()
            worker=context.Process(target=acquire,args=(str(root),result,release));worker.start()
            try:
                time.sleep(.3);self.assertTrue(worker.is_alive());self.assertTrue(result.empty())
                handles[3].close();self.assertEqual(result.get(timeout=5),3)
                with (slots/'3').open('a') as probe:
                    with self.assertRaises(BlockingIOError):fcntl.flock(probe,fcntl.LOCK_EX|fcntl.LOCK_NB)
                self.assertEqual((slots/'3').stat().st_ino,inode);self.assertEqual({p.name for p in slots.iterdir()},set(map(str,range(6))))
            finally:
                release.set();worker.join(5)
                if worker.is_alive():worker.terminate();worker.join()
                for h in handles:h.close()
            self.assertEqual(worker.exitcode,0)

if __name__=='__main__':unittest.main()
