# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_phase_prefix_v2 as proof


class PrefixComparisonTests(unittest.TestCase):
    def fixture(self):
        # Analytic test signal only; production comparisons read both native files.
        time=np.arange(0,62001,1.)
        signal=sum(.9*(np.tanh((time-(22000+i*10000))/20)-np.tanh((time-(26000+i*10000))/20)) for i in range(4))
        names=['time']+['v('+n+')' for n in ['rfast','ffast','rth','fth']]
        short=np.column_stack([time*1e-12,*([signal]*4)])
        long=short.copy();long[:,0]+=180e-9
        return names,long,short

    def test_translation_compares_without_changing_samples(self):
        names,long,short=self.fixture();original=short.copy()
        result=proof.compare(names,long,names,short,20000)
        self.assertLess(result['maximum_voltage_error_v'],1e-10)
        self.assertLess(result['maximum_edge_error_ps'],1e-8)
        np.testing.assert_array_equal(original,short)

    def test_voltage_difference_and_timing_shift_are_reported(self):
        names,long,short=self.fixture();short[:,1]+=.02
        result=proof.compare(names,long,names,short,20000)
        self.assertGreater(result['maximum_voltage_error_v'],proof.LIMITS['maximum_voltage_error_v'])
        names,long,short=self.fixture();short[:,1:]=np.roll(short[:,1:],1,axis=0)
        result=proof.compare(names,long,names,short,20000)
        self.assertGreater(result['maximum_edge_error_ps'],proof.LIMITS['maximum_edge_error_ps'])

    def test_missing_probe_and_duplicate_edge_are_rejected(self):
        names,long,short=self.fixture()
        with self.assertRaisesRegex(ValueError,'probe coverage'):proof.compare(names,long,list(reversed(names)),short,20000)
        short[(short[:,0]>23e-9)&(short[:,0]<24e-9),1]=0
        with self.assertRaisesRegex(ValueError,'Missing/extra edge'):proof.compare(names,long,names,short,20000)
