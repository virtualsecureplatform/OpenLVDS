# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from receiver_architecture_clock_pilot import fixture, pvt

DECK = '''Captured clock
.include "/old/library.spice"
.lib "/pdk/sky130.lib.spice" ss
.options device temp=40
.options timeint method=gear reltol=1e-4 abstol=1e-12
VRCP RCP 0 PWL(0 1.2 1n 1.3)
.tran 5p 80n 0 1p
.print tran V(RCP) V(RCN) V(RXCLOCK)
.end
'''


class ArchitectureClockPilot(unittest.TestCase):
    def test_original_input_and_numerical_policy_are_retained(self):
        result = fixture(DECK, Path('/old'), Path('/new'), ['XRC:CT'])
        restored = result.replace('/new/library.spice', '/old/library.spice').replace(' V(XRC:CT)', '')
        self.assertEqual(restored, DECK)
        self.assertEqual(pvt(result), ('ss', 40.))

    def test_unexpected_step_include_or_ambiguous_corner_is_refused(self):
        for deck in [DECK.replace('0 1p', '0 5p'), DECK.replace('/old/', '/wrong/')]:
            with self.assertRaises(ValueError):
                fixture(deck, Path('/old'), Path('/new'), ['XRC:CT'])
        with self.assertRaises(ValueError):
            pvt(DECK+'.options device temp=25\n')


if __name__ == '__main__':
    unittest.main()
