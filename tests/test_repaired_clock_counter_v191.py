# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_repaired_clock_counter_v191 as p


class RepairedClockCounterPhysical(unittest.TestCase):
    def cells(self):
        parent=p.ROOT/'build/diagnostics/counter_native_repairs_v183/15c6a8caf6163935'
        if not (parent/'pair.spice').exists():self.skipTest('requires retained native repaired counter pilot')
        return p.expected_cells((parent/'pair.spice').read_text(),(parent/'cells.spice').read_text())

    def test_exact_counter_repairs_and_both_clock_drivers_are_integrated(self):
        cells=self.cells();self.assertEqual(len(cells),21);by={c['name']:c for c in cells}
        self.assertEqual(by['low0_q']['model'],p.repaired.source.NEW)
        self.assertEqual(by['low0_set_pair']['model'],p.repaired.NEW)
        for tag in ('clock_driver','clock_driver_parallel'):
            self.assertEqual(by[tag]['pins'],dict(A='RCLK',X='CLK',VGND='VGND',VPWR='VPWR'))
        self.assertNotIn('prepare_load0',by);self.assertNotIn('mask_load',by)
        self.assertEqual(set(p.PORTS),{'RCLK','REQUEST','PREPARE','RESET_N','CLK','VPWR','VGND'})

    def test_new_clock_paths_are_separate_and_placed_above_the_counter(self):
        cells=self.cells();macros={c['model']:dict(bbox=[0,-2,40,12]) for c in cells};plan=p.default_plan()
        places,qx,bx=p.placement(cells,macros,plan);points,buses=p.routing(cells,places,qx,bx,plan)
        clock=[places[n] for n in ('clock_driver','clock_driver_parallel')]
        self.assertEqual(clock[0]['y'],clock[1]['y']);self.assertGreater(clock[1]['x']-clock[0]['x'],40)
        self.assertGreater(clock[0]['y'],places['request_driver']['y']+12)
        self.assertEqual(len(points['RCLK']),2);self.assertEqual({(e['cell'],e['pin'],e['x']) for e in points['RCLK']},
                          {(n,'A',8.) for n in ('clock_driver','clock_driver_parallel')})
        self.assertEqual({e['x'] for e in points['CLK']},{5.})
        self.assertGreater(min(buses[n] for n in ('RCLK','CLK','VGND','VPWR')),clock[0]['y']+12)
        self.assertEqual(plan['power_width_um'],.6);self.assertEqual(plan['power_spine_width_um'],2.)

    @unittest.skipUnless(Path(p.repaired.CAD).exists(),'requires pinned KLayout Python')
    def test_actual_gds_master_and_root_placement_mutations_are_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            code='''import sys
from pathlib import Path
import klayout.db as db
root=Path(sys.argv[1]);alter=int(sys.argv[2]);shift=int(sys.argv[3]);topname=sys.argv[4]
for model in ('Model_A','Model_B'):
    lib=db.Layout();lib.dbu=.001;native=lib.create_cell('same_native');native.shapes(lib.layer(68,20)).insert(db.Box(0,0,101 if alter and model=='Model_B' else 100,100))
    cell=lib.create_cell(model);cell.insert(db.CellInstArray(native.cell_index(),db.Trans()))
    lib.write(str(root/(model+'.gds')))
lib=db.Layout();lib.dbu=.001;native=lib.create_cell('same_native');native.shapes(lib.layer(68,20)).insert(db.Box(0,0,100,100));top=lib.create_cell(topname)
for model,x in [('Model_A',25000),('Model_B',55000)]:
    cell=lib.create_cell(model);cell.insert(db.CellInstArray(native.cell_index(),db.Trans()))
    top.insert(db.CellInstArray(cell.cell_index(),db.Trans(x+shift,10000)))
lib.write(str(root/'output.gds'))
'''
            def draw(alter,shift):subprocess.run([p.repaired.CAD,'-c',code,str(root),str(alter),str(shift),p.NAME],check=True,capture_output=True,text=True)
            macros={n:dict(folder=str(root)) for n in ('Model_A','Model_B')}
            cells=[dict(name='a',model='Model_A'),dict(name='b',model='Model_B')];places=dict(a=dict(x=25,y=10),b=dict(x=55,y=10))
            draw(0,0);result=p.native_master_witness(macros,root/'output.gds',cells,places)
            self.assertTrue(result['all_integrated_native_masters_preserved']);self.assertTrue(result['integrated_macro_placements_verified'])
            draw(1,0)
            with self.assertRaisesRegex(ValueError,'Conflicting physical master'):p.native_master_witness(macros)
            draw(0,1)
            with self.assertRaisesRegex(ValueError,'placement changed'):p.native_master_witness(macros,root/'output.gds',cells,places)


if __name__=='__main__':unittest.main()
