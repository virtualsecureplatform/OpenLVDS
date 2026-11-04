# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from normalize_dcdl_macro_frames_v3 import add_keepouts

class MimKeepoutTests(unittest.TestCase):
    def test_adds_obstructions_without_changing_pin_geometry(self):
        text='MACRO cap\n  PIN NODE\n    PORT\n      LAYER met3 ;\n        RECT 0 0 10 0.4 ;\n    END\n  END NODE\n  OBS\n      LAYER met4 ;\n        RECT 1 2 3 4 ;\n  END\nEND cap\n'
        out=add_keepouts(text,[(1475,1055,5765,6345)],.001)
        self.assertEqual(out[:out.index('  OBS')],text[:text.index('  OBS')])
        self.assertIn('RECT 1.475000 1.055000 5.765000 6.345000 ;',out)
        self.assertIn('LAYER met4 ;\n        RECT 1 2 3 4 ;',out)
        self.assertEqual(add_keepouts(text,[],.001),text)

    def test_rejects_ambiguous_obstruction_section(self):
        with self.assertRaises(ValueError):add_keepouts('  OBS\n  END\n  OBS\n',[(0,0,10,10)],.001)

if __name__=='__main__':unittest.main()
