# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits
from receiver_light_clamp_experiment import source_variant,previous_source,TOP
ROOT=Path(__file__).resolve().parents[1]


class ReceiverLightClamp(unittest.TestCase):
    def test_only_two_parallel_resistors_are_removed(self):
        source=(ROOT/'analog/openlvds.spice').read_text();before=circuits(previous_source(source,True));after=circuits(source_variant(source,True))
        self.assertEqual(set(before),set(after));self.assertEqual(before[TOP][0],after[TOP][0])
        for name in before:
            if name!=TOP:self.assertEqual(before[name],after[name])
        old={r[0]:r for r in before[TOP][1]};new={r[0]:r for r in after[TOP][1]}
        self.assertEqual(set(old)-set(new),{'XCLAMP2','XCLAMP3'})
        self.assertEqual(new,{k:v for k,v in old.items() if k not in ['XCLAMP2','XCLAMP3']})

    def test_unclamped_control_remains_identical(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        self.assertEqual(source_variant(source,False),previous_source(source,False))
