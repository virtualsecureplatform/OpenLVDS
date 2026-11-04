# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import mim_switch_abstract_v2 as view


class FineUnitAbstractTests(unittest.TestCase):
    def fixture(self):
        ports={name:dict(x_um=.3,y_um=i+1) for i,name in enumerate(['NODE','EN','ENB','VDD','VSS'])}
        blocks=[]
        for name,point in ports.items():
            y=point['y_um']
            blocks.append(f'  PIN {name}\n    ANTENNAGATEAREA 1 ;\n    PORT\n'
                '      LAYER met2 ;\n        RECT 0.1 0.2 0.4 0.5 ;\n'
                f'      LAYER met3 ;\n        RECT 0.1 {y-.1} 2.0 {y+.1} ;\n'
                '    END\n  END '+name+'\n')
        return ('MACRO unit\n  ORIGIN 0 -0.1 ;\n  SIZE 3 BY 7 ;\n'+''.join(blocks)+
            '  OBS\n      LAYER met1 ;\n        RECT 0 0 1 1 ;\n  END\nEND unit\n'),ports

    def test_only_public_rails_are_pins_and_all_other_routing_is_obstructed(self):
        text,ports=self.fixture();result,pins=view.abstract(text,ports)
        self.assertEqual(view.geometry(text),view.geometry(result))
        self.assertIn('  ORIGIN 0 -0.1 ;\n  SIZE 3 BY 7 ;',result)
        self.assertEqual(result.count('ANTENNAGATEAREA 1 ;'),5)
        for block in view.PIN.finditer(result):
            self.assertEqual([layer for layer,_ in view.rectangles(block[2])],['met3'])
        self.assertEqual(sum(layer=='met2' for layer,_ in view.rectangles(view.OBS.search(result)[1])),5)
        self.assertEqual(pins['VDD']['use'],'POWER');self.assertEqual(pins['VSS']['use'],'GROUND')
        self.assertEqual(pins['NODE']['direction'],'INPUT')
        self.assertEqual(pins['VDD']['direction'],'INOUT')

    def test_absent_or_ambiguous_public_rail_is_rejected(self):
        text,ports=self.fixture()
        with self.assertRaisesRegex(ValueError,'unique designated'):view.abstract(text,dict(ports,NODE=dict(x_um=20,y_um=1)))
        text=text.replace('RECT 0.1 0.9 2.0 1.1 ;','RECT 0.1 0.9 2.0 1.1 ;\n        RECT 0.2 0.8 1.9 1.2 ;')
        with self.assertRaisesRegex(ValueError,'unique designated'):view.abstract(text,ports)

    def test_unhandled_geometry_and_missing_pin_are_rejected(self):
        text,ports=self.fixture()
        with self.assertRaisesRegex(ValueError,'Unsupported LEF'):view.abstract(text.replace('RECT 0 0 1 1 ;','POLYGON 0 0 1 1 ;'),ports)
        with self.assertRaisesRegex(ValueError,'interface'):view.abstract(text,{n:p for n,p in ports.items() if n!='VSS'})
