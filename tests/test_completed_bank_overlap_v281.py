# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import analyze_completed_bank_overlap_v281 as diagnostic


class CompletedBankOverlapTests(unittest.TestCase):
    def rows(self):
        result=[]
        for k,(coarse,fine,duty) in enumerate([(0,31,.4),(0,31,.6),(1,0,.5)]):
            delay=120 if fine else 100
            result.append(dict(case=f'one_native_parent/{k}',source_version='native-version',
                task=dict(spec=dict(coarse=coarse,fine=fine,duty=duty,process='ss',temperature=40,cycles=8)),
                decomposition={edge:dict(total_delays_ps=[delay]*8) for edge in ('rise','fall')}))
        return result

    def test_overlap_is_a_necessary_condition_and_does_not_admit_unsampled_zero(self):
        report=diagnostic.compare(self.rows());self.assertTrue(report['all_completed_histories_overlap'])
        for flag in ('zero_code_verified','complete_four_point_pilot_verified','all_pvt_covered','electrical_qualification_passed','qualified_phy'):
            self.assertFalse(report[flag])

    def test_passing_means_cannot_hide_cross_history_gap(self):
        rows=self.rows();rows[0]['decomposition']['rise']['total_delays_ps']=[105]*8
        rows[2]['decomposition']['rise']['total_delays_ps'][-1]=110
        r=diagnostic.compare(rows)
        self.assertFalse(r['all_completed_histories_overlap'])
        self.assertEqual(r['edges']['rise']['conservative_overlap_ps'],-5)
        self.assertEqual(r['edges']['fall']['conservative_overlap_ps'],20)

    def test_missing_nonfinite_or_mixed_condition_histories_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'both duty endpoints'):diagnostic.compare(self.rows()[:2])
        for mutation in ('duplicate','missing_edge','nonfinite','different_parent','different_process'):
            rows=deepcopy(self.rows())
            if mutation=='duplicate':rows[1]=deepcopy(rows[0])
            if mutation=='missing_edge':rows[0]['decomposition']['rise']['total_delays_ps'].pop()
            if mutation=='nonfinite':rows[0]['decomposition']['fall']['total_delays_ps'][0]=float('nan')
            if mutation=='different_parent':rows[1]['case']='another_parent/1'
            if mutation=='different_process':rows[1]['task']['spec']['process']='ff'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):diagnostic.compare(rows)

    def test_completed_native_p20n10_receipt_reproduces_negative_rising_overlap(self):
        parent=diagnostic.ROOT/'build/diagnostics/completed_bank_overlap_v281/e25f79acb2473627'
        if not (parent/'summary.json').exists():self.skipTest('Completed native overlap diagnostic unavailable')
        report=json.loads((parent/'summary.json').read_text());identity=json.loads((parent/'manifest.json').read_text())['identity']
        self.assertTrue(all(diagnostic.sha(diagnostic.ROOT/n)==h for n,h in identity['inputs'].items()))
        self.assertEqual(json.loads((parent/'state.json').read_text()),dict(status='complete',analysis_completed=True,qualified_phy=False))
        self.assertEqual(diagnostic.compare(report['rows']),report['comparison'])
        result=report['comparison'];self.assertFalse(result['all_completed_histories_overlap'])
        self.assertAlmostEqual(result['edges']['rise']['conservative_overlap_ps'],-69.84920366760252,places=6)
        self.assertAlmostEqual(result['edges']['rise']['fine_endpoints'][0]['conservative_first_coarse_overlap_ps'],-3.06337719667408,places=6)
        self.assertAlmostEqual(result['edges']['fall']['conservative_overlap_ps'],63.005731617258334,places=6)
        self.assertFalse(result['zero_code_verified']);self.assertFalse(result['complete_four_point_pilot_verified'])
        self.assertFalse(report['parameters_changed']);self.assertFalse(report['qualified_phy'])


if __name__=='__main__':unittest.main()
