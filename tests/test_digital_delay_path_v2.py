# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from clocking_v2 import Delay,common_legal_codes
from digital_delay_path_v2 import common_path

class CommonPathTests(unittest.TestCase):
    def test_overlapping_coarse_bands_need_one_shared_raw_code_path(self):
        tables={}
        for p,scale,offset in [('tt',1,80),('ss',1.5,123)]:
            table={}
            for band in range(2):
                for fine in range(17):
                    code=band*32+fine;lo=band*offset+fine*8*scale
                    table[code]=Delay(code,lo,lo+1)
            tables[p]=table
        result=common_path(tables,0,200)
        self.assertEqual(result['gap_limit_ps'],20)
        path=result['codes']
        common_legal_codes({p:[t[c] for c in path] for p,t in tables.items()})
        self.assertTrue(all(s>=200 for s in result['span_lower_bound_ps'].values()))
        self.assertFalse(result['characterization_admitted'])

    def test_individually_good_corner_orders_cannot_be_substituted(self):
        tables={p:{i:Delay(i,x,x+1) for i,x in enumerate(values)} for p,values in
                [('tt',[0,10,20,30]),('ss',[0,20,10,30])]}
        for table in tables.values():
            common_legal_codes({'corner':sorted(table.values(),key=lambda d:d.lo_ps)},15)
        with self.assertRaises(ValueError):common_path(tables,0,25,maximum_gap_ps=15)

    def test_prefer_ten_ps_and_reject_insufficient_range(self):
        table={i:Delay(i,i*4,i*4+1) for i in range(30)}
        result=common_path({'tt':table},0,100)
        self.assertEqual(result['gap_limit_ps'],10)
        self.assertLessEqual(result['worst_step_ps']['tt'],10)
        with self.assertRaises(ValueError):common_path({'tt':table},0,200)
        with self.assertRaises(ValueError):common_path({'tt':table},0,100,maximum_gap_ps=21)
