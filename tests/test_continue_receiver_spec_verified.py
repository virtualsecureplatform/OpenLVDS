# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from continue_receiver_spec_verified import wait_state


class TerminalScientificReceipt(unittest.TestCase):
    def test_unloaded_owner_needs_terminal_evidence(self):
        expected=dict(MainPID='42',ActiveState='active',InvocationID='original',ExecStart='producer')
        live=dict(MainPID='0',ActiveState='inactive',InvocationID='',ExecStart='')
        self.assertEqual(wait_state(live,expected,True),'ready')
        with self.assertRaisesRegex(ValueError,'without terminal'):wait_state(live,expected,False)

    def test_exact_live_producer_is_waited_on_even_after_receipt_appears(self):
        expected=dict(MainPID='42',ActiveState='active',InvocationID='original',ExecStart='producer')
        for terminal in [False,True]:self.assertEqual(wait_state(expected,expected,terminal),'waiting')

    def test_changed_live_owner_is_not_misclassified_as_completion(self):
        expected=dict(MainPID='42',ActiveState='active',InvocationID='original',ExecStart='producer')
        for terminal in [False,True]:
            with self.assertRaisesRegex(ValueError,'Live prerequisite'):wait_state(dict(expected,MainPID='43',InvocationID='different'),expected,terminal)


if __name__=='__main__':unittest.main()
