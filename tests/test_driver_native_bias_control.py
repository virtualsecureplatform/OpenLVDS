# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_driver_native_bias_pilot import native_bias_only


class NativeBiasOnlyControl(unittest.TestCase):
    SOURCE='''.subckt lvds_bias IREF NB VA VS
R0 IREF NB 1
.ends lvds_bias
.subckt openlvds_driver_core A Y
R0 A Y 1
.ends openlvds_driver_core
'''
    def test_only_native_bias_block_can_change(self):
        native=self.SOURCE.replace('R0 IREF NB 1','R0 IREF NB 2')
        self.assertEqual(native_bias_only(self.SOURCE,native),native)
        with self.assertRaises(ValueError):native_bias_only(self.SOURCE,native.replace('R0 A Y 1','R0 A Y 2'))
        with self.assertRaises(ValueError):native_bias_only(self.SOURCE,native+'* unrelated difference\n')

    def test_duplicate_bias_control_rejected(self):
        with self.assertRaises(ValueError):native_bias_only(self.SOURCE,self.SOURCE)
