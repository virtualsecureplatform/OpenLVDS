# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from layout_receiver_tail_candidate import source_variant
from layout import circuits
ROOT=Path(__file__).resolve().parents[1]


class ReceiverTailCandidate(unittest.TestCase):
    def test_only_complementary_input_tail_widths_change(self):
        source=(ROOT/'analog/openlvds.spice').read_text();before=circuits(source);after=circuits(source_variant(source,2))
        self.assertEqual(set(before),set(after))
        for name in before:
            if name!='openlvds_receiver_core':self.assertEqual(before[name],after[name])
        ports,rows=before['openlvds_receiver_core'];new_ports,new_rows=after['openlvds_receiver_core']
        self.assertEqual(ports,new_ports);self.assertEqual(len(rows),len(new_rows))
        for a,b in zip(rows,new_rows):
            if a[0] in ['XNT','XPT']:
                self.assertEqual(a[:3],b[:3]);self.assertEqual(b[3],dict(w='24',l='1'))
            else:self.assertEqual(a,b)

    def test_baseline_is_byte_identical(self):
        source=(ROOT/'analog/openlvds.spice').read_text();self.assertEqual(source_variant(source,1),source)

    def test_unknown_current_source_dimensions_rejected(self):
        source=(ROOT/'analog/openlvds.spice').read_text().replace('XNT NT NB VSS VSS sky130_fd_pr__nfet_g5v0d10v5 w=12 l=1',
            'XNT NT NB VSS VSS sky130_fd_pr__nfet_g5v0d10v5 w=6 l=1')
        with self.assertRaisesRegex(ValueError,'Unknown input-tail'):source_variant(source,2)
