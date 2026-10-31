# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout_receiver_gain_candidate import source_variant,MID
from layout_receiver_tail_candidate import source_variant as input_source
from layout import circuits
from dll_campaign import text_block
ROOT=Path(__file__).resolve().parents[1]


class ReceiverGainCandidate(unittest.TestCase):
    def test_current_ratios_and_output_polarity_are_preserved(self):
        original=(ROOT/'analog/openlvds.spice').read_text();before=input_source(original,2);after=source_variant(original)
        b=circuits(before);a=circuits(after)
        self.assertEqual(set(a)-set(b),{MID});self.assertEqual(a['openlvds_receiver_core'][0],b['openlvds_receiver_core'][0])
        for name in b:
            if name!='openlvds_receiver_core':self.assertEqual(text_block(before,name),text_block(after,name))
        old={r[0]:r for r in b['openlvds_receiver_core'][1]};new={r[0]:r for r in a['openlvds_receiver_core'][1]}
        for label,row in old.items():
            if label in ['XCT','XC0','XC1','XCD','XCM']:
                self.assertEqual(row[:3],new[label][:3]);self.assertEqual(float(new[label][3]['w']),float(row[3]['w'])*2)
                self.assertEqual(row[3]['l'],new[label][3]['l'])
            elif label!='XI':self.assertEqual(row,new[label])
        self.assertNotIn('XI',new)
        self.assertEqual(new['XIB0'][1:3],(['CO','RESTORE0','VDDD','VSS'],'lvds_inv18'))
        self.assertEqual(new['XIB1'][1:3],(['RESTORE0','RESTORE1','VDDD','VSS'],MID))
        self.assertEqual(new['XIB2'][1:3],(['RESTORE1','Q','VDDD','VSS'],'lvds_inv18_drive'))

    def test_unexpected_decision_current_or_output_path_rejected(self):
        source=(ROOT/'analog/openlvds.spice').read_text()
        for altered in [source.replace('XCT CT NBC VSS VSS sky130_fd_pr__nfet_01v8 w=64','XCT CT NBC VSS VSS sky130_fd_pr__nfet_01v8 w=32'),
                        source.replace('XI CO Q VDDD VSS lvds_inv18_drive','XI CO OTHER VDDD VSS lvds_inv18_drive')]:
            with self.assertRaises(ValueError):source_variant(altered)
