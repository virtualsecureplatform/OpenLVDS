# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import tapped_output_cell_v72 as p


class TappedOutputRowsTests(unittest.TestCase):
    def records(self):
        return {m:dict(size_um=[w,2.72],pins={k:dict(shapes=[['li1' if k in ('A','X') else 'met1',[.1,.2,.3,.4]]]) for k in pins})
            for m,w,pins in [(p.floor.FILL,.46,['VPWR','VGND','VPB','VNB']),
                            (p.floor.TAP,.46,['VPWR','VGND']),
                            (p.MODELS['buf1'],1.38,['A','X','VPWR','VGND','VPB','VNB']),
                            (p.MODELS['buf4'],2.76,['A','X','VPWR','VGND','VPB','VNB'])]}

    def test_each_native_buffer_has_continuous_fill_tap_row_and_actual_signal_ports(self):
        records=self.records()
        for profile in ('buf1','buf4'):
            g,plan=p.design(profile,records)
            self.assertEqual(g['ports'],['IN','OUT','VPWR','VGND'])
            self.assertEqual(len(plan['cells']),5);self.assertEqual(len(plan['tapped_groups']),1)
            p.floor.validate_groups(plan['cells'],plan['placements'],records,plan['tapped_groups'])
            self.assertEqual(sum(c['model']==p.floor.TAP for c in plan['cells']),2)
            self.assertEqual(g['cells'][0]['pins']['VNB'],'VGND');self.assertEqual(g['cells'][0]['pins']['VPB'],'VPWR')
            self.assertEqual(plan['ports']['IN']['layer'],'li1');self.assertEqual(plan['ports']['OUT']['layer'],'li1')

    def test_unknown_cell_or_missing_native_metal_access_is_rejected(self):
        records=self.records()
        with self.assertRaisesRegex(ValueError,'Unknown'):p.design('other',records)
        records[p.MODELS['buf1']]['pins']['A']['shapes']=[['pwell',[.1,.2,.3,.4]]]
        with self.assertRaisesRegex(ValueError,'real signal'):p.design('buf1',records)


if __name__=='__main__':unittest.main()
