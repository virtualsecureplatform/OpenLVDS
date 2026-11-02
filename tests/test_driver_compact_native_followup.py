# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from continue_driver_compact_native import admissible_owner
from continue_receiver_spec_verified import wait_state


class CompactNativeFollowupOwnership(unittest.TestCase):
    def test_exact_live_producer_or_terminal_receipt_required(self):
        relative='build/diagnostics/driver_compact_native_pilot/example'
        live=dict(MainPID='123',ActiveState='active',InvocationID='same',
                  ExecStart='python /work/OpenLVDS/scripts/probe_driver_compact_native.py run /work/OpenLVDS/'+relative)
        admissible_owner(live,relative,False)
        for changed in [dict(live,ActiveState='failed'),dict(live,ExecStart='python other.py'),dict(MainPID='0')]:
            with self.assertRaises(ValueError): admissible_owner(changed,relative,False)
        admissible_owner(dict(MainPID='0'),relative,True)

    def test_restart_or_missing_receipt_cannot_trigger_matrix(self):
        expected=dict(MainPID='123',InvocationID='first')
        self.assertEqual(wait_state(expected,expected,True),'waiting')
        self.assertEqual(wait_state(dict(MainPID='0'),expected,True),'ready')
        with self.assertRaises(ValueError):wait_state(dict(MainPID='0'),expected,False)
        with self.assertRaises(ValueError):wait_state(dict(MainPID='124',InvocationID='second'),expected,False)
