# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import resident_dll_jobs as jobs


class OTAJobTransition(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        root=Path(temp.name);(root/'build/old').mkdir(parents=True)
        patcher=patch.object(jobs,'ROOT',root);patcher.start();self.addCleanup(patcher.stop)

    def test_reload_adopts_the_existing_dynamic_coordinator(self):
        old=dict(pid=123,pgid=100,identity={'start':'original'})
        records={};descriptors={}
        with patch.object(jobs,'alive',return_value=True),patch.object(jobs,'qualifier_owners',return_value=[(124,'build/old')]):
            jobs.configure_ota(descriptors,records,{'qualify_ota':old},Path('build/old'),['command'])
        self.assertEqual(records['qualify_ota']['pid'],123)
        self.assertEqual(records['qualify_ota']['artifact'],'build/old')
        self.assertEqual(len(records),1)

    def test_switch_retains_old_worker_identity_and_creates_a_distinct_new_owner(self):
        records={'qualify_ota':dict(pid=123,pgid=100,identity={'start':'old'},artifact='build/old')};descriptors={}
        jobs.configure_ota(descriptors,records,{},Path('build/new'),['new command'])
        self.assertNotIn('pid',records['qualify_ota'])
        retired=[record for record in records.values() if record.get('retired')]
        self.assertEqual(len(retired),1);self.assertEqual(retired[0]['pid'],123)
        self.assertEqual(retired[0]['superseded_by'],'build/new')

    def test_retirement_interrupts_only_the_python_owner_and_only_once(self):
        record=dict(pid=123,pgid=100,artifact='build/old',identity={'start':'old'})
        with patch.object(jobs,'alive',return_value=True),patch.object(jobs,'qualifier_owners',return_value=[(124,'build/old')]),\
             patch.object(jobs.os,'kill') as kill,patch.object(jobs,'process_identity',return_value={'start':'owner'}):
            jobs.retire_qualifier(record)
            record.pop('retirement_requested') # Simulate a watchdog restart before its snapshot.
            jobs.retire_qualifier(record)
        kill.assert_called_once_with(124,signal.SIGINT)
        self.assertEqual(record['state'],'draining_submitted_native_cases')

    def test_ambiguous_processes_are_never_signalled(self):
        with patch.object(jobs,'alive',return_value=True),patch.object(jobs,'qualifier_owners',return_value=[]),patch.object(jobs.os,'kill') as kill:
            with self.assertRaises(RuntimeError):jobs.retire_qualifier(dict(pid=123,pgid=100,artifact='build/old'))
        kill.assert_not_called()

    def test_owner_exit_race_does_not_signal_a_replacement_process(self):
        with patch.object(jobs,'alive',return_value=True),patch.object(jobs,'qualifier_owners',return_value=[(124,'build/old')]),\
             patch.object(jobs,'process_identity',side_effect=ProcessLookupError),patch.object(jobs.os,'kill') as kill:
            record=dict(pid=123,pgid=100,artifact='build/old');jobs.retire_qualifier(record)
        kill.assert_not_called();self.assertEqual(record['state'],'waiting_for_coordinator_exit')

    def test_completed_retirement_does_not_rewrite_a_later_run_of_the_artifact(self):
        state=jobs.ROOT/'build/old/state.json';state.write_text('{"status":"running","tasks":{}}')
        record=dict(pid=123,pgid=100,artifact='build/old',superseded_by='build/new')
        with patch.object(jobs,'alive',return_value=False),patch.object(jobs,'group_alive',return_value=False):
            jobs.retire_qualifier(record)
            self.assertEqual(record['state'],'retired')
            state.write_text('{"status":"new_run"}')
            jobs.retire_qualifier(record)
        self.assertEqual(state.read_text(),'{"status":"new_run"}')
