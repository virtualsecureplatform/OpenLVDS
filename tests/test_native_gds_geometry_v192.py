# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_gds_names_v192 as p
try:
    import klayout.db as db
except ImportError:db=None


@unittest.skipIf(db is None,'requires KLayout Python')
class NameOnlyGeometryWitness(unittest.TestCase):
    def fixture(self,root):
        lib=db.Layout();lib.dbu=.001;cap=lib.create_cell('/work/OpenLVDS/cap');cap.shapes(lib.layer(68,20)).insert(db.Box(0,0,100,100))
        top=lib.create_cell('top');top.insert(db.CellInstArray(cap.cell_index(),db.Trans(50,60)))
        top.shapes(lib.layer(68,5)).insert(db.Text('CLK',db.Trans(2,3)))
        before=root/'before.gds';lib.write(str(before));cap.name='cap';after=root/'after.gds';lib.write(str(after))
        return before,after,{'top':'top','/work/OpenLVDS/cap':'cap'}

    def test_actual_gds_name_change_preserves_all_geometry_and_text(self):
        with tempfile.TemporaryDirectory() as directory:
            before,after,mapping=self.fixture(Path(directory));r=p.equivalent(str(before),str(after),mapping)
            self.assertTrue(r['all_masks_identical']);self.assertTrue(r['all_labels_identical']);self.assertTrue(r['all_child_and_root_placements_identical'])
            self.assertEqual(r['renamed_cells'],1);self.assertFalse(r['qualified_phy'])

    def test_actual_one_grid_mask_or_label_change_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for mode in ('mask','label'):
                before,after,mapping=self.fixture(root);lib=db.Layout();lib.read(str(after))
                if mode=='mask':lib.cell('cap').shapes(lib.layer(68,20)).insert(db.Box(100,0,101,100))
                else:
                    top=lib.cell('top');top.shapes(lib.layer(68,5)).clear();top.shapes(lib.layer(68,5)).insert(db.Text('OTHER',db.Trans(2,3)))
                lib.write(str(after))
                with self.subTest(mode=mode),self.assertRaisesRegex(ValueError,'changed GDS masks|changed GDS labels'):p.equivalent(str(before),str(after),mapping)

    def test_actual_one_grid_instance_change_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            before,after,mapping=self.fixture(Path(directory));lib=db.Layout();lib.read(str(after))
            next(lib.cell('top').each_inst()).trans=db.Trans(51,60);lib.write(str(after))
            with self.assertRaisesRegex(ValueError,'changed GDS placement'):p.equivalent(str(before),str(after),mapping)


if __name__=='__main__':unittest.main()
