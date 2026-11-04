# SPDX-License-Identifier: GPL-3.0-only
import errno
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_clocking_when_idle_v2 as waiting


class ConsumerWaitTests(unittest.TestCase):
    def test_lock_contention_retries_same_context_without_starting_a_producer(self):
        out=Path('/artifact');pause=Mock()
        verify=Mock(side_effect=[BlockingIOError(errno.EAGAIN,'locked'),BlockingIOError(errno.EAGAIN,'locked'),'receipt'])
        self.assertEqual(waiting.verify_when_idle(out,verify,pause),'receipt')
        self.assertEqual([call.args for call in verify.call_args_list],[(out,)]*3)
        self.assertEqual(pause.call_count,2)

    def test_real_proof_failures_and_other_io_errors_are_not_retried(self):
        for error in [ValueError('Changed witness'),BlockingIOError(errno.EIO,'unreadable')]:
            verify=Mock(side_effect=error);pause=Mock()
            with self.assertRaises(type(error)):waiting.verify_when_idle(Path('/artifact'),verify,pause)
            verify.assert_called_once();pause.assert_not_called()
