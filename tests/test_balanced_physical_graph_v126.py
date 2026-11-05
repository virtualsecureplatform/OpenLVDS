# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import balanced_physical_graph_v126 as d


class CanonicalBalancedGraphTests(unittest.TestCase):
    def fixture(self):
        cells=[dict(native_name='Xdelay1',model=d.coarse('b2'),pins=dict(A='IN',X='tap1',VPWR='VPWR',VGND='VGND')),
               dict(native_name='Xgroup_compound0',model=d.PAIR,pins=dict(A='tree0_0',Y='regenerated0',VPWR='VPWR',VGND='VGND')),
               dict(native_name='Xfine_unit0',model=d.FINE,pins=dict(A='selected',CTRL='fine0',CTRL_B='fine_b0',VPWR='VPWR',VGND='VGND'))]
        aliases={d.coarse('b2'):dict(IN='A',OUT='X',VPWR='VPWR',VGND='VGND'),d.PAIR:dict(IN='A',OUT='Y',VPWR='VPWR',VGND='VGND'),d.FINE:dict(NODE='A',EN='CTRL',ENB='CTRL_B',VDD='VPWR',VSS='VGND')}
        g=dict(ports=['IN','OUT','VPWR','VGND'],cells=cells,physical_pin_aliases=aliases)
        text='.subckt openlvds_parallel_coarse_b2_v120 IN OUT VPWR VGND\n.ends\n.subckt '+d.PAIR_SOURCE+' IN OUT VPWR VGND\n.ends\n.subckt bank_unit NODE EN ENB VDD VSS\n.ends\n.subckt bank IN OUT VPWR VGND\nXdelay1 IN tap1 VPWR VGND openlvds_parallel_coarse_b2_v120\nXgroup_compound0 tree0_0 regenerated0 VPWR VGND '+d.PAIR_SOURCE+'\nXfine_unit0 selected fine0 fine_b0 VPWR VGND bank_unit\n.ends bank\n'
        return g,text

    def test_both_gang_and_fine_aliases_preserve_named_data_control_and_body_connections(self):
        g,text=self.fixture();r=d.compare_component(g,text,'bank','b2')
        self.assertEqual(r['components'],3);self.assertTrue(r['exact_component_calls_and_named_pins_verified'])
        self.assertFalse(r['qualified_phy'])

    def test_wrong_coarse_profile_output_and_body_are_rejected(self):
        g,text=self.fixture()
        for broken in [text.replace('Xdelay1 IN tap1','Xdelay1 IN tap2'),
                       text.replace('Xgroup_compound0 tree0_0 regenerated0 VPWR VGND','Xgroup_compound0 tree0_0 regenerated0 VGND VPWR'),
                       text.replace('openlvds_parallel_coarse_b2_v120','openlvds_parallel_coarse_b3_v120')]:
            with self.assertRaises(ValueError):d.compare_component(g,broken,'bank','b2')

    def test_native_reference_rejects_conflicts_recursion_and_unstripped_wire_elements(self):
        g=dict(top='top',ports=['IN','OUT'],orders={'a':['A','X']},cells=[dict(native_name='Xu',model='a',pins=dict(A='IN',X='OUT'))])
        a='.subckt a A X\nXn X A 0 0 sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends a\n'
        self.assertIn('Xu IN OUT a\n',d.native_source(g,[a]))
        with self.assertRaisesRegex(ValueError,'Conflicting'):d.native_source(g,[a,a.replace('w=.65','w=.84')])
        with self.assertRaisesRegex(ValueError,'Recursive'):d.native_source(g,['.subckt a A X\nXb A X b\n.ends\n.subckt b A X\nXa A X a\n.ends\n'])
        with self.assertRaisesRegex(ValueError,'routing'):d.native_source(g,['.subckt a A X\nRwire A X 1\n.ends\n'])


if __name__=='__main__':unittest.main()
