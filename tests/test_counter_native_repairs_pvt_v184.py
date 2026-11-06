# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_counter_native_repairs_pvt_v184 as p


class RepairedCounterPvtMatrix(unittest.TestCase):
    def rows(self):return [dict(task=dict(spec=s),error=None,result=dict(counter_feasibility_passed=True,minimum_clock_low_voltage_margin_v=.1,storage_component_physical_rc_qualified=True,setter_guard_geometry_qualified=True)) for s in p.specifications()]

    def test_all_authorized_pvt_duty_and_stopped_clock_combinations_are_present(self):
        specs=p.specifications();self.assertEqual(len(specs),90)
        self.assertEqual({(s['process'],s['temperature'],s['duty'],s['stop_level']) for s in specs},
                         {(c,t,d,v) for c in ('tt','ff','ss','fs','sf') for t in (0,25,40) for d in (.4,.5,.6) for v in (0,1)})
        self.assertEqual({s['mhz'] for s in specs},{410});self.assertEqual({s['input_slew_ps'] for s in specs},{100})
        r=p.assess(self.rows(),specs);self.assertTrue(r['component_pvt_screen_passed'])
        for key in ('whole_clock_rc_qualified','hardware_warmup_qualified','electrical_qualification_passed','qualified_phy'):self.assertFalse(r[key])

    def test_all_numeric_timing_and_physical_gates_remain_required(self):
        specs=p.specifications();rows=self.rows();self.assertIsNone(p.assess(rows[:-1],specs))
        for key in ('counter_feasibility_passed','storage_component_physical_rc_qualified','setter_guard_geometry_qualified'):
            changed=deepcopy(rows);changed[0]['result'][key]=False
            self.assertFalse(p.assess(changed,specs)['component_pvt_screen_passed'])
        for margin in (-1e-9,float('nan'),float('inf')):
            changed=deepcopy(rows);changed[0]['result']['minimum_clock_low_voltage_margin_v']=margin
            self.assertFalse(p.assess(changed,specs)['component_pvt_screen_passed'])
        changed=deepcopy(rows);changed[0]['task']['spec']=changed[1]['task']['spec']
        with self.assertRaises(ValueError):p.assess(changed,specs)
        changed=deepcopy(specs);changed[0]['duty']=.7
        with self.assertRaises(ValueError):p.assess(self.rows(),changed)


if __name__=='__main__':unittest.main()
