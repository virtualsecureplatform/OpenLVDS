# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import driver_restore_timestep_retry as retry


class DriverTimestepRetry(unittest.TestCase):
    def deck(self):
        return ('.include "/parent/library.spice"\nVIO VDDIO 0 3.3\n'
                '.tran 20p 188.049n 0 100p\n.print tran V(CLK0)\n.end\n')

    def test_only_maximum_integration_step_changes_after_original_fixture_binding(self):
        before, old_probes = retry.ORIGINAL_FIXTURE(self.deck(),Path('/parent'),Path('/new'))
        after, new_probes = retry.fixture(self.deck(),Path('/parent'),Path('/new'))
        self.assertEqual(new_probes,old_probes)
        self.assertEqual(after.replace('.tran 20p 188.049n 0 20p', '.tran 20p 188.049n 0 100p'),before)

    def test_unexpected_step_or_duplicate_transient_is_rejected(self):
        for deck in [self.deck().replace('0 100p','0 50p'),
                     self.deck().replace('.end', '.tran 20p 188.049n 0 100p\n.end')]:
            with self.assertRaises(ValueError):retry.fixture(deck,Path('/parent'),Path('/new'))

    def test_selection_captures_retry_and_restores_original_producer_after_failure(self):
        before=(retry.comparison.CODE,retry.comparison.fixture)
        with self.assertRaisesRegex(RuntimeError,'fixture error'):
            with retry.selection():
                self.assertIn('driver_restore_timestep_retry.py',retry.comparison.CODE)
                self.assertIs(retry.comparison.fixture,retry.fixture)
                raise RuntimeError('fixture error')
        self.assertEqual((retry.comparison.CODE,retry.comparison.fixture),before)


if __name__=='__main__':unittest.main()
