# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import importlib.util
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))


@unittest.skipUnless(importlib.util.find_spec('klayout'),'KLayout required for native component verifier')
class SetterGuardParameterChecks(unittest.TestCase):
    def devices(self,size):
        result=[]
        for model in ('sky130_fd_pr__nfet_01v8','sky130_fd_pr__pfet_01v8_hvt'):
            result += [dict(name=model+str(k),nodes=['Y','B','VGND','VGND'],model=model,params=dict(w='1',l='.15',ad='.1',**{'as':'.1'},pd='1',ps='1')) for k in range(18)]
        for k in range(4):result.append(dict(name='C'+str(k),nodes=['Y' if k<2 else 'MID'+str(k),'VGND'],model='sky130_fd_pr__cap_mim_m3_1',params=dict(w=str(size if k<2 else 2),l=str(size if k<2 else 2))))
        return result

    def test_only_two_output_guard_dimensions_change_and_inputs_stay_intact(self):
        import qualify_counter_setter_guard3_rc_v182 as p
        before=self.devices(1);after=self.devices(3);saved=deepcopy(after);r=p.parameter_change(before,after)
        self.assertEqual(after,saved);self.assertEqual(r['output_guards_changed'],2)
        self.assertTrue(r['all_mos_dimensions_and_junctions_preserved']);self.assertTrue(r['other_mim_dimensions_preserved'])
        self.assertTrue(r['normalized_reference_comparison']['native_parameters_preserved']);self.assertFalse(r['qualified_phy'])

    def test_wrong_guard_private_cap_mos_geometry_or_census_is_rejected(self):
        import qualify_counter_setter_guard3_rc_v182 as p
        before=self.devices(1)
        for kind in ('output_size','private_cap','mos','missing','wrong_net'):
            after=self.devices(3)
            if kind=='output_size':after[36]['params']['w']='2'
            elif kind=='private_cap':after[39]['params']['l']='3'
            elif kind=='mos':after[0]['params']['ad']='.2'
            elif kind=='missing':after.pop(0)
            else:after[36]['nodes'][0]='MID'
            with self.subTest(kind=kind),self.assertRaises(ValueError):p.parameter_change(before,after)


if __name__=='__main__':unittest.main()
