# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import diagnose_distributed_recovery_300_v4 as p


class ActualSwitchTopologyTests(unittest.TestCase):
    def context(self,rel):
        parent=p.ROOT/'build/diagnostics'/rel
        i=json.loads((parent/'manifest.json').read_text())['identity']
        variant=next(iter(i['observations']))
        return (i['observations'][variant],(parent/variant/'bank.spice').read_text(),i['revisions'][variant]['macro_top'])

    def test_old_and_new_native_leaf_names_are_resolved_from_topology(self):
        contexts=[('p40n32_pre_distributed_pilot_300_v1/3efd00e62550ef86',{'X0','X3'}),
                  ('tg2_p40n32_pilot_300_v1/aae4b31d0e77445c',{'X0','X1'})]
        for rel,leaves in contexts:
            observed=p.switch_nodes(*self.context(rel))
            self.assertEqual(len(observed),12)
            self.assertEqual({v['device'].split(':')[-1] for v in observed.values()},leaves)
            self.assertEqual({v['stage'] for v in observed.values()},{'pre','fine'})
            self.assertEqual({v['fine_index'] for v in observed.values()},{0,15,30})
            self.assertEqual({v['terminal'] for v in observed.values()},{'D','S'})
            self.assertTrue(all('__CAP.t' in n for n in observed))

    def test_missing_native_switch_cannot_be_replaced_by_a_capacitor_leaf(self):
        obs,library,top=self.context('tg2_p40n32_pilot_300_v1/aae4b31d0e77445c')
        obs=deepcopy(obs)
        obs['devices']=[d for d in obs['devices'] if d['name']!='XD:Xfine_mim0_c0:X1']
        with self.assertRaisesRegex(ValueError,'Missing actual native transmission switch'):
            p.switch_nodes(obs,library,top)

    def test_actual_capacitor_side_observation_must_match_library(self):
        obs,library,top=self.context('tg2_p40n32_pilot_300_v1/aae4b31d0e77445c')
        obs=deepcopy(obs)
        d=next(d for d in obs['devices'] if d['name']=='XD:Xfine_mim0_c0:X1')
        d['terminals'][0]='XD:pre_out'
        with self.assertRaisesRegex(ValueError,'differs from library'):
            p.switch_nodes(obs,library,top)
