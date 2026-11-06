# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys,unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_measured_balanced_joint_boundaries_v158 as p


class ConservativeNativeBoundaryTests(unittest.TestCase):
    def rows(self):
        delays=[(450,500),(457,510),(550,640),(558,650),(690,850),(630,690)]
        rows=[]
        for (c,f),(rise,fall) in zip(p.CODES,delays):
            r=dict(samples=[dict(rise_delay_ps=rise,fall_delay_ps=fall) for _ in range(2)],static_native_screen_passed=True,output_slew_domain_passed=True,whole_bank_rc_retained=True)
            if (c,f)==(0,0):r.update(joint_rc_zero_screen_passed=True,zero_code_fast_quarter_headroom_ps=1e6/410/4-500)
            rows.append(dict(spec=dict(p.native.spec('b2'),coarse=c,fine=f),result=r,error=None))
        return rows

    def test_complete_native_six_points_keep_dense_and_pvt_admission_false(self):
        rows=self.rows();r=p.compare(rows);self.assertTrue(r['six_point_native_screen_passed'])
        for field in ('dense_legal_code_coverage_proven','legal_code_table_admitted','all_pvt_covered','qualified_phy'):
            self.assertFalse(r[field])
        for field in ('static_native_screen_passed','output_slew_domain_passed','whole_bank_rc_retained'):
            changed=self.rows();changed[2]['result'][field]=False
            self.assertFalse(p.compare(changed)['six_point_native_screen_passed'])
        changed=self.rows();changed[0]['result']['joint_rc_zero_screen_passed']=False
        self.assertFalse(p.compare(changed)['six_point_native_screen_passed'])

    def test_conservative_intervals_reject_gaps_hidden_by_per_epoch_steps(self):
        rows=self.rows();z=rows[0]['result']['samples'];one=rows[1]['result']['samples']
        z[1]['rise_delay_ps']=461;one[0]['rise_delay_ps']=462;one[1]['rise_delay_ps']=475
        self.assertTrue(all(0<b['rise_delay_ps']-a['rise_delay_ps']<=20 for a,b in zip(z,one)))
        result=p.compare(rows);self.assertFalse(result['six_point_native_screen_passed'])
        step=next(s for s in result['steps'] if s['edge']=='rise' and s['from_fine']==0)
        self.assertEqual(step['maximum_change_ps'],25);self.assertFalse(step['adjacent_gap_passed'])
        rows=self.rows();fine=rows[4]['result']['samples'];coarse=rows[5]['result']['samples']
        fine[0]['rise_delay_ps']=631;fine[1]['rise_delay_ps']=650
        coarse[0]['rise_delay_ps']=630;coarse[1]['rise_delay_ps']=649
        self.assertTrue(all(a['rise_delay_ps']>b['rise_delay_ps'] for a,b in zip(fine,coarse)))
        result=p.compare(rows);self.assertFalse(result['six_point_native_screen_passed'])
        self.assertEqual(result['conservative_coarse_overlap']['rise_ps'],-18)

    def test_missing_duplicate_changed_pvt_invalid_or_failed_cases_cannot_pass(self):
        rows=self.rows();self.assertIsNone(p.compare(rows[:-1]))
        rows[2]['error']='missing event';self.assertIsNone(p.compare(rows))
        rows=self.rows();rows[1]['spec']=rows[0]['spec']
        with self.assertRaises(ValueError):p.compare(rows)
        rows=self.rows();rows[1]['spec']['temperature']=25
        with self.assertRaises(ValueError):p.compare(rows)
        rows=self.rows();rows[1]['result']['samples'][0]['rise_delay_ps']=float('nan')
        with self.assertRaises(ValueError):p.compare(rows)

    def test_only_three_fresh_fine_codes_preserve_complete_native_fixture(self):
        specs=p.specifications(p.native.spec('b2'));self.assertEqual([(s['coarse'],s['fine']) for s in specs],[(0,1),(0,15),(0,16)])
        ports=['IN','OUT',*[f'S{k}' for k in range(4)],*[f'E{k}' for k in range(31)],'VPWR','VGND']
        i=dict(top='bank',ports=ports,model='/model.lib',observations=dict(devices=[dict(terminals=['XD:drain.t0','XD:gate.t1','0','VDD'])],controls=[dict(node='XD:control.t2',control='fine0')]))
        for s in specs:
            actual=p.fixture(Path('/fixture'),i,s)
            expected=p.native.fixture(Path('/fixture'),dict(i,spec=s)).replace('OpenLVDS '+p.native.VERSION,'OpenLVDS '+p.VERSION,1)
            self.assertEqual(actual,expected);self.assertIn('.tran 2p 20n 0 2p',actual)
            self.assertIn('V(XD:gate.t1)',actual)
            self.assertEqual(sum(line.startswith('VE') and line.endswith(' 1.8') for line in actual.splitlines()),s['fine'])


if __name__=='__main__':unittest.main()
