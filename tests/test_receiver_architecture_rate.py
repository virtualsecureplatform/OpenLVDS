# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from receiver_architecture_rate import fixture

RATE = '''Rate test
.include "/old/source.spice"
VIO VDDIO 0 3.3
VP P 0 PULSE(1.075 1.325 5n 100p 100p 1.119n 2.439n)
VN N 0 PULSE(1.325 1.075 5n 100p 100p 1.119n 2.439n)
CQ Q 0 100f
.tran 10p 60n 0 100p
.print tran V(P) V(N) V(Q)
.end
'''
STATIC = '''.print tran V(P) V(N) V(Q) V(XR:XCORE:CO)
HOBS_IO OBS_IIO 0 VIO 1
HOBS_DIG OBS_IDIG 0 VDIG 1
.end
'''


class ArchitectureRateFixture(unittest.TestCase):
    def test_input_load_and_supply_are_preserved_while_step_is_tightened(self):
        deck = fixture(RATE, STATIC, Path('/old'), Path('/new'))
        for line in RATE.splitlines():
            if line.startswith(('VP ', 'VN ', 'CQ ', 'VIO ')):
                self.assertIn(line, deck)
        self.assertIn('.tran 5p 60n 0 1p', deck)
        self.assertIn('.include "/new/source.spice"', deck)
        self.assertEqual(deck.count('HOBS_IO '), 1)
        self.assertIn('.print tran V(P) V(N) V(Q) V(XR:XCORE:CO)', deck)

    def test_missing_meters_or_changed_original_fixture_are_refused(self):
        for rate, static in [(RATE.replace('100p\n.print', '200p\n.print'), STATIC),
                             (RATE, STATIC.replace('HOBS_DIG', 'OTHER')),
                             (RATE, STATIC.replace('V(Q) V(', 'V(OTHER) V(')),
                             (RATE+RATE, STATIC)]:
            with self.assertRaises(ValueError):
                fixture(rate, static, Path('/old'), Path('/new'))


if __name__ == '__main__':
    unittest.main()
