from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dll_analog_frontend_timing_v2 as revision


class RevisedAnalogTiming(unittest.TestCase):
    def test_profile_uses_revised_dc_and_restores_original_on_failure(self):
        original=revision.original;previous=original.dc,original.NAMESPACE,original.admission
        with self.assertRaises(RuntimeError):
            with revision.profile():
                self.assertEqual(original.dc.NAMESPACE,'dll_analog_frontend_dc_tailtrim')
                self.assertEqual(original.dc.policy.VERSION,'dll-analog-frontend-v2-tail-trim-v1')
                self.assertEqual(original.NAMESPACE,revision.NAMESPACE)
                self.assertIs(original.dc.verify,revision.revision.verify)
                raise RuntimeError('profile exit')
        self.assertEqual((original.dc,original.NAMESPACE,original.admission),previous)

    def test_profile_producer_is_captured_before_creation_without_mutating_dc_receipt(self):
        pm=dict(identity={'code':{'dc.py':'existing'}});report={'dc_ready_variants':['tail140_w40']};bm={'native':'same'}
        with patch.object(revision.original,'admission',return_value=(pm,report,bm)):
            with revision.profile():
                derived,r,b=revision.original.admission(Path('dc'),Path('baseline'))
                self.assertIn('probe_dll_analog_frontend_timing_v2.py',derived['identity']['code'])
                self.assertEqual(pm,dict(identity={'code':{'dc.py':'existing'}}))
                self.assertEqual((r,b),(report,bm))

    def test_revised_circuit_has_four_tail_observations_and_same_seed_catalog(self):
        with revision.profile():
            tasks=revision.original.tasks(['tail140_w40']);self.assertEqual(len(tasks),18)
            self.assertEqual([t['spec']['offset_ps'] for t in tasks[:2]],[50,-50])
            _,devices=revision.original.dc.policy.circuit('tail140_w40')
            self.assertEqual(len(devices),125);self.assertEqual(len(revision.original.dc.policy.tail_roles()),4)
            self.assertEqual(len(revision.original.dc.policy.op_parameters()),376)

    def test_failed_revised_dc_cannot_create_timing_artifacts(self):
        with tempfile.TemporaryDirectory() as d,patch.object(revision.original,'admission',side_effect=ValueError('revised DC failed')):
            root=Path(d)
            with self.assertRaises(ValueError):revision.prepare(root/'dc',root/'baseline')
            self.assertEqual(list(root.iterdir()),[])

    def test_campaign_orders_admission_run_and_independent_verification(self):
        events=[];out=Path('timing');report={'ranked_survivors':[]}
        with patch.object(revision,'prepare',side_effect=lambda *a:events.append('prepare') or out), \
             patch.object(revision,'run',side_effect=lambda *a:events.append('run')), \
             patch.object(revision,'verify',side_effect=lambda *a:events.append('verify') or report):
            self.assertEqual(revision.campaign(Path('dc'),Path('baseline')),report)
        self.assertEqual(events,['prepare','run','verify'])
        with patch.object(revision,'prepare',side_effect=ValueError('DC failed')),patch.object(revision,'run') as run,patch.object(revision,'verify') as verify:
            with self.assertRaises(ValueError):revision.campaign(Path('dc'),Path('baseline'))
            run.assert_not_called();verify.assert_not_called()
