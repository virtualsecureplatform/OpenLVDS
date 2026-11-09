# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import routed_dcc_fixture_300_v1 as p


class RoutedDCCFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.info=json.loads((p.proof.PARENT/'extraction.json').read_text())
        cls.text=(p.proof.ROOT/cls.info['netlist']).read_text()

    def test_actual_routed_native_ports_nodes_and_unchanged_phase_sources(self):
        for s in p.waveform.specifications()[:12]:
            out=p.proof.ROOT/'build/unused-routed-DCC-test'
            original=p.waveform.fixture(out,s);deck,obs=p.fixture(out,s,self.info,self.text)
            _,names=p.translate(deck)
            self.assertEqual(len(obs['devices']),192);self.assertEqual(len(obs['passive_resistors']),4)
            for d in obs['devices']+obs['passive_resistors']:
                for n in d['terminals']:
                    if n!='0':self.assertIn('v('+n.replace(':','.').lower()+')',names)
            def phase_lines(text):
                return text[text.index('VP0 P0 '):text.index('\nXD ')]
            self.assertEqual(phase_lines(original),phase_lines(deck))
            self.assertEqual([l for l in original.splitlines() if l.startswith(('.tran ','CQ ','.options ','VDD '))],
                             [l for l in deck.splitlines() if l.startswith(('.tran ','CQ ','.options ','VDD '))])
            self.assertNotIn('hold1.spice',deck);self.assertNotIn('cells.spice',deck)
            self.assertFalse(obs['actual_release_circuit_qualified']);self.assertFalse(obs['qualified_phy'])

    def test_every_slew_duty_and_spacing_keeps_first_active_event_on_p180(self):
        for s in p.waveform.specifications()[:324]:
            release=p.release_ps(s);events=[]
            for phase in ('P0','P180'):
                period,first,_,_=p.waveform.parameters(s,phase)
                events += [(first+k*period,phase) for k in range(18) if first+k*period>release]
            self.assertEqual(sorted(events)[0][1],'P180')
            self.assertEqual(len(events),29)
        s=p.waveform.specifications()[0]
        with self.assertRaises(ValueError):p.fixture(Path('unused'),s,dict(self.info,ports=['bad']),self.text)

        with self.assertRaises(ValueError):p.fixture(Path('unused'),s,self.info,self.text.replace(p.proof.NAME,'wrong_macro'))
