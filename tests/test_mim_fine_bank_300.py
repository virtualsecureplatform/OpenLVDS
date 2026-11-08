# SPDX-License-Identifier: GPL-3.0-only
import json,sys,unittest
from copy import deepcopy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import mim_fine_bank_300 as p

class MimFine300Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder=p.ROOT/'build/diagnostics/pullup_restored_bank_v360/8dba212d4f9eafd5'
        cls.text=(folder/'bank.spice').read_text()
        cls.obs=json.loads((folder/'manifest.json').read_text())['identity']['observations']
        cls.cell=p.qualified_cell()
    def test_all_six_bounded_native_revisions_and_actual_gate_maps(self):
        for driver in ('p40','p80'):
            for copies in (2,4,8):
                with self.subTest(driver=driver,copies=copies):
                    text,obs,revision=p.transform(self.text,self.obs,self.cell,copies=copies,driver=driver)
                    self.assertEqual(obs['controls'],self.obs['controls'])
                    self.assertEqual(len(obs['devices']),(1760 if driver=='p40' else 1816)+93*copies)
                    self.assertEqual(revision['native_mims'],(76 if driver=='p40' else 77)+62*copies)
                    self.assertEqual(len(obs['programming_gates']),80+93*copies)
                    after={d['name']:d for d in obs['devices']}
                    for gate in obs['programming_gates']:
                        self.assertEqual(gate['gate_node'],after[gate['device']]['terminals'][1])
                    self.assertFalse(revision['qualified_phy'])
                    self.assertEqual(p.SOURCE.definition(text,p.MODEL),self.cell)
                    # Every unrelated top-level call remains in its original order.
                    original=p.SOURCE.native.definitions(self.text)[p.single.parent.TOP][1]
                    actual=p.SOURCE.native.definitions(text)[revision['macro_top']][1]
                    self.assertEqual([w for w in actual if not w[0].startswith('Xfine_mim')],
                                     [w for w in original if not w[0].startswith(('Xfine_unit','Xfine_copy'))])
    def test_rejects_outside_bounded_search_and_changed_numerical_cell(self):
        for copies,driver in ((1,'p40'),(3,'p40'),(16,'p80'),(4,'p20')):
            with self.assertRaises(ValueError):p.transform(self.text,self.obs,self.cell,copies=copies,driver=driver)
        with self.assertRaises(ValueError):
            p.transform(self.text,self.obs,self.cell.replace('l=3 w=2','l=4 w=2',1))
    def test_rejects_missing_copy_or_damaged_nonfine_terminal(self):
        text=self.text.replace('Xfine_copy0 fine_node','Xfine_copy0 DIFFERENT',1)
        with self.assertRaises(ValueError):p.transform(text,self.obs,self.cell,driver='p80')
        obs=deepcopy(self.obs);obs['devices'][0]['terminals'][0]='DAMAGED'
        with self.assertRaises(ValueError):p.transform(self.text,obs,self.cell,driver='p80')
    def test_rejects_missing_old_programming_gate(self):
        obs=deepcopy(self.obs);obs['programming_gates'].pop()
        with self.assertRaises(ValueError):p.transform(self.text,obs,self.cell)
    def test_resolves_qualified_control_gate_rc_networks(self):
        self.assertEqual(p.gate_controls(self.cell),{'X0':'ENB','X3':'EN','X4':'ENB'})
        with self.assertRaises(ValueError):p.gate_controls(self.cell.replace('.ends','Rshort EN ENB 1\n.ends',1))
