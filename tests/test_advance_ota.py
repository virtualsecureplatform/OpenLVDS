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


class SelectedRXAperture(unittest.TestCase):
    def test_selected_rx_exact_hash_is_used_for_complete_table_verification(self):
        from unittest.mock import patch
        from advance_ota_candidate import verify_aperture
        models={'openlvds_ddr_rx':{'netlist_sha256':'selected-native-rx'}}
        with patch('phy_candidate.load',return_value=(b'library',{},models)),patch('rx_aperture_evidence.read_table',return_value={'qualified':True}) as read:
            result=verify_aperture(Path('/bundle'),Path('/table.json'))
            self.assertTrue(result['qualified'])
            read.assert_called_once_with(Path('/table.json'),'selected-native-rx','tt',25)


class CompletedNativeResume(unittest.TestCase):
    def setup_case(self,root,passed=True):
        artifact=root/'build/diagnostics/dll_qualification/native';artifact.mkdir(parents=True)
        (artifact/'manifest.json').write_text(json.dumps(dict(identity=dict(variant='ota_w8_c4'))))
        (artifact/'summary.json').write_text(json.dumps(dict(passed=passed)))
        stability=artifact/'stability_all_pvt/generation/summary.json'
        config=root/'build/diagnostics/resident_jobs/config.json';config.parent.mkdir(parents=True)
        config.write_bytes(b'{"disabled":["qualify_cp","qualify_ota"]}')
        return artifact,stability,config

    def test_failed_or_incomplete_native_evidence_cannot_start_signoff(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);artifact,model,config=self.setup_case(root,False)
            with patch.object(advance,'ROOT',root),patch.object(advance,'signoff') as run:
                with self.assertRaisesRegex(ValueError,'Complete native qualification'):advance.finalize(artifact,model)
                (artifact/'summary.json').unlink()
                with self.assertRaisesRegex(ValueError,'Complete native qualification'):advance.finalize(artifact,model)
            run.assert_not_called();self.assertFalse((artifact/'advancement').exists())
            self.assertEqual(config.read_bytes(),b'{"disabled":["qualify_cp","qualify_ota"]}')

    def test_resume_revalidates_native_and_all_pvt_model_without_dispatcher_changes(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);artifact,model,config=self.setup_case(root)
            before=config.read_bytes();rx=root/'build/diagnostics/selected_rx'
            aperture=root/'build/characterization/rx_aperture/selected/table.json'
            with patch.object(advance,'ROOT',root),patch.dict(os.environ),\
                 patch('dll_native_evidence.verify') as native,patch('qualify_dll_recovery.inputs') as inputs,\
                 patch.object(advance,'signoff',return_value='finished') as run:
                self.assertEqual(advance.finalize(artifact,model,rx,aperture),'finished')
                native.assert_called_once_with(artifact);inputs.assert_called_once_with(artifact,model)
                run.assert_called_once_with(artifact,model,artifact/'advancement',rx,aperture)
            self.assertEqual(config.read_bytes(),before)

    def test_damaged_native_or_model_proof_stops_before_any_downstream_job(self):
        import os
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);artifact,model,config=self.setup_case(root)
            with patch.object(advance,'ROOT',root),patch.dict(os.environ),patch.object(advance,'signoff') as run:
                with patch('dll_native_evidence.verify',side_effect=ValueError('changed native trace')),patch('qualify_dll_recovery.inputs') as inputs:
                    with self.assertRaisesRegex(ValueError,'changed native trace'):advance.finalize(artifact,model)
                    inputs.assert_not_called()
                with patch('dll_native_evidence.verify'),patch('qualify_dll_recovery.inputs',side_effect=ValueError('incomplete all-PVT model')):
                    with self.assertRaisesRegex(ValueError,'all-PVT'):advance.finalize(artifact,model)
            run.assert_not_called();self.assertFalse((artifact/'advancement').exists())

    def test_duplicate_signoff_owner_cannot_launch_another_pipeline(self):
        import fcntl,os
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);artifact,model,_=self.setup_case(root)
            with (artifact/'.advancement.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                with patch.object(advance,'ROOT',root),patch.dict(os.environ),patch('dll_native_evidence.verify'),\
                     patch('qualify_dll_recovery.inputs'),patch.object(advance,'signoff') as run:
                    with self.assertRaises(BlockingIOError):advance.finalize(artifact,model)
                    run.assert_not_called()

    def test_resume_rejects_charge_pump_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);artifact,model,_=self.setup_case(root)
            (artifact/'manifest.json').write_text(json.dumps(dict(identity=dict(variant='cp_baseline'))))
            with patch.object(advance,'ROOT',root),patch.object(advance,'signoff') as run:
                with self.assertRaisesRegex(ValueError,'Expected an OTA'):advance.finalize(artifact,model)
                run.assert_not_called()
