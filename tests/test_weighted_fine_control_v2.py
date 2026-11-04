# SPDX-License-Identifier: GPL-3.0-only
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import weighted_fine_control_v2 as circuit
import probe_weighted_fine_control_v2 as pilot
import verify_weighted_fine_control_v2 as verifier


class WeightedControlTests(unittest.TestCase):
    def wave(self,overstress=False,stuck_cap=False):
        spec=pilot.specifications()[1];t=np.arange(0,12001,10);state=np.minimum((t//2000).astype(int),5)
        values={'data':np.full(len(t),1.8),'vdd':np.full(len(t),1.8)}
        for i in range(5):
            bit=np.array([1.8 if (pilot.CODES[j]>>i)&1 else 0 for j in state])
            values['b'+str(i)]=bit.copy();values['en'+str(i)]=bit.copy();values['enb'+str(i)]=1.8-bit
            values[f'xd.xfine{i}.cap']=bit.copy()
        if overstress:values['en0'][210]=2.05
        if stuck_cap:values['xd.xfine4.cap'][(t>=9500)&(t<=9900)]=1.8
        return ['time',*['v('+n+')' for n in values]],np.column_stack([t/1e12,*values.values()])

    def measured(self,**kw):
        device=dict(name='XD:test',model=circuit.fine.N,limit_v=1.95,terminals=['EN0','B0','0','0'])
        with patch.object(pilot,'validate',return_value=self.wave(**kw)):
            return pilot.measure(Path('/fixture'),pilot.specifications()[1],[device])

    def test_transient_overstress_and_incomplete_keeper_discharge_remain_failures(self):
        self.assertTrue(self.measured()['component_pilot_passed'])
        over=self.measured(overstress=True);self.assertFalse(over['terminal_screen_passed']);self.assertFalse(over['component_pilot_passed'])
        stuck=self.measured(stuck_cap=True);self.assertFalse(stuck['control_settling_passed']);self.assertFalse(stuck['component_pilot_passed'])

    def test_source_fine_geometry_is_unchanged_and_actual_driver_ports_are_mapped(self):
        orders={circuit.native.CLOCK_BUFFER:['X','VGND','A','VPWR'],circuit.native.MODELS['inv_8']:['Y','A','VPWR','VGND'],
                circuit.fine.old.native.SC+'buf_1':['A','VGND','VNB','VPB','VPWR','X'],circuit.fine.old.native.SC+'inv_1':['A','VGND','VNB','VPB','VPWR','Y']}
        for mode in circuit.MODES:
            text=circuit.source(mode,orders);self.assertTrue(text.startswith(circuit.fine.fine_cells('root').rstrip()))
            self.assertEqual(text.count('Xfine'),5)
        guarded=circuit.source('guarded',orders)
        self.assertIn('Xbuffer0 EN0 VSS B0 VDD '+circuit.native.CLOCK_BUFFER,guarded)
        spec=pilot.specifications()[0]
        with patch.dict(os.environ,PDK_ROOT='/pdk'):deck=pilot.fixture(Path('/fixture'),spec,[])
        self.assertIn('VDD VDD 0 1.8',deck);self.assertIn('.tran 1p 12n 0 1p',deck)
        self.assertEqual(pilot.CODES,[0,31,0,16,15,0])

    def test_failed_source_reference_does_not_hide_guarded_profile_but_every_bias_is_required(self):
        good=dict(component_pilot_passed=True,maximum_terminal_difference_v=1.9,control_settling_passed=True,terminal_screen_passed=True)
        rows=[dict(task=dict(spec=s),result=copy.deepcopy(good)) for s in pilot.specifications()]
        rows[2]['result'].update(component_pilot_passed=False,terminal_screen_passed=False,maximum_terminal_difference_v=2.08)
        groups=verifier.assess(rows);self.assertTrue(groups[0]['component_pilot_passed']);self.assertFalse(groups[1]['component_pilot_passed'])
        with self.assertRaises(ValueError):verifier.assess(rows[:-1])


if __name__=='__main__':unittest.main()
