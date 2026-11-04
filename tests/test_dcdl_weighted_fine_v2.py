# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcdl_weighted_fine_v2 as bank


class WeightedFineTopologyTests(unittest.TestCase):
    def test_native_mim_areas_preserve_all_31_unit_weights(self):
        self.assertEqual([w*l for w,l in bank.GEOMETRIES],[6,12,24,48,96])
        self.assertEqual(sum(w*l for w,l in bank.GEOMETRIES),31*2*3)
        for variant in bank.SCALES:
            text=bank.fine_cells(variant)
            self.assertEqual(text.count('XSWN '),5);self.assertEqual(text.count('XSWP '),5)
            self.assertEqual(text.count('XCLR '),5);self.assertEqual(text.count('XCCTRL '),5)
            self.assertNotIn('.ic',text);self.assertNotIn(' CLOAD ',text)

    def test_complete_native_coarse_path_is_preserved(self):
        orders={}
        for c in bank.old.instances():
            if c['name'].startswith(('fine_unit','fine_buffer','fine_inverse')) or c['name']=='shared_base':continue
            orders[c['model']]=list(c['pins'])+(['VGND','VNB','VPB','VPWR'] if c['model'].startswith(bank.old.native.SC) else [])
        orders[bank.old.native.SC+'buf_1']=['A','X','VGND','VNB','VPB','VPWR']
        orders[bank.old.native.SC+'inv_1']=['A','Y','VGND','VNB','VPB','VPWR']
        text=bank.source('unit',orders)
        for c in bank.old.instances():
            if c['name'].startswith(('fine_unit','fine_buffer','fine_inverse')) or c['name']=='shared_base':continue
            self.assertEqual(len(re.findall(r'(?m)^X'+re.escape(c['name'])+r' ',text)),1)
        self.assertEqual(len(re.findall(r'(?m)^Xfine\d ',text)),5)
        self.assertNotIn(' E0 ',text);self.assertIn(' B0 ',text)


if __name__=='__main__':unittest.main()
