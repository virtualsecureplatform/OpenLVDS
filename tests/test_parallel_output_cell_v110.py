# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import parallel_output_cell_v110 as cell


class ParallelOutputTests(unittest.TestCase):
    def records(self):
        return {cell.INV:dict(size_um=[12.55,15.4],requires_external_taps=False,
            pins={p:dict(shapes=[['met3',[.33,y,12.41,y+.32]]])
                  for p,y in [('VGND',0.),('A',1.66),('Y',3.1),('VPWR',4.4)]})}

    def test_each_bridge_contains_both_native_rails_without_crossing_other_ports(self):
        records=self.records();g,p=cell.design('inv2',records)
        self.assertEqual(len(g['cells']),2)
        self.assertEqual({c['pins']['Y'] for c in g['cells']},{'OUT'})
        self.assertEqual({r['net'] for r in p['fixed_routes']},set(g['ports']))
        for r in p['fixed_routes']:
            pin={'IN':'A','OUT':'Y'}.get(r['net'],r['net'])
            a=records[cell.INV]['pins'][pin]['shapes'][0][1]
            for x,y in p['placements'].values():
                self.assertLessEqual(r['rect'][0],x+a[0])
                self.assertGreaterEqual(r['rect'][2],x+a[2])
                self.assertEqual(r['rect'][1],round(y+a[1],6))
                self.assertEqual(r['rect'][3],round(y+a[3],6))
        lib='.subckt '+cell.INV+' A VGND VPWR Y\nXdummy A Y VGND VPWR native\n.ends\n'
        ref=cell.reference(g,lib)
        self.assertIn('Xinv0 IN VGND VPWR OUT '+cell.INV,ref)
        self.assertIn('Xinv1 IN VGND VPWR OUT '+cell.INV,ref)

    def test_untapped_missing_metal_and_shorting_rails_are_rejected(self):
        records=self.records();records[cell.INV]['requires_external_taps']=True
        with self.assertRaisesRegex(ValueError,'tapped'):cell.design('inv2',records)
        records=self.records();records[cell.INV]['pins']['A']['shapes'][0][0]='li1'
        with self.assertRaisesRegex(ValueError,'M3'):cell.design('inv2',records)
        records=self.records();records[cell.INV]['pins']['A']=deepcopy(records[cell.INV]['pins']['Y'])
        with self.assertRaisesRegex(ValueError,'clearance'):cell.design('inv2',records)


if __name__=='__main__':unittest.main()
