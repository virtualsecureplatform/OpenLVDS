# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import weighted_fine_control_v3 as circuit
import probe_weighted_fine_control_v3 as pilot
import verify_weighted_fine_control_v3 as verifier


class PhysicalFineControlTests(unittest.TestCase):
    def network(self):
        n=circuit.unit.name(0)
        return f'''.subckt {n} NODE EN ENB VDD VSS
Xn c0 EN NODE VSS {circuit.fine.N} w=.42 l=.15
Xp NODE ENB c1 VDD {circuit.fine.P} w=.84 l=.15
Xk VSS ENB c2 VSS {circuit.fine.N} w=.42 l=.15
Xload c3 VSS {circuit.fine.CAP} w=2 l=3
Xctrl ENB VSS {circuit.fine.CAP} w=2 l=2
R0 c0 c3 2
R1 c1 c3 2
R2 c2 c3 2
R3 c3 c4 2
C0 c4 EN 2f
.ends {n}
'''

    def test_plate_observation_follows_resistors_and_preserves_all_terminals(self):
        nodes=circuit.cap_nodes(self.network(),0)
        self.assertEqual(nodes,[f'XD:Xfine0:c{i}' for i in range(5)])
        self.assertNotIn('XD:Xfine0:EN',nodes)
        for replacement in [('R2 c2 c3 2','C2 c2 c3 2f'),
                            ('R3 c3 c4 2','R3 c3 EN 2'),
                            ('R0 c0 c3 2','R0 c0 c3 -2'),
                            ('w=2 l=3','w=2 l=2')]:
            with self.assertRaises(ValueError):
                circuit.cap_nodes(self.network().replace(*replacement),0)

    def test_every_fine_cell_uses_its_actual_port_order(self):
        orders={circuit.native.CLOCK_BUFFER:['X','VGND','A','VPWR'],
                circuit.native.MODELS['inv_8']:['Y','A','VPWR','VGND']}
        orders.update({circuit.unit.name(b):['VSS','ENB','NODE','VDD','EN'] for b in range(5)})
        text=circuit.source('guarded',orders)
        self.assertNotIn('weighted_root_',text)
        self.assertNotIn('XSWN',text)
        for b in range(5):
            self.assertIn(f'Xfine{b} VSS ENB{b} DATA VDD EN{b} '+circuit.unit.name(b),text)
        orders[circuit.unit.name(4)]=['NODE','EN','VDD','VSS']
        with self.assertRaises(ValueError):circuit.source('guarded',orders)

    def wave(self,stuck=False,overstress=False):
        t=np.arange(0,12001,10);state=np.minimum((t//2000).astype(int),5)
        values={'data':np.full(len(t),1.8),'vdd':np.full(len(t),1.8)}
        for bit in range(5):
            v=np.array([1.8 if pilot.CODES[j]>>bit&1 else 0 for j in state])
            values['b'+str(bit)]=v.copy();values['en'+str(bit)]=v.copy();values['enb'+str(bit)]=1.8-v
            for cap in ('near','far'):values[f'xd.xfine{bit}.{cap}']=v.copy()
        if stuck:values['xd.xfine4.far'][(t>=9500)&(t<=9900)]=1.8
        if overstress:values['xd.xfine4.far'][210]=2.05
        return ['time',*['v('+n+')' for n in values]],np.column_stack([t/1e12,*values.values()])

    def witness(self):
        return dict(mos=[dict(name='XD:Xfine4:test',model=circuit.fine.N,limit_v=1.95,
                             terminals=['XD:Xfine4:far','EN4','0','0'])],
                    cap_nodes={str(b):[f'XD:Xfine{b}:{n}' for n in ['near','far']] for b in range(5)})

    def test_far_plate_settling_and_transient_native_stress_are_required(self):
        def measured(**kw):
            with patch.object(pilot,'validate',return_value=self.wave(**kw)):
                return pilot.measure(Path('/fixture'),pilot.specifications()[1],self.witness())
        self.assertTrue(measured()['component_pilot_passed'])
        self.assertFalse(measured(stuck=True)['control_settling_passed'])
        self.assertFalse(measured(overstress=True)['terminal_screen_passed'])

    def test_deck_keeps_bias_sequence_and_requests_real_plate_nodes(self):
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            deck=pilot.fixture(Path('/fixture'),pilot.specifications()[1],self.witness())
        self.assertIn('VDD VDD 0 1.8',deck)
        self.assertIn('.tran 1p 12n 0 1p',deck)
        self.assertIn('V(XD:Xfine4:far)',deck)
        self.assertNotIn('V(XD:Xfine4:CAP)',deck)
        self.assertEqual(pilot.CODES,[0,31,0,16,15,0])
        with self.assertRaises(ValueError):verifier.assess([])
