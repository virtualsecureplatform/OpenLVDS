# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import parallel_coarse_cell_v120 as c


class ParallelCoarseCellTests(unittest.TestCase):
    def records(self):
        return {c.INV:dict(size_um=[6.82,3.6],requires_external_taps=False,
            pins={p:dict(shapes=[['met3',[.2,y-w/2,6.62,y+w/2]]])
                  for p,y,w in [('VGND',.3,.6),('A',1.1,.32),('X',1.78,.32),('VPWR',3.3,.6)]})}

    def test_both_native_gang_sizes_join_every_true_rail_and_keep_one_public_output(self):
        records=self.records()
        for profile,count in c.COPIES.items():
            g,p=c.design(profile,records);self.assertEqual(len(g['cells']),count)
            self.assertEqual(g['ports'],['IN','OUT','VPWR','VGND'])
            self.assertTrue(all(x['pins']['A']=='IN' and x['pins']['X']=='OUT' for x in g['cells']))
            for route in p['fixed_routes']:
                pin=dict(IN='A',OUT='X').get(route['net'],route['net'])
                r=records[c.INV]['pins'][pin]['shapes'][0][1]
                for x,y in p['placements'].values():
                    self.assertLessEqual(route['rect'][0],round(x+r[0],6))
                    self.assertGreaterEqual(route['rect'][2],round(x+r[2],6))
            ref=c.reference(g,'.subckt '+c.INV+' A X VPWR VGND\n.ends\n')
            self.assertEqual(ref.count(' IN OUT VPWR VGND '+c.INV+'\n'),count)

    def test_unknown_untapped_and_shorting_rails_are_rejected(self):
        records=self.records()
        with self.assertRaises(ValueError):c.design('other',records)
        records[c.INV]['requires_external_taps']=True
        with self.assertRaisesRegex(ValueError,'tapped'):c.design('b2',records)
        records=self.records();records[c.INV]['pins']['A']=deepcopy(records[c.INV]['pins']['X'])
        with self.assertRaisesRegex(ValueError,'clearance'):c.design('b3',records)


if __name__=='__main__':unittest.main()
