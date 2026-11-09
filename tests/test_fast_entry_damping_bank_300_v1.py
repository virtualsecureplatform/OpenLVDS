# SPDX-License-Identifier: GPL-3.0-only
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import fast_entry_damping_bank_300_v1 as p


class FastEntryInterventionTests(unittest.TestCase):
    def setUp(self):
        parent=p.source.ROOT/'build/diagnostics/tg2_next_bank_early_zero_pilot_300_v2/23dee609d6ca5e51'
        self.library=(parent/'bank.spice').read_text();self.top=p.source.TOP
        self.obs=json.loads((parent/'0/observations.json').read_text())['first']

    def test_factorial_interventions_preserve_all_old_devices_and_programmable_controls(self):
        for kind in p.KINDS:
            with self.subTest(kind=kind):
                library,top,obs,revision=p.transform(self.library,self.top,self.obs,kind)
                self.assertTrue(library.startswith(self.library+'\n'))
                self.assertEqual(obs['controls'],self.obs['controls'])
                self.assertEqual(obs['programming_gates'],self.obs['programming_gates'])
                old={d['name']:d for d in self.obs['devices']};new={d['name']:d for d in obs['devices']}
                self.assertTrue(old.keys()<new.keys())
                for n,d in old.items():self.assertEqual(new[n],d)
                defs=p.native.definitions(library);body=defs[top][1]
                boosters=[w for w in body if w[0].endswith('_boost')]
                self.assertEqual(len(boosters),revision['decode_inverse_boosters'])
                originals={w[0]:w for w in defs[self.top][1]}
                for w in boosters:self.assertEqual(w[1:],originals[w[0].removesuffix('_boost')][1:])
                if revision['coarse_shunt_units']:
                    coarse=defs['openlvds_coarse_mid_shunted_300_v1'][1]
                    self.assertEqual(coarse[-1],['Xdamp','mid','VPWR','VGND','VPWR','VGND',p.source.MODEL])
                    calls=[w for w in body if w[-1]=='openlvds_coarse_mid_shunted_300_v1']
                    self.assertEqual(len(calls),16);self.assertIn('Xtail_load',{w[0] for w in calls})
                    extra=[d for n,d in new.items() if n not in old and ':Xdamp:' in n]
                    self.assertEqual(len(extra),16*3)
                    self.assertEqual(p.source.SOURCE.definition(library,p.source.MODEL),p.source.qualified_cell())
                self.assertFalse(revision['qualified_phy'])

    def test_wrong_inventory_or_unknown_variant_refused(self):
        with self.assertRaisesRegex(ValueError,'Unknown'):p.transform(self.library,self.top,self.obs,'unknown')
        changed=self.library.replace('Xtail_load tap15 unused_tail','Xmissing_tail tap15 unused_tail',1)
        with self.assertRaisesRegex(ValueError,'tail termination'):p.transform(changed,self.top,self.obs,'combined')
