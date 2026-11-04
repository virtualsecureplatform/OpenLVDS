# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import weighted_bank_flow_v2 as flow


class WeightedFlowTests(unittest.TestCase):
    def spec(self):
        ports=['IN','OUT',*[f'C{i}' for i in range(15)],*[f'B{i}' for i in range(5)],'VPWR','VGND']
        cells=[dict(name='tie',model=flow.SC+'conb_1',pins=dict(HI='high',LO='low',**flow.POWER))]
        cells += [dict(name=f'coarse_buffer{i}',model=flow.SC+'buf_4',pins=dict(A=f'C{i}',X=f'coarse{i}',**flow.POWER)) for i in range(15)]
        cells += [dict(name=f'g{i}',model='hard',pins=dict(A='IN',Y=f'g{i}',VPWR='VPWR',VGND='VGND')) for i in range(78)]
        return dict(top='bank',ports=ports,cells=cells)

    def test_power_adapter_keeps_all_cells_and_refuses_changed_body_wiring(self):
        spec=self.spec();text=flow.verilog(spec)
        self.assertEqual(text.count('dont_touch="true"'),94)
        buf=next(line for line in text.splitlines() if 'coarse_buffer0 (' in line)
        self.assertIn('.A(C0)',buf);self.assertIn('.X(coarse0)',buf);self.assertNotIn('.VNB(',buf)
        self.assertIn('hard g0 (.A(IN),.Y(g0),.VPWR(VPWR),.VGND(VGND))',text)
        bad=deepcopy(spec);bad['cells'][1]['pins']['VNB']='IN'
        with self.assertRaises(ValueError):flow.verilog(bad)

    def test_native_interface_checker_rejects_gate_changes_and_bad_tap_power(self):
        spec=self.spec();rows=[[c['name'],c['model'],p,n] for c in spec['cells'] for p,n in c['pins'].items()]
        self.assertTrue(flow.connections_pass(rows,spec['ports'],spec))
        bad=deepcopy(rows);bad[-1][-1]='VPWR'
        self.assertFalse(flow.connections_pass(bad,spec['ports'],spec))
        self.assertFalse(flow.connections_pass(rows+[['extra',flow.SC+'buf_1','A','IN']],spec['ports'],spec))
        self.assertFalse(flow.connections_pass(rows+[['tap',flow.SC+'tapvpwrvgnd_1','VGND','VPWR']],spec['ports'],spec))
        self.assertFalse(flow.connections_pass(rows,spec['ports'][:-1],spec))

    def test_control_strip_is_site_aligned_and_contains_all_sixteen_controls(self):
        spec=self.spec();macros={'hard':dict(instances=dict(fine0=dict(location=[210.,10.],orientation='N'),shared_base=dict(location=[210.,150.],orientation='N')))}
        sizes={'hard':dict(width=20.,height=10.),flow.SC+'buf_4':dict(width=2.76,height=2.72),flow.SC+'conb_1':dict(width=1.38,height=2.72)}
        places=flow.control_placements(spec,sizes,macros,[0.,0.,305.,468.])
        self.assertEqual(len(places),16)
        for p in places.values():
            x,y=p['location'];self.assertAlmostEqual(x/.46,round(x/.46),places=6)
            self.assertAlmostEqual(y/2.72,round(y/2.72),places=6)
            self.assertGreater(y,160.);self.assertLess(x,295.)
