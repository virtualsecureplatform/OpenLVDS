# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import inspect_failed_dcc_prefix_300_v1 as p


class AbortedPrefixTests(unittest.TestCase):
    def raw(self,points=0):
        header=(f'No. Variables: 3\nNo. Points: {points}\nVariables:\n0 time time\n1 v(in) voltage\n2 v(vdd) voltage\nBinary:\n').encode()
        return header+np.array([[0,0,1.8],[4e-14,0,1.8]],dtype='<f8').tobytes()

    def test_all_stored_failed_rows_retained(self):
        names,w=p.read_prefix(self.raw());self.assertEqual(len(w),2)
        self.assertEqual(names,['time','v(in)','v(vdd)']);self.assertEqual(w[-1,0],4e-14)

    def test_complete_header_partial_record_and_nonfinite_refused(self):
        for raw in (self.raw(points=2),self.raw()+b'partial',self.raw().replace(np.float64(1.8).tobytes(),np.float64(float('nan')).tobytes(),1)):
            with self.subTest(),self.assertRaises(ValueError):p.read_prefix(raw)
