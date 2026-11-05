# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import os
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import nlvt_guard2_bank_v36 as circuit
import probe_nlvt_guard2_bank_v36 as pilot
import verify_nlvt_guard2_bank_v36 as proof


class ActualGuardTwoBankTests(unittest.TestCase):
    def component(self,model,size):
        rows=[f'.subckt {model} A Y VGND VPWR','R1 A ag 1','C1 Y VGND 1f']
        for native,body in [(circuit.proof.physical.previous.tg.N,'VGND'),(circuit.proof.physical.previous.tg.P,'VPWR')]:
            for i in range(8):rows.append(f'X{body}{i} Y ag {body} {body} {native} w=.65 l=.15 ad=.2 as=.3 pd=1 ps=2')
        rows += [f'XC Y VGND sky130_fd_pr__cap_mim_m3_1 w={size} l={size}',f'.ends {model}']
        return '\n'.join(rows)+'\n'

    def inputs(self):
        cells=self.component(circuit.OLD,3)+'.subckt keep A Y\nR1 A Y 9\n.ends keep\n'
        root=circuit.baseline.name('actual_nlvt')
        bank=f'.subckt {root} IN OUT VPWR VGND\nXinput_inverse IN a VGND VPWR {circuit.OLD}\nXfine_driver selected OUT VGND VPWR {circuit.OLD}\n.ends {root}\n'
        return cells,bank,self.component(circuit.MODEL,2)

    def test_replaces_exactly_selected_drivers_and_keeps_all_rc(self):
        cells,bank,guard=self.inputs()
        for profile in circuit.PROFILES:
            c,b,changes=circuit.transform(cells,bank,guard,profile)
            self.assertIn(guard.rstrip(),c);self.assertIn('.subckt keep A Y\nR1 A Y 9\n.ends keep',c)
            count=len(circuit.PROFILES[profile]);self.assertEqual(b.count(' '+circuit.MODEL+'\n'),count)
            self.assertEqual(b.count(' '+circuit.OLD+'\n'),2-count)
            self.assertEqual(changes['actual_component_counts']['inv2'],count)
            self.assertFalse(changes['whole_bank_rc_retained']);self.assertFalse(changes['qualified_phy'])

    def test_missing_driver_wrong_cap_or_changed_mos_is_rejected(self):
        cells,bank,guard=self.inputs()
        missing='\n'.join(l for l in bank.splitlines() if not l.startswith('Xfine_driver '))+'\n'
        with self.assertRaises(ValueError):circuit.transform(cells,missing,guard,'both2')
        for before,after in [('w=2 l=2','w=1 l=1'),('w=.65','w=.66')]:
            with self.subTest(fault=before),self.assertRaises(ValueError):
                circuit.transform(cells,bank,guard.replace(before,after,1),'both2')

    def test_matched_fixture_installs_selected_root_and_includes(self):
        for spec in pilot.specifications():
            with patch.dict(os.environ,PDK_ROOT='/test/pdk'):
                text=pilot.fixture(Path('/work/OpenLVDS/build/example'),spec,[])
            self.assertIn(' '+circuit.name(spec['profile'])+'\n',text)
            self.assertIn('cells_'+spec['profile']+'.spice',text);self.assertNotIn('cells_actual_nlvt.spice',text)
            self.assertEqual(spec['coarse'],0);self.assertEqual(spec['fine'],0)

    def test_zero_success_cannot_qualify_sparse_or_phy(self):
        rows=[]
        for spec in pilot.specifications():
            result=dict(terminal_screen_passed=True,control_settling_passed=True,onehot_control_settling_passed=True,
                        repeated_delay_difference_ps=dict(rise=0,fall=0),zero_code_fast_quarter_headroom_ps=20,
                        samples=[dict(rise_delay_ps=500,fall_delay_ps=580)]*2)
            rows.append(dict(task=dict(spec=spec),result=result))
        for report in proof.comparisons(rows):
            self.assertTrue(report['zero_code_native_gate_passed']);self.assertFalse(report['all_sparse_points_present'])
            self.assertFalse(report['sparse_native_screen_passed']);self.assertFalse(report['qualified_phy'])


if __name__=='__main__':unittest.main()
