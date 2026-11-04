# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import static_phase_clock_release_v4 as circuit
import probe_static_phase_clock_release_v4 as pilot
import test_guarded_static_phase_release_v2 as previous


class BodytapStaticPhaseReleaseTests(unittest.TestCase):
    def test_body_contact_variant_changes_only_the_physical_setters_and_retains_all_checks(self):
        with patch.object(previous,'circuit',circuit),patch.object(previous,'pilot',pilot):
            previous.GuardedStaticPhaseReleaseTests().test_only_low_setters_change_and_each_uses_two_actual_guarded_rc_components()
            previous.GuardedStaticPhaseReleaseTests().test_guarded_variants_keep_intermediate_order_and_stopped_clear_checks()


if __name__=='__main__':unittest.main()
