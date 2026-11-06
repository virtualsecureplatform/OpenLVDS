# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import os,sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_static_phase_clock_drive_pvt_v156 as p


class ClockDrivePvtTests(unittest.TestCase):
    def rows(self):
        return [dict(task=dict(spec=s),result=dict(counter_feasibility_passed=True,minimum_clock_low_voltage_margin_v=.1),error=None) for s in p.specifications()]

    def test_full_matrix_and_exact_four_case_reuse(self):
        specs=p.specifications();self.assertEqual(len(specs),90)
        self.assertEqual({(s['process'],s['temperature'],s['duty'],s['stop_level']) for s in specs},
                         {(c,t,d,l) for c in ('tt','ff','ss','fs','sf') for t in (0,25,40) for d in (.4,.5,.6) for l in (0,1)})
        old=p.original.specifications();self.assertTrue(all(s in specs for s in old));self.assertEqual(len([s for s in specs if s not in old]),86)
        self.assertEqual((specs[0]['process'],specs[0]['temperature']),('ff',0))
        self.assertTrue(all(s['mhz']==410 and s['input_slew_ps']==100 for s in specs))

    def test_fixture_retains_duration_step_all_native_probes_and_actual_pvt(self):
        devices=[dict(name='sample',terminals=['XD:gate.t1','VDD','0'])]
        with patch.dict(os.environ,{'PDK_ROOT':'/pdk'}):
            for s in p.specifications():
                old=p.original.fixture(Path('/fixture'),s,devices)
                actual=p.fixture(Path('/fixture'),s,devices)
                self.assertEqual(actual,old.replace('OpenLVDS '+p.original.VERSION,'OpenLVDS '+p.VERSION,1))
                self.assertIn('.options device temp='+str(s['temperature']),actual)
                self.assertIn('sky130.lib.spice" '+s['process'],actual)
                self.assertIn('V(XD:gate.t1)',actual)
                self.assertIn('.tran 1p 26n 0 1p',actual)

    def test_native_low_phase_and_complete_unique_coverage_are_required(self):
        rows=self.rows();specs=p.specifications();r=p.assess(rows,specs)
        self.assertTrue(r['component_pvt_screen_passed']);self.assertFalse(r['qualified_phy']);self.assertFalse(r['whole_clock_rc_qualified'])
        self.assertIsNone(p.assess(rows[:-1],specs))
        rows[0]['result']['counter_feasibility_passed']=False;self.assertFalse(p.assess(rows,specs)['component_pvt_screen_passed'])
        for margin in (-.001,float('nan'),float('inf')):
            changed=self.rows();changed[0]['result']['minimum_clock_low_voltage_margin_v']=margin
            self.assertFalse(p.assess(changed,specs)['component_pvt_screen_passed'])
        changed=self.rows();changed[0]['error']='missing phase';self.assertIsNone(p.assess(changed,specs))
        changed=self.rows();changed[1]['task']=changed[0]['task']
        with self.assertRaises(ValueError):p.assess(changed,specs)


if __name__=='__main__':unittest.main()
