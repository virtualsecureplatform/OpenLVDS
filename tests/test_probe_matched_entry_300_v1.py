# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_matched_entry_300_v1 as p


class MatchedPilotCoverageTests(unittest.TestCase):
    def rows(self):
        base=dict(process='ss',temperature=40,frequency_mhz=310,coarse=0,fine=0,cycles=8,stop_ns=40,load_ff=20)
        specs=p.specifications(base)
        return [dict(task=dict(id=str(k),spec=specs[k%2],centered=k<2,setting=k%2),
                     error=None,result=dict(two_bank_zero_pilot_passed=True)) for k in range(4)]

    def test_all_fresh_pairs_required_and_physical_failure_retained(self):
        rows=self.rows();pairs={'0':dict(passed=True),'1':dict(passed=True)}
        self.assertTrue(p.pilot_passed(rows,pairs))
        rows[0]['result']['two_bank_zero_pilot_passed']=False
        self.assertFalse(p.pilot_passed(rows,pairs))
        with self.assertRaises(ValueError):p.pilot_passed(rows[:2],pairs)
        rows=self.rows();rows[3]['task']['spec']=dict(rows[3]['task']['spec'],duty=.5)
        with self.assertRaises(ValueError):p.pilot_passed(rows,pairs)
        with self.assertRaises(ValueError):p.pilot_passed(self.rows(),{'0':dict(passed=True)})

    def test_declared_settings_and_invalid_base_refused(self):
        rows=self.rows()
        self.assertEqual([(r['task']['spec']['input_slew_ps'],r['task']['spec']['duty']) for r in rows],[(100,.5),(100,.6),(100,.5),(100,.6)])
        with self.assertRaises(ValueError):p.specifications(dict(rows[0]['task']['spec'],frequency_mhz=300))
