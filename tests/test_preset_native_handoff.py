# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from queue_preset_native_screen import ready


class PresetNativeHandoff(unittest.TestCase):
    def test_both_gates_are_required(self):
        self.assertFalse(ready(dict(status='running'),dict(passed=True)))
        self.assertFalse(ready(dict(status='completed'),None))
        self.assertTrue(ready(dict(status='completed'),dict(passed=True)))

    def test_any_failed_gate_holds_candidate(self):
        with self.assertRaisesRegex(ValueError,'source screen failed'):
            ready(dict(status='completed_with_failures'),dict(passed=True))
        with self.assertRaisesRegex(ValueError,'RC audit failed'):
            ready(dict(status='completed'),dict(passed=False))
