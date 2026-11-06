# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from itertools import combinations
from pathlib import Path
import random
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import common_delay_sequence_v296 as p

class CommonDelaySequenceTests(unittest.TestCase):
    def curves(self,coarse=16,fine=16,step=5,base=100):
        # Synthetic conservative intervals test selection; no native proof.
        return {corner:{edge:[p.Delay(code,base+step*code+index*.1+(edge=='fall')*.05,
            base+step*code+index*.1+(edge=='fall')*.05+.2) for code in range(coarse*fine)]
            for edge in ('rise','fall')} for index,corner in enumerate(p.PVT)}

    def test_tx_common_order_brackets_all_quarter_targets_and_keeps_admission_false(self):
        r=p.select(self.curves(),'tx',16,16)
        self.assertTrue(r['common_sequence_found']);self.assertTrue(r['target_10ps_gaps_met'])
        self.assertEqual(len(r['witnesses']),30)
        for w in r['witnesses']:
            self.assertLessEqual(w['first_upper_ps'],1e6/410/4)
            self.assertGreaterEqual(w['last_lower_ps'],1e6/390/4)
            self.assertGreater(w['minimum_increment_ps'],0);self.assertLessEqual(w['maximum_increment_ps'],10)
        for key in ('native_characterization_verified','updates_qualified','legal_code_table_admitted','electrical_qualification_passed','qualified_phy'):
            self.assertFalse(r[key])

    def test_rx_covers_conservative_longest_period_plus_500ps(self):
        r=p.select(self.curves(64,16),'rx',64,16)
        self.assertTrue(r['common_sequence_found'])
        self.assertAlmostEqual(r['policy']['rx_span_ps'],3064.102564102564,places=8)
        self.assertTrue(all(w['conservative_span_ps']>=r['policy']['rx_span_ps'] for w in r['witnesses']))
        self.assertTrue(all(x['coarse']==x['code']//16 and x['fine']==x['code']%16 for x in r['raw_coarse_fine']))

    def test_largest_declared_rx_configuration_keeps_full_input_coverage(self):
        r=p.select(self.curves(256,32),'rx',256,32)
        self.assertTrue(r['common_sequence_found']);self.assertEqual(r['raw_codes_per_curve'],8192)
        self.assertEqual(len(r['selected_curves']),30)
        self.assertTrue(all(x['coarse']==x['code']//32 and x['fine']==x['code']%32 for x in r['raw_coarse_fine']))

    def test_missing_pvt_edge_raw_code_or_duplicate_is_rejected(self):
        good=self.curves()
        for fault in ('pvt','edge','missing','duplicate'):
            bad=deepcopy(good)
            if fault=='pvt':bad.pop(p.PVT[-1])
            elif fault=='edge':bad[p.PVT[0]].pop('fall')
            elif fault=='missing':bad[p.PVT[0]]['rise'].pop()
            else:bad[p.PVT[0]]['rise'][-1]=bad[p.PVT[0]]['rise'][0]
            with self.assertRaises(ValueError):p.select(bad,'tx',16,16)
        for mode,c,f in [('rx',16,16),('tx',8,16),('tx',16,8)]:
            with self.assertRaises(ValueError):p.select(good,mode,c,f)

    def test_20ps_is_hard_limit_10ps_is_preferred_target(self):
        r=p.select(self.curves(step=12),'tx',16,16)
        self.assertTrue(r['common_sequence_found']);self.assertEqual(r['search_gap_ps'],20)
        self.assertFalse(r['target_10ps_gaps_met'])
        self.assertFalse(p.select(self.curves(step=21),'tx',16,16)['common_sequence_found'])

    def test_range_failure_never_claims_a_shorter_sequence_as_success(self):
        self.assertFalse(p.select(self.curves(base=700),'tx',16,16)['common_sequence_found'])
        self.assertFalse(p.select(self.curves(base=0,step=1),'tx',16,16)['common_sequence_found'])
        self.assertFalse(p.select(self.curves(64,16,step=2),'rx',64,16)['common_sequence_found'])

    def test_a_corner_specific_reversal_is_filtered_by_one_common_code_order(self):
        curves=self.curves()
        # Only one corner reverses 15/16. Neither corner gets its own ROM.
        table=curves[p.PVT[-1]]['fall'];a,b=table[15],table[16]
        table[15]=p.Delay(15,b.lo_ps,b.hi_ps);table[16]=p.Delay(16,a.lo_ps,a.hi_ps)
        r=p.select(curves,'tx',16,16);self.assertTrue(r['common_sequence_found'])
        self.assertFalse(15 in r['codes'] and 16 in r['codes'])
        self.assertLessEqual(max(w['maximum_increment_ps'] for w in r['witnesses']),20)
        self.assertTrue(all([d['code'] for d in table]==r['codes'] for table in r['selected_curves'].values()))

    def test_overlap_in_one_edge_prevents_universal_ordering(self):
        curves=self.curves()
        curves[p.PVT[-1]]['fall']=[p.Delay(code,500,501) for code in range(256)]
        self.assertFalse(p.select(curves,'tx',16,16)['common_sequence_found'])

    def test_input_order_does_not_choose_different_corner_specific_sequences(self):
        curves=self.curves();expected=p.select(curves,'tx',16,16)['codes']
        rng=random.Random(296)
        for record in curves.values():
            for table in record.values():rng.shuffle(table)
        self.assertEqual(p.select(curves,'tx',16,16)['codes'],expected)

    def test_common_physical_order_can_interleave_raw_codes(self):
        curves=self.curves()
        for record in curves.values():
            for table in record.values():
                a,b=table[15],table[16]
                table[15]=p.Delay(15,b.lo_ps,b.hi_ps);table[16]=p.Delay(16,a.lo_ps,a.hi_ps)
        path=p.select(curves,'tx',16,16)['codes']
        self.assertLess(path.index(16),path.index(15))

    def test_incomparable_start_labels_are_retained_until_range_can_be_decided(self):
        pairs={0:(0,4),1:(4,0),2:(6,6),3:(12,8)}
        points={code:tuple(p.Delay(code,value,value) for value in pair) for code,pair in pairs.items()}
        # At node 2, start 0 is earlier in one dimension, start 1 in the other.
        # Only start 1 can cover a conservative seven-ps span at node 3.
        self.assertEqual(p.find_path(points,6,'rx',rx_span=7),[1,2,3])

    def test_interval_path_search_matches_exhaustive_small_graphs(self):
        rng=random.Random(967)
        for _ in range(64):
            points={c:tuple(p.Delay(c,(v:=rng.randrange(10)),v+rng.choice((0,.2,.5))) for d in range(2)) for c in range(7)}
            ordered=sorted(points,key=lambda c:(points[c][0].lo_ps,c))
            for mode in ('tx','rx'):
                expected=False
                for length in range(2,8):
                    for path in combinations(ordered,length):
                        edges=all(all(b.lo_ps>a.hi_ps and b.hi_ps-a.lo_ps<=4 for a,b in zip(points[x],points[y])) for x,y in zip(path,path[1:]))
                        coverage=(all(a.hi_ps<=3 and b.lo_ps>=5 for a,b in zip(points[path[0]],points[path[-1]])) if mode=='tx'
                            else all(b.lo_ps-a.hi_ps>=3 for a,b in zip(points[path[0]],points[path[-1]])))
                        if edges and coverage:expected=True;break
                    if expected:break
                found=p.find_path(points,4,mode,quarter_min=3,quarter_max=5,rx_span=3)
                self.assertEqual(found is not None,expected,(mode,points))

if __name__=='__main__':unittest.main()
