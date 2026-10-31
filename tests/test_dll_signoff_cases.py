# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from dll_signoff_cases import limiting_corners,recovery_cases,BASE_CORNERS
from qualify_dll_recovery import matches


def corner(name,pm,gm,t90):
    return dict(corner=name,passed=True,
        models=[dict(passed=True,phase_margin_min_deg=pm,gain_margin_min_db=gm) for _ in range(3)],
        transient_validation=[dict(passed=True,predicted_t90_ns=t90) for _ in range(2)])


class MeasuredCornerSelection(unittest.TestCase):
    def test_covers_distinct_margin_and_settling_limitations(self):
        report=dict(passed=True,all_pvt=True,results=[corner('fs_40',61,10,100),
            corner('sf_25',80,6.1,200),corner('ff_0',85,15,300)])
        self.assertEqual(limiting_corners(report),{('fs',40),('sf',25),('ff',0)})
        cases=recovery_cases(report)
        self.assertEqual(len(cases),15)
        self.assertEqual(set((p,t) for p,t,_ in cases),BASE_CORNERS|{('fs',40),('sf',25)})
        for p,t in BASE_CORNERS|limiting_corners(report):
            self.assertEqual({target for pp,tt,target in cases if (pp,tt)==(p,t)},{390,410,None})

    def test_partial_or_invalid_models_cannot_choose_a_release_corner(self):
        report=dict(passed=True,all_pvt=False,results=[corner('tt_25',70,10,200)])
        with self.assertRaises(ValueError):limiting_corners(report)
        report['all_pvt']=True;report['results'][0]['models'][1]['phase_margin_min_deg']=float('nan')
        with self.assertRaises(ValueError):limiting_corners(report)

    def test_existing_nominal_and_fast_cases_cannot_replace_recovery(self):
        task=dict(fast_rc=False,spec=dict(kind='loop',process='ss',temperature=0,mhz=400,duty=.5))
        self.assertFalse(matches(task,'ss',0,None))
        task['spec']['step_mhz']=390
        self.assertTrue(matches(task,'ss',0,390));self.assertFalse(matches(task,'ss',0,410))
        task['fast_rc']=True;self.assertFalse(matches(task,'ss',0,390))
        task['fast_rc']=False;task['spec'].update(step_mhz=None,interruption=True)
        self.assertTrue(matches(task,'ss',0,None))
