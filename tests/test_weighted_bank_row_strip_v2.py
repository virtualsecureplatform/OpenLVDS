# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import weighted_bank_row_strip_v2 as strip


class ControlRowTests(unittest.TestCase):
    def fixture(self):
        model=strip.flow.SC+'buf_4'
        spec={'cells':[{'name':f'c{i}','model':model} for i in range(16)]+[{'name':'macro','model':'native'}]}
        places={f'c{i}':{'location':[10+i*3.68,29.92],'orientation':'N'} for i in range(16)}
        return spec,places,{model:{'width':2.76,'height':2.72}}

    def test_native_control_extent_uses_all_sixteen_cells_and_real_cell_width(self):
        spec,places,sizes=self.fixture()
        self.assertEqual(strip.control_box(spec,places,sizes),[10000,29920,67960,32640])

    def test_missing_control_multiple_rows_wrong_height_and_orientation_are_rejected(self):
        spec,places,sizes=self.fixture()
        for change in ['missing','row','height','orientation']:
            p=deepcopy(places);s=deepcopy(sizes)
            if change=='missing':p.pop('c15')
            elif change=='row':p['c15']['location'][1]+=2.72
            elif change=='height':s[next(iter(s))]['height']=5.44
            else:p['c15']['orientation']='FS'
            with self.assertRaises(ValueError):strip.control_box(spec,p,s)
