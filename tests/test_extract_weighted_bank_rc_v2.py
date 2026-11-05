# SPDX-License-Identifier: GPL-3.0-only
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import extract_weighted_bank_rc_v2 as extraction


class RoutedBankExtractionAdmissionTests(unittest.TestCase):
    def test_route_only_success_cannot_admit_whole_bank_rc(self):
        with tempfile.TemporaryDirectory() as temp:
            parent=Path(temp)
            (parent/'summary.json').write_text(json.dumps(dict(
                routing_bringup_passed=True,physical_implementation_passed=False)))
            with patch.object(extraction.physical,'bound',return_value={'identity':{}}):
                with self.assertRaisesRegex(ValueError,'whole-bank physical checks'):
                    extraction.parent_files(parent)

    def test_changed_actual_output_is_rejected_even_with_all_reported_checks_green(self):
        with tempfile.TemporaryDirectory() as temp:
            parent=Path(temp);view=parent/'final.odb';view.write_bytes(b'accepted database')
            digest=hashlib.sha256(view.read_bytes()).hexdigest()
            (parent/'summary.json').write_text(json.dumps(dict(
                physical_implementation_passed=True,returncode=0,target_step_completed=True,
                placement_check={'passed':True},metrics={k:0 for k in extraction.physical.ZERO_METRICS},
                outputs={str(view):digest})))
            view.write_bytes(b'changed database')
            with patch.object(extraction.physical,'bound',return_value={'identity':{}}):
                with self.assertRaisesRegex(ValueError,'actual output views'):
                    extraction.parent_files(parent)


if __name__=='__main__':unittest.main()
