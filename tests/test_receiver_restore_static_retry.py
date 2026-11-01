# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from retry_receiver_restore_static import tighten


class ReceiverRestoreStaticRetry(unittest.TestCase):
    def test_only_maximum_step_changes(self):
        deck = 'Static fixture\n.options timeint method=gear reltol=1e-4 abstol=1e-12\nVP P 0 PWL(0 0 1n 1)\n.tran 10p 144n 0 50p\n.end\n'
        changed = tighten(deck)
        self.assertEqual(changed.replace('.tran 10p 144n 0 1p', '.tran 10p 144n 0 50p'), deck)
        self.assertEqual(tighten(changed), changed)

    def test_duration_output_step_start_and_ambiguous_commands_are_refused(self):
        deck = '.tran 10p 144n 0 50p\n'
        for changed in [deck.replace('144n', '72n'), deck.replace('10p', '5p'),
                        deck.replace(' 0 ', ' 1n '), deck+deck, deck.replace('50p', '100p')]:
            with self.assertRaises(ValueError):
                tighten(changed)


if __name__ == '__main__':
    unittest.main()
