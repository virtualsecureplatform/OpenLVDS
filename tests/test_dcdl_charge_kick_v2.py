# SPDX-License-Identifier: GPL-3.0-only
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_dcdl_charge_kick_v2 as source


class ChargeKickFixtures(unittest.TestCase):
    def test_serialized_updates_change_exactly_one_physical_gate_bit(self):
        for repair in ['single_low','single_high']:
            spec=source.specification(repair)
            for a,b in zip(spec['codes'],spec['codes'][1:]):
                # Controls are thermometer encoded, not a binary code bus.
                self.assertEqual(((1<<a)-1 ^ (1<<b)-1).bit_count(),1)
            self.assertEqual(spec['control_slew_ps'],20)
            self.assertEqual(spec['restore'],'mim2x2')

    def test_node_repairs_keep_the_original_worst_bulk_update(self):
        for repair,size in [('node_mim2x2',2),('node_mim4x4',4)]:
            self.assertEqual(source.specification(repair)['codes'],source.parent_source.CODES)
            text,devices=source.parent_source.original.policy.circuit(0)
            modified=source.circuit(text,repair)
            expected=f'XCKICK r0 VSS sky130_fd_pr__cap_mim_m3_1 w={size} l={size}\n'
            self.assertEqual(modified.replace(expected,''),text)
            self.assertEqual(len(devices),93)
            with patch.dict(os.environ,PDK_ROOT='/pdk'):
                deck=source.fixture(Path('/context'),source.specification(repair))
            self.assertIn(f'/coarse0_{repair}.spice"',deck)
            self.assertEqual(deck.count('XCEB'),31)
            self.assertIn('.options device temp=40',deck)
            self.assertIn('VDD VDD 0 1.8',deck)

    def test_single_bit_repair_does_not_change_delay_circuit(self):
        text,_=source.parent_source.original.policy.circuit(0)
        for repair in ['single_low','single_high']:
            self.assertEqual(source.circuit(text,repair),text)
        with self.assertRaises(ValueError):source.specification('unknown')
