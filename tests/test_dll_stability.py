# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import tempfile
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dll_stability import margins
from native_ac import read_complex


class Stability(unittest.TestCase):
    def test_complex_reader_accepts_frequency_grid_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ac.raw'
            data=np.array([[10,1+2j],[100,3+4j]],dtype='<c16')
            header='Flags: complex\nNo. Variables: 2\nNo. Points: 2\nVariables:\n0 frequency frequency grid=3\n1 v(out) voltage\nBinary:\n'
            path.write_bytes(header.encode()+data.tobytes())
            names,values=read_complex(path)
            self.assertEqual(names,['frequency','v(out)'])
            np.testing.assert_equal(values,data)
    def test_stable_and_poorly_compensated_loops_are_distinguished(self):
        f=np.geomspace(1e3,1e9,2001);s=2j*np.pi*f
        stable=margins(f,2*np.pi*1e6/(s*(1+s/(2*np.pi*10e6))),1,-1,400e6)
        unstable=margins(f,2*np.pi*30e6/(s*(1+s/(2*np.pi*1e6))),1,-1,400e6)
        self.assertTrue(stable['passed'])
        self.assertFalse(unstable['passed'])

    def test_wrong_feedback_sign_cannot_pass(self):
        with self.assertRaises(ValueError):margins([1,2,3],[1j,2j,3j],1,1,400e6)
