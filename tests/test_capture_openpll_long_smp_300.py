# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import capture_openpll_long_smp_300 as p

class BaselineSolverClockTests(unittest.TestCase):
    def test_reference_duration_deck_is_byte_identical(self):
        original=(p.BASE/'bench.cir').read_text()
        self.assertEqual(p.deck(original,70),original)
    def test_long_deck_changes_only_duration_and_reset_hold(self):
        original=(p.BASE/'bench.cir').read_text();long=p.deck(original,20000)
        undo=long.replace('20000.0n 40000.0n','70.0n 140.0n').replace('.tran 2.0p 20000.0n','.tran 2.0p 70.0n')
        self.assertEqual(undo,original)
        self.assertNotIn('.option klu',long.lower())
    def test_altered_solver_or_tolerances_rejected(self):
        original=(p.BASE/'bench.cir').read_text()
        with self.assertRaises(ValueError):p.deck(original+'\n.option klu\n',20000)
        with self.assertRaises(ValueError):p.deck(original.replace('reltol=1e-3','reltol=1e-2'),20000)
        with self.assertRaises(ValueError):p.prepare(70)

if __name__=='__main__':unittest.main()
