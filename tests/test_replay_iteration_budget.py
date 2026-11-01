# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from replay_selected_receiver_iterations import iteration_fixture


class ReplayIterationBudget(unittest.TestCase):
    def test_only_newton_effort_changes(self):
        deck = 'Replay\n.options timeint method=gear reltol=1e-4 abstol=1e-12\n.tran 5p 188.049n 0 5p\n.end\n'
        changed = iteration_fixture(deck)
        self.assertEqual(changed.replace('.options itl4=100\n', ''), deck)
        with self.assertRaises(ValueError):
            iteration_fixture(changed)


if __name__ == '__main__':
    unittest.main()
