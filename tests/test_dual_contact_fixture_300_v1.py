# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import dual_contact_fixture_300_v1 as p
import two_bank_native_measure_300_v1 as reader


class FastEntryFixtureTests(unittest.TestCase):
    def test_actual_fast_and_slow_decks_retain_stimulus_and_complete_reader_vectors(self):
        parent=p.architecture.source.ROOT/'build/diagnostics/tg2_entry_domain_pilot_300_v1/b98f2003774d19d6'
        library=(parent/'bank.spice').read_text()
        for number in ('0','2'):
            folder=parent/number;original=(folder/'bench.cir').read_text()
            obs=json.loads((folder/'observations.json').read_text());spec=json.loads((folder/'summary.json').read_text())['task']['spec']
            for kind in p.architecture.KINDS:
                with self.subTest(number=number,kind=kind):
                    deck,new,observations,revision=p.fixture(original,library,obs,kind,Path('new-bank.spice'))
                    for prefix in ('BIN ','VDD ','I_BENCH_CURRENT_CENTER ','VNEXT_','CNEXT_LOAD ','.tran '):
                        self.assertEqual([l for l in original.splitlines() if l.startswith(prefix)],
                                         [l for l in deck.splitlines() if l.startswith(prefix)])
                    _,names=p.translate(deck);required=set()
                    def collect(path,wanted,stop):
                        required.update(wanted);raise RuntimeError('reader requirements captured')
                    with patch.object(reader,'validate',side_effect=collect):
                        with self.assertRaisesRegex(RuntimeError,'requirements captured'):
                            reader.measure(Path('unused'),observations,spec,next_coarse=0,next_fine=0)
                    self.assertTrue(required<=set(names),sorted(required-set(names)))
                    first={d['name'] for d in observations['first']['devices']};second={d['name'] for d in observations['next']['devices']}
                    self.assertFalse(first&second);self.assertEqual(len(first),len(second))
                    self.assertEqual(len(first),revision['native_mos'])
                    self.assertNotEqual(new,library)
                    gates=observations['first']['programming_gates']
                    devices={d['name']:d for d in observations['first']['devices']}
                    for gate in gates:self.assertEqual(gate['gate_node'],devices[gate['device']]['terminals'][1])
                    if revision['coarse_shunt_units']:
                        self.assertIn('v(xd.xtail_load.mid)',names);self.assertIn('v(xl.xtail_load.mid)',names)
