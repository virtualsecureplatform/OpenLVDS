# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from diagnose_native_ff_guards_v2 import inspect,private_node


class NativeFfGuardTargetTests(unittest.TestCase):
    def test_identifies_positive_and_negative_private_excursions_at_violating_pair(self):
        values={'a':np.array([0.,0.]),'XR0:r0__boost':np.array([1.8,2.25]),'XR0:r0__low':np.array([0.,-.3]),'vdd':np.array([1.8,1.8])}
        devices=[dict(name='XR0:Xr0__X0',model='native',limit_v=1.95,terminals=['a','XR0:r0__boost','XR0:r0__low','vdd'])]
        r=inspect(np.array([0.,1.]),values.__getitem__,devices)
        self.assertEqual(r['private_nodes'],['boost','low']);self.assertFalse(r['uncovered_violations'])
        self.assertIsNone(private_node('XD:r0__boost'))

    def test_public_pin_violation_does_not_get_hidden_by_a_private_guard_list(self):
        values={'a':np.array([0.,0.]),'CLK':np.array([1.8,2.1]),'vdd':np.array([1.8,1.8])}
        devices=[dict(name='XR0:Xr0__X0',model='native',limit_v=1.95,terminals=['a','CLK','a','vdd'])]
        r=inspect(np.array([0.,1.]),values.__getitem__,devices)
        self.assertTrue(r['uncovered_violations']);self.assertFalse(r['private_nodes'])


if __name__=='__main__':unittest.main()
