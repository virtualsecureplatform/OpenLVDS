# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from recover_driver_cm_impedance import impedance


class RealACFrequencyCoordinate(unittest.TestCase):
    def test_unused_imaginary_frequency_padding_does_not_reject_real_frequency(self):
        f=np.logspace(4,9,401);z=50/(1+2j*np.pi*f*100*2e-12)
        w=np.column_stack([f+6.4e-310j,2e-6*z,2e-6*z])
        frequency,actual,_=impedance(['frequency','v(p)','v(n)'],w)
        np.testing.assert_array_equal(frequency,f)
        np.testing.assert_allclose(actual,z,rtol=1e-14)
        w[5,1]=complex(float('nan'),0)
        with self.assertRaises(ValueError):impedance(['frequency','v(p)','v(n)'],w)
