# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from probe_tx_candidate_link import rebind


class TXDiagnosticFixture(unittest.TestCase):
    def test_only_library_path_changes(self):
        deck='Title\n.include "/old/library.spice"\nVD VD 0 1.8\nVCLK CLK 0 PWL(0 0 1n 1.8)\n.tran 5p 200n 0 20p\n.end\n'
        result=rebind(deck,Path('/old'),Path('/new'))
        self.assertEqual(result.replace('/new/library.spice','/old/library.spice'),deck)

    def test_missing_or_ambiguous_binding_rejected(self):
        for deck in ['', '.include "/old/library.spice"\n.include "/old/library.spice"']:
            with self.assertRaisesRegex(ValueError,'one captured library'):rebind(deck,Path('/old'),Path('/new'))
