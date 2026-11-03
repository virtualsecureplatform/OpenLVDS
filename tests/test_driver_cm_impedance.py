# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import measure_driver_cm_impedance as measurement


class ClosedLoopCommonModeImpedance(unittest.TestCase):
    def test_total_current_normalization_matches_two_parallel_rc_shunts(self):
        frequency=np.logspace(4,9,401)
        exact=50/(1+2j*np.pi*frequency*100*2e-12)
        voltage=exact*2e-6
        wave=np.column_stack([frequency,voltage,voltage]).astype(complex)
        f,z,diff=measurement.impedance(['frequency','v(p)','v(n)'],wave)
        np.testing.assert_allclose(z,exact,rtol=1e-14)
        np.testing.assert_array_equal(diff,np.zeros(len(f)))
        with self.assertRaises(ValueError):measurement.impedance(['frequency','v(p)','v(n)'],wave[:-1])

    def test_static_excitation_preserves_supplies_bias_and_load(self):
        deck='''.include "/old/source.spice"
.options device temp=25
.options timeint method=gear reltol=1e-4 abstol=1e-12
VIO VDDIO 0 3.3
VDIG VDDD 0 1.8
VREF VREF 0 1.2
IREF IREF 0 35u
VD D 0 PWL(0n 0 10n 1.8)
XD D P N VREF IREF VDDIO VDDD 0 openlvds_driver
RT P N 100
CP P 0 2p
CN N 0 2p
.tran 1p 80n 0 1p
.print tran V(D) V(P) V(N)
.save i(VIO) i(VDIG)
.end
'''
        with patch.object(measurement,'ProbeNetwork'):
            result=measurement.fixture(deck,Path('/old'),Path('/new'),'same model',1.8,{})
        retained=['VIO VDDIO 0 3.3','VDIG VDDD 0 1.8','VREF VREF 0 1.2','IREF IREF 0 35u',
                  'RT P N 100','CP P 0 2p','CN N 0 2p']
        self.assertTrue(all(line in result for line in retained))
        self.assertIn('VD D 0 DC 1.8',result)
        self.assertIn('IACP 0 P DC 0 AC 1u',result)
        self.assertIn('IACN 0 N DC 0 AC 1u',result)
        self.assertIn('.temp 25',result)
        self.assertIn('.options klu',result)
        self.assertNotRegex(result,r'(?m)^\.(tran|dc)\b')
        with self.assertRaises(ValueError):measurement.fixture(deck,Path('/old'),Path('/new'),'same model',3.3,{})
