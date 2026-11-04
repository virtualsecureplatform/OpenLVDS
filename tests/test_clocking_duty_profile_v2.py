# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import clocking_duty_profile_v2 as profile


class DutyAmendmentTests(unittest.TestCase):
    def test_only_the_authorized_input_duty_range_changes(self):
        base=(profile.ROOT/'clocking_v2.json').read_bytes();expected=json.loads(base)
        expected['timing']['rx_reference_duty_range']=[.4,.6]
        self.assertEqual(profile.load(),expected);self.assertEqual((profile.ROOT/'clocking_v2.json').read_bytes(),base)
        self.assertEqual(profile.load()['timing']['mean_half_cycle_error_ps'],50)
        self.assertFalse(profile.load()['qualified_phy'])

    def test_unrelated_requirement_override_is_rejected(self):
        original=json.loads(profile.PROFILE.read_text());original['timing_overrides']['mean_half_cycle_error_ps']=100
        read=Path.read_text
        def text(p,*args,**kwargs):return json.dumps(original) if p==profile.PROFILE else read(p,*args,**kwargs)
        with patch.object(Path,'read_text',text):
            with self.assertRaises(ValueError):profile.load()


if __name__=='__main__':unittest.main()
