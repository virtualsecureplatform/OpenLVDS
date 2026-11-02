# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_driver_output_shape as shape
from driver_current_variant import source_variant
from driver_gate_taper import transform
from layout import circuits


class DriverOutputShapePilot(unittest.TestCase):
    def source(self):
        return transform(source_variant((shape.ROOT/'analog/openlvds.spice').read_text()),'taper_16_32_64')

    def test_only_two_existing_symmetric_mim_dimensions_change(self):
        before=circuits(self.source());after=circuits(shape.shaped(self.source()))
        for name,definition in before.items():
            if name!=shape.pilot.circuit.TOP:self.assertEqual(after[name],definition)
        old={r[0]:r for r in before[shape.pilot.circuit.TOP][1]};new={r[0]:r for r in after[shape.pilot.circuit.TOP][1]}
        self.assertEqual(old.keys(),new.keys())
        for name,row in old.items():
            if name in ['XCOUTP','XCOUTN']:self.assertEqual(new[name],(row[0],row[1],row[2],dict(w='30',l='30')))
            else:self.assertEqual(row,new[name])
        with self.assertRaises(ValueError):shape.shaped(shape.shaped(self.source()))

    def test_positive_initial_logic_preserves_all_breakpoint_times_and_other_sources(self):
        deck='Shape\nVIO VDDIO 0 3.3\nVD D 0 PWL(0n 0 9.95n 0 10.05n 1.8 11.2n 1.8 11.3n 0)\nVDIG VDDD 0 1.8\n'
        result=shape.stimulus_polarity(deck,True)
        self.assertIn('VD D 0 PWL(0n 1.8 9.95n 1.8 10.05n 0 11.2n 0 11.3n 1.8)',result)
        self.assertEqual(shape.stimulus_polarity(deck,False),deck)
        self.assertIn('VIO VDDIO 0 3.3',result);self.assertIn('VDIG VDDD 0 1.8',result)

    def waveform(self,ramp):
        ns=np.arange(0,80.002,.002);phase=(ns-10)%2.5
        d=np.interp(phase,[0,ramp/2,1.25-ramp/2,1.25+ramp/2,2.5-ramp/2,2.5],[0,-.34,-.34,.34,.34,0]);d[ns<=8]=-.34
        return np.column_stack([np.arange(len(ns)),ns*1e-9,1.25+d/2,1.25-d/2]),{'V(P)':2,'V(N)':3}

    def test_fresh_dc_calibration_and_twenty_eighty_edge_limits(self):
        w,h=self.waveform(.45);dc=shape.initial_dc(w,h)
        self.assertAlmostEqual(dc['differential_v'],-.34);self.assertAlmostEqual(dc['common_mode_v'],1.25)
        result=shape.transitions(w,h,-.34,.34)
        self.assertGreaterEqual(result['edges'],40);self.assertTrue(result['within_reference'])
        self.assertAlmostEqual(result['min_ps'],270,places=5);self.assertAlmostEqual(result['max_ps'],270,places=5)
        for ramp in [.3,.8]:self.assertFalse(shape.transitions(*self.waveform(ramp),-.34,.34)['within_reference'])
        with self.assertRaises(ValueError):shape.transitions(w,h,.34,-.34)

    def test_unrelated_contexts_are_not_admitted(self):
        with self.assertRaises(ValueError):shape.prepare(Path('/tmp/other'))
        with self.assertRaises(ValueError):shape.run(Path('/tmp/other'))


if __name__=='__main__':unittest.main()
