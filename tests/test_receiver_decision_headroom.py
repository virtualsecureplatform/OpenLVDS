# SPDX-License-Identifier: GPL-3.0-only
import copy
from pathlib import Path
import sys
import unittest
import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import receiver_decision_headroom as headroom
from layout import circuits

ROOT=Path(__file__).resolve().parents[1]


class DecisionHeadroom(unittest.TestCase):
    def fixture(self):
        wave=np.zeros((145,11));wave[:,1]=np.arange(145)*1e-9
        headers={'INDEX':0,'TIME':1,'V(P)':2,'V(N)':3,'V(Q)':4,'V(XR:XCORE:PP)':5,
            'V(XR:XCORE:PN)':6,'V(XR:XCORE:CO)':7,'V(XR:XCORE:CL)':8,'V(XR:XCORE:CT)':9,'V(XR:XCORE:NBC)':10}
        wave[:,5:]=[1.0,1.2,1.5,.9,.1,.8]
        source=headroom.source.source_variant((ROOT/'analog/openlvds.spice').read_text(),True)
        rows={r[0]:r for r in circuits(source)[headroom.source.TOP][1]}
        return wave,headers,rows

    def test_reports_five_devices_and_settled_headroom_without_inventing_regions(self):
        wave,headers,rows=self.fixture();result=headroom.terminal_metrics(wave,headers,rows)
        self.assertEqual(set(result['devices']),set(headroom.DEVICES))
        self.assertTrue(all(d['thin_guard_passed'] for d in result['devices'].values()))
        self.assertAlmostEqual(result['devices']['XCT']['settled_min_abs_vds_v'],.1)
        self.assertNotIn('saturation',result)

    def test_transient_stress_between_static_sample_times_is_observed(self):
        wave,headers,rows=self.fixture();wave[40,7]=2.05;wave[40,9]=.0001
        result=headroom.terminal_metrics(wave,headers,rows)['devices']
        self.assertFalse(result['XC1']['thin_guard_passed'])
        self.assertAlmostEqual(result['XC1']['maximum_terminal_difference']['voltage_v'],2.05)
        self.assertAlmostEqual(result['XC1']['maximum_terminal_difference']['time_ns'],40)
        self.assertAlmostEqual(result['XCT']['settled_min_abs_vds_v'],.1)

    def test_incomplete_wave_or_unobserved_terminal_is_refused(self):
        wave,headers,rows=self.fixture()
        with self.assertRaisesRegex(ValueError,'Incomplete'):headroom.terminal_metrics(wave[:50],headers,rows)
        rows=copy.deepcopy(rows);rows['XC0'][1][0]='NOT_OBSERVED'
        with self.assertRaisesRegex(ValueError,'Missing decision terminal'):headroom.terminal_metrics(wave,headers,rows)


if __name__=='__main__':unittest.main()
