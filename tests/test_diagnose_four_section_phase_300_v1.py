# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_four_section_phase_300_v1 as p
import test_four_bank_native_measure_300_v1 as fixtures


class CapturedPhaseTests(unittest.TestCase):
    def test_pending_trace_refused_before_hashing(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent=Path(tmp);(parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version=p.chain.VERSION))))
            with patch.object(p.chain,'bound',side_effect=AssertionError('must not bind pending trace')):
                with self.assertRaisesRegex(ValueError,'pending'):p.run(parent,['0'])
                with self.assertRaisesRegex(ValueError,'explicit unique'):p.run(parent,['0','0'])

    def test_native_binary_phase_failure_and_changed_witness(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);parent=root/'producer';folder=parent/'0';folder.mkdir(parents=True)
            obs,s=fixtures.FourSectionMeasureTests().fixture(folder)
            task=dict(id='0',centered=True,spec=s)
            m=dict(identity=dict(version=p.chain.VERSION,inputs={}),tasks=[task])
            p.chain.atomic(parent/'manifest.json',m);(parent/'bank.spice').write_text('* synthetic fixture\n')
            for n in ('bench.cir','bench.ngspice.cir','ngspice.log'):(folder/n).write_text('* synthetic fixture\n')
            p.chain.atomic(folder/'observations.json',obs)
            result=p.chain.metrology.measure(folder,obs,s)
            row=dict(task=task,error=None,result=result,files={f.name:p.chain.sha(f) for f in folder.iterdir()})
            p.chain.atomic(folder/'summary.json',row)
            with patch.object(p,'ROOT',root),patch.object(p.chain,'bound',return_value=m):
                out=p.run(parent,['0']);summary=json.loads((out/'summary.json').read_text())
                self.assertTrue(summary['rows'][0]['original_transport_passed'])
                self.assertFalse(summary['rows'][0]['phase']['observed_50ps_phase_grid_passed'])
                self.assertFalse(summary['calibrated_phase_qualified']);self.assertFalse(summary['qualified_phy'])
                with (folder/'bench.raw').open('ab') as handle:handle.write(b'changed')
                with patch.object(p.phase,'measure',side_effect=AssertionError('must reject hash first')):
                    with self.assertRaisesRegex(ValueError,'witness changed'):p.run(parent,['0'])
