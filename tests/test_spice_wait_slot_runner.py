# SPDX-License-Identifier: GPL-3.0-only
import fcntl
import json
from pathlib import Path
import sys
import tempfile
from threading import Event,Thread
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_spice_wait_slot as runner
import rx_candidate_aperture as aperture


class CapturedWaitSlotRunner(unittest.TestCase):
    def test_invalid_reserved_or_oversubscribed_slot_policies_are_rejected(self):
        original=lambda:None;target=SimpleNamespace(slot=original)
        for slots,retain,reserved in [([],False,0),([6],False,0),([-1],False,0),
                                      ([True],False,0),([1],False,4),([1,4],True,0)]:
            with self.subTest(slots=slots),patch.object(runner,'reserved_slots',return_value=reserved):
                with self.assertRaises(ValueError):
                    with runner.allocation(target,slots,retain):self.fail('Invalid resource policy entered')
                self.assertIs(target.slot,original)

    def test_waiter_cannot_start_until_the_real_existing_lease_is_released(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);folder=root/'build/diagnostics/spice_slots';folder.mkdir(parents=True)
            waiting=Event();acquired=Event();finish=Event();original=lambda:None;target=SimpleNamespace(slot=original)
            def observe(status,*args):
                if status=='waiting_for_slot':waiting.set()
            def worker():
                with target.slot():
                    acquired.set();finish.wait(timeout=3)
            with patch.object(aperture,'ROOT',root),patch.object(aperture,'reserved_slots',return_value=0),\
                 patch.object(runner,'reserved_slots',return_value=0),(folder/'4').open('a') as held:
                fcntl.flock(held,fcntl.LOCK_EX)
                with runner.allocation(target,[4],observe=observe):
                    thread=Thread(target=worker);thread.start()
                    try:
                        self.assertTrue(waiting.wait(timeout=2));self.assertFalse(acquired.wait(timeout=.05))
                        fcntl.flock(held,fcntl.LOCK_UN)
                        self.assertTrue(acquired.wait(timeout=2))
                    finally:finish.set();thread.join(timeout=3)
                    self.assertFalse(thread.is_alive())
                self.assertIs(target.slot,original)

    def test_serial_batch_retains_only_one_real_lease_and_restores_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);target=SimpleNamespace(slot=lambda:None);original=target.slot;events=[]
            with patch.object(aperture,'ROOT',root),patch.object(aperture,'reserved_slots',return_value=0),\
                 patch.object(runner,'reserved_slots',return_value=0):
                with self.assertRaisesRegex(RuntimeError,'test batch error'):
                    with runner.allocation(target,[1],retain=True,observe=lambda status,*args:events.append(status)):
                        for _ in range(2):
                            with target.slot(),(root/'build/diagnostics/spice_slots/1').open('a') as other:
                                with self.assertRaises(BlockingIOError):fcntl.flock(other,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        raise RuntimeError('test batch error')
                self.assertEqual(events,['waiting_for_slot','holding_slot','released_slot'])
                self.assertIs(target.slot,original)

    def test_scheduling_receipt_preserves_the_original_scientific_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);artifact=root/'build/diagnostics/receiver_clamp/test';artifact.mkdir(parents=True)
            scripts=root/'scripts';scripts.mkdir()
            names=['run_spice_wait_slot.py','test_entry.py','test_target.py','science.py','rx_candidate_aperture.py','spice_slots.py']
            for name in names:(scripts/name).write_text('# '+name+'\n')
            manifest=dict(identity=dict(code={'science.py':runner.digest(scripts/'science.py')}))
            (artifact/'manifest.json').write_text(json.dumps(manifest,indent=1));before=(artifact/'manifest.json').read_bytes()
            original=lambda:None;target=SimpleNamespace(slot=original);entered=[]
            def scientific_run(path):
                self.assertEqual(path,artifact)
                with target.slot():entered.append(path)
            entry=SimpleNamespace(run=scientific_run)
            with patch.object(runner,'ROOT',root),patch.dict(runner.PROFILES,test=('test_entry','test_target','receiver_clamp',False)),\
                 patch.object(runner.importlib,'import_module',side_effect=lambda name:entry if name=='test_entry' else target),\
                 patch.object(aperture,'ROOT',root),patch.object(aperture,'reserved_slots',return_value=0),\
                 patch.object(runner,'reserved_slots',return_value=0):runner.run('test',artifact,[1])
            self.assertEqual(entered,[artifact]);self.assertIs(target.slot,original)
            self.assertEqual((artifact/'manifest.json').read_bytes(),before)
            states=list((artifact/'execution_scheduling').glob('*/state.json'));self.assertEqual(len(states),1)
            report=json.loads(states[0].read_text());self.assertEqual(report['status'],'original_producer_completed')
            self.assertTrue(report['scheduling_only']);self.assertFalse(report['qualified_phy'])


if __name__=='__main__':unittest.main()
