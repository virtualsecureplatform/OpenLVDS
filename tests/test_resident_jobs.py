# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_dll_comparison as manager
import resident_dll_jobs as resident


class ResidentJobs(unittest.TestCase):
    def test_archived_partial_traces_are_not_archived_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'point';out.mkdir()
            (out/'bench.raw').write_bytes(b'partial')
            (out/'bench.cir').write_text('captured input')
            resident.archive_unfinished(root)
            first=list(root.rglob('bench.raw'))
            resident.archive_unfinished(root)
            self.assertEqual(first,list(root.rglob('bench.raw')))
            self.assertEqual((out/'bench.cir').read_text(),'captured input')

    def test_dead_or_reused_pid_is_not_a_live_worker(self):
        with patch.object(manager,'process_identity',return_value={'start_ticks':'2'}):
            self.assertFalse(manager.alive(12,{'start_ticks':'1'}))
        with patch.object(manager,'process_identity',side_effect=ProcessLookupError):
            self.assertFalse(manager.alive(12))

    def test_stale_state_cannot_report_running(self):
        with patch.object(resident,'alive',return_value=False):
            self.assertEqual(resident.snapshot({'status':'running'},12,1),'interrupted')
        with patch.object(resident,'alive',return_value=True):
            self.assertEqual(resident.snapshot({'status':'running'},12,120),'unresponsive')

    def test_interrupted_trace_is_preserved_and_retry_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'task';out.mkdir()
            (out/'bench.cir').write_text('captured input')
            (out/'library.spice').write_text('captured model')
            (out/'bench.raw').write_bytes(b'partial')
            record=dict(status='running',pid=12)
            manager.recover_interrupted(root,'task',record)
            self.assertEqual(record['status'],'pending')
            self.assertEqual((Path(record['interruption_archive'])/'bench.raw').read_bytes(),b'partial')
            self.assertEqual((out/'bench.cir').read_text(),'captured input')
            manager.recover_interrupted(root,'task',record)
            manager.recover_interrupted(root,'task',record)
            self.assertEqual(record['status'],'failed')
