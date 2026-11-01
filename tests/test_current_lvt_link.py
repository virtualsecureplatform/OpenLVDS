# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import compare_current_lvt_link as link


class CurrentLvtLink(unittest.TestCase):
    def test_both_views_use_identical_numerics_and_observations(self):
        deck = ('Original\nXDR inputs native\n.tran 20p 188.049n 0 100p\n'
                '.print tran V(RXDATA) V(RXCLOCK)\n.end\n')
        result = link.instrument(deck)
        suffix = ' '+' '.join('V('+n+')' for n in link.PROBES)
        self.assertEqual(result.replace(' 0 20p\n', ' 0 100p\n').replace(suffix, ''), deck)
        self.assertEqual(len(link.PROBES), 14)
        with self.assertRaises(ValueError):
            link.instrument(deck.replace('188.049n', '80n'))

    def test_profiles_restore_both_frozen_producers_after_failure(self):
        for corrected in [False, True]:
            previous = link.pilot.NAME, link.pilot.rebind, link.pilot.slot
            native = link.current.native
            oldnative = native.physical_models, native.CODE, native.slot
            with self.assertRaises(RuntimeError):
                with link.profile(corrected):
                    self.assertEqual(link.pilot.NAME, link.NAME)
                    if corrected:
                        self.assertIs(native.physical_models, link.current.physical_models)
                    raise RuntimeError('test failure')
            self.assertEqual(previous, (link.pilot.NAME, link.pilot.rebind, link.pilot.slot))
            self.assertEqual(oldnative, (native.physical_models, native.CODE, native.slot))

    def test_different_receiver_source_cannot_use_original_admission(self):
        paths = [Path('/unused')]*6
        with patch.object(link, 'source_gate', return_value={'static/source.spice': 'admitted'}), \
                patch.object(link.pilot, 'digest', return_value='different'), \
                patch.object(link.pilot, 'prepare') as prepare:
            with self.assertRaisesRegex(ValueError, 'differs from the admitted matrix'):
                link.prepare(*paths)
            prepare.assert_not_called()


if __name__ == '__main__':
    unittest.main()
