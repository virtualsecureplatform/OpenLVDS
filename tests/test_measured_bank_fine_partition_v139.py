# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import measured_bank_fine_partition_v139 as p


class MeasuredFinePartitionTests(unittest.TestCase):
    def bank(self):
        rows=['.subckt bank NODE VPWR VGND '+' '.join('E'+str(k) for k in range(31))]
        for k in range(31):
            c=f'q{k}';en=f'E{k}';eb=f'b{k}'
            rows += [f'XN{k} NODE {en} {c} VGND {p.N} w=.42 l=.15',
                     f'XP{k} {c} {eb} NODE VPWR {p.P} w=.84 l=.15',
                     f'XR{k} {c} {eb} VGND VGND {p.N} w=.42 l=.15',
                     f'XCN{k} VGND {c} VGND VGND {p.N} w=1.26 l=.15 ad=0 as=0 pd=0 ps=0',
                     f'XCP{k} VPWR {c} VPWR VPWR {p.P} w=1.26 l=.15 ad=0 as=0 pd=0 ps=0',
                     f'XC{k} {eb} VGND {p.MIM} w=2 l=2']
        return '\n'.join(rows+['.ends bank',''])

    def measurements(self):
        rows=[]
        for model in [p.N,p.P]:
            rows.append(dict(primitive=dict(model=model,width_um='1.26',length_um='.15',cell=model+'_measured'),
                 actual=dict(model=model,nodes=['D','G','S','B'],params=dict(w='1.26',l='.15',ad='.3654',**{'as':'.3654'},pd='3.1',ps='3.1')),
                 geometry=dict(passed=True,drc_count='0')))
        return rows

    def test_all_sections_identified_by_topology_with_no_name_or_geometry_admission(self):
        text=self.bank();r=p.identify(text,'bank')
        self.assertEqual((r['fine_sections'],r['capacitor_mos'],r['programming_mos'],r['guard_mims']),(31,62,93,31))
        self.assertTrue(r['geometry_proof_required']);self.assertTrue(r['whole_bank_lvs_required'])
        self.assertFalse(r['parameters_changed']);self.assertFalse(r['qualified_phy'])
        renamed=text.replace('q','private_').replace('XCN','Xfoo').replace('XCP','Xbar')
        self.assertEqual(p.identify(renamed,'bank')['fine_sections'],31)

    def test_missing_cap_merged_private_node_and_wrong_cap_tie_are_refused(self):
        text=self.bank()
        for changed in [text.replace('w=1.26','w=1.25',1),text.replace('q1 ','q0 '),text.replace('XCN0 VGND q0 VGND VGND','XCN0 NODE q0 VGND VGND')]:
            with self.subTest(changed=changed[:20]),self.assertRaises(ValueError):p.identify(changed,'bank')

    def test_control_guard_or_extra_device_cannot_hide_in_a_fine_section(self):
        text=self.bank()
        changes=[text.replace('XR0 q0 b0','XR0 q0 E0'),text.replace('XC0 b0 VGND','XC0 b0 NODE'),
                 text.replace('XP0 q0 b0 NODE VPWR','XP0 q0 b0 NODE VGND'),
                 text.replace('.ends bank',f'Xextra q0 E0 NODE VGND {p.N} w=.42 l=.15\n.ends bank')]
        for changed in changes:
            with self.subTest(changed=changed[:20]),self.assertRaises(ValueError):p.identify(changed,'bank')

    def test_zero_and_nonzero_allocation_mismatches_are_reported_without_correction(self):
        text=self.bank().replace('ad=0 as=0','ad=0 as=99',1);original=text
        r=p.diagnose(text,'bank',self.measurements())
        self.assertEqual(r['summary'],dict(devices=62,devices_with_mismatch=62,zero_field_mismatches=247,nonzero_field_mismatches=1))
        self.assertFalse(r['per_device_capacitor_junctions_match_geometry']);self.assertFalse(r['parameters_changed'])
        self.assertFalse(r['joint_rc_qualified']);self.assertFalse(r['qualified_phy']);self.assertEqual(text,original)
        missing=self.measurements()[:1]
        with self.assertRaisesRegex(ValueError,'Missing measured'):p.diagnose(text,'bank',missing)


if __name__=='__main__':unittest.main()
