# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_regular_regenerated_dense_v294 as p

class RoutedDenseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Synthetic aggregation records are not native electrical evidence.
        cls.matrix=p.specifications();cls.rows=[]
        for s in cls.matrix:
            delay=500+s['coarse']*160+s['fine']*6
            r={k:True for k in p.NATIVE_FLAGS}
            r.update(whole_bank_rc_retained=True,terminal_stress=[dict(passed=True)]*1529,
                programming_gates=[dict(passed=True)]*173,controls=[dict(passed=True)],
                edge_delays_ps={edge:[delay+k*.1 for k in range(8)] for edge in ('rise','fall')})
            cls.rows.append(dict(spec=s,result=r,error=None))

    def test_all_64_codes_reuse_only_three_identical_periodic_conditions(self):
        self.assertEqual({(s['coarse'],s['fine']) for s in self.matrix},{(c,f) for c in (0,1) for f in range(32)})
        old=p.source.specifications(p.source.native.spec())
        self.assertEqual(len([s for s in self.matrix if s in old]),3)
        self.assertEqual(len([s for s in self.matrix if s not in old]),61)
        self.assertTrue(all(s['frequency_mhz']==410 and s['duty']==.5 and s['process']=='ss' and s['temperature']==40 for s in self.matrix))
        r=p.assess(self.rows,self.matrix);self.assertTrue(r['raw_adjacent_dense_feasibility_passed']);self.assertEqual(len(r['adjacent_fine_intervals']),124)
        self.assertTrue(r['target_10ps_adjacent_gaps_met']);self.assertEqual(len(r['delay_intervals']),64)
        for key in ('all_pvt_covered','full_coarse_range_covered','legal_code_table_admitted','qualified_phy'):
            self.assertFalse(r[key])

    def test_positive_mean_cannot_hide_cross_history_reversal_at_15_16_boundary(self):
        rows=deepcopy(self.rows);row=next(r for r in rows if (r['spec']['coarse'],r['spec']['fine'])==(0,16))
        row['result']['edge_delays_ps']['rise'][0]-=8
        r=p.assess(rows,self.matrix)
        self.assertTrue(r['all_64_dense_codes_characterized'])
        self.assertFalse(r['all_adjacent_fine_intervals_passed']);self.assertFalse(r['raw_adjacent_dense_feasibility_passed'])
        failed=next(s for s in r['adjacent_fine_intervals'] if s['coarse']==0 and s['from_fine']==15 and s['edge']=='rise')
        self.assertLess(failed['minimum_increment_ps'],0)

    def test_maximum_possible_gap_not_mean_increment_is_bounded(self):
        rows=deepcopy(self.rows);row=next(r for r in rows if (r['spec']['coarse'],r['spec']['fine'])==(1,16))
        row['result']['edge_delays_ps']['fall'][-1]+=15
        r=p.assess(rows,self.matrix);self.assertFalse(r['raw_adjacent_dense_feasibility_passed'])
        failed=next(s for s in r['adjacent_fine_intervals'] if s['coarse']==1 and s['from_fine']==15 and s['edge']=='fall')
        self.assertGreater(failed['maximum_increment_ps'],20)

    def test_native_failure_missing_history_or_nonfinite_delays_cannot_pass(self):
        for field in ('terminal_screen_passed','current_downstream_250ps_slew_domain_passed','repeated_delay_screen_passed'):
            rows=deepcopy(self.rows);rows[0]['result'][field]=False
            self.assertFalse(p.assess(rows,self.matrix)['all_64_dense_codes_characterized'])
        for values in ([500]*7,[500]*7+[float('nan')]):
            rows=deepcopy(self.rows);rows[0]['result']['edge_delays_ps']['rise']=values
            r=p.assess(rows,self.matrix);self.assertFalse(r['complete_eight_edge_histories']);self.assertFalse(r['all_adjacent_fine_intervals_passed'])

    def test_missing_duplicate_wrong_clock_and_source_failure_are_rejected(self):
        self.assertIsNone(p.assess(self.rows[:-1],self.matrix))
        rows=list(self.rows);rows[-1]=rows[0]
        with self.assertRaisesRegex(ValueError,'64 unique'):p.assess(rows,self.matrix)
        rows=deepcopy(self.rows);rows[0]['spec']['duty']=.6
        with self.assertRaises(ValueError):p.assess(rows,self.matrix)
        rows=deepcopy(self.rows);rows[0]['error']='native failure'
        self.assertIsNone(p.assess(rows,self.matrix))

    def test_all_generated_fine_codes_retain_complete_original_periodic_fixture(self):
        i=dict(top='native_bank',ports=['IN','OUT','VPWR','VGND'],model='model.lib',observations=dict(devices=[],controls=[]));out=Path('/unused-fixture')
        for s in self.matrix:
            text=p.fixture(out,i,s)
            self.assertEqual(text.replace('OpenLVDS '+p.VERSION,'OpenLVDS '+p.source.VERSION,1),p.source.fixture(out,i,s))
            self.assertEqual(text.count('tanh('),16);self.assertIn('.tran 2p 25n 0 2p',text)
            self.assertIn('method=gear reltol=1e-4 abstol=1e-12',text)

    def test_unadmitted_parent_cannot_create_dense_campaign(self):
        with patch.object(p.source,'bound',side_effect=ValueError('Native prerequisites absent')):
            with self.assertRaises(ValueError):p.prepare(Path('/unadmitted-bank'))

if __name__=='__main__':unittest.main()
