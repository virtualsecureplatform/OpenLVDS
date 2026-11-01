# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_receiver_pmos_compact as pmos


class PMOSNativeReplay(unittest.TestCase):
    def test_profile_rejects_lvt_and_restores_all_factories_on_failure(self):
        n = pmos.native
        old = n.PROFILE, n.CODE, n.source_variant, n.source_clock, n.atomic
        with self.assertRaises(RuntimeError):
            with pmos.profile():
                n.validate_profile(pmos.PROFILE)
                with self.assertRaises(ValueError):
                    n.validate_profile(old[0])
                self.assertIs(n.source_clock, pmos.source_clock)
                raise RuntimeError('test failure')
        self.assertEqual(old, (n.PROFILE, n.CODE, n.source_variant, n.source_clock, n.atomic))

    def test_scope_adapter_preserves_the_computed_native_verdict(self):
        with patch.object(pmos.native, 'atomic') as write:
            with pmos.profile():
                value = dict(scope='Native compact LVT decision-pair experiment with original pin stimuli and RX load; no PVT, stress, aperture or link qualification', native_clock_passed=False, qualified_phy=False)
                pmos.native.atomic(Path('/summary.json'), value)
            captured = write.call_args.args[1]
            self.assertEqual(captured['scope'], pmos.SCOPE)
            self.assertIs(captured['native_clock_passed'], False)
            self.assertIs(captured['qualified_phy'], False)


if __name__ == '__main__':
    unittest.main()
