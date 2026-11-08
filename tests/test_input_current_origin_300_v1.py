# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import input_current_origin_300_v1 as p
import clocking_profile_300 as policy


class InputOriginTests(unittest.TestCase):
    def test_actual_decks_change_only_dc_zero_external_current_card(self):
        root=policy.ROOT/'build/diagnostics'
        for ctx,key in [('tg2_next_bank_early_zero_pilot_300_v2','23dee609d6ca5e51'),('dcc_four_section_pilot_300_v1','7c2674e516231ffb')]:
            parent=root/ctx/key;original=(parent/'0/bench.cir').read_text()
            library='\n'.join(f.read_text() for f in parent.glob('*.spice'))
            trial=p.fixture(original,library)
            self.assertEqual(trial.replace(p.CARD+'\n','',1),original)
            self.assertIn('DC 0 PWL(0 0 2p 1m 40n 1m)',trial)
            with self.assertRaises(ValueError):p.fixture(trial,library)

    def test_current_feedback_and_incomplete_transient_refused(self):
        parent=policy.ROOT/'build/diagnostics/dcc_four_section_pilot_300_v1/7c2674e516231ffb'
        original=(parent/'0/bench.cir').read_text();library=(parent/'bank.spice').read_text()
        for changed,lib in ((original+'\nBTEST X 0 V={I(BIN)}\n',library),
                            (original,library+'\nFTEST X 0 BIN 1\n'),
                            (original.replace('.tran 2p 40n 0 2p','.tran 2p 1n 0 2p'),library)):
            with self.subTest(),self.assertRaises(ValueError):p.fixture(changed,lib)
