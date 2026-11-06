# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import run_native_eligible_sequence_v304 as p


class EligibilityFollowupTests(unittest.TestCase):
    def fixture(self,root):
        relative='build/diagnostics/regular_regenerated_full_range_v301/0123456789abcdef'
        campaign=root/relative;campaign.mkdir(parents=True)
        state=dict(status='complete',cases=7680,consumed_cases=106,errors=0,qualified_phy=False)
        (campaign/'state.json').write_text(json.dumps(state))
        coordinator=root/'coordinator';coordinator.mkdir()
        handoff=dict(status='full_range_characterization_complete',artifacts=dict(full_range=relative))
        return campaign,coordinator,handoff

    def test_original_complete_campaign_can_be_independently_evaluated(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'ROOT',Path(tmp)):
            campaign,coordinator,state=self.fixture(Path(tmp))
            self.assertEqual(p.ready_campaign(state,coordinator),campaign)

    def test_only_exact_all_raw_rejection_with_complete_zero_error_native_state_is_supported(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'ROOT',Path(tmp)):
            campaign,coordinator,state=self.fixture(Path(tmp))
            state.update(status='failed',error="Command returned non-zero exit status 1.")
            (coordinator/'verify.log').write_text('retained original traceback\n'+p.ALL_RAW_REJECTION+'\n')
            self.assertEqual(p.ready_campaign(state,coordinator),campaign)
            native=json.loads((campaign/'state.json').read_text());native['errors']=1
            (campaign/'state.json').write_text(json.dumps(native))
            with self.assertRaisesRegex(ValueError,'without measurement errors'):p.ready_campaign(state,coordinator)

    def test_source_or_waveform_failures_cannot_be_masked_as_ineligible_codes(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'ROOT',Path(tmp)):
            _,coordinator,state=self.fixture(Path(tmp));state.update(status='failed',error='Command returned non-zero exit status 1.')
            for message in ('ValueError: Original native result changed','ValueError: PDK changed','ValueError: Native waveform incomplete'):
                (coordinator/'verify.log').write_text(message+'\n')
                with self.assertRaisesRegex(ValueError,'not the original all-raw'):p.ready_campaign(state,coordinator)
            state['error']='Owner changed'
            with self.assertRaisesRegex(ValueError,'Unsupported'):p.ready_campaign(state,coordinator)

    def test_running_incomplete_foreign_or_missing_artifact_never_advances(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(p,'ROOT',Path(tmp)):
            _,coordinator,state=self.fixture(Path(tmp))
            for status in ('waiting_for_native_donors','running_full_range','verifying_full_range'):
                with self.assertRaisesRegex(ValueError,'has not completed'):p.ready_campaign(dict(state,status=status),coordinator)
            for path in ('','build/diagnostics/another_bank/0123456789abcdef'):
                with self.assertRaisesRegex(ValueError,'explicit original'):p.ready_campaign(dict(state,artifacts=dict(full_range=path)),coordinator)


if __name__=='__main__':unittest.main()
