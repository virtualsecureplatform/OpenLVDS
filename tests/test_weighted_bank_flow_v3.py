# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import weighted_bank_flow_v3 as flow
import test_weighted_bank_flow_v2 as fixtures


class WeightedFlowNamespaceTests(unittest.TestCase):
    def test_reversible_net_aliases_preserve_instance_names_and_every_connection(self):
        spec=fixtures.WeightedFlowTests().spec();before=deepcopy(spec);aliases=flow.net_aliases(spec)
        self.assertEqual(len(aliases),78)
        self.assertFalse(set(aliases.values())&{c['name'] for c in spec['cells']})
        text=flow.verilog(spec)
        self.assertIn('hard g0 (.A(IN),.Y('+aliases['g0']+')',text)
        self.assertEqual(text.count('dont_touch="true"'),94);self.assertEqual(spec,before)
        rows=[[c['name'],c['model'],p,aliases.get(n,n)] for c in spec['cells'] for p,n in c['pins'].items()]
        self.assertTrue(flow.connections_pass(rows,spec['ports'],spec))
        rows[-1][-1]='VPWR'
        self.assertFalse(flow.connections_pass(rows,spec['ports'],spec))

    def test_aliases_cannot_collide_with_an_existing_wire_or_public_port(self):
        spec=fixtures.WeightedFlowTests().spec()
        spec['cells'][16]['pins']['A']='lvds_g0_net'
        aliases=flow.net_aliases(spec)
        self.assertEqual(aliases['g0'],'lvds_g0_net_1')
        self.assertFalse(set(aliases)&set(spec['ports']))
        self.assertEqual(len(set(aliases.values())),len(aliases))
