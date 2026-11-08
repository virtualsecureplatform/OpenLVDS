# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import two_bank_independent_measure_300_v1 as p
import two_bank_native_measure_300_v1 as original
import replay_tg2_loaded_native_300_v1 as replay
from replay_bank_300_v2 import same
import test_two_bank_native_measure_300_v1 as fixtures


class IndependentLoadedWitnessTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.RelativeTransportTests();self.fixture.setUp()

    def test_binary_witness_reproduces_both_code_settings_and_supply_failure(self):
        for fine,supply in ((0,1.8),(31,1.8),(31,1.9)):
            with tempfile.TemporaryDirectory() as folder:
                folder=Path(folder);obs=self.fixture.binary_fixture(folder,fine=fine,supply=supply)
                spec=dict(self.fixture.s,stop_ns=40)
                recorded=original.measure(folder,obs,spec,next_coarse=0,next_fine=fine)
                witness=p.measure(folder,obs,spec,next_coarse=0,next_fine=fine)
                self.assertTrue(same(recorded,witness))
                self.assertEqual(witness['two_bank_zero_pilot_passed'],supply==1.8)
                changed=json.loads(json.dumps(recorded));changed['banks']['next']['timing']['edge_delays_ps']['rise'][0]+=1
                self.assertFalse(same(changed,witness))

    def test_independent_witness_preserves_startup_pulse_loss(self):
        f=self.fixture
        for ideal,inp in ((True,f.wave()),(False,f.wave(700))):
            out=f.wave(1450,missing_first=True)
            recorded=original.stage(f.t,inp,out,f.s,ideal_input=ideal)
            witness=p.stage(f.t,inp,out,f.s,ideal_input=ideal)
            self.assertTrue(same(recorded,witness));self.assertFalse(witness['stage_transport_passed'])
            self.assertEqual(witness['pulse_counts']['rise']['output'],7)

    def test_missing_native_point_refused_before_full_binding_or_receipt(self):
        with tempfile.TemporaryDirectory(dir=replay.ROOT/'build') as folder:
            parent=Path(folder);(parent/'manifest.json').write_text(json.dumps(dict(identity=dict(version=replay.early.VERSION))))
            with patch.object(replay.early,'bound') as bound:
                with self.assertRaisesRegex(ValueError,'still pending: 0'):
                    replay.run(parent,['0'])
                bound.assert_not_called()
            self.assertEqual({p.name for p in parent.iterdir()},{'manifest.json'})

    def test_unknown_duplicate_and_empty_selections_refused(self):
        with patch.object(replay,'select',return_value=replay.early),patch.object(replay.early,'bound') as bound:
            for numbers in ([],['0','0'],['4']):
                with self.assertRaisesRegex(ValueError,'explicit unique'):
                    replay.run(replay.ROOT/'build/unused-loaded-independent',numbers)
            bound.assert_not_called()
