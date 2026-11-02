# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import require_openpll_contract as gate


class RequiredCurrentClockContract(unittest.TestCase):
    def test_complete_passing_audit_is_returned_without_regenerating_clocks(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(gate.audit,'verify',return_value=Path(tmp)) as verify:
            out=Path(tmp);report=dict(passed=True,results=[dict(kind=k,metrics=dict(passed=True),legacy_metrics_verified=True) for k in ['rtl','physical']])
            (out/'summary.json').write_text(json.dumps(report))
            self.assertEqual(gate.require(),out);verify.assert_called_once_with()

    def test_false_or_incomplete_audit_cannot_pass_the_command_gate(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(gate.audit,'verify',return_value=Path(tmp)):
            out=Path(tmp)
            for report in [dict(passed=False,results=[]),dict(passed=True,results=[]),dict(passed=True,results=[dict(kind='rtl',metrics=dict(passed=True),legacy_metrics_verified=True)]),dict(passed=True,results=[dict(kind=k,metrics=dict(passed=k=='rtl'),legacy_metrics_verified=True) for k in ['rtl','physical']])]:
                (out/'summary.json').write_text(json.dumps(report))
                with self.assertRaises(ValueError):gate.require()
