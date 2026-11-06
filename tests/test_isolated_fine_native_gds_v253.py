# SPDX-License-Identifier: GPL-3.0-only
from copy import deepcopy
from pathlib import Path
import json
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    import klayout.db
except ImportError:
    CAD=False
else:
    CAD=True

@unittest.skipUnless(CAD,'KLayout required by streamed native GDS producer')
class RoutedNativeGdsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import build_isolated_fine_native_gds_v253 as producer
        cls.p=producer
        placement=producer.ROOT/'build/diagnostics/isolated_fine_placement_v238/da8cd048ac28c378'
        cls.graph=json.loads((placement/'manifest.json').read_text())['identity']['graph']
        cls.old=(placement/'reference.spice').read_text()
        cls.corrected=(producer.ROOT/'build/diagnostics/isolated_fine_bank_junctions_v246/100682d1c98a6745/reference.spice').read_text()

    def test_corrected_native_reference_covers_every_graph_component_and_port_order(self):
        proof=self.p.reference_contract(self.corrected,self.graph)
        self.assertTrue(proof['all_180_root_component_calls_and_named_nets_verified'])
        self.assertTrue(proof['all_native_master_port_orders_verified'])

    def test_old_reference_supply_header_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'definition order differs'):
            self.p.reference_contract(self.old,self.graph)

    def test_wrong_fine_programming_connection_is_rejected(self):
        g=deepcopy(self.graph)
        next(c for c in g['cells'] if c['name']=='u_fine_unit0')['pins']['CTRL']='fine1'
        with self.assertRaisesRegex(ValueError,'component pin/net graph differs'):
            self.p.reference_contract(self.corrected,g)

    def test_incomplete_or_nonzero_violation_route_cannot_admit_native_gds(self):
        report=dict(route_bringup_passed=True,returncode=0,router_final_violations=0,connection_and_coverage_check=dict(complete=True))
        complete=dict(status='complete',passed=True,qualified_phy=False)
        self.p.require_route(complete,report)
        for state,row in [(dict(status='routing',qualified_phy=False),report),(complete,dict(report,router_final_violations=1)),
                          (complete,dict(report,returncode=1)),(complete,dict(report,connection_and_coverage_check=None))]:
            with self.assertRaisesRegex(ValueError,'complete passing zero-violation'):
                self.p.require_route(state,row)

if __name__=='__main__':unittest.main()
