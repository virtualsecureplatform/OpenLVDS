# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from unittest.mock import patch
from dll_design import candidate_source
from dll_campaign import text_block, bias_reference_count
from repair_dll_monitor import repaired_source
import screen_repaired_dll as screen

ROOT=Path(__file__).resolve().parents[1]


class RepairedDLLScreen(unittest.TestCase):
    def source(self):
        return candidate_source((ROOT/'analog/openlvds.spice').read_text(),'ota_w8_c4',
                                (ROOT/'analog/experiments/phase_area.spice').read_text())

    def test_screen_uses_submitted_monitor_and_preserves_native_detector_and_bias(self):
        original=self.source();repair=repaired_source(original)
        native_pfd='.subckt lvds_pfd REF FB RESET_N PD_ENABLE UP DN VDDD VSS\n* extracted detector sentinel\n.ends lvds_pfd'
        from spice_library import replace
        captured=replace(original,'lvds_pfd',native_pfd)
        result=screen.source_library(repair,captured)
        self.assertIn(native_pfd,result)
        self.assertEqual(text_block(result,'lvds_bias'),text_block(original,'lvds_bias'))
        analog=text_block(result,'openlvds_dll_analog')
        self.assertIn('XAREA__XCU_3',analog)
        self.assertIn('XAREA__XCD_3',analog)
        self.assertEqual(bias_reference_count('XL A B C D E F G H I J K L M N O P openlvds_dll',result),1)

    def test_screen_uses_candidate_core_connections(self):
        original=self.source();modified=original.replace('XPFD PD_REF PH180','XPFD PH0 PH180')
        result=screen.source_library(modified,original)
        self.assertEqual(text_block(result,'openlvds_dll_core'),text_block(modified,'openlvds_dll_core'))

    def test_changed_source_is_rejected_before_any_evidence_is_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'inputs').mkdir();source=root/'inputs/ota_w8_c4.spice';source.write_text('altered')
            manifest=dict(identity=dict(producer_code={'captured':'code'},source_sha256='old'),tasks=[])
            with patch.object(screen,'producer_code',return_value={'captured':'code'}):
                with self.assertRaisesRegex(ValueError,'source changed'):screen.validate(root,manifest)

    def test_changed_producer_is_rejected(self):
        with patch.object(screen,'producer_code',return_value={'new':'code'}):
            with self.assertRaisesRegex(ValueError,'producer changed'):
                screen.validate(Path('.'),dict(identity=dict(producer_code={'old':'code'})))
