# SPDX-License-Identifier: GPL-3.0-only
import hashlib
from contextlib import nullcontext
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import verify_analog as runner


class AnalogResume(unittest.TestCase):
    def test_reuses_only_matching_circuit_and_untampered_waveform(self):
        source=b'.subckt openlvds_driver A B\nR1 A B 10\n.ends openlvds_driver\n'
        script=b'original simulation runner\n'
        deck='unit bench\n.include "'+str(runner.ROOT/'analog/openlvds.spice')+'"\n.tran 1n 10n 0 1n\n.end\n'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            def simulate(*args,**kwargs):
                (Path(kwargs['cwd'])/'bench.cir.prn').write_text('Index TIME V(P) V(N)\n0 0 1.2 1.2\n1 1e-8 1.375 1.025\n')
                return SimpleNamespace(returncode=0,stdout='',stderr='')
            with patch.multiple(runner,ARTIFACT_ROOT=root,SOURCE_BYTES=source,SCRIPT_BYTES=script,
                    SCRIPT_HASH=hashlib.sha256(script).hexdigest(),SCHEMATIC_HASH=hashlib.sha256(source).hexdigest(),
                    EXTRACTED=False,EXTRACTION_INPUTS={},SETTLED_START=False,MAX_STEP_PS=None,
                    RESUME=True,REUSED={},CASE_LOCKS={},SIMULATOR_STAMP='unit provenance'), \
                    patch.object(runner,'slot',return_value=nullcontext()) as slots, \
                    patch.object(runner,'engine',return_value='unit'), \
                    patch.object(runner,'spice_command',return_value=['unit simulator']), \
                    patch.object(runner.subprocess,'run',side_effect=simulate) as call:
                def execute():
                    out,wave,error=runner.run_deck('driver_tt_25',deck)
                    self.assertIsNotNone(wave,error)
                    return runner.save(out,dict(passed=True),deck)
                self.assertFalse(execute()['reused_waveform'])
                runner.SOURCE_BYTES=source+b'.subckt unused A B\nR2 A B 100\n.ends unused\n'
                self.assertTrue(execute()['reused_waveform'])
                self.assertEqual(call.call_count,1)
                self.assertEqual(slots.call_count,1)
                wave=root/'driver_tt_25/bench.cir.prn'
                wave.write_text(wave.read_text().replace('1.375','1.3'))
                self.assertFalse(execute()['reused_waveform'])
                self.assertEqual(call.call_count,2)
                runner.SOURCE_BYTES=source.replace(b'B 10',b'B 11')
                self.assertFalse(execute()['reused_waveform'])
                self.assertEqual(call.call_count,3)
                self.assertEqual(slots.call_count,3)
                history=list((root/'driver_tt_25/history').glob('*/archive.json'))
                self.assertEqual(len(history),2)
                for report in history:
                    import json
                    record=json.loads(report.read_text())
                    self.assertFalse(record['qualified_phy'])
                    for name,digest in record['files'].items():
                        self.assertEqual(hashlib.sha256((report.parent/name).read_bytes()).hexdigest(),digest)


if __name__=='__main__':unittest.main()
