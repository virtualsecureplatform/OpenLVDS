# SPDX-License-Identifier: GPL-3.0-only
import fcntl
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_native_dll as probe


class NativeProbeAdmission(unittest.TestCase):
    def test_rejects_duplicate_requests_and_worker_overallocation(self):
        for names,jobs in [(['a','a'],1),([],1),(['a'],0),(['a'],4)]:
            with self.assertRaises(ValueError):probe.run('/unused',names,jobs)

    def test_only_full_static_fixtures_can_dispatch(self):
        for fast,kind in [(True,'phase'),(False,'loop')]:
            with self.assertRaisesRegex(ValueError,'full-RC static'):
                probe.select(dict(tasks=[dict(id='a',fast_rc=fast,spec=dict(kind=kind))]),'a')

    def test_existing_campaign_lease_prevents_any_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);q=root/'build/diagnostics/dll_qualification/q';q.mkdir(parents=True)
            (root/'requirements.json').write_text('{}');(q/'requirements.json').write_text('{}')
            tasks=[dict(id=name,fast_rc=False,spec=dict(kind='phase')) for name in ['a','b']]
            (q/'manifest.json').write_text(json.dumps(dict(tasks=tasks)))
            with (q/'.execution.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with patch.object(probe,'ROOT',root),patch.object(probe,'engine',return_value='ngspice'),patch.object(probe,'validate'),patch.object(probe,'execute') as execute:
                    with self.assertRaises(BlockingIOError):probe.run(q,['a','b'],2)
                    execute.assert_not_called()
