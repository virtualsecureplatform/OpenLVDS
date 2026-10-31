# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits
from receiver_wide_input_experiment import source_variant,previous_source,TOP
ROOT=Path(__file__).resolve().parents[1]


class ReceiverWideInput(unittest.TestCase):
    def test_only_four_input_widths_change_without_bias_or_load_changes(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        before=circuits(previous_source(source,True));after=circuits(source_variant(source,True))
        self.assertEqual(set(before),set(after));self.assertEqual(before[TOP][0],after[TOP][0])
        for name in before:
            if name!=TOP:self.assertEqual(before[name],after[name])
        old={r[0]:r for r in before[TOP][1]};new={r[0]:r for r in after[TOP][1]}
        self.assertEqual(set(old),set(new))
        for name,row in old.items():
            if name in ['XNP','XNN','XPP','XPN']:
                self.assertEqual(new[name][:3],row[:3]);self.assertEqual(new[name][3],dict(w='40',l='0.5'))
            else:self.assertEqual(new[name],row)

    def test_unclamped_control_remains_the_same_original_source(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        self.assertEqual(source_variant(source,False),previous_source(source,False))

    def test_unexpected_input_size_is_rejected(self):
        source=(ROOT/'analog/openlvds.spice').read_text().replace('XNP NL INP NT VSS sky130_fd_pr__nfet_g5v0d10v5 w=20',
                                                                'XNP NL INP NT VSS sky130_fd_pr__nfet_g5v0d10v5 w=10')
        with self.assertRaisesRegex(ValueError,'input-pair'):source_variant(source,True)
