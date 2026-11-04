# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import static_phase_clock_release_v5 as circuit
import probe_static_phase_clock_release_v5 as pilot
import test_guarded_static_phase_release_v2 as previous


class StackGuardStaticPhaseReleaseTests(unittest.TestCase):
    def test_stack_guard_variants_preserve_setter_interface_and_all_measurement_checks(self):
        with patch.object(previous,'circuit',circuit),patch.object(previous,'pilot',pilot):
            previous.GuardedStaticPhaseReleaseTests().test_only_low_setters_change_and_each_uses_two_actual_guarded_rc_components()
            previous.GuardedStaticPhaseReleaseTests().test_guarded_variants_keep_intermediate_order_and_stopped_clear_checks()


if __name__=='__main__':unittest.main()
