# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits
from receiver_fast_restore_experiment import source_variant,previous_source,TOP
ROOT=Path(__file__).resolve().parents[1]


class ReceiverFastRestore(unittest.TestCase):
    def test_only_first_two_restoration_bindings_change(self):
        source=(ROOT/'analog/openlvds.spice').read_text();before=circuits(previous_source(source,True));after=circuits(source_variant(source,True))
        self.assertEqual(set(before),set(after));self.assertEqual(before[TOP][0],after[TOP][0])
        for name in before:
            if name!=TOP:self.assertEqual(before[name],after[name])
        old={r[0]:r for r in before[TOP][1]};new={r[0]:r for r in after[TOP][1]};self.assertEqual(set(old),set(new))
        for name,row in old.items():
            if name in ['XIB0','XIB1']:self.assertEqual(new[name][:2],row[:2]);self.assertEqual(new[name][3],row[3])
            else:self.assertEqual(new[name],row)
        self.assertEqual([new[name][2] for name in ['XIB0','XIB1','XIB2']],
                         ['lvds_rx_restore_mid','lvds_inv18_drive','lvds_inv18_drive'])
        self.assertEqual([r[3]['w'] for r in after['lvds_rx_restore_mid'][1]],['8','4'])
        self.assertEqual([r[3]['w'] for r in after['lvds_inv18_drive'][1]],['16','8'])

    def test_original_unclamped_control_is_identical(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        self.assertEqual(source_variant(source,False),previous_source(source,False))
