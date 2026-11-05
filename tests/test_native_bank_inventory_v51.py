# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_bank_inventory_v51 as inventory
import physical_cell_adapter_v44 as parameters


class NativeBankInventoryTests(unittest.TestCase):
    def source(self):
        return '''.subckt leaf A Z VSS
XN Z A hidden VSS sky130_fd_pr__nfet_01v8 w=650000u l=150000u ad=.1 as=.2 pd=1 ps=2
XP hidden A 0 VSS sky130_fd_pr__nfet_01v8 w=12 l=.15 ad=.3 as=.4 pd=3 ps=4
.ends leaf
.subckt bank IN OUT VGND
Xfirst IN mid VGND leaf
Xsecond mid OUT VGND leaf
.ends bank
'''

    def test_preserves_native_suffixes_wide_devices_and_junctions(self):
        ports,devices=inventory.native_leaves(self.source(),'bank')
        self.assertEqual(ports,['IN','OUT','VGND']);self.assertEqual(len(devices),4)
        self.assertEqual(devices[0]['params']['w'],'650000u')
        self.assertEqual(devices[1]['params']['w'],'12')
        text=inventory.layout.schematic_text('flat',ports,devices)
        numeric=text.replace('650000u','0.65').replace('150000u','0.15')
        self.assertEqual(parameters.parameter_signature(text),parameters.parameter_signature(numeric))
        self.assertNotEqual(parameters.parameter_signature(text),parameters.parameter_signature(text.replace('ad=.1','ad=.11')))

    def test_maps_shared_ports_and_separates_private_nodes(self):
        _,d=inventory.native_leaves(self.source(),'bank')
        self.assertEqual(d[0]['nodes'][1],'IN');self.assertEqual(d[2]['nodes'][0],'OUT')
        self.assertEqual(d[0]['nodes'][0],d[2]['nodes'][1])
        self.assertNotEqual(d[0]['nodes'][2],d[2]['nodes'][2])
        self.assertEqual(d[0]['nodes'][3],d[2]['nodes'][3])
        self.assertEqual(d[1]['nodes'][2],'0')
        self.assertEqual(len({v['name'] for v in d}),4)

    def test_rejects_parameterized_invalid_or_recursive_hierarchy(self):
        with self.assertRaisesRegex(ValueError,'Parameterized'):
            inventory.native_leaves(self.source().replace('VGND leaf','VGND leaf m=2',1),'bank')
        with self.assertRaisesRegex(ValueError,'expects 3 terminals'):
            inventory.native_leaves(self.source().replace('IN mid VGND leaf','IN VGND leaf'),'bank')
        source='.subckt loop A\nXagain A loop\n.ends loop\n'
        with self.assertRaisesRegex(ValueError,'Recursive'):inventory.native_leaves(source,'loop')

    def test_new_standard_junctions_are_measured_without_waiving_known_geometry(self):
        from copy import deepcopy
        _,expected=inventory.native_leaves(self.source(),'bank');expected=expected[:2]
        expected[1]['params']={'w':'12','l':'.15'}
        actual=deepcopy(expected);actual[1]['params'].update(ad='.3',**{'as':'.4'},pd='3',ps='4')
        result=inventory.compare_parameters(expected,actual)
        self.assertEqual(result['newly_characterized_junction_devices'],1)
        bad=deepcopy(actual);bad[0]['params']['ad']='.11'
        with self.assertRaisesRegex(ValueError,'junction geometry'):inventory.compare_parameters(expected,bad)
        bad=deepcopy(actual);bad[1]['params']['w']='11'
        with self.assertRaisesRegex(ValueError,'dimensions'):inventory.compare_parameters(expected,bad)

    def test_spice_suffix_comparison_is_decimal_exact(self):
        from copy import deepcopy
        _,expected=inventory.native_leaves(self.source().replace('650000u','790000u'),'bank')
        actual=deepcopy(expected)
        for d in actual:
            if d['params']['w']=='790000u':d['params']['w']='.79'
        self.assertTrue(inventory.compare_parameters(expected,actual)['native_parameters_preserved'])
        self.assertEqual(inventory.exact_number('790000u'),inventory.exact_number('.79'))
        with self.assertRaises(ValueError):inventory.exact_number('790000garbage')


if __name__=='__main__':unittest.main()
