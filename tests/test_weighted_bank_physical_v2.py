# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import weighted_bank_physical_v2 as bank
import assemble_weighted_bank_v2 as assembly
import verify_weighted_bank_assembly_v2 as verification


class WeightedBankPhysicalTests(unittest.TestCase):
    def test_independent_connection_reader_uses_actual_model_order(self):
        text='.subckt bank IN CLK OUT VDD VSS\nXfirst IN VSS CLK VDD OUT gate\n.ends\n'
        top,ports,models,pins=verification.connections(text,dict(gate=['B','VGND','A','VPWR','Y']))
        self.assertEqual(models,dict(first='gate'))
        self.assertEqual(pins[('first','B','IN')],1)
        self.assertEqual(pins[('first','A','CLK')],1)
        self.assertEqual(pins[('first','VGND','VSS')],1)
        self.assertEqual(len(pins),5)

    def test_independent_connection_reader_rejects_duplicate_or_missing_instances(self):
        text='.subckt bank IN OUT\nXfirst IN OUT gate\n.ends\n'
        for changed in [text.replace('Xfirst IN OUT gate','Xfirst IN OUT gate\nXfirst IN OUT gate'),
                        text.replace('Xfirst IN OUT gate','Xfirst IN gate'),
                        text.replace('Xfirst IN OUT gate','Rfirst IN OUT 2')]:
            with self.assertRaises(ValueError):verification.connections(changed,dict(gate=['A','Y']))

    def test_complete_hierarchy_preserves_choices_fine_drivers_and_body_pins(self):
        cells=bank.instances();self.assertEqual(len(cells),94)
        hard=[c for c in cells if not c['model'].startswith('sky130_fd_sc_hd__')]
        self.assertEqual(len(hard),78);self.assertEqual(len({c['model'] for c in hard}),11)
        for role,count in [('forward',15),('turn',16),('pass',15),('merge',16)]:
            self.assertEqual(len([c for c in cells if c['name'].startswith(role)]),count)
        orders={c['model']:list(c['pins']) for c in cells}
        for c in cells:
            if c['model'].startswith('sky130_fd_sc_hd__'):
                orders[c['model']]=list(c['pins'])+['VPWR','VGND','VPB','VNB']
        tie=next(c for c in cells if c['name']=='tie')
        self.assertEqual(bank.pins(tie,orders)['VNB'],'VGND')
        self.assertEqual(bank.pins(tie,orders)['VPB'],'VPWR')
        self.assertEqual(bank.spice(orders).count('\nX'),94)
        self.assertEqual(bank.verilog(orders).count('dont_touch="true"'),94)

    def test_full_leaf_proof_preserves_passives_dimensions_and_multiplicity(self):
        source='.subckt reference IN OUT VDD VSS\nR0 IN OUT 5\nXcap OUT VSS sky130_fd_pr__cap_mim_m3_1 w=4 l=4\n.ends\n'
        physical='.subckt plate NODE VSS\nXc NODE VSS sky130_fd_pr__cap_mim_m3_1 l=4 w=4\n.ends\n.subckt physical IN OUT VPWR VGND\nR0 IN OUT 5\nXb OUT VGND plate\n.ends\n'
        self.assertEqual(bank.leaves(source,'reference'),bank.leaves(physical,'physical'))
        for changed in [physical.replace('R0 IN OUT 5\n',''),physical.replace('w=4','w=3'),
                        physical.replace('Xb OUT VGND plate','Xb OUT VGND plate\nXextra OUT VGND plate')]:
            self.assertNotEqual(bank.leaves(source,'reference'),bank.leaves(changed,'physical'))
        with self.assertRaises(ValueError):bank.leaves('.subckt recursive A\nXself A recursive\n.ends\n','recursive')

    def test_placement_uses_actual_large_macro_dimensions(self):
        cells=bank.instances();models={c['model'] for c in cells if not c['model'].startswith('sky130_fd_sc_hd__')}
        with tempfile.TemporaryDirectory() as folder:
            macros={}
            for model in models:
                # Deliberately much wider than the old bank's fixed pitch.
                width=120 if model==bank.candidate.GUARD else 30
                height=60 if 'weighted_fine_root' in model else 20
                path=Path(folder)/(model+'.lef')
                path.write_text(f'MACRO {model}\n  SIZE {width} BY {height} ;\nEND {model}\n')
                macros[model]=dict(lef=[str(path)])
            places,die=assembly.locations(macros)
            self.assertEqual(len(places),78)
            self.assertGreaterEqual(places['pass0']['location'][0]-places['turn0']['location'][0],130)
            self.assertGreaterEqual(places['fine1']['location'][1]-places['fine0']['location'][1],70)
            self.assertGreater(die[2],400)
