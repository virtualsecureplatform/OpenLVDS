# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from passive_net_capacitance_v211 import loading


class PassiveLoading(unittest.TestCase):
    def test_wire_group_aliases_coupling_and_internal_self_caps(self):
        text='.subckt test A B VGND\nR0 A aa 100\nR1 aa ab 20\nC0 aa VGND 2f\nC1 ab B 3f\nC2 A ab 50f\nC3 B VGND 4f\nX0 A VGND sky130_fd_pr__cap_mim_m3_1 w=2 l=2\n.ends test\n'
        r=loading(text,['A','ab','B','VGND']);self.assertEqual(r['self_caps_after_wire_short_ignored'],1)
        self.assertEqual(r['targets']['A']['incident_parasitic_capacitance_ff'],5.)
        self.assertEqual(r['targets']['A']['dc_equivalent_targets'],['A','ab'])
        self.assertEqual(r['targets']['B']['incident_parasitic_capacitance_ff'],7.)
        self.assertEqual(r['targets']['VGND']['incident_parasitic_capacitance_ff'],6.)
        self.assertEqual(r['targets']['B']['coupling_to_other_targets_ff'],{'A,ab':3.,'VGND':4.})
        self.assertEqual(r['native_model_counts'],{'sky130_fd_pr__cap_mim_m3_1':1})

    def test_nonpassive_missing_and_hierarchical_views_refused(self):
        for line in ('R0 A B 0','R0 A B -1','C0 A B -1f','X0 A B other_subckt'):
            with self.subTest(line=line),self.assertRaises(ValueError):loading('.subckt test A B\n'+line+'\n.ends test\n',['A'])
        with self.assertRaises(ValueError):loading('.subckt test A B\n.ends test\n',['missing'])
        with self.assertRaises(ValueError):loading('.subckt test A B\n.ends test\n',['A','A'])


if __name__=='__main__':unittest.main()
