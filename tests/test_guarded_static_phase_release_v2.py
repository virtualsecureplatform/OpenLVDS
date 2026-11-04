# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import static_phase_clock_release_v3 as circuit
import probe_static_phase_clock_release_v3 as pilot
import test_static_phase_clock_release_v2 as original


class GuardedStaticPhaseReleaseTests(unittest.TestCase):
    def test_only_low_setters_change_and_each_uses_two_actual_guarded_rc_components(self):
        c=circuit.components
        rc={c.MODELS['nand2_'+str(n)]:dict(info=dict(ports=['A','B','Y','VGND','VPWR'])) for n in [4,8]}
        rc[c.CLOCK_BUFFER]=dict(info=dict(ports=['A','X','VGND','VPWR']))
        rc[circuit.previous.NAND2B]=dict(info=dict(ports=['A_N','B','Y','VPWR','VGND']))
        for model in circuit.MACROS.values():rc[model]=dict(info=dict(ports=['A_N','B','Y','VGND','VPWR']))
        old=circuit.previous.source(rc,4).splitlines()[1:-1]
        for variant,model in circuit.MACROS.items():
            text=circuit.source(rc,variant);rows=text.splitlines()
            for row in old:
                if row.split()[-1]!=circuit.previous.NAND2B:self.assertIn(row,rows)
            self.assertEqual(text.count(model),6)
            self.assertIn('Xlow0_set_0 CLK request_i low0_sn VGND VPWR '+model,rows)
            self.assertIn('Xlow1_set_1 CLK high1 low1_sn VGND VPWR '+model,rows)
            self.assertIn('Xlow2_set_0 CLK PREPARE low2_sn VGND VPWR '+model,rows)
            self.assertNotIn(circuit.previous.NAND2B,text)

    def test_guarded_variants_keep_intermediate_order_and_stopped_clear_checks(self):
        with patch.object(original,'pilot',pilot):
            original.StaticPhaseReleaseTests().test_intermediate_order_and_stopped_clear_are_required_at_both_duties()


if __name__=='__main__':unittest.main()
