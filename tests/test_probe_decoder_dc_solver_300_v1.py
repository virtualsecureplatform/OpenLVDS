# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import probe_decoder_dc_solver_300_v1 as p


class DecoderDCPrecisionTests(unittest.TestCase):
    def test_actual_native_cells_fixed_inputs_and_only_explicit_precision_changes(self):
        source=(p.PARENT/'bank.spice').read_text();cells=p.library(source)
        self.assertEqual(set(p.native.definitions(cells)),{p.CELL,p.INV})
        for name in (p.CELL,p.INV):self.assertEqual(p.native.definitions(cells)[name],p.native.definitions(source)[name])
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp);(out/'cells.spice').write_text(cells);decks=[]
            for setting in p.SETTINGS:
                deck=p.fixture(out,setting,dict(A=1.79999999,B=0),Path('model.spice'));decks.append(deck)
                klu,names=p.klu.translate(deck);smp,other=p.smp.translate(deck)
                self.assertEqual(names,other);self.assertEqual(klu.replace('.options klu\n','',1),smp)
                self.assertIn('v(xd.a_110_47#)',names);self.assertIn('v(x)',names);self.assertIn('v(y)',names)
                self.assertIn('.tran .1p 2p 0 .1p',deck);self.assertIn('VDD VDD 0 1.8',deck)
                self.assertNotIn('UIC',deck);self.assertNotIn('.ic ',deck);self.assertNotIn('I_BENCH',deck)
            stripped=lambda text:[line for line in text.splitlines() if not line.startswith('.options timeint ')]
            self.assertEqual(stripped(decks[0]),stripped(decks[1]));self.assertEqual(stripped(decks[0]),stripped(decks[2]))
            with self.assertRaises(ValueError):p.fixture(out,'loose',dict(A=1.8,B=0),Path('model.spice'))

    def test_complete_pairs_and_strict_dc_parity(self):
        rows=[]
        for setting in p.SETTINGS:
            for backend in ('klu','smp'):
                rows.append(dict(task=dict(id=str(len(rows)),setting=setting,backend=backend),error=None,
                    result=dict(dc={'v(xd.a_110_47#)':1.3366,'v(vdd)':1.8})))
        self.assertTrue(all(r['dc_agrees_within_1nv'] for r in p.comparisons(rows).values()))
        rows[1]['result']['dc']['v(xd.a_110_47#)']+=62e-6
        self.assertFalse(p.comparisons(rows)['native']['dc_agrees_within_1nv'])
        rows[3]['error']='native failed';rows[3]['result']=None
        self.assertFalse(p.comparisons(rows)['tight_current']['complete'])
        with self.assertRaisesRegex(ValueError,'all six'):p.comparisons(rows[:-1])
