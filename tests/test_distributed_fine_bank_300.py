# SPDX-License-Identifier: GPL-3.0-only
import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import distributed_fine_bank_300 as p

class DistributedFineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=p.mim.ROOT/'build/diagnostics/pullup_restored_bank_v360/8dba212d4f9eafd5'
        cls.original=(folder/'bank.spice').read_text();cls.obs=json.loads((folder/'manifest.json').read_text())['identity']['observations']
    def test_all_control_variants_preserve_native_maps_and_polarity(self):
        for variant in p.VARIANTS:
            text,obs,r=p.transform(self.original,self.obs,variant)
            self.assertEqual(len(obs['devices']),r['native_mos'])
            self.assertEqual(obs['controls'],self.obs['controls'])
            self.assertEqual(len(obs['programming_gates']),r['programming_gates'])
            body=p.SOURCE.native.definitions(text)[r['macro_top']][1]
            self.assertIn(['Xfine_pre','selected','pre_out','VGND','VPWR',p.mim.single.parent.FINE],body)
            self.assertEqual(r['pre_mos_after'],112)
            self.assertFalse(r['qualified_phy'])
    def test_strength_control_changes_only_pre_driver_call(self):
        base,_,r=p.mim.transform(self.original,self.obs,p.mim.qualified_cell(),copies=4,driver='p80')
        changed,_,new=p.transform(self.original,self.obs,'strong_pre_c4')
        before=p.SOURCE.native.definitions(base)[r['macro_top']][1]
        after=p.SOURCE.native.definitions(changed)[new['macro_top']][1]
        self.assertEqual([(a[0],b[0]) for a,b in zip(before,after) if a!=b],[('Xfine_pre','Xfine_pre')])
    def test_split_control_changes_only_thirty_one_capacitor_attachments(self):
        base,_,r=p.transform(self.original,self.obs,'strong_pre_c2')
        changed,_,new=p.transform(self.original,self.obs,'split_c1_c1')
        before=p.SOURCE.native.definitions(base)[r['macro_top']][1]
        after=p.SOURCE.native.definitions(changed)[new['macro_top']][1]
        pairs=[(a,b) for a,b in zip(before,after) if a!=b]
        self.assertEqual(len(pairs),31);self.assertEqual(r['native_mos'],new['native_mos'])
        self.assertEqual(r['native_mims'],new['native_mims'])
        for a,b in pairs:self.assertEqual(a[2:],b[2:]);self.assertEqual((a[1],b[1]),('fine_node','pre_out'))
    def test_rejects_unplanned_variants(self):
        with self.assertRaises(ValueError):p.transform(self.original,self.obs,'unqualified_driver')
