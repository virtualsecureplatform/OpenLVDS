# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout import circuits
import receiver_strong_clamp_experiment as strong
ROOT=Path(__file__).resolve().parents[1]


class StrongReceiverClamp(unittest.TestCase):
    def test_only_reference_strength_and_parallel_clamp_count_change(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        before=circuits(strong.weak_source(source,True));after=circuits(strong.source_variant(source,True))
        self.assertEqual(set(after)-set(before),{strong.TRACK})
        for name in before:
            if name!=strong.TOP:self.assertEqual(before[name],after[name])
        self.assertEqual(before[strong.TOP][0],after[strong.TOP][0])
        old={r[0]:r for r in before[strong.TOP][1]};new={r[0]:r for r in after[strong.TOP][1]}
        self.assertEqual(set(new)-set(old),{'XCLAMP2','XCLAMP3'})
        for name in old:
            if name!='XTRACK':self.assertEqual(old[name],new[name])
        self.assertEqual(new['XTRACK'][1:3],(['CO_TRACK','CO_TRACK','VDDD','VSS'],strong.TRACK))
        for name in ['XCLAMP2','XCLAMP3']:self.assertEqual(new[name][1:],old['XCLAMP0'][1:])
        weak={r[0]:r for r in before[strong.MID][1]};reference={r[0]:r for r in after[strong.TRACK][1]}
        for name in ['XP','XN']:
            self.assertEqual(weak[name][:3],reference[name][:3])
            self.assertEqual(float(reference[name][3]['w']),4*float(weak[name][3]['w']))
            self.assertEqual(weak[name][3]['l'],reference[name][3]['l'])

    def test_unclamped_control_is_identical_to_original_schematic(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        self.assertEqual(strong.source_variant(source,False),strong.weak_source(source,False))

    def test_factory_and_attestation_are_restored_after_prepare_failure(self):
        previous_code=strong.experiment.CODE;previous_source=strong.experiment.source_variant
        def failed(parent):
            self.assertIn('receiver_strong_clamp_experiment.py',strong.experiment.CODE)
            self.assertIs(strong.experiment.source_variant,strong.source_variant)
            raise ValueError('capture failed')
        with patch.object(strong.experiment,'prepare',side_effect=failed):
            with self.assertRaisesRegex(ValueError,'capture failed'):strong.prepare(Path('/parent'))
        self.assertIs(strong.experiment.CODE,previous_code)
        self.assertIs(strong.experiment.source_variant,previous_source)
