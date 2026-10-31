# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import advance_ota_candidate as advance


class OTAAdvancement(unittest.TestCase):
    def test_new_profile_cannot_inherit_another_profiles_full_stage_gate(self):
        old=dict(ota_qualification='old',ota_stage='full',ota_stability='old/report',disabled=['rx_aperture'])
        result=advance.qualification_config(old,'new')
        self.assertNotIn('ota_stage',result);self.assertNotIn('ota_stability',result)
        self.assertEqual(set(result['disabled']),{'qualify_cp','rx_aperture'})
        self.assertEqual(old['ota_stage'],'full')

    def test_same_profile_retains_its_completed_stage(self):
        old=dict(ota_qualification='same',ota_stage='full',ota_stability='same/report')
        self.assertEqual(advance.qualification_config(old,'same')['ota_stability'],'same/report')

    def test_new_candidate_retires_old_hold_but_same_candidate_keeps_it(self):
        old=dict(ota_qualification='failed',disabled=['qualify_ota','rx_aperture'],ota_hold_reason='native monitor failure')
        same=advance.qualification_config(old,'failed')
        self.assertIn('qualify_ota',same['disabled']);self.assertIn('ota_hold_reason',same)
        new=advance.qualification_config(old,'repair')
        self.assertNotIn('qualify_ota',new['disabled']);self.assertNotIn('ota_hold_reason',new)
        self.assertIn('rx_aperture',new['disabled']);self.assertIn('qualify_cp',new['disabled'])

    def test_restart_reuses_verified_model_and_rejects_damaged_current_evidence(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);case=root/'generation';case.mkdir()
            path=case/'summary.json';path.write_text('{}')
            code={name:hashlib.sha256((advance.ROOT/'scripts'/name).read_bytes()).hexdigest() for name in advance.PRODUCERS}
            (case/'manifest.json').write_text(json.dumps(dict(code=code)))
            with patch.object(advance,'verify_stability') as verify:
                self.assertEqual(advance.cached_model(root,{'circuit':'hash'},('ss_0',)),path)
                verify.assert_called_once_with(path,{'circuit':'hash'},('ss_0',))
            with patch.object(advance,'verify_stability',side_effect=ValueError('damaged')):
                with self.assertRaisesRegex(ValueError,'damaged'):advance.cached_model(root,{},())

    def test_old_model_producer_is_not_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);case=root/'old';case.mkdir();(case/'summary.json').write_text('{}')
            (case/'manifest.json').write_text(json.dumps(dict(code={'old':'producer'})))
            with patch.object(advance,'verify_stability') as verify:
                self.assertIsNone(advance.cached_model(root,{},()));verify.assert_not_called()
