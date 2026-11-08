# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import tg2_p40n32_bank_300 as architecture
import probe_tg2_p40n32_300 as pilot


class DoubleTGBankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=pilot.PARENT
        cls.original=(p/'bank.spice').read_text()
        cls.observations=json.loads((p/'manifest.json').read_text())['identity']['observations']
        cls.baseline=architecture.parent.transform(cls.original,cls.observations)

    def test_exact_nonfine_preservation_and_actual_gate_maps(self):
        text,obs,revision=architecture.transform(self.original,self.observations)
        source=architecture.SOURCE
        old,previous,_=self.baseline
        defs=source.native.definitions(old)
        for name in defs:
            if name!=architecture.parent.TOP:
                self.assertEqual(source.definition(text,name),source.definition(old,name))
        self.assertEqual((revision['native_mos'],revision['native_mims']),(2056,202))
        self.assertEqual(obs['controls'],previous['controls'])
        devices={d['name']:d for d in obs['devices']}
        self.assertEqual(len(obs['programming_gates']),266)
        for gate in obs['programming_gates']:
            self.assertEqual(devices[gate['device']]['terminals'][1],gate['gate_node'])
        body=source.native.definitions(text)[architecture.TOP][1]
        calls=[w for w in body if w[-1]==architecture.MODEL]
        self.assertEqual(len(calls),62)
        self.assertEqual(sum(w[1]=='pre_out' for w in calls),31)
        self.assertEqual(sum(w[1]=='fine_node' for w in calls),31)
        self.assertFalse(revision['qualified_phy'])

    def test_reject_changed_split_wiring(self):
        text,obs,revision=self.baseline
        text=text.replace('Xfine_mim0_c1 pre_out ','Xfine_mim0_c1 fine_node ',1)
        with patch.object(architecture.parent,'transform',return_value=(text,obs,revision)):
            with self.assertRaisesRegex(ValueError,'exact P40/N32'):
                architecture.transform(self.original,self.observations)

    def test_fresh_native_numerical_control_required(self):
        tasks=pilot.specifications()
        self.assertEqual(len(tasks),5)
        self.assertEqual([t['centered'] for t in tasks],[True,True,True,True,False])
        self.assertEqual(tasks[1]['spec'],tasks[4]['spec'])
        self.assertEqual({t['variant'] for t in tasks},{pilot.VARIANT})
