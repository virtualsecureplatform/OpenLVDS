# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import re
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from normalize_dcdl_macro_frames_v2 import normalized_lef,boundary


class MacroFrameNormalizationTests(unittest.TestCase):
    def test_routed_global_pin_positions_are_preserved_in_zero_origin_frame(self):
        text='MACRO cell\nORIGIN 0.190 0.300 ;\nSIZE 6.820 BY 3.600 ;\nPIN VGND\nPORT\nLAYER met3 ;\nRECT 0 -0.300 6.440 0.300 ;\nEND\nEND VGND\nEND cell\n'
        result,offset=normalized_lef(text);self.assertEqual(offset,(.19,.3))
        self.assertIn('ORIGIN 0.000 0.000 ;',result);self.assertIn('RECT 0.190000 0.000000 6.630000 0.600000 ;',result)
        self.assertEqual(boundary(result,.001),[0,0,6820,3600])
        # Original DB pin = placement + old origin + old rectangle;
        # canonical DB/GDS pin = placement + translated rectangle.
        old=[0,-.3,6.44,.3];new=[.19,0,6.63,.6]
        for n,(a,b) in enumerate(zip(old,new)):self.assertAlmostEqual(a+offset[n%2],b)

    def test_negative_origin_and_obstructions_follow_the_same_rigid_translation(self):
        text='ORIGIN 0 -0.100 ;\nSIZE 12.400 BY 11.600 ;\nOBS\nLAYER met4 ;\nRECT 2.5 6.7 3.92 7.3 ;\nEND\n'
        result,offset=normalized_lef(text);self.assertEqual(offset,(0,-.1))
        self.assertIn('RECT 2.500000 6.600000 3.920000 7.200000 ;',result)

    def test_unhandled_geometry_does_not_get_silently_misregistered(self):
        with self.assertRaises(ValueError):normalized_lef('ORIGIN 0 0 ;\nPOLYGON 0 0 1 1 2 0 ;\n')


if __name__=='__main__':unittest.main()
