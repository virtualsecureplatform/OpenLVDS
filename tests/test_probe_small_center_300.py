# SPDX-License-Identifier: GPL-3.0-only
import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_small_center_300 as p

class SmallOriginTests(unittest.TestCase):
    def test_only_current_origin_and_library_location_change(self):
        original=(p.PARENT/'0/bench.cir').read_text();out=p.ROOT/'build/unused-small-origin/bank.spice'
        for offset in p.OFFSETS:
            text=p.deck(original,out,p.PARENT/'bank.spice',offset)
            restored=text.replace(f'I_BENCH_CURRENT_CENTER VDD 0 {offset:.9g}\n','',1).replace(str(out),str(p.PARENT/'bank.spice'))
            self.assertEqual(restored,original)
    def test_feedback_or_existing_offset_is_rejected(self):
        original=(p.PARENT/'0/bench.cir').read_text();out=p.ROOT/'build/unused-small-origin/bank.spice'
        for changed in (original+'\nFfeedback N 0 VDD 1\n',original+'\n* i(vdd) feedback\n',original+'\nI_BENCH_CURRENT_CENTER VDD 0 .001\n'):
            with self.assertRaises(ValueError):p.deck(changed,out,p.PARENT/'bank.spice',1e-5)
    def test_unbounded_offsets_and_supply_changes_are_rejected(self):
        original=(p.PARENT/'0/bench.cir').read_text();out=p.ROOT/'build/unused-small-origin/bank.spice'
        with self.assertRaises(ValueError):p.deck(original,out,p.PARENT/'bank.spice',.001)
        with self.assertRaises(ValueError):p.deck(original.replace('VDD VDD 0 1.8','VDD VDD 0 1.9'),out,p.PARENT/'bank.spice',1e-5)
