# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
import re
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    import klayout.db
except ImportError:
    CAD=False
else:
    CAD=True


@unittest.skipUnless(CAD,'KLayout required by native geometry binder')
class RegularPairJunctionReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import analyze_regular_regenerated_junctions_v276 as producer
        cls.p=producer
        parent=producer.ROOT/'build/diagnostics/regular_regenerated_placement_v272/82dc7493ef40f70d'
        standards=producer.ROOT/'build/diagnostics/isolated_bank_standard_references_v250/70e0b0dbd0180169'
        cls.pi=json.loads((parent/'manifest.json').read_text())['identity']
        cls.merged=json.loads((parent/'summary.json').read_text())['merged_library']
        cls.si=json.loads((standards/'manifest.json').read_text())['identity']
        cls.original=json.loads((producer.ROOT/cls.pi['parent']/'manifest.json').read_text())['identity']

    def test_exact_unchanged_native_master_records_and_merged_masks_allow_reference_reuse(self):
        r=self.p.standard_reuse(self.pi,self.original,self.si,self.merged)
        self.assertEqual(len(r['models']),5)
        self.assertTrue(r['exact_standard_master_records_preserved'])
        self.assertTrue(r['merged_native_masks_hierarchy_and_labels_preserved'])
        self.assertEqual(r['source_placement'],self.pi['parent'])
        self.assertFalse(r['qualified_phy'])

    def test_changed_parent_model_inventory_native_geometry_or_masks_cannot_reuse_reference(self):
        bad=deepcopy(self.si);bad['parent']='another_parent'
        with self.assertRaisesRegex(ValueError,'source placement'):self.p.standard_reuse(self.pi,self.original,bad,self.merged)
        bad=deepcopy(self.si);bad['models'].pop(next(iter(bad['models'])))
        with self.assertRaisesRegex(ValueError,'five-master'):self.p.standard_reuse(self.pi,self.original,bad,self.merged)
        bad=deepcopy(self.pi);model=next(iter(self.si['models']));bad['records'][model]['size_um'][0]+=.005
        with self.assertRaisesRegex(ValueError,'master record'):self.p.standard_reuse(bad,self.original,self.si,self.merged)
        for key in ('all_native_cell_masks_preserved','all_native_instance_arrays_preserved','all_native_cell_labels_preserved'):
            bad=dict(self.merged);bad[key]=False
            with self.assertRaisesRegex(ValueError,'merged masks'):self.p.standard_reuse(self.pi,self.original,self.si,bad)

    def test_completed_fresh_extraction_reproduces_census_and_capacitor_diagnostic(self):
        parent=self.p.ROOT/'build/diagnostics/regular_regenerated_junctions_v276/ca85f4dd7ca7a27a'
        if not (parent/'summary.json').exists():self.skipTest('Completed native junction diagnostic unavailable')
        report=json.loads((parent/'summary.json').read_text());top=self.pi['graph']['top']
        self.assertEqual(json.loads((parent/'state.json').read_text()),dict(status='complete',analysis_completed=True,qualified_phy=False))
        self.assertTrue(all(self.p.sha(parent/n)==h for n,h in report['files'].items()))
        actual=re.sub(r'\n[ \t]*\+[ \t]*',' ',(parent/'ordinary'/(top+'.lvs.spice')).read_text())
        census=self.p.inventory.verify((parent/'reference.spice').read_text(),top,actual,top+'_flat')
        self.assertEqual(census,report['native_census']);self.assertEqual(census['native_primitives'],1572)
        measurements=json.loads((self.p.MEASUREMENTS/'summary.json').read_text())['rows']
        self.assertEqual(self.p.partition.diagnose(actual,top+'_flat',measurements),report['diagnostic'])
        self.assertEqual(report['diagnostic']['summary'],dict(devices=62,devices_with_mismatch=62,zero_field_mismatches=120,nonzero_field_mismatches=4))
        self.assertEqual(report['geometry']['bank_native_hierarchy']['native_instances'],353)
        self.assertTrue(report['geometry']['all_fine_active_regions_separate_between_instances'])
        for flag in ('whole_bank_native_lvs_passed','joint_rc_qualified','electrical_qualification_passed','qualified_phy'):
            self.assertFalse(report[flag])


if __name__=='__main__':unittest.main()
