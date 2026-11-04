# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import terminate_nonpassive_children_v2 as termination


class NonpassiveTerminationGuardTests(unittest.TestCase):
    def test_live_or_missing_coordinator_is_rejected_before_any_signal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);identity=dict(coordinator=dict(pid=123,start='0',argv=['python','test']),artifact='build/diagnostics/native_clock_components_v2/test')
            (p/'identity.json').write_text(json.dumps(identity))
            with patch.object(termination.drain,'proc',return_value=None),patch.object(termination.os,'kill') as kill:
                with self.assertRaises(ValueError):termination.terminate(p)
                kill.assert_not_called()

    def test_unrelated_campaign_cannot_be_terminated(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);(p/'identity.json').write_text(json.dumps(dict(coordinator=dict(pid=123),artifact='build/diagnostics/phase_threshold_pvt_v2/test')))
            with patch.object(termination.os,'kill') as kill:
                with self.assertRaises(ValueError):termination.terminate(p)
                kill.assert_not_called()


if __name__=='__main__':unittest.main()
