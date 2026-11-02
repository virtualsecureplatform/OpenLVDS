# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from prepare_tx_isolation import exportable


class TxExportFix(unittest.TestCase):
    def test_only_constant_ground_probe_changes(self):
        deck='Title\nVDD VDD 0 1.8\n.tran 1p 12n 0 1p\n.print tran V(0) V(VDD) V(XTX:VGND.t436)\n.end\n'
        self.assertEqual(exportable(deck,True),deck.replace('V(0) ',''))
        clean=deck.replace('V(0) ','')
        self.assertEqual(exportable(clean,False),clean)

    def test_ambiguous_or_unexpected_probes_fail(self):
        for deck,tx in [('.print tran V(0) V(0)\n',True),('.print tran V(Q)\n',True),('.print tran V(0)\n',False),('',False)]:
            with self.assertRaises(ValueError):exportable(deck,tx)


if __name__=='__main__':unittest.main()
