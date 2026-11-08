# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dcc_chain_fanout_300_v1 as p
import clocking_profile_300 as policy


class DccFanoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chain=policy.ROOT/'build/diagnostics/tg2_four_section_zero_pilot_300_v1/4bf88d17231064da'
        cls.dcc=policy.ROOT/'build/diagnostics/dcc_source_300_v1/1a4f4e8eabb896e4'
        cls.library=p.namespace((cls.dcc/'cells.spice').read_text()+'\n'+(cls.dcc/'hold1.spice').read_text())
        cls.bank=(cls.chain/'bank.spice').read_text();cls.original=(cls.chain/'0/bench.cir').read_text()

    def test_native_fanout_and_complete_source_device_probes(self):
        deck,obs=p.fixture(self.original,self.bank,self.library,policy.ROOT/'build/unused-dcc-chain-source.spice')
        self.assertIn('XDC0 IN B1_OUT DCC_RESET_N DCC0_OUT VDD 0 dcc_source',deck)
        self.assertIn('XDC1 OUT B2_OUT DCC_RESET_N DCC1_OUT VDD 0 dcc_source',deck)
        self.assertEqual(deck.count('CCHAIN_LOAD B3_OUT 0 20f'),1)
        names=[d['name'] for o in obs.values() for d in o['devices']]
        self.assertGreater(len(names),100);self.assertEqual(len(names),len(set(names)))
        probes=next(l for l in deck.splitlines() if l.startswith('.print tran ')).split()[2:]
        self.assertEqual(len(probes),len(set(n.lower().replace(':','.') for n in probes)))
        for o in obs.values():
            self.assertEqual(len(o['passive_resistors']),2)
            for d in o['devices']+o['passive_resistors']:
                for n in d['terminals']:
                    if n!='0':self.assertIn('V('+n+')',probes)
        self.assertEqual(obs['0']['input_nodes'],['IN','B1_OUT'])
        with self.assertRaisesRegex(ValueError,'untouched'):p.fixture(deck,self.bank,self.library,'unused')

    def test_unknown_leaf_and_interface_refused(self):
        altered=self.library.replace('sky130_fd_pr__res_generic_po','unknown_passive')
        with self.assertRaisesRegex(ValueError,'Unsupported'):p.fixture(self.original,self.bank,altered,'unused')
        altered=self.library.replace('.subckt dcc_source P0 P180 RESET_N Q VDD VSS','.subckt dcc_source P0 P180 Q RESET_N VDD VSS')
        with self.assertRaisesRegex(ValueError,'interface'):p.fixture(self.original,self.bank,altered,'unused')

    def test_namespace_preserves_every_primitive_and_parameter(self):
        original=(self.dcc/'cells.spice').read_text()+'\n'+(self.dcc/'hold1.spice').read_text()
        before=p.native.definitions(original);after=p.native.definitions(self.library)
        names={n:n if n=='dcc_source' else 'openlvds_chain_dcc_'+n for n in before}
        self.assertEqual(set(after),set(names.values()))
        for name,(ports,body) in before.items():
            expected=[]
            for row in body:
                row=list(row);stop=next((k for k,w in enumerate(row) if '=' in w),len(row))
                row[stop-1]=names.get(row[stop-1],row[stop-1]);expected.append(row)
            self.assertEqual(after[names[name]],(ports,expected))
        mapping=dict(zip(p.PORTS,['IN','HALF','RESET','Q','VDD','0']))
        self.assertEqual(p.mapped_mos(original,mapping,'XD'),p.mapped_mos(self.library,mapping,'XD'))
