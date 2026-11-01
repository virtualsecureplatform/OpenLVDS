# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import layout_driver_restore_candidate as physical
import driver_restore_candidate_rc as rc
from driver_restore_variant import source_variant

SOURCE=(Path(__file__).resolve().parents[1]/'analog/openlvds.spice').read_text()


class DriverRestoreLayout(unittest.TestCase):
    def fixture(self,root):
        (root/'analog').mkdir();(root/'analog/openlvds.spice').write_text(SOURCE)
        (root/'scripts').mkdir()
        for name in physical.CODE:(root/'scripts'/name).write_text('# '+name+'\n')

    def draw(self,out,top,ports,devices,library):
        for suffix in ['.gds','.sch.spice','.lvs.log','.drc.txt','.drc_count.txt']:
            (out/(top+suffix)).write_text('0\n' if suffix=='.drc_count.txt' else suffix+'\n')
        return dict(ports=ports,devices=len(devices),gds=str(out/(top+'.gds')))

    def test_selected_sources_are_exact_original_and_ratio_only_factory(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.fixture(root)
            with patch.object(physical,'ROOT',root):
                self.assertEqual(physical.selected_source('source_control'),SOURCE)
                self.assertEqual(physical.selected_source('restore_64_24'),source_variant(SOURCE))
                with self.assertRaises(ValueError):physical.selected_source('unknown')

    def build(self,root,variant='restore_64_24'):
        with patch.object(physical,'ROOT',root),patch.object(physical,'invoke_magic'),\
             patch.object(physical,'pcell_info',return_value={}),patch.object(physical,'draw_macro',side_effect=self.draw),\
             patch.object(physical,'qualify',return_value=dict(passed=True,drc_count='0',lvs_passed=True)):
            return physical.build(variant)

    def test_cached_geometry_is_immutable_and_does_not_rerun_magic(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.fixture(root);out,summary=self.build(root)
            before=(out/'summary.json').read_bytes()
            self.assertFalse(summary['qualified_phy']);self.assertEqual(summary['identity']['restoration_widths_um'],[64,24])
            with patch.object(physical,'ROOT',root),patch.object(physical,'invoke_magic') as magic:
                cached,captured=physical.build('restore_64_24')
                self.assertEqual(cached,out);self.assertEqual(captured,summary);magic.assert_not_called()
            self.assertEqual((out/'summary.json').read_bytes(),before)

    def test_control_and_candidate_have_distinct_diagnostic_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.fixture(root)
            a,control=self.build(root,'source_control');b,candidate=self.build(root)
            self.assertNotEqual(a,b)
            self.assertEqual(control['identity']['restoration_widths_um'],[48,40])
            self.assertEqual(candidate['identity']['restoration_widths_um'],[64,24])
            self.assertIn('driver_restore_candidate_rc.py',candidate['identity']['code'])
            self.assertEqual(control['designs'][physical.TOP]['ports'],physical.PORTS)

    def test_changed_gds_is_rejected_by_both_cached_builder_and_extraction(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);self.fixture(root);out,_=self.build(root)
            (out/(physical.TOP+'.gds')).write_text('changed geometry')
            with patch.object(physical,'ROOT',root),self.assertRaisesRegex(ValueError,'geometry'):
                physical.build('restore_64_24')
            with patch.object(rc,'ROOT',root),patch.object(rc,'extract') as extract:
                with self.assertRaisesRegex(ValueError,'geometry'):rc.run(out)
                extract.assert_not_called()

    def test_extraction_rejects_artifacts_outside_driver_layout(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(rc,'ROOT',Path(directory)),patch.object(rc,'extract') as extract:
                with self.assertRaises(ValueError):rc.run(Path(directory)/'build/diagnostics/receiver_layout/test')
                extract.assert_not_called()


if __name__=='__main__':unittest.main()
