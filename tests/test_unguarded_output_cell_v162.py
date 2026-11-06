# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))


@unittest.skipUnless(importlib.util.find_spec('klayout'),'KLayout required for native mask tests')
class UnguardedOutputTests(unittest.TestCase):
    def test_schematic_removes_only_guard_and_renames_hierarchy(self):
        import build_unguarded_output_cell_v162 as p
        text=f'.subckt {p.INV} A Y VGND VPWR\nX0 Y A VGND VGND nfet w=.65 l=.15 ad=.1\nX8 Y VGND sky130_fd_pr__cap_mim_m3_1 l=2 w=2\n.ends\n.subckt {p.OLD} IN OUT VPWR VGND\nXinv0 IN OUT VGND VPWR {p.INV}\nXinv1 IN OUT VGND VPWR {p.INV}\n.ends\n'
        candidate=p.schematic(text)
        self.assertNotIn('cap_mim',candidate)
        self.assertIn('X0 Y A VGND VGND nfet w=.65 l=.15 ad=.1\n',candidate)
        self.assertEqual(candidate.count(p.NEW_INV),3)
        self.assertIn(p.NAME,candidate)
        for wrong in (text.replace('l=2 w=2','l=3 w=2'),text.replace('X8 Y VGND','X8 A VGND')):
            with self.assertRaises(ValueError):p.schematic(wrong)

    def test_geometry_drops_guards_but_rejects_mos_or_wiring_changes(self):
        import build_unguarded_output_cell_v162 as p
        db=p.base.db
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.gds';target=Path(directory)/'candidate.gds'
            lib=db.Layout();lib.dbu=.001
            cap=lib.create_cell(p.CAP);core=lib.create_cell('native_core');inv=lib.create_cell(p.INV);top=lib.create_cell(p.OLD)
            layer=lib.layer(68,20);core.shapes(layer).insert(db.Box(0,0,100,100))
            cap.shapes(layer).insert(db.Box(0,0,200,200))
            inv.insert(db.CellInstArray(core.cell_index(),db.Trans()))
            inv.insert(db.CellInstArray(cap.cell_index(),db.Trans(500,0)))
            for x in (0,1000):top.insert(db.CellInstArray(inv.cell_index(),db.Trans(x,0)))
            top.shapes(layer).insert(db.Box(0,0,1500,20));lib.write(str(source))
            proof=p.geometry(source,target);self.assertEqual(proof['output_guard_instances_removed'],2)
            for cellname in ('native_core',p.NAME):
                changed=db.Layout();changed.read(str(target));changed.cell(cellname).shapes(changed.layer(68,20)).insert(db.Box(0,300,50,350))
                wrong=Path(directory)/(cellname+'.gds');changed.write(str(wrong))
                with self.assertRaises(ValueError):p.mask_check(source,wrong)


if __name__=='__main__':unittest.main()
