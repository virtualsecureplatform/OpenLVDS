# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import inspect_nand_stack_access_v2 as inspection
import label_nand_mid_access_v2 as access


class NativeMidAccessTests(unittest.TestCase):
    def test_annotation_preserves_masks_and_existing_ports_and_filters_contact_size(self):
        text='magic\n<< locali >>\nrect 0 0 80 40\nrect 100 0 120 40\n<< labels >>\nrlabel metal1 0 0 0 0 0 A\nport 2 nsew\n<< end >>\n'
        result,points=access.annotate(text,'a_27_47#')
        self.assertEqual(text.split('<< labels >>')[0],result.split('<< labels >>')[0])
        self.assertIn('rlabel ndiff 29 49 29 49 0 MID\nport 3 nsew',result)
        self.assertIn('rlabel metal1 0 0 0 0 0 A\nport 2 nsew',result)
        self.assertEqual(set(points),{'LI_0'})
        self.assertEqual(points['LI_0']['coordinate_um'],[.2,.1])

    def test_only_extracted_electrical_equivalences_select_li_access(self):
        ext='equiv "MID" "alias"\nequiv "LI_0" "alias"\nequiv "VGND" "LI_1"\n'
        self.assertEqual(access.connected_labels(ext,'MID'),{'MID','alias','LI_0'})
        self.assertNotIn('LI_1',access.connected_labels(ext,'MID'))

    def test_extended_source_changes_only_the_private_node_and_port_list(self):
        text='.subckt gate A B Y VPWR VGND\nX0 Y A a_27_47# VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15\n.ends gate\n'
        self.assertEqual(inspection.private_nodes(text),['a_27_47#'])
        result=access.source_with_mid(text,'a_27_47#')
        self.assertIn('.subckt gate A B Y VPWR VGND MID\n',result)
        self.assertIn('X0 Y A MID VGND sky130_fd_pr__nfet_01v8 w=.65 l=.15',result)
        with self.assertRaisesRegex(ValueError,'Unknown'):access.source_with_mid(text,'a_1_2#')


if __name__=='__main__':unittest.main()
