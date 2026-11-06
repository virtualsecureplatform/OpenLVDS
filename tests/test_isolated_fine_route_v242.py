# SPDX-License-Identifier: GPL-3.0-only
from pathlib import Path
import json
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
try:
    import klayout.db
except ImportError:
    CAD=False
else:
    CAD=True

@unittest.skipUnless(CAD,'KLayout required by native route producer')
class IsolatedRouteTests(unittest.TestCase):
    def test_incomplete_native_pilot_cannot_admit_a_route(self):
        import route_isolated_fine_bank_v242 as route
        with tempfile.TemporaryDirectory(dir=route.ROOT/'build') as tmp:
            p=Path(tmp);(p/'state.json').write_text(json.dumps(dict(status='running',qualified_phy=False)))
            with self.assertRaisesRegex(ValueError,'Require complete error-free native isolated-driver pilot'):
                route.native_gate(p)
            self.assertEqual({f.name for f in p.iterdir()},{'state.json'})

    def test_router_uses_existing_input_metal_and_retains_fixed_bus_terms(self):
        import route_isolated_fine_bank_v242 as route
        placement=route.ROOT/'build/diagnostics/isolated_fine_placement_v238/da8cd048ac28c378'
        if not (placement/'summary.json').exists():self.skipTest('Complete isolated placement required')
        pi=json.loads((placement/'manifest.json').read_text())['identity']
        c=dict(route.interface.contract(pi),input_proxy=route.input_proxy(placement,pi),fixed_bus_terminals_retained_for_routing=True)
        text=route.tcl(placement,placement/'unused_test_output',c)
        self.assertIn('detailed_route -output_drc',text)
        self.assertIn('__fixed_bus_fine_node',text)
        self.assertNotIn('__fixed_bus_selected',text)
        self.assertEqual(text.count('# Native fixed-bus terminal remains connected'),94)
        self.assertEqual(text.count('$term disconnect'),1) # only nonrouting bulk-pin loop remains
        self.assertTrue(c['input_proxy']['existing_native_metal_verified'])
        self.assertIn('set input_original_coords',text)
        self.assertIn('odb::dbBox_create $input_pin $input_layer {*}$input_original_coords',text)

if __name__=='__main__':unittest.main()
