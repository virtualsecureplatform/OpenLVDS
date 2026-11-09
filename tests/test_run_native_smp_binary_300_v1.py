# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_native_smp_binary_300_v1 as p
import run_native_binary_v2 as original


class SMPTranslationTests(unittest.TestCase):
    def test_actual_completed_deck_differs_only_in_linear_solver_selection(self):
        path=p.ROOT/'build/diagnostics/tg2_next_bank_early_zero_pilot_300_v2/23dee609d6ca5e51/0/bench.cir'
        text=path.read_text();klu,names=original.translate(text);smp,other=p.translate(text)
        self.assertEqual(names,other)
        first,rest=klu.split('\n',1)
        self.assertEqual(smp,first+'\n'+rest.removeprefix('.options klu\n'))
        self.assertIn('.options method=gear reltol=1e-4 abstol=1e-12',smp)
        self.assertIn('.tran 2p 40n 0 2p',smp)
        self.assertNotIn('.options klu',smp)

    def test_conflicting_explicit_solver_selection_refused(self):
        for option in ('.options klu','.option klu'):
            with self.subTest(option=option),self.assertRaisesRegex(ValueError,'explicit source KLU'):
                p.translate('Title\n'+option+'\n.print tran V(IN)\n.end\n')
