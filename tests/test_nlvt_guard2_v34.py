# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import build_nlvt_guard2_v34 as physical


class NativeGuardTwoTests(unittest.TestCase):
    def native(self, size):
        rows=['.subckt fixture A Y VGND VPWR']
        for model,body in [(physical.previous.tg.N,'VGND'),(physical.previous.tg.P,'VPWR')]:
            for i in range(8):
                rows.append(f'X{body}{i} Y A {body} {body} {model} w=.65 l=.15 ad=.2 as=.3 pd=1 ps=2')
        rows += [f'XC Y VGND sky130_fd_pr__cap_mim_m3_1 w={size} l={size}','.ends fixture']
        return '\n'.join(rows)+'\n'

    def test_only_guard_dimension_changes(self):
        report=physical.native_check(self.native(3),self.native(2))
        self.assertEqual(report['native_guard_mim_um'],[2,2])
        self.assertTrue(report['all_sixteen_native_mos_and_junctions_preserved'])

    def test_wrong_native_guard_and_connection_are_rejected(self):
        for text in [self.native(1),self.native(3),self.native(2).replace('XC Y VGND','XC A VGND')]:
            with self.subTest(source=text[-100:]),self.assertRaises(ValueError):physical.native_check(self.native(3),text)

    def test_mos_width_junction_and_body_changes_are_rejected(self):
        for before,after in [('w=.65','w=.66'),('ad=.2','ad=.21'),('A VGND VGND','A VGND VPWR')]:
            with self.subTest(fault=before),self.assertRaises(ValueError):
                physical.native_check(self.native(3),self.native(2).replace(before,after,1))

    def test_source_renames_root_and_keeps_native_low_vt_core_name(self):
        core=physical.OLD+'_core'
        source=f'.subckt {core} A Y VGND VPWR\n.ends\n.subckt {physical.OLD} A Y VGND VPWR\nXgate A Y VGND VPWR {core}\nXC Y VGND sky130_fd_pr__cap_mim_m3_1 w=3 l=3\n.ends {physical.OLD}\n'
        result=physical.schematic(source)
        self.assertIn('.subckt '+physical.NAME+' ',result);self.assertIn(' '+core+'\n',result)
        self.assertIn('w=2 l=2',result);self.assertNotIn(physical.NAME+'_core',result)


if __name__=='__main__':unittest.main()
