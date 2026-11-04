# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_phase_threshold_slew_v2 as source
import verify_phase_threshold_slew_v2 as proof


class ThresholdSlewTests(unittest.TestCase):
    def test_complement_of_prior_matched_order_covers_full_36(self):
        specs=source.specifications()
        self.assertEqual(len(specs),30)
        keys={(s['reference_slew_ps'],s['feedback_slew_ps'],s['swap'],s['offset_ps'],s['positive_offset']) for s in specs}
        self.assertEqual(len(keys),30)
        self.assertTrue(all(s['settle_ps']==20000 for s in specs))
        self.assertEqual({(s['reference_slew_ps'],s['feedback_slew_ps']) for s in specs},{(100,100),(20,250),(250,20)})
        keys.update((100,100,0,o,p) for o in [-20,0,20] for p in [0,1])
        self.assertEqual(len(keys),36)

    def test_orders_are_independent_and_missing_offset_rejects_group(self):
        rows=[dict(task=dict(spec=s),error=None,result=dict(correct_sign_fraction=1,frontend_stress_passed=True,common_mode_passed=True))
              for s in source.specifications()]
        groups=proof.groups(rows)
        self.assertEqual(len(groups),10)
        self.assertTrue(all(g['source_threshold_and_health_passed'] for g in groups))
        rows[0]['result']['frontend_stress_passed']=False
        self.assertEqual(sum(not g['source_threshold_and_health_passed'] for g in proof.groups(rows)),1)
        self.assertEqual(sum(not g['source_threshold_and_health_passed'] for g in proof.groups(rows[1:])),1)
