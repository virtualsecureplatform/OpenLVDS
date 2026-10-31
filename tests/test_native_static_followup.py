# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import continue_native_static as followup


class SeedAdmission(unittest.TestCase):
    def test_failure_or_changed_waveform_holds_expansion(self):
        for passed,changed in [(False,False),(True,True)]:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);(root/'requirements.json').write_text('{}')
                name=followup.SEEDS[0];folder=root/name;folder.mkdir()
                for n in ['bench.cir','bench.cir.prn','bench.raw']:(folder/n).write_text(n)
                task=dict(id=name,fast_rc=False,spec=dict(kind='phase'),deck_sha256=followup.digest(folder/'bench.cir'))
                report=dict(passed=passed,returncode=0,task=name,deck_sha256=task['deck_sha256'],metrics={'passed':passed},
                    waveform_sha256=followup.digest(folder/'bench.cir.prn'),raw_sha256=followup.digest(folder/'bench.raw'))
                (folder/'summary.json').write_text(json.dumps(report))
                if changed:(folder/'bench.cir.prn').write_text('changed')
                with patch.object(followup,'ROOT',root),patch.object(followup,'validate'),patch.object(followup,'architecture_sources'),patch.object(followup,'evaluate',return_value=report['metrics']):
                    with self.assertRaisesRegex(ValueError,'seed has not passed intact'):
                        followup.admission(root,dict(tasks=[task]))
