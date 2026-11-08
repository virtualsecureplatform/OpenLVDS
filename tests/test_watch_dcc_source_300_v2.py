# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys,unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import watch_dcc_source_300_v2 as p


class OptionalServiceProbeTests(unittest.TestCase):
    def test_missing_service_tool_is_unknown(self):
        with patch.object(p.subprocess,'run',side_effect=FileNotFoundError('systemctl')):
            self.assertIsNone(p.source_live())

    def test_unreachable_service_manager_is_unknown(self):
        with patch.object(p.subprocess,'run',return_value=SimpleNamespace(returncode=1,stdout='')):
            self.assertIsNone(p.source_live())

    def test_available_service_state_is_interpreted(self):
        for text,expected in [('ActiveState=active\nMainPID=123\n',True),
                              ('ActiveState=inactive\nMainPID=0\n',False)]:
            with patch.object(p.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=text)):
                self.assertIs(p.source_live(),expected)
