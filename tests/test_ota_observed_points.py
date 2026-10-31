# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import ota_operating_points as ota


POINT=dict(id='ff_native',cm_v=.34,ctrl_v=.834,diff_v=.0015)


class ObservedOTAPoints(unittest.TestCase):
    def test_guards_preserve_the_observed_common_mode_and_control_pairing(self):
        groups,rows=ota.grid([POINT,dict(id='ss_native',cm_v=.73,ctrl_v=1.08,diff_v=.004)])
        self.assertEqual(len(groups),18)
        self.assertFalse(any(row['cm_v']<.4 and row['ctrl_v']>1 for row in rows))
        self.assertAlmostEqual(min(row['cm_v'] for row in rows),.32)
        with self.assertRaises(ValueError):ota.grid([])

    def test_thick_input_devices_are_not_misclassified_as_thin_oxide(self):
        source='''.subckt lvds_phase_ota UF DF OUT PB VDDIO VDDD VSS
XTAIL T PB VDDIO VDDIO sky130_fd_pr__pfet_g5v0d10v5 w=2 l=2.5
XM OUT G VSS VSS sky130_fd_pr__nfet_01v8 w=8 l=1
.ends lvds_phase_ota
'''
        devices=ota.thin_devices(source)
        self.assertEqual(len(devices),1)
        self.assertEqual(devices[0]['nodes'],['OUT','XO:G','0','0'])
        with self.assertRaises(ValueError):ota.thin_devices(source.replace('UF DF OUT PB','DF UF OUT PB'))

    def characterize(self,offset=.005,nonlinear=False,unsafe=False,rail=3.3):
        groups,rows=ota.grid([POINT]);t=np.arange(0,len(rows)*10+.05,.05)*1e-9
        at=np.minimum((t/(10e-9)).astype(int),len(rows)-1)
        cm=np.array([r['cm_v'] for r in rows])[at];ctrl=np.array([r['ctrl_v'] for r in rows])[at]
        diff=np.array([r['diff_v'] for r in rows])[at]
        current=40e-6*(diff-700*diff**2) if nonlinear else 40e-6*(diff-offset)
        names=['time','i(vforce)','v(u)','v(d)','v(out)','v(vddio)','v(vddd)','v(unsafe)']
        wave=np.column_stack([t,current,cm+diff/2,cm-diff/2,ctrl,np.full(len(t),rail),
            np.full(len(t),1.8),np.full(len(t),-1.2 if unsafe else .6)])
        device=dict(name='thin_test',nodes=['OUT','UNSAFE','0','0'])
        with patch.object(ota,'read_raw',return_value=(names,wave)):
            return ota.analyze(Path('raw'),groups,rows,[device])

    def test_gm_and_offset_use_the_forced_output_current_and_actual_differential(self):
        result=self.characterize()
        self.assertTrue(result['passed'],result)
        for point in result['points']:
            self.assertAlmostEqual(point['gm_zero_s'],40e-6)
            self.assertAlmostEqual(point['gm_operating_s'],40e-6)
            self.assertAlmostEqual(point['input_offset_v'],.005)

    def test_offset_and_gain_at_the_actual_differential_both_gate(self):
        self.assertFalse(self.characterize(offset=.012)['passed'])
        result=self.characterize(nonlinear=True)
        self.assertTrue(all(p['gm_zero_s']>1e-6 for p in result['points']))
        self.assertTrue(all(p['gm_operating_s']<0 for p in result['points']))
        self.assertFalse(result['passed'])

    def test_device_stress_and_fixed_rails_cannot_be_hidden_by_good_gain(self):
        self.assertFalse(self.characterize(unsafe=True)['passed'])
        self.assertFalse(self.characterize(rail=3.2)['passed'])

    def test_fixture_retains_fixed_rails_one_bias_and_actual_signal_grid(self):
        groups,rows=ota.grid([POINT]);devices=[dict(name='xm',nodes=['OUT','U','0','0'])]
        text=ota.fixture(Path('/case'),'ff',0,rows,devices,'/pdk/sky130.lib.spice')
        for value in ['VA VDDIO 0 3.3','VD VDDD 0 1.8','IB PB 0 35u','.options device temp=0']:
            self.assertIn(value,text)
        self.assertEqual(text.count('lvds_bias'),1)
        self.assertNotIn('V(0)',text)
