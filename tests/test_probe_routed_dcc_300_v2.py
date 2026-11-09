# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_routed_dcc_300_v2 as p


class RoutedDCCPilotTests(unittest.TestCase):
    def test_nine_declared_points_include_nominal_mixed_slew_and_both_duties(self):
        specs=p.specifications();self.assertEqual(len(specs),9)
        for s in specs:p.wiring.waveform.check(s)
        self.assertEqual({s['process'] for s in specs},{'ss','sf','tt'})
        self.assertEqual({s['mhz'] for s in specs},{300,310})
        self.assertEqual({(s['r_slew_10_90_ps'],s['f_slew_10_90_ps']) for s in specs},{(20,20),(250,250),(20,250),(250,20)})
        self.assertEqual({s['r_duty'] for s in specs},{.4,.5,.6})
        self.assertTrue(all(s['phase_error_ps']==0 for s in specs))
        self.assertEqual({(s['r_slew_10_90_ps'],s['f_slew_10_90_ps']) for s in specs if s['process']=='sf' and s['r_duty']==.6},{(250,250),(20,250),(250,20)})

    def test_native_and_physical_failures_and_missing_cases_never_pass(self):
        rows=[dict(task=dict(id=str(k),spec=s),error=None,result=dict(routed_point_passed=True)) for k,s in enumerate(p.specifications())]
        self.assertTrue(p.pilot_passed(rows))
        rows[0]['result']['routed_point_passed']=False;self.assertFalse(p.pilot_passed(rows))
        rows[0]['result']=None;rows[0]['error']='native failed';self.assertFalse(p.pilot_passed(rows))
        with self.assertRaisesRegex(ValueError,'all nine'):p.pilot_passed(rows[:-1])
