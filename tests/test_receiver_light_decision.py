# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits
from receiver_light_decision_experiment import source_variant,previous_source,TOP
ROOT=Path(__file__).resolve().parents[1]


class ReceiverLightDecision(unittest.TestCase):
    def test_only_coherent_decision_sizes_return_to_original_values(self):
        source=(ROOT/'analog/openlvds.spice').read_text();before=circuits(previous_source(source,True));after=circuits(source_variant(source,True))
        self.assertEqual(set(before),set(after));self.assertEqual(before[TOP][0],after[TOP][0])
        for name in before:
            if name!=TOP:self.assertEqual(before[name],after[name])
        old={r[0]:r for r in before[TOP][1]};new={r[0]:r for r in after[TOP][1]};canonical={r[0]:r for r in circuits(source)[TOP][1]}
        self.assertEqual(set(old),set(new))
        for name,row in old.items():
            if name in ['XCT','XC0','XC1','XCD','XCM']:
                self.assertEqual(new[name],canonical[name])
            else:self.assertEqual(new[name],row)
        self.assertEqual(new['XNT'][3]['w'],'24');self.assertEqual(new['XPT'][3]['w'],'24')

    def test_original_unclamped_control_is_preserved(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        self.assertEqual(source_variant(source,False),previous_source(source,False))

    def test_unexpected_decision_geometry_is_rejected(self):
        source=(ROOT/'analog/openlvds.spice').read_text().replace('XCT CT NBC VSS VSS sky130_fd_pr__nfet_01v8 w=64',
                                                                'XCT CT NBC VSS VSS sky130_fd_pr__nfet_01v8 w=32')
        with self.assertRaisesRegex(ValueError,'decision topology'):source_variant(source,True)
