# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_dcdl_batch_v2 as consumer
import test_dcdl_batch_v2 as fixture

class ControlMarginTests(unittest.TestCase):
    def measure(self,wave):
        with patch.object(consumer.h,'read_raw',return_value=wave):
            return consumer.measure(Path('/fixture'),fixture.DenseDCDLTests().task())
    def test_observed_native_feedthrough_is_not_a_reference_error(self):
        names,w=fixture.DenseDCDLTests().data()
        # The native low inverter output showed 26 mV positive feedthrough.
        t=w[:,0];w[(t>12.6e-9)&(t<12.7e-9),names.index('v(eb0)')]=.026
        result=self.measure((names,w))
        self.assertTrue(result['custom_mos_stress_passed'])
        self.assertAlmostEqual(result['controls'][1]['internal_max_deviation_v'],.026)
        self.assertFalse(result['legal_code_table_admitted'])
    def test_logic_margin_and_stimulus_checks_remain_separate(self):
        for node,voltage in [('eb0',.181),('e0',1.785)]:
            names,w=fixture.DenseDCDLTests().data();t=w[:,0]
            w[(t>12.6e-9)&(t<12.7e-9),names.index('v('+node+')')]=voltage
            with self.assertRaises(ValueError):self.measure((names,w))
    def test_thin_oxide_stress_cannot_be_waived_by_logic_margins(self):
        names,w=fixture.DenseDCDLTests().data();w[:,names.index('v(xd.cap17)')]=2.1
        result=self.measure((names,w))
        self.assertFalse(result['custom_mos_stress_passed'])
        self.assertFalse(result['custom_mos_stress'][17*3]['passed'])
