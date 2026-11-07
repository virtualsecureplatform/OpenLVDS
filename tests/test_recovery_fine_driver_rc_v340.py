# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    import qualify_recovery_fine_driver_rc_v340 as p
except ModuleNotFoundError as e:
    if e.name not in ('klayout','pya'):raise
    p=None


@unittest.skipIf(p is None,'requires CAD KLayout environment')
class DischargeDriverRcAdmission(unittest.TestCase):
    def test_both_layouts_and_every_physical_gate_required(self):
        rows=[dict(spec=s,macro=p.physical.name(s),passed=True,lvs_passed=True,native_inventory_passed=True,drc_count='0') for s in p.physical.PROFILES]
        report=dict(passed=True,rows=rows);state=dict(status='complete',passed=True,qualified_phy=False)
        p.require_physical(state,report)
        for n in range(1):
            for key,value in [('passed',False),('lvs_passed',False),('native_inventory_passed',False),('drc_count','1')]:
                bad=deepcopy(report);bad['rows'][n][key]=value
                with self.subTest(row=n,key=key),self.assertRaises(ValueError):p.require_physical(state,bad)
        with self.assertRaises(ValueError):p.require_physical(dict(state,status='routing'),report)
        with self.assertRaises(ValueError):p.require_physical(state,dict(report,rows=rows*2))

    def test_actual_native_p40_n16_inventory_and_electrodes(self):
        parent=p.ROOT/'build/diagnostics/recovery_fine_driver_physical_v339/9462b5bca99a0905'
        spec=p.physical.PROFILES[0];name=p.physical.name(spec)
        text=(parent/name/(name+'.lvs.spice')).read_text()
        result=p.census(text,name,spec)
        self.assertEqual(result['native_primitives'],57)
        self.assertEqual(result['native_model_counts'],{'sky130_fd_pr__pfet_01v8':40,
            'sky130_fd_pr__nfet_01v8':16,p.physical.CAP:1})
        with self.assertRaises(ValueError):
            p.census(text.replace('sky130_fd_pr__pfet_01v8','sky130_fd_pr__pfet_01v8_hvt',1),name,spec)
        with self.assertRaises(ValueError):
            p.census(text.replace(' A Y VGND VPWR',' Y A VGND VPWR',1),name,spec)



if __name__=='__main__':unittest.main()
