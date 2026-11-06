# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_discharge_fine_clock_matrix_v221 as p


class CompleteDischargeFineClockMatrix(unittest.TestCase):
    def rows(self,specs):
        return [dict(spec=s,error=None,result=dict(current_clock_interface_screen_passed=True,
                    edge_delays_ps={edge:[700 if s['fine']==31 else 600 if s['coarse']==1 else 400]*8 for edge in ('rise','fall')})) for s in specs]

    def test_all_nine_frequency_duty_combinations_for_every_sparse_code(self):
        variants=[p.source.variants()[0],p.source.variants()[-1]];matrix=p.specifications(variants)
        self.assertEqual(len(matrix),54)
        for v in variants:
            selected=[s for s in matrix if p.source.key(s)==p.source.key(v)]
            self.assertEqual({(s['coarse'],s['fine'],s['frequency_mhz'],s['duty']) for s in selected},
                             {(c,f,mhz,d) for c,f in ((0,0),(0,31),(1,0)) for mhz in (390,400,410) for d in (.4,.5,.6)})
            pilot=[s for s in p.source.specifications() if p.source.key(s)==p.source.key(v)]
            missing=p.remaining(selected,[dict(spec=s) for s in pilot]);self.assertEqual(len(missing),23)
            self.assertEqual((missing[0]['coarse'],missing[0]['fine'],missing[0]['frequency_mhz'],missing[0]['duty']),(0,0,410,.6))
        with self.assertRaises(ValueError):p.specifications(variants[::-1])
        with self.assertRaises(ValueError):p.specifications([variants[0],variants[0]])
        with self.assertRaises(ValueError):p.specifications([])

    def test_only_complete_passing_pilot_variants_are_admitted(self):
        rows=self.rows(p.source.specifications());summary=dict(rows=rows,comparison=p.source.compare(rows))
        self.assertEqual(p.admitted(summary),p.source.variants())
        changed=deepcopy(rows);changed[0]['result']['current_clock_interface_screen_passed']=False
        summary=dict(rows=changed,comparison=p.source.compare(changed))
        self.assertEqual(p.admitted(summary),p.source.variants()[1:])
        summary['comparison'][0]['component_hypothesis_passed']=True
        with self.assertRaises(ValueError):p.admitted(summary)
        for row in changed:row['result']['current_clock_interface_screen_passed']=False
        with self.assertRaises(ValueError):p.admitted(dict(rows=changed,comparison=p.source.compare(changed)))
        with self.assertRaises(ValueError):p.admitted(dict(rows=rows[:-1],comparison=None))

    def test_zero_duty60_failure_and_any_history_or_overlap_loss_block_admission(self):
        variants=p.source.variants()[:1];matrix=p.specifications(variants);rows=self.rows(matrix)
        result=p.assess(rows,variants)[0];self.assertTrue(result['complete_27_case_clock_stress_screen_passed'])
        self.assertTrue(result['frequency_duty_sparse_matrix_complete'])
        for key in ('new_common_routing_qualified','dense_legal_table_qualified','all_pvt_covered','electrical_qualification_passed','qualified_phy'):self.assertFalse(result[key])
        index=next(k for k,s in enumerate(matrix) if s['coarse']==s['fine']==0 and s['frequency_mhz']==410 and s['duty']==.6)
        changed=deepcopy(rows);changed[index]['result']['current_clock_interface_screen_passed']=False
        self.assertFalse(p.assess(changed,variants)[0]['complete_27_case_clock_stress_screen_passed'])
        for values in ([],[float('nan')]*8):
            changed=deepcopy(rows);changed[0]['result']['edge_delays_ps']['rise']=values
            self.assertFalse(p.assess(changed,variants)[0]['complete_27_case_clock_stress_screen_passed'])
        index=next(k for k,s in enumerate(matrix) if s['fine']==31)
        for edge in ('rise','fall'):
            changed=deepcopy(rows);changed[index]['result']['edge_delays_ps'][edge][0]=590
            self.assertFalse(p.assess(changed,variants)[0]['complete_27_case_clock_stress_screen_passed'])
        self.assertIsNone(p.assess(rows[:-1],variants))
        changed=deepcopy(rows);changed[0]['spec']=changed[1]['spec']
        with self.assertRaises(ValueError):p.assess(changed,variants)


if __name__=='__main__':unittest.main()
