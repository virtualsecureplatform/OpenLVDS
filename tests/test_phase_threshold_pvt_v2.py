# SPDX-License-Identifier: GPL-3.0-only
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import expand_phase_threshold_pvt_v2 as source
import verify_phase_threshold_pvt_v2 as proof


class ThresholdPVTTests(unittest.TestCase):
    def specifications(self):return source.specifications(json.loads((source.ROOT/'requirements.json').read_text()))

    def test_all_540_unique_points_include_both_swaps_and_extreme_slews_at_15_pvt(self):
        specs=self.specifications();self.assertEqual(len(specs),540)
        self.assertEqual(len({tuple(sorted(s.items())) for s in specs}),540)
        self.assertEqual(len({(s['process'],s['temperature']) for s in specs}),15)
        self.assertEqual((specs[0]['process'],specs[0]['temperature']),('ff',0))
        self.assertEqual({(s['reference_slew_ps'],s['feedback_slew_ps']) for s in specs},{(100,100),(20,250),(250,20)})

    def test_fixture_changes_the_actual_model_and_temperature_without_time_or_load_changes(self):
        spec=self.specifications()[0]
        with patch.dict(os.environ,PDK_ROOT='/pdk'):
            old=source.pilot.fixture(Path('/context'),spec,[]);new=source.fixture(Path('/context'),spec,[])
        self.assertIn('" ff\n',new);self.assertIn('.options device temp=0\n',new)
        self.assertEqual(new.replace('" ff\n','" ss\n').replace('.options device temp=0\n','.options device temp=40\n'),old)
        self.assertIn('.tran 1p 62n 0 1p',new)

    def test_brackets_remain_separate_by_corner_slew_order_and_offset_polarity(self):
        rows=[dict(task=dict(spec=s),error=None,result=dict(correct_sign_fraction=1,frontend_stress_passed=True,common_mode_passed=True))
            for s in self.specifications()]
        grouped=proof.groups(rows);self.assertEqual(len(grouped),180)
        self.assertTrue(all(g['source_threshold_and_health_passed'] for g in grouped))
        rows[0]['result']['frontend_stress_passed']=False
        self.assertEqual(sum(not g['source_threshold_and_health_passed'] for g in proof.groups(rows)),1)
