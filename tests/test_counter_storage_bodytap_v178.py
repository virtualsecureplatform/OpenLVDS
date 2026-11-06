# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))


@unittest.skipUnless(importlib.util.find_spec('klayout'),'KLayout required for native contact-row geometry')
class StorageBodyTapTests(unittest.TestCase):
    def test_reference_and_magic_keep_original_devices_and_add_only_declared_contacts(self):
        import build_counter_storage_bodytap_v178 as p
        ref=f'.subckt {p.TAP} VGND VPWR\n.ends\n.subckt {p.OLD} A B Y VGND VPWR\nXn Y A VGND VGND nfet w=1 l=.15\n.ends {p.OLD}\n'
        plan=dict(count=2,pitch_um=.46,ground_y_um=-.4,layers=dict(metal2=[[0,-200,80,0]]))
        revised=p.schematic(ref,plan)
        self.assertIn('Xn Y A VGND VGND nfet w=1 l=.15\n',revised)
        for k in range(2):self.assertIn(f'Xtap_bottom{k} VGND VPWR {p.TAP}',revised)
        mag='magic\ntech sky130A\nmagscale 1 2\n<< metal2 >>\nrect 0 0 80 80\nuse core gate\ntimestamp 0\ntransform 1 0 0 0 1 0\nbox 0 0 80 80\n<< labels >>\n<< end >>\n'
        updated=p.geometry(mag,[0,0,.46,2.72],plan)
        for line in mag.splitlines():self.assertIn(line,updated)
        self.assertIn('transform 1 0 92 0 -1 -80',updated)
        with self.assertRaises(ValueError):p.geometry(updated,[0,0,.46,2.72],plan)

    def test_mask_proof_rejects_changed_native_mos_even_with_correct_contact_row(self):
        import build_counter_storage_bodytap_v178 as p
        db=p.rc_proof.db;plan=dict(count=2,pitch_um=.46,ground_y_um=-.4,layers={})
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'source.gds';candidate=Path(directory)/'candidate.gds';witness=Path(directory)/'row.gds'
            a=db.Layout();a.dbu=.001;core=a.create_cell('core');core.shapes(a.layer(65,20)).insert(db.Box(0,0,100,100))
            tap=a.create_cell(p.TAP);tap.shapes(a.layer(65,44)).insert(db.Box(0,0,100,100));top=a.create_cell(p.OLD);top.insert(db.CellInstArray(core.cell_index(),db.Trans()))
            a.write(str(source));top.name=p.NAME
            for k in range(2):top.insert(db.CellInstArray(tap.cell_index(),db.Trans(0,True,k*460,-400)))
            a.write(str(candidate))
            w=db.Layout();w.dbu=.001;wt=w.create_cell(p.TAP);wt.copy_tree(tap);row=w.create_cell(p.NAME+'_contact_row')
            for k in range(2):row.insert(db.CellInstArray(wt.cell_index(),db.Trans(0,True,k*460,-400)))
            w.write(str(witness));self.assertEqual(p.masks(source,candidate,plan,witness)['mirrored_native_body_taps'],2)
            core.shapes(a.layer(65,20)).insert(db.Box(200,0,300,100));a.write(str(candidate))
            with self.assertRaises(ValueError):p.masks(source,candidate,plan,witness)


if __name__=='__main__':unittest.main()
