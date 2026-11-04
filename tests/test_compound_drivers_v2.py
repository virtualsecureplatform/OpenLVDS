# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_compound_drivers_v3 as driver
import restrict_macro_rails_v4 as rails


class CompoundDriverTests(unittest.TestCase):
    def test_native_bbox_ignores_sticky_labels_and_uses_masks(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'native.mag'
            path.write_text('magic\nrect -38 -48 600 592\nrlabel metal1 s 0 0 0 0 0 VPWR\nrect 20 30 700 620\n')
            self.assertEqual(driver.native_bbox(path),[-.19,-.24,3.5,3.1])
            path.write_text('magic\nrlabel metal1 s 0 0 0 0 0 VPWR\n')
            with self.assertRaisesRegex(ValueError,'rectangles'):driver.native_bbox(path)

    def test_source_includes_two_gates_and_real_taps_with_bulk_connections(self):
        for model,(inputs,output) in driver.topology.SIGNALS.items():
            gate_ports=[*inputs,'VGND','VNB','VPB','VPWR',output]
            lib='.subckt '+model+' '+' '.join(gate_ports)+'\n.ends '+model+'\n'
            lib+='.subckt '+driver.TAP+' VGND VPWR\n.ends '+driver.TAP+'\n'
            source=driver.source_schematic(model,lib)
            gates=[line.split() for line in source.splitlines() if line.startswith('Xgate')]
            self.assertEqual(len(gates),2)
            self.assertEqual(gates[0][1:],gates[1][1:])
            self.assertEqual(gates[0][1:],[*inputs,'VGND','VGND','VPWR','VPWR',output,model])
            self.assertIn('Xtap_left VGND VPWR '+driver.TAP,source)
            self.assertIn('Xtap_right VGND VPWR '+driver.TAP,source)
            with self.assertRaisesRegex(ValueError,'Missing native'):driver.source_schematic(model,lib.split('.subckt '+driver.TAP)[0])

    def test_output_access_and_no_obs_preserve_every_routing_shape(self):
        text=('MACRO pair\n  SIZE 3 BY 4 ;\n'
              '  PIN Y\n    PORT\n      LAYER met2 ;\n        RECT 1 1 1.4 2 ;\n'
              '      LAYER met3 ;\n        RECT 0.1 1.3 2.9 1.7 ;\n    END\n  END Y\nEND pair\n')
        result,view=rails.restrict(text,dict(Y=dict(x_um=.3,y_um=1.5)),dict(Y=('OUTPUT','SIGNAL')))
        self.assertEqual(view['Y']['direction'],'OUTPUT')
        self.assertEqual(rails.geometry.geometry(text),rails.geometry.geometry(result))
        self.assertEqual(len(list(rails.geometry.OBS.finditer(result))),1)
        self.assertIn('DIRECTION OUTPUT',result)
        with self.assertRaisesRegex(ValueError,'designated'):rails.restrict(text,dict(Y=dict(x_um=.3,y_um=3)),dict(Y=('OUTPUT','SIGNAL')))


if __name__=='__main__':unittest.main()
