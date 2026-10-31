# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits,flatten
from receiver_clamp_experiment import source_variant as baseline,TOP
from receiver_strong_clamp_experiment import source_variant
from layout_receiver_strong_clamp_candidate import place_clamp
ROOT=Path(__file__).resolve().parents[1]


class StrongClampPlacement(unittest.TestCase):
    def test_only_ten_added_devices_move_and_all_original_devices_are_preserved(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        _,original=flatten(circuits(baseline(source,False)),TOP)
        _,devices=flatten(circuits(source_variant(source,True)),TOP)
        result=place_clamp(devices)
        self.assertEqual({d['name']:d for d in devices},{d['name']:d for d in result})
        self.assertEqual([d for d in result if d in original],original)
        at=next(i for i,d in enumerate(result) if '__XIB0__' in d['name'])
        self.assertEqual(len([d for d in result[at-10:at] if d not in original]),10)

    def test_weak_clamp_cannot_be_mislabeled_as_strong(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        _,devices=flatten(circuits(baseline(source,True)),TOP)
        with self.assertRaisesRegex(ValueError,'topology'):place_clamp(devices)
