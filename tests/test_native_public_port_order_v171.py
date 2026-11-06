# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import native_public_port_order_v171 as p


class NativePortOrderTests(unittest.TestCase):
    def fixture(self):
        return ('* keep extraction provenance\n.subckt bank IN OUT E0\n+ S0 VPWR VGND\n'
                'R0 OUT y0 .125 $ keep\nC0 y0 VGND 2f\n'
                'Xn y0 S0 VGND VGND sky130_fd_pr__nfet_01v8 w=1 l=.15 ad=.1 as=.1 pd=1 ps=1\n'
                'Xc y0 E0 sky130_fd_pr__cap_mim_m3_1 w=2 l=2\n.ends bank\n')

    def test_only_header_changes_and_named_device_and_passive_bytes_survive(self):
        source=self.fixture();ports=['IN','OUT','S0','E0','VPWR','VGND']
        result,proof=p.canonicalize(source,'bank',ports)
        self.assertTrue(proof['header_changed']);self.assertTrue(proof['named_public_port_bijection_verified'])
        self.assertTrue(result.startswith('* keep extraction provenance\n.subckt bank '+' '.join(ports)+'\n'))
        self.assertTrue(result.endswith(source.split('+ S0 VPWR VGND\n',1)[1]))
        self.assertEqual(p.cards.passive_lines(result),p.cards.passive_lines(source))
        again,q=p.canonicalize(result,'bank',ports);self.assertEqual(again,result);self.assertFalse(q['header_changed'])
        self.assertFalse(proof['qualified_phy'])

    def test_missing_extra_duplicate_or_hierarchical_public_interface_is_rejected(self):
        source=self.fixture();ports=['IN','OUT','S0','E0','VPWR','VGND']
        for text,order in [(source,ports[:-1]),(source,ports+['extra']),(source,['IN',*ports[1:-1],'IN']),
                           (source.replace('E0\n','S0\n'),ports),(source+'.subckt child A B\n.ends child\n',ports)]:
            with self.assertRaises(ValueError):p.canonicalize(text,'bank',order)


if __name__=='__main__':unittest.main()
