# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from exact_rc_candidate import parse,render,static_signature,witness
from reduce_rc import eliminate

SOURCE='''.subckt DUT A B C VSS
X1 A gate VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=1
C0 center VSS 1p
R0 A n0 1
R1 B n0 2
R2 C n0 3
R3 center n0 4
.ends DUT
'''


class ExactRCCandidate(unittest.TestCase):
    def reduce(self):
        reference=parse(SOURCE);candidate=deepcopy(reference)
        self.assertEqual(eliminate(candidate['graph'],candidate['protected'],8),1)
        return reference,parse(render(candidate,8))

    def test_devices_capacitors_and_their_terminal_names_are_unchanged(self):
        reference,reduced=self.reduce()
        self.assertEqual(static_signature(reference),static_signature(reduced))
        self.assertEqual(reference['protected'],reduced['protected'])
        self.assertNotIn('n0',reduced['graph']);self.assertIn('center',reduced['graph'])
        self.assertIn('C0 center VSS 1p',reduced['kept'])

    def test_nonphysical_or_nonflattened_input_is_rejected(self):
        with self.assertRaises(ValueError):parse(SOURCE.replace('R0 A n0 1','R0 A n0 0'))
        with self.assertRaises(ValueError):parse(SOURCE+SOURCE)
        with self.assertRaises(ValueError):parse(SOURCE.replace('R0 A n0 1','R0 A n0 {value}'))

    @unittest.skipUnless(importlib.util.find_spec('scipy'),'Use build/tools/exact-rc-venv/bin/python')
    def test_independent_sparse_solver_accepts_exact_reduction_and_rejects_changed_resistance(self):
        reference,reduced=self.reduce()
        self.assertTrue(witness(reference,reduced)['passed'])
        a=next(iter(reduced['graph']));b=next(iter(reduced['graph'][a]))
        reduced['graph'][a][b]*=1.01;reduced['graph'][b][a]*=1.01
        self.assertFalse(witness(reference,reduced)['passed'])
