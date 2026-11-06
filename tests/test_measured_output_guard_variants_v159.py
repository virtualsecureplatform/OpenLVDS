# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_measured_output_guard_variants_v159 as p


class OutputGuardHypothesesTests(unittest.TestCase):
    def result(self):return dict(samples=[dict(rise_delay_ps=500.,fall_delay_ps=550.) for _ in range(2)],joint_rc_sparse_point_passed=True,static_native_screen_passed=True,output_slew_domain_passed=True,whole_bank_rc_retained=True)

    def test_hypothesis_cannot_admit_original_bank_and_zero_uses_both_epochs(self):
        original=self.result()
        with patch.object(p.source,'measure',return_value=original):r=p.measure(Path('/case'),{},p.native.spec('b2'))
        self.assertTrue(r['hypothesis_point_checks_passed']);self.assertTrue(original['whole_bank_rc_retained'])
        for flag in ('joint_rc_sparse_point_passed','whole_bank_rc_retained','candidate_layout_qualified','qualified_phy'):self.assertFalse(r[flag])
        wide=self.result();wide['samples'][0]['fall_delay_ps']=700
        with patch.object(p.source,'measure',return_value=wide):self.assertFalse(p.measure(Path('/case'),{},p.native.spec('b2'))['hypothesis_point_checks_passed'])
        failed=self.result();failed['static_native_screen_passed']=False
        with patch.object(p.source,'measure',return_value=failed):self.assertFalse(p.measure(Path('/case'),{},p.native.spec('b2'))['hypothesis_point_checks_passed'])

    def test_both_variants_get_all_three_complete_fixed_load_native_fixtures(self):
        tasks=p.specifications(p.native.spec('b2'));self.assertEqual(len(tasks),6)
        self.assertEqual([(t['variant'],t['spec']['fine']) for t in tasks[:2]],[('shared',31),('none',31)])
        ports=['IN','OUT',*[f'S{k}' for k in range(4)],*[f'E{k}' for k in range(31)],'VPWR','VGND']
        i=dict(top='bank',ports=ports,model='/model.lib',observations=dict(devices=[dict(terminals=['XD:drain.t0','XD:gate.t1','0','VDD'])],controls=[dict(node='XD:control.t2',control='fine0')]))
        for task in tasks:
            text=p.fixture(Path('/candidate'),i,task)
            expected=p.native.fixture(Path('/candidate')/task['variant'],dict(i,spec=task['spec'])).replace('OpenLVDS '+p.native.VERSION,'OpenLVDS '+p.VERSION,1)
            self.assertEqual(text,expected)
            for fragment in ('CLOAD OUT 0 20f','.tran 2p 20n 0 2p','V(XD:gate.t1)'):self.assertIn(fragment,text)

    def test_three_point_comparison_never_grants_geometry_or_release(self):
        rows=[]
        for task in p.specifications(p.native.spec('b2')):
            spec=task['spec'];c,f=spec['coarse'],spec['fine'];rise,fall={(0,0):(450,500),(0,31):(690,850),(1,0):(630,690)}[c,f]
            r=dict(samples=[dict(rise_delay_ps=rise,fall_delay_ps=fall) for _ in range(2)],hypothesis_point_checks_passed=True,zero_code_fast_quarter_headroom_ps=109. if c==f==0 else None)
            rows.append(dict(task=task,spec=spec,result=r,error=None))
        reports=p.compare(rows);self.assertTrue(all(r['hypothesis_feasible'] for r in reports))
        for r in reports:
            for flag in ('candidate_layout_qualified','bank_admitted','electrical_qualification_passed','qualified_phy'):self.assertFalse(r[flag])
        rows[0]['result']['hypothesis_point_checks_passed']=False;self.assertFalse(p.compare(rows)[0]['hypothesis_feasible'])
        rows[0]['error']='incomplete';self.assertIsNone(p.compare(rows))


if __name__=='__main__':unittest.main()
