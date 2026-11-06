# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    import qualify_discharge_fine_driver_rc_v219 as p
except ModuleNotFoundError as e:
    if e.name not in ('klayout','pya'):raise
    p=None


@unittest.skipIf(p is None,'requires CAD KLayout environment')
class DischargeDriverRcAdmission(unittest.TestCase):
    def test_both_layouts_and_every_physical_gate_required(self):
        rows=[dict(spec=s,macro=p.physical.name(s),passed=True,lvs_passed=True,native_inventory_passed=True,drc_count='0') for s in p.physical.PROFILES]
        report=dict(passed=True,rows=rows);state=dict(status='complete',passed=True,qualified_phy=False)
        p.require_physical(state,report)
        for n in range(2):
            for key,value in [('passed',False),('lvs_passed',False),('native_inventory_passed',False),('drc_count','1')]:
                bad=deepcopy(report);bad['rows'][n][key]=value
                with self.subTest(row=n,key=key),self.assertRaises(ValueError):p.require_physical(state,bad)
        with self.assertRaises(ValueError):p.require_physical(dict(state,status='routing'),report)
        with self.assertRaises(ValueError):p.require_physical(state,dict(report,rows=rows[:1]))

    def test_actual_native_regular_pn_inventory_and_order(self):
        parent=p.ROOT/'build/diagnostics/discharge_fine_driver_physical_v218/e9cdc083fc9a84bc'
        if not parent.exists():self.skipTest('requires retained actual balanced native geometry')
        for s in p.physical.PROFILES:
            name=p.physical.name(s);text=(parent/name/(name+'.lvs.spice')).read_text()
            result=p.census(text,name,s);self.assertEqual(result['native_primitives'],s['n_fingers']+s['p_fingers']+1)
            with self.assertRaises(ValueError):p.census(text.replace('sky130_fd_pr__pfet_01v8','sky130_fd_pr__pfet_01v8_hvt',1),name,s)
            with self.assertRaises(ValueError):p.census(text.replace(' A Y VGND VPWR',' Y A VGND VPWR',1),name,s)


if __name__=='__main__':unittest.main()
