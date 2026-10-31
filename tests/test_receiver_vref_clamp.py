# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits
from receiver_vref_clamp_experiment import source_variant,previous_source,TOP
ROOT=Path(__file__).resolve().parents[1]


class ReceiverVrefClamp(unittest.TestCase):
    def test_only_two_resistor_reference_terminals_change(self):
        source=(ROOT/'analog/openlvds.spice').read_text();before=circuits(previous_source(source,True));after=circuits(source_variant(source,True))
        self.assertEqual(set(before),set(after));self.assertEqual(before[TOP][0],after[TOP][0])
        for name in before:
            if name!=TOP:self.assertEqual(before[name],after[name])
        old={r[0]:r for r in before[TOP][1]};new={r[0]:r for r in after[TOP][1]};self.assertEqual(set(old),set(new))
        for name,row in old.items():
            if name in ['XCLAMP0','XCLAMP1']:
                self.assertEqual(new[name][1],['CO','VREF','VSS']);self.assertEqual(new[name][2:],row[2:])
            else:self.assertEqual(new[name],row)
        connected=[r[0] for r in after[TOP][1] if 'CO_TRACK' in r[1]]
        self.assertEqual(connected,['XTRACK'])

    def test_unclamped_source_control_is_unchanged(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        self.assertEqual(source_variant(source,False),previous_source(source,False))
